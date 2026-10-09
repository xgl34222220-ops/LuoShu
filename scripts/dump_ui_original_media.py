#!/usr/bin/env python3
"""Retain five fixed original media files in the same job log, without decoding.

This is byte retention only. Diagnostic footage never supplies primary visual
acceptance. A consumer must require MEDIA_END as well as exact offsets/length/SHA;
a truncated log or any ERROR/REJECTED is incomplete evidence.
"""
from __future__ import annotations

import base64
from contextlib import ExitStack
import errno
import hashlib
import os
from pathlib import Path
import stat
import sys
from typing import TextIO
import uuid


OUTPUT_DIRECTORY = "launch-visual-output"
MEDIA_FILES = (
    ("light-cold-start.mp4", "primary"),
    ("light-warm-start.mp4", "primary"),
    ("dark-cold-start.mp4", "primary"),
    ("dark-warm-start.mp4", "primary"),
    ("diagnostic-only/diagnostic.mp4", "diagnostic-only"),
)
CHUNK_BYTES = 3072
HASH_CHUNK_BYTES = 65536


class MediaError(Exception):
    def __init__(self, kind: str, reason: str):
        self.kind = kind
        self.reason = reason
        super().__init__(reason)


class NotProduced(Exception):
    pass


def _directory(parent: int, name: str, stack: ExitStack, chain: list,
               *, missing: bool = False) -> int:
    try:
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                     dir_fd=parent)
    except FileNotFoundError:
        if missing:
            _check_chain(chain)
            raise NotProduced from None
        raise MediaError("REJECTED", "invalid-workspace") from None
    except OSError as error:
        kind = "REJECTED" if error.errno in (errno.ELOOP, errno.ENOTDIR) else "ERROR"
        raise MediaError(kind, "unsafe-directory") from None
    stack.callback(os.close, fd)
    info = os.fstat(fd)
    chain.append((parent, fd, name, info.st_dev, info.st_ino))
    return fd


def _workspace(path: Path, stack: ExitStack, chain: list) -> int:
    # Walk the configured workspace itself too: resolving first would hide a
    # symlink in its parent components. No relative path or traversal is allowed.
    raw = os.fspath(path)
    parts = raw.split(os.sep)
    if not os.path.isabs(raw) or raw == os.sep or any(part in (".", "..") for part in parts):
        raise MediaError("REJECTED", "invalid-workspace")
    fd = os.open(os.sep, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    stack.callback(os.close, fd)
    for part in parts:
        if part:
            fd = _directory(fd, part, stack, chain)
    return fd


def _check_chain(chain: list) -> None:
    for parent, fd, name, device, inode in chain:
        try:
            descriptor = os.fstat(fd)
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except OSError:
            raise MediaError("ERROR", "directory-changed") from None
        if (not stat.S_ISDIR(descriptor.st_mode) or not stat.S_ISDIR(current.st_mode)
                or (descriptor.st_dev, descriptor.st_ino) != (device, inode)
                or (current.st_dev, current.st_ino) != (device, inode)):
            raise MediaError("ERROR", "directory-changed")


def _signature(info: os.stat_result) -> tuple:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _check_file(fd: int, parent: int, name: str, expected: tuple, chain: list) -> None:
    _check_chain(chain)
    try:
        descriptor = os.fstat(fd)
        entry = os.stat(name, dir_fd=parent, follow_symlinks=False)
    except OSError:
        raise MediaError("ERROR", "file-changed") from None
    if _signature(descriptor) != expected or _signature(entry) != expected:
        raise MediaError("ERROR", "file-changed")


def _media(root: int, relative: str, stack: ExitStack, chain: list) -> tuple:
    if relative not in {name for name, _ in MEDIA_FILES}:
        raise MediaError("REJECTED", "not-whitelisted")
    _check_chain(chain)
    parts = relative.split("/")
    parent = root
    for part in parts[:-1]:
        parent = _directory(parent, part, stack, chain, missing=True)
    try:
        # O_NONBLOCK prevents a substituted FIFO from blocking before fstat.
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                     dir_fd=parent)
    except FileNotFoundError:
        _check_chain(chain)
        raise NotProduced from None
    except OSError as error:
        kind = "REJECTED" if error.errno in (errno.ELOOP, errno.ENXIO, errno.ENODEV) else "ERROR"
        raise MediaError(kind, "unsafe-file") from None
    stack.callback(os.close, fd)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        raise MediaError("REJECTED", "not-regular-file")
    if info.st_nlink != 1:
        raise MediaError("REJECTED", "extra-hardlink")
    expected = _signature(info)
    _check_file(fd, parent, parts[-1], expected, chain)
    return fd, parent, parts[-1], expected


