#!/usr/bin/env python3
"""Bounded, read-only Google/OPlus font evidence, never a rendering verdict.

Only stdout is written. No stores are created, migrated, locked, or repaired.
Provider font contents, accounts, full maps/FD paths and personal font names are
never exported. Missing evidence remains unknown, including inaccessible procfs.
Host fixtures exercise the collector; they are not OnePlus device reproduction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import time

sys.dont_write_bytecode = True
from google_font_fallback_core import (COMPONENT, GMS, SCHEMA as UNDO_SCHEMA,
                                      FallbackError, parse_snapshot,
                                      validated_code_path, validated_update_time)

SCHEMA = 'luoshu-google-font-diagnostic-v1'
BUDGET_MS = 8000
MAX_JSON_BYTES = 65536
MAX_TARGETS = 96
MAX_PROCESSES = 24
MAX_FDS = 256
MAX_SCAN = 512
MAX_MAP_BYTES = 131072
PACKAGES = ('com.android.vending', 'com.android.chrome', 'com.chrome.beta',
            'com.chrome.dev', 'com.chrome.canary', GMS, GMS + '.persistent',
            GMS + '.unstable', 'com.google.android.googlequicksearchbox')
SYSTEM_PROCESSES = ('zygote64', 'zygote', 'zygote_secondary', 'zygote64_32',
                    'zygote_ocomp', 'system_server')
PROPERTIES = ('ro.product.brand', 'ro.product.manufacturer', 'ro.product.model',
              'ro.build.version.sdk', 'ro.build.display.id',
              'ro.build.version.incremental', 'ro.build.version.oplusrom',
              'ro.build.version.opporom', 'ro.mi.os.version.name',
              'ro.miui.ui.version.name')
FAMILY = re.compile(r'(?<![A-Za-z0-9_-])(google-sans(?:-text)?|product-sans|'
                    r'sans-serif|oplus-sans|oppo-sans|op-sans(?:-en)?|'
                    r'oplus-os-ui|oplusosui|coloros-sans|oneplus-sans)(?![A-Za-z0-9_-])', re.I)
SLOT = re.compile(r'(?:GoogleSans[A-Za-z0-9_.-]*|Roboto[A-Za-z0-9_.-]*|'
                  r'SysFont[A-Za-z0-9_.-]*|SysSans[A-Za-z0-9_.-]*|'
                  r'Oplus[A-Za-z0-9_.-]*|OPlus[A-Za-z0-9_.-]*|'
                  r'OppoSans[A-Za-z0-9_.-]*|OPSans[A-Za-z0-9_.-]*)\.(?:ttf|otf|ttc)$')
SLOT_ROOTS = ('/system/fonts', '/system_ext/fonts', '/product/fonts',
              '/my_product/fonts', '/oplus_product/fonts')


class BudgetExpired(Exception):
    pass


def token(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8', errors='replace')).hexdigest()[:20]


def revision(snapshot: dict) -> dict:
    path = validated_code_path(snapshot.get('codePath'))
    version = snapshot.get('versionCode')
    return {'versionCode': version if type(version) is int and 0 <= version <= 2**63 - 1 else None,
            'lastUpdateTime': validated_update_time(snapshot.get('lastUpdateTime')),
            'codePathToken': token(path) if path else None}


def _allowed_name(name: str) -> bool:
    base = name.split(':', 1)[0]
    return name in SYSTEM_PROCESSES or base in PACKAGES


class Collector:
    def __init__(self, module: Path, user: int, phase: str, root: Path = Path('/'),
                 runner=None, budget_ms: int = BUDGET_MS):
        self.module, self.user, self.phase, self.root = module, user, phase, root
        self.runner = runner
        self.started = time.monotonic()
        self.deadline = self.started + min(BUDGET_MS, budget_ms) / 1000
        self.reasons: list[str] = []
        self.first_snapshot = None
        self.truncated = False
        self.report = {'schema': SCHEMA, 'status': 'diagnostic', 'phase': phase,
                       'capturedAtEpochMs': int(time.time() * 1000), 'user': user,
                       'bootToken': None,
                       'component': {'classification': 'unknown'},
                       'provider': {}, 'systemFonts': {}, 'rom': {},
                       'limitations': ['组件停用不等于字体渲染通过验收。',
                           '未发现旧 FD/mmap 不能排除应用内存中的 Typeface 缓存、内置字体或网页字体。',
                           '仅枚举固定名称进程和已记录的待刷新进程；未记录的隔离子进程可能未覆盖。',
                           '历史字体验证记录不是当前真机字体效果证明。']}

    def check(self):
        if time.monotonic() >= self.deadline:
            raise BudgetExpired()

    def issue(self, reason: str, truncated=False):
        if reason not in self.reasons and len(self.reasons) < 32:
            self.reasons.append(reason)
        self.truncated = self.truncated or truncated

    def path(self, absolute: str) -> Path:
        return self.root / absolute.lstrip('/')

    def read(self, path: Path, limit=65536) -> tuple[str, str]:
        self.check()
        try:
            with path.open('rb') as stream:
                raw = stream.read(limit + 1)
        except OSError:
            return '', 'unavailable'
        self.check()
        if len(raw) > limit:
            self.issue('input-byte-limit', True)
            return raw[:limit].decode('utf-8', errors='replace'), 'truncated'
        return raw.decode('utf-8', errors='replace'), 'read'

    def command(self, args: tuple[str, ...], limit=196608, seconds=1.2) -> tuple[str, str]:
        self.check()
        # Fixed commands only; no caller-supplied shell, package, path or command.
        if self.runner is not None:
            text, status = self.runner(args)
            if len(text.encode('utf-8')) > limit:
                self.issue('command-byte-limit', True)
                return text.encode('utf-8')[:limit].decode('utf-8', errors='replace'), 'truncated'
            self.check()
            return text, status
        try:
            process = subprocess.Popen(args, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError:
            return '', 'unavailable'
        chunks = bytearray()
        status = 'read'
        stop = min(self.deadline, time.monotonic() + seconds)
        selector = selectors.DefaultSelector()
        try:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = stop - time.monotonic()
                if remaining <= 0:
                    status = 'timeout'
                    break
                ready = selector.select(min(remaining, 0.1))
                if not ready:
                    continue
                raw = os.read(process.stdout.fileno(), min(32768, limit + 1 - len(chunks)))
                if not raw:
                    break
                chunks.extend(raw)
                if len(chunks) > limit:
                    status = 'truncated'
                    self.issue('command-byte-limit', True)
                    break
            if status == 'read' and process.wait(timeout=max(0.01, stop - time.monotonic())) != 0:
                status = 'failed'
        except (OSError, subprocess.TimeoutExpired):
            status = 'unavailable'
        finally:
            selector.close()
            # Kill only our own read-command subprocess, never an Android package.
            if process.poll() is None:
                process.kill()
            try:
                process.wait(timeout=0.1)
            except subprocess.TimeoutExpired:
                pass
            process.stdout.close()
        self.check()
        return bytes(chunks[:limit]).decode('utf-8', errors='replace'), status

    def identity(self, path: Path, follow=True):
        self.check()
        try:
            s = path.stat() if follow else path.lstat()
        except OSError:
            return None
        if not stat.S_ISREG(s.st_mode):
            return None
        return {'device': s.st_dev, 'inode': s.st_ino, 'size': s.st_size,
                'mtimeNs': s.st_mtime_ns}

    def journal(self) -> dict:
        canonical = self.path('/data/adb/luoshu/google-font-fallback')
        legacy = self.path('/data/adb/luoshu-google-font-fallback')
        folder = canonical if canonical.exists() else legacy
        try:
            info = folder.lstat()
            if stat.S_ISLNK(info.st_mode):
                if folder != legacy or folder.resolve() != canonical.resolve():
                    return {'readState': 'unsafe-directory'}
                folder = canonical
                info = folder.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                return {'readState': 'unsafe-directory'}
            p = folder / f'user-{self.user}.json'
            info = p.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022:
                return {'readState': 'unsafe-record'}
            if info.st_size > 16384:
                return {'readState': 'oversized-record'}
        except OSError:
            return {'readState': 'missing-or-unavailable'}
        raw, state = self.read(p, 16384)
        try:
            saved = json.loads(raw)
            valid = (state == 'read' and isinstance(saved, dict) and saved.get('schema') == UNDO_SCHEMA
                     and saved.get('component') == COMPONENT and type(saved.get('user')) is int
                     and saved['user'] == self.user and type(saved.get('appId')) is int
                     and type(saved.get('original')) is int and saved['original'] in (0, 1)
                     and isinstance(saved.get('firstInstallTime'), str))
            if not valid:
                return {'readState': 'invalid-record'}
        except (ValueError, TypeError):
            return {'readState': 'invalid-record'}
        return {'readState': 'valid', 'original': saved['original'], 'user': saved['user'],
                'appId': saved['appId'], 'firstInstallTimeToken': token(saved['firstInstallTime']),
                'originalRevision': revision(saved),
                'verifiedRevision': revision({'versionCode': saved.get('lastVerifiedVersionCode', saved.get('versionCode')),
                    'lastUpdateTime': saved.get('lastVerifiedUpdateTime', saved.get('lastUpdateTime')),
                    'codePath': saved.get('lastVerifiedCodePath', saved.get('codePath'))})}

    def component(self):
        text, state = self.command(('/system/bin/dumpsys', '-t', '1', 'package', GMS), limit=1048576)
        result = {'readState': state, 'actual': None, 'undo': self.journal(),
                  'classification': 'unknown', 'stability': 'unknown',
                  'afterCollection': None}
        if state != 'read':
            self.issue('component-snapshot-unavailable')
        else:
            try:
                current = parse_snapshot(text, self.user)
                self.first_snapshot = current
                undo = result['undo']
                managed = (undo['readState'] == 'valid' and undo['appId'] == current['appId']
                           and undo['firstInstallTimeToken'] == token(current['firstInstallTime']))
                result.update({'actual': {'componentState': current['componentState'],
                     'packageState': current['packageState'], 'declared': current['declared']},
                     'managed': managed, 'currentRevision': revision(current),
                     'verifiedRevision': undo.get('verifiedRevision')})
                result['classification'] = ('managed-disabled' if managed and current['componentState'] == 2
                    else 'managed-component-changed' if managed
                    else 'unmanaged-disabled' if current['componentState'] == 2 else 'unmanaged')
            except (FallbackError, ValueError, TypeError):
                result['readState'] = 'unparseable'
                self.issue('component-snapshot-unparseable')
        self.report['component'] = result

    def component_stability(self):
        self.check()
        raw, state = self.command(('/system/bin/dumpsys', '-t', '1', 'package', GMS), limit=1048576)
        result = self.report['component']
        try:
            if state != 'read' or self.first_snapshot is None:
                raise FallbackError('unknown')
            after = parse_snapshot(raw, self.user)
            result['afterCollection'] = {'actual': {'componentState': after['componentState'],
                'packageState': after['packageState'], 'declared': after['declared']},
                'currentRevision': revision(after)}
            result['stability'] = 'stable' if after == self.first_snapshot else 'changed-during-collection'
            if result['stability'] != 'stable':
                self.issue('component-changed-during-collection')
        except (FallbackError, ValueError, TypeError):
            result['stability'] = 'unknown'
            self.issue('component-after-snapshot-unavailable')

    def user_target(self, raw: str) -> str | None:
        for package in ('com.google.android.gms', 'com.android.vending'):
            for prefix in (f'/data/user/{self.user}/{package}/files/fonts/',
                           f'/data/user_de/{self.user}/{package}/files/fonts/'):
                if raw.startswith(prefix):
                    return package + '-provider'
            if self.user == 0 and raw.startswith(f'/data/data/{package}/files/fonts/'):
                return package + '-provider'
        if raw.startswith('/data/fonts/files/'):
            return 'system-updatable-font'
        return None

    def valid_target(self, raw):
        return (isinstance(raw, str) and self.user_target(raw) is not None
                and not any(x in ('.', '..', '') for x in raw.split('/')[1:])
                and not any(ord(x) < 32 or x == '|' for x in raw))

    def clone_path(self, raw: str) -> Path | None:
        for folder in (self.module / '.luoshu-state/cache/google-font-provider',
                       self.module / 'config/google-font-provider'):
            path = Path(raw)
            if path.parent == folder and re.fullmatch(r'[a-f0-9]{32,64}\.ttf', path.name):
                return path
        return None

    def bounded_rows(self, name: str, maxrows=128):
        path = self.module / 'config' / name
        try:
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode):
                return [], 'unsafe-record-type'
        except OSError:
            return [], 'unavailable'
        raw, state = self.read(path, 49152)
        rows = raw.splitlines()
        if len(rows) > maxrows:
            self.issue('journal-row-limit', True)
            state = 'truncated'
        return rows[:maxrows], state

    def provider(self):
        targets: dict[str, dict] = {}
        old_ids: set[tuple[int, int]] = set()
        mounts, mount_state = self.bounded_rows('google-font-provider-namespaces.conf')
        sources, source_state = self.bounded_rows('google-font-provider-mounts.conf')
        pending, pending_state = self.bounded_rows('google-font-refresh-pending.conf')
        queue_boot, queue_boot_state = self.read(self.module / 'config/google-font-refresh-pending.conf.boot', 128)
        pending_same_boot = (token(queue_boot.strip()) == self.report['bootToken']
                             if queue_boot_state == 'read' and self.report['bootToken'] else None)
        owned = []
        for line in sources:
            v = line.split('|')
            if len(v) != 8 or v[6] != 'provider-v3' or not self.valid_target(v[0]):
                continue
            clone = self.clone_path(v[1])
            if clone is None:
                continue
            original = self.numeric_identity(v[7])
            if original:
                old_ids.add(original[:2])
            targets[v[0]] = {'pathToken': token(v[0]), 'category': self.user_target(v[0]),
                            'recorded': True, 'currentIdentity': self.identity(self.path(v[0])),
                            'cloneIdentity': self.identity(clone), 'weight': int(v[5]) if v[5] in tuple(str(i) for i in range(100, 1000, 100)) else None,
                            'originalIdentity': list(original[:2]) if original else None}
        for line in mounts:
            v = line.split('|')
            if len(v) != 4 or not re.fullmatch(r'mnt:\[\d+\]', v[0]) or not self.valid_target(v[1]):
                continue
            clone = self.clone_path(v[3])
            identity = self.numeric_identity(v[2])
            if clone is not None and identity:
                owned.append({'namespace': v[0], 'targetToken': token(v[1]),
                              'recordedIdentity': list(identity), 'cloneToken': token(v[3])})
        queued = []
        for line in pending:
            v = line.split('|')
            if len(v) != 7 or not all(re.fullmatch(r'\d{1,20}', x) for x in (v[0], v[1], v[3], v[5])):
                continue
            if int(v[3]) != self.user or v[2] not in PACKAGES or v[2].startswith(GMS):
                continue
            identity = self.numeric_identity(v[4])
            if identity:
                old_ids.add(identity[:2])
                queued.append({'pid': int(v[0]), 'starttime': int(v[1]), 'package': v[2],
                               'lastAttemptEpoch': int(v[5]), 'oldIdentity': list(identity[:2])})
        roots = [(self.path(f'/data/{kind}/{self.user}/{package}/files/fonts'), package + '-provider', 6)
                 for kind in ('user', 'user_de') for package in ('com.google.android.gms', 'com.android.vending')]
        if self.user == 0:
            roots += [(self.path(f'/data/data/{package}/files/fonts'), package + '-provider', 6)
                      for package in ('com.google.android.gms', 'com.android.vending')]
        roots += [(self.path('/data/fonts/files'), 'system-updatable-font', 3)]
        allowed_roots = {path for path, category, depth in roots}
        scanned = 0
        seen = set()
        for folder, category, depth in roots:
            # /data/data may alias /data/user/0. Never walk a theme/cache link
            # into another app's files or an arbitrary directory.
            try:
                if folder.resolve(strict=True) not in allowed_roots:
                    self.issue('provider-directory-outside-allowlist')
                    continue
            except FileNotFoundError:
                continue
            except OSError:
                self.issue('provider-directory-unavailable')
                continue
            stack = [(folder, 0)]
            while stack:
                self.check()
                directory, level = stack.pop()
                try:
                    entries = os.scandir(directory)
                except FileNotFoundError:
                    continue
                except OSError:
                    self.issue('provider-directory-unavailable')
                    continue
                with entries:
                    for entry in entries:
                        self.check()
                        scanned += 1
                        if scanned > MAX_SCAN or len(targets) >= MAX_TARGETS:
                            self.issue('provider-target-limit', True)
                            stack.clear()
                            break
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False) and level < depth:
                            stack.append((Path(entry.path), level + 1))
                        elif entry.is_file(follow_symlinks=False):
                            raw = '/' + str(Path(entry.path).relative_to(self.root))
                            identity = self.identity(Path(entry.path), follow=False)
                            if identity and (identity['device'], identity['inode']) not in seen:
                                seen.add((identity['device'], identity['inode']))
                                if raw not in targets:
                                    targets[raw] = {'pathToken': token(raw), 'category': category,
                                                   'recorded': False, 'currentIdentity': identity,
                                                   'recognition': 'unknown-metadata-only'}
                if scanned > MAX_SCAN or len(targets) >= MAX_TARGETS:
                    break
            if scanned > MAX_SCAN or len(targets) >= MAX_TARGETS:
                break
        stale_pending_count = len(queued) if pending_same_boot is False else None
        if pending_same_boot is not True and queued:
            self.issue('pending-boot-identity-unknown-or-stale')
            queued = []  # A previous boot's PID/FD identity cannot identify a live process.
        self.report['provider'] = {'targets': list(targets.values()), 'mounts': owned,
                    'mountJournalReadState': mount_state, 'sourceJournalReadState': source_state,
                    'pending': queued, 'pendingReadState': pending_state,
                    'pendingSameBoot': pending_same_boot, 'stalePendingCount': stale_pending_count,
                    'unrecordedCandidates': sum(not t['recorded'] for t in targets.values()),
                    'unrecordedCandidatesMeaning': '仅有文件元数据，未读取字体内容；不等于新字体已识别或根因已确认。'}
        self.processes(targets, owned, queued, old_ids)

    @staticmethod
    def numeric_identity(raw: str):
        if not re.fullmatch(r'\d{1,20}:\d{1,20}(?::\d{1,20})?', raw):
            return None
        return tuple(int(x) for x in raw.split(':'))

    def process_start(self, pid):
        raw, state = self.read(self.path(f'/proc/{pid}/stat'), 4096)
        try:
            value = raw.rsplit(') ', 1)[1].split()[19]
            return int(value) if state == 'read' and value.isdigit() else None
        except (IndexError, ValueError):
            return None

    def processes(self, targets, owned, queued, old_ids):
        raw, state = self.command(('/system/bin/pidof', *PACKAGES, *SYSTEM_PROCESSES), limit=8192, seconds=.6)
        pids = {int(x) for x in raw.split() if re.fullmatch(r'\d{1,10}', x) and 0 < int(x) <= 2147483647}
        pids.update(q['pid'] for q in queued)
        if state not in ('read', 'failed'):
            self.issue('process-enumeration-unavailable')
        if len(pids) > MAX_PROCESSES:
            self.issue('process-limit', True)
        processes = []
        self.report['provider']['processes'] = processes
        for pid in sorted(pids)[:MAX_PROCESSES]:
            self.check()
            cmdline, name_state = self.read(self.path(f'/proc/{pid}/cmdline'), 256)
            name = cmdline.split('\0', 1)[0]
            if name_state != 'read':
                processes.append({'pid': pid, 'readState': 'unknown-process-exited-or-inaccessible'})
                self.issue('process-identity-unavailable')
                continue
            if not _allowed_name(name):
                # PID reuse: do not read any further data from this process.
                self.issue('process-identity-changed')
                continue
            status, status_state = self.read(self.path(f'/proc/{pid}/status'), 16384)
            uid_match = re.search(r'^Uid:\s*(\d+)\b', status, re.M)
            if status_state != 'read' or uid_match is None:
                processes.append({'pid': pid, 'readState': 'unknown-uid'})
                self.issue('process-uid-unavailable')
                continue
            uid = int(uid_match[1])
            system = name in SYSTEM_PROCESSES
            if not system and uid // 100000 != self.user:
                continue
            if system and uid not in (0, 1000):
                continue
            start = self.process_start(pid)
            process = {'pid': pid, 'package': name.split(':', 1)[0], 'starttime': start,
                       'user': None if system else uid // 100000, 'readState': 'read'}
            processes.append(process)
            if start is None:
                process['readState'] = 'unknown-starttime'
                self.issue('process-starttime-unavailable')
                continue
            try:
                ns = os.readlink(self.path(f'/proc/{pid}/ns/mnt'))
                process['namespace'] = ns if re.fullmatch(r'mnt:\[\d+\]', ns) else None
            except OSError:
                process['namespace'] = None
                self.issue('namespace-unavailable')
            views = []
            mountinfo, mount_read_state = self.read(self.path(f'/proc/{pid}/mountinfo'), 65536)
            mount_targets = {}
            for line in mountinfo.splitlines():
                fields = line.split()
                if len(fields) >= 6:
                    target_path = re.sub(r'\\([0-7]{3})', lambda match: chr(int(match[1], 8)), fields[4])
                    if target_path in targets:
                        mount_targets[target_path] = 'ro' in fields[5].split(',')
            for path, target in list(targets.items())[:48]:
                identity = self.identity(self.path(f'/proc/{pid}/root{path}'))
                expected = [o for o in owned if o['targetToken'] == target['pathToken'] and o['namespace'] == process['namespace']]
                owned_match = None if identity is None else any(
                    identity['device'] == o['recordedIdentity'][0] and identity['inode'] == o['recordedIdentity'][1] for o in expected)
                views.append({'targetToken': target['pathToken'], 'identity': identity,
                              'ownedMountMatches': owned_match,
                              'mountReadState': mount_read_state,
                              'mountPresent': path in mount_targets if mount_read_state == 'read' else None,
                              'mountReadonly': mount_targets.get(path) if mount_read_state == 'read' else None})
            process['targetViews'] = views
            process['pendingStarttimeMatches'] = (all(q['starttime'] == start for q in queued if q['pid'] == pid)
                if any(q['pid'] == pid for q in queued) else None)
            fd_matches, fd_state, fd_scanned = 0, 'read', 0
            try:
                with os.scandir(self.path(f'/proc/{pid}/fd')) as entries:
                    for entry in entries:
                        self.check()
                        if not entry.name.isdigit():
                            continue
                        fd_scanned += 1
                        if fd_scanned > MAX_FDS:
                            fd_state = 'truncated'
                            self.issue('fd-limit', True)
                            break
                        s = self.identity(Path(entry.path))
                        if s and (s['device'], s['inode']) in old_ids:
                            fd_matches += 1
            except OSError:
                fd_state = 'unavailable'
                self.issue('fd-view-unavailable')
            maps, map_state = self.read(self.path(f'/proc/{pid}/maps'), MAX_MAP_BYTES)
            map_matches = 0
            for line in maps.splitlines():
                v = line.split(None, 5)
                if len(v) < 5:
                    continue
                try:
                    major, minor = (int(x, 16) for x in v[3].split(':'))
                    identity = (os.makedev(major, minor), int(v[4]))
                except (ValueError, OverflowError):
                    continue
                if identity in old_ids:
                    map_matches += 1
            if map_state != 'read':
                self.issue('maps-view-unavailable-or-truncated', map_state == 'truncated')
            process['oldDescriptorEvidence'] = {'fdReadState': fd_state,
                'fdScanned': min(fd_scanned, MAX_FDS), 'fdMatches': fd_matches if fd_state == 'read' else None,
                'mapsReadState': map_state, 'mmapMatches': map_matches if map_state == 'read' else None,
                'memoryTypefaceCache': 'unknown'}
            if self.process_start(pid) != start:
                process.clear()
                process.update({'pid': pid, 'readState': 'unknown-process-changed-during-collection'})
                self.issue('process-identity-changed')

    def system_fonts(self):
        raw, state = self.command(('/system/bin/cmd', 'font', 'dump'), limit=131072, seconds=.9)
        if state != 'read':
            raw, state = self.command(('/system/bin/dumpsys', '-t', '1', 'font'), limit=131072, seconds=.9)
        # Export only constant allowlisted family names, never whole lines.
        families = sorted({m[1].lower() for m in FAMILY.finditer(raw)})
        versions = re.findall(r'(?im)^\s*(?:config(?:uration)?\s*version|configVersion)\s*[:=]\s*(\d{1,12})\s*$', raw)
        map_info = {'readState': state, 'allowlistedFamilies': families,
                    'configVersion': int(versions[0]) if len(versions) == 1 else None}
        if state != 'read':
            self.issue('font-map-unavailable')
        slots = []
        for folder in SLOT_ROOTS:
            self.check()
            try:
                with os.scandir(self.path(folder)) as entries:
                    for entry in entries:
                        self.check()
                        if not SLOT.fullmatch(entry.name):
                            continue
                        if len(slots) >= 40:
                            self.issue('system-slot-limit', True)
                            break
                        slots.append({'partition': folder.split('/')[1], 'slot': entry.name,
                                      'identity': self.identity(Path(entry.path))})
            except FileNotFoundError:
                continue
            except OSError:
                self.issue('system-slot-unavailable')
        raw_config, config_state = self.read(self.path('/data/fonts/config/config.xml'), 65536)
        # Configuration content is neither copied nor parsed as arbitrary output.
        config_token = token(raw_config) if config_state == 'read' else None
        self.report['systemFonts'] = {'map': map_info, 'slots': slots,
             'dynamicConfig': {'readState': config_state, 'contentToken': config_token},
             'historicalVerification': {'currentRenderingProven': False}}
        historical, history_state = self.read(self.module / 'config/device-font-load-verification.conf', 4096)
        fields = {}
        for line in historical.splitlines():
            key, sep, value = line.partition('=')
            if sep and key in ('state', 'mode', 'reason') and re.fullmatch(r'[A-Za-z0-9_-]{1,100}', value):
                fields[key] = value
            elif sep and key == 'time' and value.isdigit():
                fields['time'] = int(value)
        self.report['systemFonts']['historicalVerification'].update({'readState': history_state, **fields})

    def rom(self):
        properties = {}
        for prop in PROPERTIES:
            raw, state = self.command(('/system/bin/getprop', prop), limit=512, seconds=.2)
            value = raw.strip()
            properties[prop] = value if state == 'read' and re.fullmatch(r'[\w .:/+()-]{0,160}', value, re.ASCII) else None
            if state != 'read':
                self.issue('rom-properties-unavailable')
        self.report['rom'] = properties

    def module_state(self):
        raw, state = self.read(self.module / 'module.prop', 4096)
        fields = {'readState': state}
        for line in raw.splitlines():
            key, sep, value = line.partition('=')
            if key == 'versionCode' and sep and re.fullmatch(r'\d{1,12}', value):
                fields['versionCode'] = int(value)
            elif key == 'version' and sep and re.fullmatch(r'[A-Za-z0-9_.+ ()-]{1,80}', value):
                fields['version'] = value
        active, active_state = self.read(self.module / 'config/active_font.conf', 512)
        fields['activeCustomFont'] = (active.strip() not in ('', 'default') if active_state == 'read' else None)
        fields['disabled'] = (self.module / 'disable').exists()
        fields['removed'] = (self.module / 'remove').exists()
        self.report['module'] = fields

    def collect(self):
        ownership_only = False
        try:
            if self.phase == 'before-maintenance':
                undo = self.journal()
                if undo.get('readState') != 'valid':
                    # Automatic foreground maintenance must be nearly free for
                    # users who never enabled this feature. No Android/procfs
                    # evidence is read without our validated undo record.
                    ownership_only = True
                    self.report['component'] = {'classification': 'not-owned',
                        'actual': None, 'managed': False, 'readState': 'ownership-only',
                        'undo': undo, 'stability': 'unknown', 'afterCollection': None}
                    return self.finish(ownership_only=True)
            boot, state = self.read(self.path('/proc/sys/kernel/random/boot_id'), 128)
            self.report['bootToken'] = token(boot.strip()) if state == 'read' and re.fullmatch(r'[a-fA-F0-9-]{8,64}', boot.strip()) else None
            self.module_state()
            self.component()
            self.provider()
            self.system_fonts()
            self.rom()
            self.component_stability()
        except BudgetExpired:
            self.issue('time-budget-exhausted', True)
        except OSError:
            self.issue('filesystem-evidence-unavailable')
        return self.finish(ownership_only=ownership_only)

    def finish(self, ownership_only=False):
        self.report['collection'] = {'complete': not self.reasons, 'truncated': self.truncated,
            'reasons': self.reasons, 'elapsedMs': int((time.monotonic() - self.started) * 1000),
            'budgetMs': BUDGET_MS, 'scope': 'ownership-only' if ownership_only else 'full-evidence'}
        if ownership_only:
            self.report['collection']['skippedReason'] = 'no-validated-owned-undo'
        return self.report


def encode(report: dict) -> str:
    def dump():
        return json.dumps(report, ensure_ascii=False, separators=(',', ':'))
    raw = dump()
    if len(raw.encode('utf-8')) <= MAX_JSON_BYTES:
        return raw
    collection = report['collection']
    collection['complete'], collection['truncated'] = False, True
    collection['reasons'].append('output-byte-limit')
    processes = report.get('provider', {}).get('processes', [])
    for process in processes:
        process.pop('targetViews', None)
    raw = dump()
    if len(raw.encode('utf-8')) > MAX_JSON_BYTES:
        report.get('provider', {})['targets'] = []
        report.get('provider', {})['mounts'] = []
        raw = dump()
    if len(raw.encode('utf-8')) > MAX_JSON_BYTES:
        # A future field must never weaken the output contract. Retain only
        # fixed, small, independently validated envelope values in this case.
        component = report.get('component', {})
        actual = component.get('actual') or {}
        user = report.get('user')
        captured = report.get('capturedAtEpochMs')
        boot = report.get('bootToken')
        small = {'schema': SCHEMA, 'status': 'diagnostic',
            'phase': report.get('phase') if report.get('phase') in ('before-maintenance', 'explicit-report') else 'unknown',
            'user': user if type(user) is int and 0 <= user <= 21474 else None,
            'capturedAtEpochMs': captured if type(captured) is int and 0 <= captured <= 2**63-1 else None,
            'bootToken': boot if isinstance(boot, str) and re.fullmatch(r'[a-f0-9]{20}', boot) else None,
            'component': {'actual': {
                'componentState': actual.get('componentState') if type(actual.get('componentState')) is int and actual.get('componentState') in (0, 1, 2, 3, 4) else None,
                'packageState': actual.get('packageState') if type(actual.get('packageState')) is int and actual.get('packageState') in (0, 1, 2, 3, 4) else None,
                'declared': actual.get('declared') if type(actual.get('declared')) is bool else None},
                'classification': component.get('classification') if component.get('classification') in ('managed-disabled', 'managed-component-changed', 'unmanaged-disabled', 'unmanaged', 'not-owned', 'unknown') else 'unknown',
                'stability': component.get('stability') if component.get('stability') in ('stable', 'changed-during-collection', 'unknown') else 'unknown'},
            'collection': {'complete': False, 'truncated': True, 'reasons': ['output-byte-limit'], 'budgetMs': BUDGET_MS},
            'limitations': ['报告超过输出预算，只保留组件读数；其余证据未知。组件读数不代表字体渲染验收。']}
        raw = json.dumps(small, ensure_ascii=False, separators=(',', ':'))
    return raw


def main() -> int:
    parser = argparse.ArgumentParser(description='只读 Google/OPlus 字体复发诊断，不更改系统。')
    parser.add_argument('--user', required=True, type=int)
    parser.add_argument('--phase', required=True, choices=('before-maintenance', 'explicit-report'))
    args = parser.parse_args()
    if not 0 <= args.user <= 21474:
        parser.error('invalid Android user')
    collector = Collector(Path(os.environ.get('MODDIR', str(Path(__file__).resolve().parent.parent))), args.user, args.phase)
    def expire(signum, frame):
        raise BudgetExpired()
    old_handler = signal.signal(signal.SIGALRM, expire)
    signal.setitimer(signal.ITIMER_REAL, BUDGET_MS / 1000)
    try:
        result = collector.collect()
    except BudgetExpired:
        collector.issue('time-budget-exhausted', True)
        result = collector.report
        result['collection'] = {'complete': False, 'truncated': True, 'reasons': collector.reasons,
            'elapsedMs': BUDGET_MS, 'budgetMs': BUDGET_MS}
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
    print(encode(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
