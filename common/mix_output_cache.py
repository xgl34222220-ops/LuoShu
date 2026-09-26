#!/usr/bin/env python3
"""Reuse verified composite inventory output without reusing request ownership."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import subprocess
import tempfile
import time

SCHEMA = 'luoshu-mix-inventory-cache-v1'
SNAPSHOT = '.luoshu-mix-output-cache-input.json'
STORE = 'system/fonts/.luoshu-font-store'
WEIGHTS = '.luoshu-mix-source-weights.json'
OUTPUT = '.luoshu-inventory-output-manifest.json'
CACHE_MAX_BYTES = 768 * 1024 * 1024
METADATA = (OUTPUT, '.luoshu-metrics-report.json', '.luoshu-metrics-covered.lst',
            '.luoshu-coverage-remediation.conf', '.luoshu-coverage-preserved.tsv',
            '.luoshu-coverage-summary.conf')


class InputsChanged(RuntimeError):
    pass


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path: Path, value) -> None:
    temporary = path.with_name(path.name + f'.tmp.{os.getpid()}')
    temporary.write_text(json.dumps(value, sort_keys=True, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary, path)


def identity(path: Path):
    value = path.stat()
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def digest(path: Path, memo: dict | None = None) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'cache input is not a regular file: {path.name}')
    key = identity(path)
    if memo is not None and key in memo:
        return memo[key]
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    if identity(path) != key:
        raise InputsChanged('字体缓存校验期间文件发生变化')
    result = value.hexdigest()
    if memo is not None:
        memo[key] = result
    return result


def values(path: Path) -> dict:
    return dict(line.split('=', 1) for line in path.read_text().splitlines() if '=' in line)


def current_request(module: Path, stage: Path, request: str) -> None:
    if not request or values(module / 'config/mix-stage-next.conf').get('requestId') != request:
        raise InputsChanged('字体组合任务已被新请求替换')
    if values(stage / '.luoshu-mix-generation.conf').get('requestId') != request:
        raise InputsChanged('组合字体源不属于当前任务')


def safe_path(root: Path, relative: str) -> Path:
    parts = PurePosixPath(relative).parts
    if (not parts or relative.startswith('/') or any(p in ('', '.', '..') for p in relative.split('/'))
            or any(c in relative for c in '\x00\r\n\t')):
        raise ValueError('invalid cached relative path')
    target = root
    for part in parts:
        target /= part
        if target.is_symlink():
            raise ValueError('cached path crosses a symlink')
    return target


def output_path(root: Path, logical: str) -> Path:
    if not isinstance(logical, str) or not logical.startswith('/'):
        raise ValueError('invalid cached system path')
    relative = logical[1:]
    parts = relative.split('/')
    if (len(parts) < 2 or parts[0].startswith('.') or parts[0] in
            {'data', 'storage', 'sdcard', 'proc', 'sys', 'dev', 'mnt', 'apex'}
            or '.luoshu-font-store' in parts):
        raise ValueError('cached output is not a system font')
    return safe_path(root, relative)


def anchors(stage: Path) -> tuple[dict, str]:
    store = safe_path(stage, STORE)
    sources = {path.name: digest(path) for path in sorted(store.glob('*.font'))}
    if not sources:
        raise ValueError('no composite source anchors')
    exact = dict(sources)
    manifest = store / WEIGHTS
    if manifest.exists():
        metadata = read_json(manifest)
        if metadata.get('schema') != 'luoshu-mix-source-weights-v1':
            raise ValueError('invalid source weight manifest')
        exact[WEIGHTS] = digest(manifest)
        # Request identity never changes the resulting glyphs. Keep every other
        # field (including real weights, axes and each composite digest).
        metadata.pop('requestId', None)
        sources[WEIGHTS] = metadata
    exact_digest = hashlib.sha256(json.dumps(exact, sort_keys=True).encode()).hexdigest()
    return sources, exact_digest


def inventory_proof(module: Path) -> str:
    # Match inventory_font_stage.run's output/repair proof exactly. The cache key
    # separately fingerprints the complete installed inventory and route files.
    slots = read_json(module / 'config/device_font_inventory.json')['slots']
    return hashlib.sha256(json.dumps(slots, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def snapshot(module: Path, stage: Path, request: str) -> dict:
    current_request(module, stage, request)
    sources, exact = anchors(stage)
    weights = stage / STORE / WEIGHTS
    if weights.exists() and read_json(weights).get('requestId', '') != request:
        raise InputsChanged('组合字体字重记录不属于当前任务')
    inventory = module / 'config/device_font_inventory.json'
    inventory_data = read_json(inventory)
    if (inventory_data.get('schema') != 'device-font-inventory-v1'
            or inventory_data.get('state') != 'ready' or not inventory_data.get('slots')):
        raise ValueError('invalid installed inventory')
    inputs = {'schema': SCHEMA, 'sources': sources, 'inventory': {}, 'engine': {}}
    for name in ('device_font_inventory.json', 'device_font_partitions.conf', 'device_font_roots.conf'):
        path = module / 'config' / name
        inputs['inventory'][name] = digest(path) if path.exists() else None
    paths = set()
    for base in (module / 'common', module / 'common/legacy_v14_4'):
        for pattern in ('*.py', '*.sh'):
            paths.update(base.glob(pattern))
    paths.update((module / 'common/python/lib').glob('python*/site-packages/fontTools/__init__.py'))
    for path in sorted(paths):
        inputs['engine'][str(path.relative_to(module))] = digest(path)
    key = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
    current_request(module, stage, request)
    return {'schema': SCHEMA, 'requestId': request, 'key': key, 'anchors': exact}


def unchanged(module: Path, stage: Path, request: str, pinned: dict) -> None:
    if snapshot(module, stage, request) != pinned:
        raise InputsChanged('生成期间字体源、字重记录、系统清单或生成组件发生变化，已取消本次应用')


def link_copy(source: str | Path, target: str | Path) -> str:
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)
    return str(target)


def progress(done: int, total: int, logical: str = '') -> None:
    configured = os.environ.get('LUOSHU_INVENTORY_PROGRESS_FILE', '')
    if not configured:
        return
    try:
        write_json(Path(configured), {'updatedAt': time.time(), 'completed': done,
            'total': total, 'fileCompleted': done, 'fileTotal': total,
            'phase': 'cache', 'path': logical})
    except OSError:
        pass


def verify_outputs(stage: Path, *, report_progress: bool = True) -> tuple[dict, dict]:
    manifest = read_json(stage / OUTPUT)
    if manifest.get('schema') != 'inventory-font-output-v1' or manifest.get('mode') != 'mix':
        raise ValueError('invalid output manifest')
    files = manifest.get('files')
    if not isinstance(files, dict) or not files:
        raise ValueError('empty generated output')
    hashes, memo = {}, {}
    for number, (logical, expected) in enumerate(files.items()):
        if report_progress:
            progress(number, len(files), logical)
        path = output_path(stage, logical)
        actual = digest(path, memo)
        if actual != expected:
            raise ValueError('cached generated font content changed')
        hashes[logical[1:]] = actual
    if report_progress:
        progress(len(files), len(files))
    covered = set((stage / '.luoshu-metrics-covered.lst').read_text().splitlines())
    if covered != set(files):
        raise ValueError('coverage list does not match generated output')
    for name in METADATA:
        if (stage / name).exists():
            hashes[name] = digest(stage / name, memo)
    return manifest, hashes


def tree_bytes(tree: Path) -> int:
    seen = set()
    size = 0
    for file in tree.rglob('*'):
        if file.is_file() and not file.is_symlink():
            data = file.stat()
            inode = (data.st_dev, data.st_ino)
            if inode not in seen:
                seen.add(inode)
                size += data.st_size
    return size


def prune(cache: Path) -> None:
    try:
        entries = sorted((path for path in cache.iterdir() if path.is_dir()
                          and not path.is_symlink() and not path.name.startswith('.')),
                         key=lambda path: path.stat().st_mtime_ns, reverse=True)
        used = kept = 0
        for path in entries:
            size = tree_bytes(path)
            if kept >= 3 or used + size > CACHE_MAX_BYTES:
                shutil.rmtree(path)
            else:
                used += size
                kept += 1
    except OSError:
        pass


def clean_unmapped(stage: Path, inventory: dict, mapped: set[str]) -> None:
    # Match full-inventory generation's cleanup, including extensionless files
    # under scanner-declared roots. Never remove this request's source anchors.
    old = {}
    try:
        old = read_json(stage / OUTPUT).get('files', {})
    except (OSError, ValueError):
        pass
    for logical in set(inventory['slots']) | set(old):
        if logical not in mapped:
            output_path(stage, logical).unlink(missing_ok=True)
    roots = {root / 'fonts' for root in stage.iterdir()
             if root.is_dir() and not root.is_symlink() and not root.name.startswith('.')}
    for field in ('sourceRoots', 'auxiliaryRoots', 'discoveredFontRoots'):
        for item in inventory.get(field, []):
            if isinstance(item, dict) and isinstance(item.get('logical'), str):
                roots.add(output_path(stage, item['logical']))
    for root in roots:
        if not root.is_dir() or root.is_symlink():
            continue
        for path in root.rglob('*'):
            if '.luoshu-font-store' in path.parts or not (path.is_file() or path.is_symlink()):
                continue
            logical = '/' + path.relative_to(stage).as_posix()
            font_file = path.suffix.lower() in {'.ttf', '.otf', '.ttc', '.otc'}
            if not font_file and not path.is_symlink():
                with path.open('rb') as stream:
                    font_file = stream.read(4) in (b'\x00\x01\x00\x00', b'OTTO', b'ttcf', b'true')
            if logical not in mapped and font_file:
                path.unlink()


def restore(module: Path, stage: Path, request: str, cache: Path) -> bool:
    pinned = snapshot(module, stage, request)
    write_json(stage / SNAPSHOT, pinned)
    entry = cache / pinned['key']
    if not (entry / 'cache.json').is_file() or entry.is_symlink():
        return False
    pending = None
    backup = stage.with_name(f'.luoshu-mix-cache-backup.{os.getpid()}')
    try:
        index = read_json(entry / 'cache.json')
        if index.get('schema') != SCHEMA or index.get('key') != pinned['key']:
            return False
        tree = safe_path(entry, 'tree')
        # Hash each physical output once, not every hardlinked system alias.
        # Metadata-only stat checks cannot catch same-size in-place font edits.
        manifest, hashes = verify_outputs(tree)
        if hashes != index.get('hashes'):
            return False
        pending = Path(tempfile.mkdtemp(prefix='.luoshu-mix-cache-restore.', dir=module))
        shutil.copytree(stage, pending, dirs_exist_ok=True, symlinks=True, copy_function=link_copy)
        clean_unmapped(pending, read_json(module / 'config/device_font_inventory.json'), set(manifest['files']))
        for relative in hashes:
            destination = safe_path(pending, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.unlink(missing_ok=True)
            link_copy(safe_path(tree, relative), destination)
        # This proof includes the exact current weight manifest, whose requestId
        # intentionally differs from the request that first filled the cache.
        manifest['anchors'] = pinned['anchors']
        write_json(pending / OUTPUT, manifest)
        unchanged(module, stage, request, pinned)
        if backup.exists():
            raise ValueError('restore backup already exists')
        os.rename(stage, backup)
        try:
            os.rename(pending, stage)
        except BaseException:
            os.rename(backup, stage)
            raise
        pending = None
        shutil.rmtree(backup, ignore_errors=True)
        try:
            os.utime(entry, None)
        except OSError:
            pass
        return True
    except InputsChanged:
        raise
    except (OSError, ValueError, KeyError, TypeError):
        # No partially restored stage is exposed on a corrupt/missing entry.
        return False
    finally:
        if pending is not None:
            shutil.rmtree(pending, ignore_errors=True)


def store(module: Path, stage: Path, request: str, cache: Path) -> bool:
    pinned = read_json(stage / SNAPSHOT)
    unchanged(module, stage, request, pinned)
    try:
        manifest, hashes = verify_outputs(stage, report_progress=False)
        if (manifest.get('anchors') != pinned['anchors']
                or manifest.get('inventory') != inventory_proof(module)):
            raise ValueError('generated outputs do not match pinned inputs')
    except (OSError, ValueError) as exc:
        raise InputsChanged('生成字体与校验记录不一致，已取消本次应用') from exc
    cache.mkdir(parents=True, exist_ok=True)
    pending = Path(tempfile.mkdtemp(prefix='.stage.', dir=cache))
    try:
        tree = pending / 'tree'
        tree.mkdir()
        for relative in hashes:
            destination = safe_path(tree, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            link_copy(safe_path(stage, relative), destination)
        write_json(pending / 'cache.json', {'schema': SCHEMA, 'key': pinned['key'], 'hashes': hashes})
        unchanged(module, stage, request, pinned)
        if tree_bytes(pending) > CACHE_MAX_BYTES:
            return False
        entry = cache / pinned['key']
        if entry.exists():
            shutil.rmtree(entry)
        os.rename(pending, entry)
        prune(cache)
        return True
    finally:
        shutil.rmtree(pending, ignore_errors=True)


def reap_abandoned(module: Path, stage: Path, request: str, cache: Path) -> None:
    # Called only inside the router's kernel lock. A missing/invalid stage may
    # need the backup left between restore's two renames: never discard it.
    if stage != module / '.luoshu-mix-stage' or not stage.is_dir() or stage.is_symlink():
        return
    current_request(module, stage, request)
    anchors(stage)  # A metadata-only or damaged stage cannot retire its backup.
    candidates = list(cache.glob('.stage.*')) if cache.is_dir() else []
    for pattern in ('.luoshu-mix-cache-restore.*', '.luoshu-mix-cache-backup.*'):
        candidates.extend(module.glob(pattern))
    for abandoned in candidates:
        try:
            if (abandoned.is_dir() and not abandoned.is_symlink()
                    and abandoned.stat().st_uid == os.geteuid()):
                shutil.rmtree(abandoned, ignore_errors=True)
        except OSError:
            pass


def apply(module: Path, stage: Path, request: str, cache: Path) -> int:
    # Reap cancelled unpublished stores and isolated restore/backup clones only
    # when a valid current request already owns a complete source stage.
    reap_abandoned(module, stage, request, cache)
    helper = module / 'common/inventory_font_stage.sh'
    result = subprocess.call(['sh', str(helper), '--ensure-inventory'])
    if result:
        return result
    try:
        if restore(module, stage, request, cache):
            print('[MIX-CACHE] verified inventory output hit; skipped generation', flush=True)
            (stage / SNAPSHOT).unlink(missing_ok=True)
            return 0
    except InputsChanged:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'[MIX-CACHE] lookup skipped: {exc}', file=sys.stderr, flush=True)
    result = subprocess.call(['sh', str(helper), str(stage), 'mix', 'mix'])
    if result:
        return result
    if (stage / SNAPSHOT).exists():
        # Failure to re-read a pinned input is also a change, never permission to
        # commit output that no longer has the original generation evidence.
        try:
            unchanged(module, stage, request, read_json(stage / SNAPSHOT))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise InputsChanged('无法核验本次生成所用的字体源和系统清单') from exc
        try:
            saved = store(module, stage, request, cache)
            print('[MIX-CACHE] verified inventory output ' + ('stored' if saved else 'exceeds cache budget'), flush=True)
        except InputsChanged:
            raise
        except (OSError, ValueError, KeyError, TypeError) as exc:
            # Out of cache space cannot make a valid isolated generation fail.
            print(f'[MIX-CACHE] store skipped: {exc}', file=sys.stderr, flush=True)
        (stage / SNAPSHOT).unlink(missing_ok=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('apply', 'restore', 'store', 'check'))
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--request', required=True)
    args = parser.parse_args()
    module, stage = args.module.absolute(), args.stage.absolute()
    try:
        if stage != module / '.luoshu-mix-stage' or stage.is_symlink() or not stage.is_dir():
            raise ValueError('untrusted composite stage')
        cache = safe_path(module, 'config/mix-inventory-cache')
        if args.action == 'apply':
            return apply(module, stage, args.request, cache)
        if args.action == 'restore':
            success = restore(module, stage, args.request, cache)
        elif args.action == 'store':
            success = store(module, stage, args.request, cache)
        else:
            unchanged(module, stage, args.request, read_json(stage / SNAPSHOT))
            success = True
        print(json.dumps({'cache': args.action, 'status': 'ok' if success else 'miss'}))
        return 0 if success else 1
    except InputsChanged as exc:
        print(f'通用字体生成失败：{exc}', file=sys.stderr)
        return 3
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'[MIX-CACHE] {args.action} skipped: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