def _chunks(fd: int, length: int, size: int):
    remaining = length
    while remaining:
        chunk = os.read(fd, min(size, remaining))
        if not chunk:
            raise MediaError("ERROR", "file-changed")
        remaining -= len(chunk)
        yield chunk
    # A growing file is an error, not a silently capped successful stream.
    if os.read(fd, 1):
        raise MediaError("ERROR", "file-changed")


def _dump_file(root: int, relative: str, role: str, workspace_chain: list, output: TextIO) -> None:
    with ExitStack() as stack:
        chain = list(workspace_chain)
        fd, parent, name, expected = _media(root, relative, stack, chain)
        length = expected[4]
        original = hashlib.sha256()
        for chunk in _chunks(fd, length, HASH_CHUNK_BYTES):
            original.update(chunk)
        _check_file(fd, parent, name, expected, chain)
        digest = original.hexdigest()
        os.lseek(fd, 0, os.SEEK_SET)
        print(f"ROLE {relative} role={role}", file=output, flush=True)
        print(f"FILE {relative} bytes={length} sha256={digest}", file=output, flush=True)
        streamed = hashlib.sha256()
        offset = 0
        for chunk in _chunks(fd, length, CHUNK_BYTES):
            streamed.update(chunk)
            print(f"BASE64 offset={offset} {base64.b64encode(chunk).decode('ascii')}",
                  file=output, flush=True)
            offset += len(chunk)
        _check_file(fd, parent, name, expected, chain)
        if offset != length or streamed.hexdigest() != digest:
            raise MediaError("ERROR", "stream-mismatch")
        # Required terminal receipt: a log ending after the last BASE64 line
        # cannot hide a later mutation rejection and masquerade as complete.
        print(f"MEDIA_END {relative} role={role} bytes={offset} sha256={streamed.hexdigest()}",
              file=output, flush=True)


def dump_original_media(workspace: Path, output: TextIO, *, reject_arguments: bool = False) -> int:
    boundary = uuid.uuid4().hex
    try:
        print(f"::stop-commands::{boundary}", file=output, flush=True)
        print("MEDIA_SCOPE original-bytes-only; diagnostic-only is not primary acceptance",
              file=output, flush=True)
        with ExitStack() as stack:
            chain: list = []
            try:
                if reject_arguments:
                    raise MediaError("REJECTED", "unexpected-arguments")
                workspace_fd = _workspace(workspace, stack, chain)
                root = _directory(workspace_fd, OUTPUT_DIRECTORY, stack, chain, missing=True)
            except NotProduced:
                for relative, role in MEDIA_FILES:
                    print(f"MISSING {relative} role={role} reason=not-produced", file=output, flush=True)
                return 0
            except MediaError as error:
                for relative, role in MEDIA_FILES:
                    print(f"{error.kind} {relative} role={role} reason={error.reason}",
                          file=output, flush=True)
                return 1
            except OSError:
                for relative, role in MEDIA_FILES:
                    print(f"ERROR {relative} role={role} reason=workspace-open-failed", file=output, flush=True)
                return 1
            failed = False
            for relative, role in MEDIA_FILES:
                try:
                    _dump_file(root, relative, role, chain, output)
                except NotProduced:
                    print(f"MISSING {relative} role={role} reason=not-produced", file=output, flush=True)
                except MediaError as error:
                    failed = True
                    print(f"{error.kind} {relative} role={role} reason={error.reason}",
                          file=output, flush=True)
                except OSError:
                    failed = True
                    print(f"ERROR {relative} role={role} reason=io-failure", file=output, flush=True)
            return 1 if failed else 0
    finally:
        # A partial failed write may have left the output in the middle of a
        # line. Start the restore command on its own line even in that case.
        print(f"\n::{boundary}::", file=output, flush=True)


def main(argv: list[str] | None = None) -> int:
    # The workflow supplies no path arguments. Unexpected arguments are rejected
    # under the same safe boundary without echoing private paths or command text.
    arguments = sys.argv[1:] if argv is None else argv
    return dump_original_media(Path.cwd(), sys.stdout, reject_arguments=bool(arguments))


if __name__ == "__main__":
    raise SystemExit(main())
