#!/usr/bin/env python3
"""Inventory-authorized dynamic font views; original files stay untouched."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile

from fontTools.ttLib import TTFont, TTLibError
from font_slot_coverage import preferred_unicode_codepoints, unicode_codepoints
from inventory_stock_source import StockFont, file_digest, file_identity


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


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def _target_is_owned(route_cache: Path, target: Path) -> bool:
    observed = ':'.join(map(str, file_identity(target)[:3]))
    journal = route_cache / 'namespaces.conf'
    if journal.is_file():
        if any(len(row) == 4 and row[1] == observed and row[3] == str(target)
               for row in (line.split('|') for line in journal.read_text().splitlines())):
            return True
    # A failed/lost journal must not turn one of our cached views into stock.
    for clone in route_cache.glob('*.ttf'):
        if clone.is_file() and ':'.join(map(str, file_identity(clone)[:3])) == observed:
            return True
    # A file mount without ownership evidence cannot certify original bytes.
    # This also covers a lost journal whose unlinked clone still has a bind.
    mountinfo = Path(os.environ.get('LUOSHU_MOUNTINFO', '/proc/self/mountinfo'))
    for line in mountinfo.read_text().splitlines():
        fields = line.split()
        if len(fields) > 5:
            mountpoint = re.sub(r'\\([0-7]{3})', lambda match: chr(int(match[1], 8)), fields[4])
            if mountpoint == str(target):
                raise ValueError('dynamic font is mounted without verifiable original bytes')
    return False


def _stock_snapshot(route_cache: Path, target: Path, owned: bool) -> tuple[StockFont, dict]:
    """Pin the actual unoverlaid dynamic target, never a generated consumer view.

    Dynamic /data files are outside the read-only inventory resolver's domain.
    Retain their original bytes before our first bind and use the same complete
    file/cmap/identity proofs as StockSourceResolver on subsequent generations.
    """
    evidence = route_cache / 'stock-face.json'
    if owned:
        saved = json.loads(evidence.read_text())
        digest = str(saved.get('sha256', '')) if isinstance(saved, dict) else ''
        if (not isinstance(saved, dict) or saved.get('schema') != 'dynamic-font-stock-v1'
                or saved.get('target') != str(target) or not isinstance(saved.get('face'), dict)
                or not isinstance(saved['face'].get('metrics'), dict) or not re.fullmatch('[0-9a-f]{64}', digest)):
            raise ValueError('owned dynamic view has no verified original font snapshot; preserving current route')
        snapshot = route_cache / f'stock-{digest}.font'
        stamp = file_identity(snapshot)
        if snapshot.is_symlink() or not snapshot.is_file() or file_digest(snapshot) != digest:
            raise ValueError('original dynamic font snapshot is missing or changed; preserving current route')
        face = saved['face']
    else:
        route_cache.mkdir(parents=True, exist_ok=True)
        before = file_identity(target)
        fd, name = tempfile.mkstemp(prefix='.stock-font-', dir=route_cache)
        os.close(fd)
        temporary = Path(name)
        try:
            shutil.copyfile(target, temporary)
            if file_identity(target) != before:
                raise ValueError('dynamic font changed while saving its original bytes')
            face = target_face(temporary)
            digest = file_digest(temporary)
            snapshot = route_cache / f'stock-{digest}.font'
            os.chmod(temporary, 0o400)
            os.replace(temporary, snapshot)
            stamp = file_identity(snapshot)
            _atomic_json(evidence, {'schema': 'dynamic-font-stock-v1', 'target': str(target),
                                   'sha256': digest, 'face': face})
            for stale in route_cache.glob('stock-*.font'):
                if stale != snapshot:
                    stale.unlink(missing_ok=True)
        finally:
            temporary.unlink(missing_ok=True)
    # Metrics-only legacy records cannot prove stock glyph bytes. Even a valid
    # hash is checked against the saved metric contract before supplementation.
    from inventory_stock_source import StockSourceResolver
    StockSourceResolver._check_metrics(face['metrics'], target_face(snapshot)['metrics'])
    with TTFont(snapshot, lazy=True, recalcTimestamp=False) as font:
        points = frozenset(unicode_codepoints(font))
        cmap_digest = hashlib.sha256(font.reader['cmap']).hexdigest()
    stock = StockFont(snapshot, 0, digest, cmap_digest, points, 'dynamic-stock-snapshot', stamp)
    stock.verify_unchanged()
    return stock, face


def _build_view(module: Path, alias: Path, target: Path, output: Path, route_cache: Path) -> dict:
    from inventory_font_stage import SourcePool, replacement_points, replacement_counts
    from inventory_font_supplement import supplement
    from inventory_font_metrics import restrict_unicode_scope
    authorized_target(module, alias, target)
    if output.resolve() == target.resolve():
        raise ValueError('refusing to replace original dynamic font')
    original_stamp = file_identity(target)
    stock, face = _stock_snapshot(route_cache, target, _target_is_owned(route_cache, target))
    live = module / '.luoshu-payload'
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.dynamic-source-', dir=output.parent) as directory:
        pool = SourcePool(module, live, 'mix', None, Path(directory))
        face['_stockPoints'] = stock.codepoints
        source, weight, reason = pool.pick(face)
        if source is None:
            raise ValueError(reason)
        try:
            points = replacement_points(source.points, stock.codepoints, face['_replacementRoles'])
            if not points:
                raise ValueError('selected source supplies no requested dynamic text glyphs')
            anchor = pool.materialize(source, weight)
            retained = stock.codepoints - points
            def variants(path):
                with TTFont(path, lazy=True, recalcTimestamp=False) as font:
                    return {(selector, cp) for table in font['cmap'].tables if table.format == 14
                            for selector, entries in table.uvsDict.items() for cp, _glyph in entries}
            missing_variants = variants(stock.path) - variants(anchor)
            needs_supplement = bool(retained or missing_variants)
            detail = {'replacedCodepoints': len(points), 'retainedStockCodepoints': len(retained),
                      'supplemented': needs_supplement, 'roles': replacement_counts(points)}
            if needs_supplement:
                supplemented = Path(directory) / 'supplemented.font'
                detail.update(supplement(anchor, stock.path, supplemented,
                                         stock_face_index=stock.face_index, stock_weight=weight,
                                         replace_codepoints=set(points)))
                anchor = supplemented
            elif source.points - stock.codepoints:
                # A larger donor must not steal scripts routed to other system
                # fonts. Restrict cmap only; retain its original outline bytes.
                anchor = restrict_unicode_scope(anchor, Path(directory) / 'scoped.font', stock.codepoints)
            stock.verify_unchanged()
            result = patch(anchor, target, output, stock_face=face)
            with TTFont(output, lazy=True, recalcTimestamp=False) as font:
                if stock.codepoints != frozenset(preferred_unicode_codepoints(font)):
                    raise ValueError('dynamic view would change the original character scope')
            result.update(detail)
            result.update({'stockSha256': stock.digest, 'stockVerifiedBy': stock.verified_by,
                           'alias': str(alias), 'target': str(target)})
            # The framework may rebuild its router while FontTools is working.
            # Never mount a clone aligned against a superseded generation.
            authorized_target(module, alias, target)
            if original_stamp != file_identity(target):
                raise RuntimeError('dynamic font changed while preparing its view')
            stock.verify_unchanged()
            return result
        except Exception:
            output.unlink(missing_ok=True)
            raise


def build_view(module: Path, alias: Path, target: Path, output: Path) -> dict:
    key = hashlib.sha256(os.fsencode(alias)).hexdigest()[:24]
    route_cache = module / 'config/dynamic-font-routes' / key
    try:
        result = _build_view(module, alias, target, output, route_cache)
    except (ValueError, OSError, RuntimeError, TTLibError) as error:
        _atomic_json(route_cache / 'result.json', {'status': 'preserved', 'replaced': False,
                     'alias': str(alias), 'target': str(target), 'reason': str(error)})
        raise
    _atomic_json(route_cache / 'result.json', result)
    return result


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
    except (ValueError, OSError, RuntimeError, TTLibError) as error:
        print(json.dumps({'status': 'preserved', 'reason': str(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
