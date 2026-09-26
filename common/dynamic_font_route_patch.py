#!/usr/bin/env python3
"""Inventory-authorized dynamic font views; original files stay untouched."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile


def clean_path(value: object) -> Path:
    if not isinstance(value, str) or not value.startswith('/') or value.startswith('//'):
        raise ValueError('dynamic font path is not absolute')
    if any(c in value for c in '\r\n\t|') or any(p in ('', '.', '..') for p in value[1:].split('/')):
        raise ValueError('dynamic font path is not canonical')
    return Path(value)


def route_rows(inventory: dict) -> list[tuple[str, Path, Path]]:
    if inventory.get('schema') != 'device-font-inventory-v1' or inventory.get('state') != 'ready':
        raise ValueError('dynamic routes require a ready stock inventory')
    roots = []
    for key in ('sourceRoots', 'auxiliaryRoots', 'discoveredFontRoots'):
        for root in inventory.get(key, []):
            if isinstance(root, dict):
                roots.append(clean_path(root.get('logical')))
    result, seen = [], set()
    for route in inventory.get('dynamicFontRoutes', []):
        if not isinstance(route, dict):
            continue
        alias, target = clean_path(route.get('alias')), clean_path(route.get('target'))
        if alias in seen or alias.suffix.lower() not in {'.ttf', '.otf', '.ttc', '.otc'}:
            continue
        if not any(alias != root and alias.is_relative_to(root) for root in roots):
            continue
        key = hashlib.sha256(os.fsencode(alias)).hexdigest()[:24]
        result.append((key, alias, target))
        seen.add(alias)
    return result


def authorized_target(module: Path, alias: Path, target: Path) -> None:
    """Trust the measured system alias, never an arbitrary user-selected path.

    A mutable route may legitimately switch directories or become a regular
    file. The alias must still resolve to this file, beneath system-owned data
    directories. Shared storage and app/user-owned directories cannot qualify.
    """
    inventory = json.loads((module / 'config/device_font_inventory.json').read_text())
    if alias not in {row[1] for row in route_rows(inventory)}:
        raise ValueError('font alias is absent from the stock inventory')
    if not alias.is_symlink() or alias.resolve(strict=True) != target:
        raise ValueError('font router changed before validation')
    data = Path(os.environ.get('LUOSHU_DYNAMIC_DATA_ROOT', '/data')).resolve(strict=True)
    if not target.is_relative_to(data) or target == data or target.is_relative_to(module.resolve()):
        raise ValueError('dynamic target is outside system-owned data')
    relative = target.relative_to(data)
    if relative.parts[0] in {'media', 'user', 'user_de', 'data', 'local', 'adb', 'misc_ce', 'misc_de'}:
        raise ValueError('user/app data is not a dynamic system font route')
    if target.is_symlink():
        raise ValueError('dynamic target is not a regular file')
    owners, groups = {0, 1000}, {0, 1000}
    # Non-root fixture runners cannot own Android UID 1000 files. The override
    # affects only an explicitly supplied data root, never the Android default.
    if 'LUOSHU_DYNAMIC_DATA_ROOT' in os.environ and data != Path('/data'):
        owners.add(os.geteuid())
        groups.add(os.getegid())
    current = target
    while current != data:
        info = current.lstat()
        if (info.st_uid not in owners or info.st_mode & stat.S_IWOTH
                or info.st_mode & stat.S_IWGRP and info.st_gid not in groups):
            raise ValueError('dynamic route has an untrusted owner or writable parent')
        if current == target:
            if not stat.S_ISREG(info.st_mode):
                raise ValueError('dynamic target is not a regular file')
        elif not stat.S_ISDIR(info.st_mode):
            raise ValueError('dynamic route contains a non-directory parent')
        current = current.parent


def target_face(target: Path) -> dict:
    from font_inventory import InventoryError, _font_format, _read_metrics, _text_face_reason
    try:
        if _font_format(target) not in {'TTF', 'OTF'}:
            raise ValueError('dynamic collections require a face-preserving builder')
        _fmt, metrics = _read_metrics(target)
    except InventoryError as error:
        raise ValueError(str(error)) from error
    reason = _text_face_reason(metrics)
    if reason:
        raise ValueError('protected dynamic font: ' + reason)
    return {'metrics': metrics, 'weight': metrics['weightClass'],
            'replacementRole': 'digits' if not metrics['fontTraits']['letterScripts'] else 'text'}


def patch(source: Path, target: Path, output: Path, *, stock_face: dict | None = None) -> dict:
    from inventory_font_metrics import contract_for_face, write_metrics
    if output.resolve() in {source.resolve(), target.resolve()}:
        raise ValueError('refusing to replace source or dynamic font')
    face = stock_face if stock_face is not None else target_face(target)
    contract = contract_for_face(face)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.dynamic-view-', dir=output.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        report = write_metrics(source, temporary, contract)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return {'status': 'ok', 'outputBytes': output.stat().st_size, **report}


def build_view(module: Path, alias: Path, target: Path, output: Path) -> dict:
    from inventory_font_stage import SourcePool
    authorized_target(module, alias, target)
    original_stamp = target.stat()
    observed = f'{original_stamp.st_dev}:{original_stamp.st_ino}:{original_stamp.st_size}'
    key = hashlib.sha256(os.fsencode(alias)).hexdigest()[:24]
    route_cache = module / 'config/dynamic-font-routes' / key
    evidence = route_cache / 'stock-face.json'
    journal = route_cache / 'namespaces.conf'
    owned = False
    if journal.is_file():
        owned = any(len(row) == 4 and row[1] == observed and row[3] == str(target)
                    for row in (line.split('|') for line in journal.read_text().splitlines()))
    if owned:
        # A shared namespace can expose our previous view here. Its cmap may
        # contain extra scripts from the old source: that is not stock evidence.
        saved = json.loads(evidence.read_text())
        if saved.get('target') != str(target) or not isinstance(saved.get('face'), dict):
            raise RuntimeError('owned dynamic view has no matching stock contract')
        face = saved['face']
    else:
        face = target_face(target)
    live = module / '.luoshu-payload'
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.dynamic-source-', dir=output.parent) as directory:
        pool = SourcePool(module, live, 'mix', None, Path(directory))
        source, weight, reason = pool.pick(face)
        if source is None:
            raise ValueError(reason)
        try:
            result = patch(pool.materialize(source, weight), target, output, stock_face=face)
            # The framework may rebuild its router while FontTools is working.
            # Never mount a clone aligned against a superseded generation.
            authorized_target(module, alias, target)
            now = target.stat()
            if (original_stamp.st_dev, original_stamp.st_ino, original_stamp.st_size,
                    original_stamp.st_mtime_ns, original_stamp.st_ctime_ns) != (
                    now.st_dev, now.st_ino, now.st_size, now.st_mtime_ns, now.st_ctime_ns):
                raise RuntimeError('dynamic font changed while preparing its view')
            route_cache.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix='.stock-face-', dir=route_cache)
            with os.fdopen(fd, 'w') as stream:
                json.dump({'target': str(target), 'face': face}, stream)
            os.replace(name, evidence)
            return result
        except Exception:
            output.unlink(missing_ok=True)
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path)
    parser.add_argument('--module', type=Path)
    parser.add_argument('--alias', type=Path)
    parser.add_argument('--target', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        if args.inventory:
            for key, alias, target in route_rows(json.loads(args.inventory.read_text())):
                print(f'{key}|{alias}|{target}')
        else:
            if not all((args.module, args.alias, args.target, args.output)):
                parser.error('a view requires module, alias, target and output')
            print(json.dumps(build_view(args.module, args.alias, args.target, args.output)))
        return 0
    except (ValueError, OSError) as error:
        print(json.dumps({'status': 'preserved', 'reason': str(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
