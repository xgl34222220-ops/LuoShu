#!/usr/bin/env python3
"""Verify inventory outputs in Android's runtime mount namespace.

Explicit verification hashes complete files once per inode. Status reuses evidence
only for the same boot, selection, manifest, namespaces and file stat identities.
Mount/probe flags alone never establish that the selected font bytes are visible.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import time

SCHEMA = 'physical-font-load-v1'
MANIFEST = '.luoshu-inventory-output-manifest.json'
RESULT = 'device-font-physical-verification.json'


def boot_id() -> str:
    return os.environ.get('LUOSHU_TEST_BOOT_ID') or Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def identity(path: Path) -> list[int]:
    item = path.stat()
    return [item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns]


def digest(path: Path, cache: dict | None = None) -> str:
    key = tuple(identity(path))
    if cache is not None and key in cache:
        return cache[key]
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    if tuple(identity(path)) != key:
        raise ValueError('file-changed-during-verification')
    result = value.hexdigest()
    if cache is not None:
        cache[key] = result
    return result


def logical_path(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError('unsafe-manifest-font-path')
    parts = PurePosixPath(value).parts
    if (not value.startswith('/') or value.startswith('//') or len(parts) < 3
            or any(part in ('', '.', '..') for part in value[1:].split('/'))
            or any(char in value for char in '\r\n\t\x00')
            or parts[1] in {'proc', 'sys', 'dev', 'data', 'storage', 'sdcard', 'mnt'}):
        raise ValueError('unsafe-manifest-font-path')
    return value


def manifest_data(module: Path, payload: Path) -> tuple[str, dict[str, str]]:
    path = payload / MANIFEST
    if path.exists():
        raw = path.read_bytes()
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get('schema') != 'inventory-font-output-v1' or not isinstance(data.get('files'), dict):
            raise ValueError('invalid-output-manifest')
        # The inventory engine already validated the mapped font contents. XML
        # may reference real OpenType files with .font or no standard suffix.
        files = data['files']
    else:
        # Read-only compatibility with already installed legacy payloads.
        path = module / 'config/font-payload-manifest.conf'
        raw = path.read_bytes()
        files = {}
        for line in raw.decode().splitlines():
            row = line.split('|')
            if len(row) >= 2 and Path(row[0]).suffix.lower() in {'.ttf', '.otf', '.ttc', '.otc'}:
                files['/' + row[0].lstrip('/')] = row[1]
    for name, expected in files.items():
        logical_path(name)
        if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
            raise ValueError('invalid-output-digest')
    if not files:
        raise ValueError('empty-output-manifest')
    return hashlib.sha256(raw).hexdigest(), files


def runtime_namespaces() -> list[dict]:
    custom = os.environ.get('LUOSHU_VISIBLE_ROOT')
    if custom:
        root = Path(custom).resolve()
        return [{'kind': 'explicit', 'root': str(root), 'identity': identity(root)[:2]}]
    roots = []
    # /proc/PID/root traverses the target process's mount namespace. Reading /
    # here would instead test the privileged command's potentially private view.
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            name = (proc / 'cmdline').read_bytes().split(b'\0', 1)[0].decode(errors='replace').rsplit('/', 1)[-1]
            if name not in {'system_server', 'zygote', 'zygote32', 'zygote64'}:
                continue
            namespace = os.readlink(proc / 'ns/mnt')
            start = (proc / 'stat').read_text().rsplit(')', 1)[1].split()[19]
            roots.append({'kind': 'android-runtime', 'root': str(proc / 'root'),
                          'namespace': namespace, 'start': start, 'process': name})
        except (OSError, ValueError, IndexError):
            continue
    # PID 1 remains useful diagnostic context but cannot prove the app runtime
    # sees these bytes when its font-service namespace cannot be inspected.
    return roots


def namespace_current(item: dict) -> bool:
    try:
        root = Path(item['root'])
        if item.get('kind') == 'explicit':
            return (os.environ.get('LUOSHU_VISIBLE_ROOT') is not None
                    and root == Path(os.environ['LUOSHU_VISIBLE_ROOT']).resolve()
                    and identity(root)[:2] == item['identity'])
        proc = root.parent
        return (os.readlink(proc / 'ns/mnt') == item['namespace']
                and (proc / 'stat').read_text().rsplit(')', 1)[1].split()[19] == item['start'])
    except (OSError, KeyError, ValueError, IndexError):
        return False



def reapply_required(module: Path, active: str) -> bool:
    try:
        values = dict(line.split('=', 1) for line in
                      (module / 'config/font-payload-rebuild-pending.conf').read_text().splitlines() if '=' in line)
        return (values.get('font', active) == active
                and values.get('reason') != 'coverage-remediate')
    except OSError:
        return False


def prepared_next_boot(module: Path, active: str) -> bool:
    try:
        values = dict(line.split('=', 1) for line in
                      (module / 'config/font-payload-next.conf').read_text().splitlines() if '=' in line)
        return (values.get('state') == 'prepared' and values.get('font') == active
                and (module / '.luoshu-payload-next').is_dir())
    except OSError:
        return False


def pending(active: str, reason: str) -> dict:
    return {'schema': SCHEMA, 'state': 'pending', 'activeFont': active,
            'reason': reason, 'files': {}}


def load_cached_verification(module: Path, payload: Path, active: str) -> dict:
    """Validate cached observations using metadata only; never read font bytes."""
    if reapply_required(module, active):
        return pending(active, 'font-payload-reapply-required')
    if prepared_next_boot(module, active):
        return pending(active, 'prepared-payload-awaiting-reboot')
    try:
        data = json.loads((module / 'config' / RESULT).read_text())
        checksum, files = manifest_data(module, payload)
        if (not isinstance(data, dict) or data.get('schema') != SCHEMA or data.get('activeFont') != active
                or data.get('bootId') != boot_id() or data.get('manifestDigest') != checksum
                or data.get('payloadRoot') != str(payload.resolve())):
            return pending(active, 'verification-cache-identity-changed')
        roots = data.get('namespaces', [])
        if not roots or not all(namespace_current(item) for item in roots):
            return pending(active, 'runtime-namespace-unconfirmed')
        # Validate every old observation, including mismatches. A changed file
        # invalidates stale success and stale failure alike until explicit verify.
        for name, expected in files.items():
            item = data.get('files', {}).get(name, {})
            if (item.get('expectedDigest') != expected
                    or identity(payload / name.lstrip('/')) != item.get('payloadIdentity')):
                return pending(active, 'verification-cache-file-changed')
            for observation in item.get('observations', []):
                current = Path(observation['path'])
                saved = observation.get('identity')
                if saved is None:
                    if observation.get('state') != 'missing':
                        return pending(active, 'runtime-namespace-unconfirmed')
                    if current.exists():
                        return pending(active, 'verification-cache-file-changed')
                elif identity(current) != saved:
                    return pending(active, 'verification-cache-file-changed')
            if len(item.get('observations', [])) != len(roots):
                return pending(active, 'verification-cache-incomplete')
        return data
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return pending(active, 'verification-evidence-unavailable')


def verify(module: Path, payload: Path, active: str) -> dict:
    if reapply_required(module, active):
        return pending(active, 'font-payload-reapply-required')
    if prepared_next_boot(module, active):
        return pending(active, 'prepared-payload-awaiting-reboot')
    result = pending(active, 'runtime-namespace-unconfirmed')
    result.update(bootId=boot_id(), payloadRoot=str(payload.resolve()), time=int(time.time()))
    try:
        checksum, files = manifest_data(module, payload)
    except (OSError, ValueError, TypeError):
        result['reason'] = 'output-manifest-unavailable'
        return result
    roots = runtime_namespaces()
    result.update(manifestDigest=checksum, namespaces=roots)
    cache = {}
    for name, expected in files.items():
        record = {'expectedDigest': expected, 'state': 'unconfirmed', 'observations': []}
        result['files'][name] = record
        source = payload / name.lstrip('/')
        try:
            record['payloadIdentity'] = identity(source)
            record['payloadDigest'] = digest(source, cache)
        except (OSError, ValueError):
            record.update(state='missing', reason='payload-file-unreadable')
            continue
        if record['payloadDigest'] != expected:
            record.update(state='mismatch', reason='payload-digest-mismatch')
        for root in roots:
            visible = Path(root['root']) / name.lstrip('/')
            observation = {'namespace': root['root'], 'path': str(visible), 'state': 'unconfirmed'}
            try:
                observation['identity'] = identity(visible)
                observation['digest'] = digest(visible, cache)
                observation['state'] = 'verified' if observation['digest'] == expected else 'mismatch'
            except FileNotFoundError:
                observation.update(state='missing', identity=None)
            except (OSError, ValueError):
                observation['state'] = 'unconfirmed'
            record['observations'].append(observation)
        if record['state'] in {'missing', 'mismatch'}:
            continue
        states = [row['state'] for row in record['observations']]
        if states and all(value == 'verified' for value in states):
            record.update(state='verified', reason='runtime-visible-digest-match')
        elif 'mismatch' in states:
            record.update(state='mismatch', reason='runtime-visible-digest-mismatch')
        elif 'missing' in states:
            record.update(state='missing', reason='runtime-visible-file-missing')
        else:
            record.update(state='unconfirmed', reason='runtime-namespace-unconfirmed')
    states = [row['state'] for row in result['files'].values()]
    if states and all(value == 'verified' for value in states):
        result.update(state='verified', reason='visible-font-files-match')
    elif any(value in {'mismatch', 'missing'} for value in states):
        result.update(state='failed', reason='visible-font-files-mismatch')
    return result


def save_result(module: Path, result: dict, full: bool) -> None:
    config = module / 'config'
    config.mkdir(parents=True, exist_ok=True)
    if full:
        path = config / RESULT
        temporary = path.with_name(path.name + f'.tmp.{os.getpid()}')
        temporary.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True))
        os.replace(temporary, path)
    record = dict(result, mode='mount-verified' if result['state'] == 'verified' else 'physical-evidence')
    path = config / 'device-font-load-verification.conf'
    temporary = path.with_name(path.name + f'.tmp.{os.getpid()}')
    temporary.write_text(''.join(f'{key}={str(record.get(key, "")).replace(chr(10), " ")}\n'
                                 for key in ('state', 'mode', 'activeFont', 'reason', 'bootId', 'manifestDigest', 'time')))
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', required=True, type=Path)
    parser.add_argument('action', choices=('status', 'verify'))
    args = parser.parse_args()
    try:
        active = (args.module / 'config/active_font.conf').read_text().splitlines()[0].strip() or 'default'
    except (OSError, IndexError):
        active = 'default'
    if active == 'default':
        result = dict(pending(active, 'default-font'), state='not-applicable')
    else:
        payload = args.module / '.luoshu-payload'
        result = (verify(args.module, payload, active) if args.action == 'verify'
                  else load_cached_verification(args.module, payload, active))
    save_result(args.module, result, args.action == 'verify')
    return 0 if result['state'] in {'verified', 'not-applicable'} else 1 if result['state'] == 'failed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
