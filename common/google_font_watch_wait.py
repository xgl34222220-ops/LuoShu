#!/usr/bin/env python3
"""Bounded, read-only event wait for the no-Hook Google font guard.

No FontTools import, font reads, mounts, process signals or app-data writes.
Inotify is notification, NOT permission interception; periodic reconciliation
and the bridge's old-FD handling remain necessary. Exit 0=change, 2=deadline,
3=unavailable (caller uses its cancellable sleep). Paths never go to stdout.
"""
from __future__ import annotations

import ctypes
import glob
import json
import os
from pathlib import Path
import select
import struct
import sys
import time

MASK = 0x8 | 0x40 | 0x80 | 0x100 | 0x200 | 0x400 | 0x800 | 0x4
OVERFLOW = 0x4000
IGNORED = 0x8000
HEADER = struct.Struct('iIII')
MAX_WATCHES = 512
MAX_PROCESSES = 16384
GOOGLE_PACKAGES = ('com.google.android.', 'com.android.vending',
                   'com.android.chrome', 'com.chrome.beta', 'com.chrome.dev', 'com.chrome.canary')


class ProcessView:
    """One Python proc listing per tick; reread cmdline only for new PIDs.

    Start times distinguish PID reuse. Each recognized process is retained,
    even when several share a mount namespace. No fd/maps scans here.
    """
    def __init__(self, root: Path):
        self.root = root
        self.known: dict[str, tuple[str, bool]] = {}

    def snapshot(self) -> tuple:
        live = {}
        views = []
        try:
            entries = os.scandir(self.root)
        except OSError:
            return ()
        with entries:
            for entry in entries:
                if not entry.name.isdigit():
                    continue
                if len(live) >= MAX_PROCESSES:
                    break
                path = Path(entry.path)
                try:
                    # comm may contain spaces and parentheses; fields after
                    # the last ') ' begin at state (3), starttime is field 22.
                    tail = (path / 'stat').read_text().rsplit(') ', 1)[1].split()
                    start = tail[19]
                    prior = self.known.get(entry.name)
                    if prior is not None and prior[0] == start:
                        selected = prior[1]
                    else:
                        with (path / 'cmdline').open('rb') as stream:
                            name = stream.read(256).split(b'\0', 1)[0].decode('ascii', 'ignore')
                        if not name:
                            continue
                        selected = name.startswith(GOOGLE_PACKAGES) or name.startswith('zygote')
                    live[entry.name] = (start, selected)
                    if selected:
                        views.append((entry.name, start, os.readlink(path / 'ns/mnt')))
                except (OSError, IndexError, ValueError):
                    # A transient /proc read failure must be retried next tick.
                    continue
        self.known = live
        return tuple(sorted(views))


class EventWait:
    def __init__(self):
        libc = ctypes.CDLL(None, use_errno=True)
        self.add = libc.inotify_add_watch
        self.add.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
        self.add.restype = ctypes.c_int
        init = libc.inotify_init1
        init.argtypes = [ctypes.c_int]
        init.restype = ctypes.c_int
        self.fd = init(os.O_NONBLOCK | os.O_CLOEXEC)
        if self.fd < 0:
            raise OSError(ctypes.get_errno(), 'inotify unavailable')
        self.filters: dict[int, set[str] | None] = {}

    def close(self):
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def directory(self, path: Path, names: set[str] | None = None):
        if len(self.filters) >= MAX_WATCHES:
            return
        # Parents may legitimately be ROM aliases such as /data/data.
        wd = self.add(self.fd, os.fsencode(path), MASK | 0x01000000)
        if wd < 0:
            return
        if wd not in self.filters:
            self.filters[wd] = names
        elif self.filters[wd] is None or names is None:
            self.filters[wd] = None
        else:
            self.filters[wd].update(names)

    def tree(self, path: Path, depth: int = 6):
        # Watch the nearest existing parent as well. Creation/replacement of
        # fonts or the package's files directory wakes us to rebuild watches.
        parent = path
        while not parent.is_dir() and parent.parent != parent:
            child = parent.name
            parent = parent.parent
            if parent.is_dir():
                self.directory(parent, {child})
                break
        if not path.is_dir():
            return
        self.directory(path.parent, {path.name})
        self.directory(path)
        for directory, subdirs, _files in os.walk(path, followlinks=False):
            relative = Path(directory).relative_to(path)
            if len(relative.parts) >= depth or len(self.filters) >= MAX_WATCHES:
                subdirs[:] = []
                continue
            subdirs[:] = [name for name in subdirs if not (Path(directory) / name).is_symlink()]
            for name in subdirs:
                self.directory(Path(directory) / name)

    def changed(self) -> bool:
        try:
            raw = os.read(self.fd, 65536)
        except BlockingIOError:
            return False
        offset = 0
        while offset + HEADER.size <= len(raw):
            wd, mask, _cookie, length = HEADER.unpack_from(raw, offset)
            offset += HEADER.size
            name = os.fsdecode(raw[offset:offset + length].split(b'\0', 1)[0])
            offset += length
            if mask & OVERFLOW:
                return True  # Lost events require full reconciliation.
            if wd not in self.filters:
                continue
            allowed = self.filters[wd]
            if mask & (IGNORED | 0x400 | 0x800) or allowed is None or name in allowed:
                return True
        return False


def configure(watcher: EventWait, module: Path):
    watcher.directory(module, {'disable', 'remove', '.luoshu-payload'})
    watcher.directory(module / 'config', {'active_font.conf', 'device_font_inventory.json'})
    override = os.environ.get('LUOSHU_GOOGLE_FONT_WATCH_ROOTS')
    if override is not None:
        roots = [Path(p) for p in override.splitlines() if p]
    else:
        roots = [Path('/data/fonts/files')]
        # Inventory routes are file watches, never a recursive walk of arbitrary
        # data directories. Periodic reconciliation remains the fallback when a
        # directory is not yet present or inotify is unavailable.
        try:
            from dynamic_font_route_patch import route_rows
            inventory = json.loads((module / 'config/device_font_inventory.json').read_text())
            for _key, alias, recorded_target in route_rows(inventory):
                watcher.directory(alias.parent, {alias.name})
                for target in (recorded_target, alias.resolve(strict=False)):
                    watcher.directory(target.parent, {target.name})
        except (OSError, ValueError, TypeError):
            pass
        # Do not watch unrelated Google databases/caches or traverse all /data.
        homes = {'/data/data', *glob.glob('/data/user/[0-9]*'), *glob.glob('/data/user_de/[0-9]*')}
        for home in sorted(homes):
            for package in ('com.google.android.gms', 'com.android.vending'):
                roots.append(Path(home) / package / 'files/fonts')
    for root in roots:
        watcher.tree(root)


def wait(module: Path, seconds: float, proc: Path, tick: float = 2.0) -> int:
    watcher = EventWait()
    try:
        configure(watcher, module)
        processes = ProcessView(proc)
        baseline = processes.snapshot()
        deadline = time.monotonic() + max(0.0, min(seconds, 300.0))
        poller = select.poll()
        poller.register(watcher.fd, select.POLLIN)
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                return 2
            if poller.poll(max(1, int(min(tick, left) * 1000))):
                if watcher.changed():
                    return 0
            current = processes.snapshot()
            if current != baseline:
                return 0
    finally:
        watcher.close()


def main() -> int:
    try:
        if len(sys.argv) != 3:
            return 3
        module = Path(sys.argv[1])
        if not module.is_dir():
            return 3
        return wait(module, float(sys.argv[2]), Path(os.environ.get('LUOSHU_PROC_ROOT', '/proc')))
    except (OSError, AttributeError, ValueError):
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
