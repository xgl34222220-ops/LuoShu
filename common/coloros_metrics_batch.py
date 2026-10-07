#!/usr/bin/env python3
"""Restore stock ColorOS layout metrics on existing isolated payload aliases.

The legacy mapper chooses the font and weight for each alias. This pass retains
those choices and completes missing upright text slots from the stock inventory.
Only existing stock files are admitted; glyph outlines and ROM XML stay intact.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from font_inventory import (FONT_EXTENSIONS, LOGICAL_FONT_ROOTS, _generic_font_name_candidate,
                            _generic_text_slot_candidate, _heuristic_candidate)
from font_inventory_scan import _is_ui_family, _safe_dynamic_partition_name
from hyperos_metrics_batch import (bitmap_bottom_slot, contract_for_slot, link_copy,
                                  nonempty, read_inventory, weight_for_name, write_metrics)


def eligible_slot(slot: object, logical: str) -> bool:
    if not isinstance(slot, dict) or slot.get('path', logical) != logical:
        return False
    name = Path(logical).name
    if any(token in name.lower() for token in ('emoji', 'symbol', 'icon', 'math', 'music', 'serif', 'mono')):
        return False
    families = slot.get('families', [])
    return _heuristic_candidate(name) or (
        isinstance(families, list) and any(isinstance(family, str) and _is_ui_family(family) for family in families)
    )


def font_roots(module: Path) -> dict[str, Path]:
    roots = dict(LOGICAL_FONT_ROOTS)
    try:
        partitions = (module / 'config/device_font_partitions.conf').read_text().splitlines()
    except OSError:
        partitions = []
    for partition in partitions:
        if _safe_dynamic_partition_name(partition):
            roots[partition] = Path('/') / partition / 'fonts'
    return roots


def completion_slot(slot: object, logical: str) -> bool:
    """Reuse the scanner's evidence policy, never promote arbitrary filenames."""
    if not isinstance(slot, dict) or slot.get('path', logical) != logical:
        return False
    name = Path(logical).name
    # Collections can have language/face references that a single output cannot
    # preserve. Existing aliases keep the separate collection-preservation path.
    if (Path(name).suffix.lower() not in {'.ttf', '.otf'} or
            slot.get('format') in {'TTC', 'OTC'} or slot.get('faceIndex', 0) != 0 or
            slot.get('style', 'normal') != 'normal' or not _generic_font_name_candidate(name)):
        return False
    return eligible_slot(slot, logical) or (
        slot.get('source') == 'verified-scan' and
        _generic_text_slot_candidate(name, slot.get('metrics', {}))
    )


def completion_source(fonts: Path, slot: dict, name: str) -> Path:
    weight = slot.get('weight', weight_for_name(name))
    if type(weight) is not int or not 1 <= weight <= 1000:
        weight = weight_for_name(name)
    role = {100: 'thin', 200: 'extralight', 300: 'light', 400: 'regular',
            500: 'medium', 600: 'semibold', 700: 'bold', 800: 'extrabold', 900: 'black'}.get(weight)
    store = fonts / '.luoshu-font-store'
    candidates = [store / f'wght-{weight}.font', fonts / f'LuoShu-{weight}.ttf']
    if role:
        candidates.append(store / f'{role}.font')
    candidates.extend((fonts / f'{weight}.ttf', fonts / name,
                       store / 'mix-composite.font', store / 'regular.font'))
    for path in candidates:
        if nonempty(path):
            return path
    raise ValueError(f'没有可用的源字体：{name}')


def write_report(stage: Path, slots: list[dict]) -> None:
    report = stage / '.luoshu-metrics-report.json'
    temporary = report.with_name(report.name + f'.tmp.{os.getpid()}')
    try:
        temporary.write_text(json.dumps({'schema': 'luoshu-slot-metrics-v1',
                                         'romKind': 'coloros', 'slots': slots},
                                        ensure_ascii=False), encoding='utf-8')
        temporary.chmod(0o644)
        os.replace(temporary, report)
    finally:
        temporary.unlink(missing_ok=True)


def build(module: Path, stage: Path) -> dict:
    live = (module / '.luoshu-payload').resolve()
    resolved = stage.resolve()
    if resolved == module.resolve() or resolved == live or live in resolved.parents:
        raise ValueError('拒绝修改本次启动正在使用的字体负载')
    if not stage.is_dir():
        raise ValueError('ColorOS 字体暂存目录不存在')
    inventory = read_inventory(module)
    indexed = inventory.get('slots', {})
    if not isinstance(indexed, dict):
        indexed = {}
    jobs = []
    reports = []
    seen = set()
    roots = font_roots(module)
    for partition, logical_root in roots.items():
        root = stage / partition / 'fonts'
        if not root.is_dir():
            continue
        if root.is_symlink() or resolved not in root.resolve().parents:
            raise ValueError('字体暂存槽位指向隔离目录之外')
        for source in sorted(root.iterdir()):
            if not source.is_file() or source.suffix.lower() not in FONT_EXTENSIONS:
                continue
            logical = str(logical_root / source.name)
            seen.add(logical)
            report = {'slot': logical, 'metricsSource': 'preserved'}
            reports.append(report)
            slot = indexed.get(logical)
            if not eligible_slot(slot, logical):
                report['reason'] = 'missing-or-ineligible-stock-slot'
                continue
            contract = contract_for_slot(inventory, logical)
            if contract[-1] != 'stock':
                report['reason'] = 'invalid-stock-metrics'
                continue
            with source.open('rb') as stream:
                signature = stream.read(4)
            if signature == b'ttcf':
                # A collection may be addressed at a nonzero face index by ROM
                # XML. The single-face writer must not silently discard faces.
                report['reason'] = 'collection-metrics-preserved'
                continue
            jobs.append((source, source, contract, report))

    # The old filename table cannot anticipate OEM renames or partition moves.
    # Complete only current, trusted inventory slots, using their real physical
    # existence and stock metrics rather than another ROM-specific target list.
    for logical, slot in sorted(indexed.items()):
        if not isinstance(logical, str) or logical in seen or not completion_slot(slot, logical):
            continue
        parts = Path(logical).parts
        if (len(parts) != 4 or parts[0] != '/' or parts[2] != 'fonts' or parts[1] not in roots
                or str(Path(logical)) != logical or parts[3] in {'.', '..'}):
            continue
        partition, name = parts[1], parts[3]
        contract = contract_for_slot(inventory, logical)
        if contract[-1] != 'stock':
            continue
        stock_root = Path(os.environ.get(f'LUOSHU_{partition.upper()}_FONTS_ROOT', str(roots[partition])))
        stock = stock_root / name
        if not stock.is_file() or stock.is_symlink():
            continue
        destination = stage / partition / 'fonts' / name
        if resolved not in destination.parent.resolve().parents:
            raise ValueError('字体暂存槽位指向隔离目录之外')
        report = {'slot': logical, 'metricsSource': 'preserved', 'slotSource': 'stock-inventory'}
        reports.append(report)
        jobs.append((completion_source(stage / 'system/fonts', slot, name), destination, contract, report))

    outputs = Path(tempfile.mkdtemp(prefix='.coloros-metrics-', dir=stage))
    cache = {}
    cached_reports = {}
    prepared = []
    try:
        # Pin every source/contract result before replacing any hard-linked alias.
        # Reading a later source after an earlier replacement can change its
        # frame or weight, especially when the same basename spans partitions.
        for source, destination, contract, report in jobs:
            stat = source.stat()
            align_bottom = bitmap_bottom_slot(inventory, report['slot'], contract)
            key = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, contract, align_bottom)
            if key not in cache:
                output = outputs / f'{len(cache)}.font'
                cached_reports[key] = write_metrics(source, output, contract,
                                                   align_bitmap_bottom=align_bottom)
                cache[key] = output
            prepared.append((cache[key], destination))
            report.update({'metricsSource': 'stock', 'referenceUpem': contract[0],
                           'hhea': list(contract[1:4]), 'typo': list(contract[4:7]),
                           'win': list(contract[7:9]), 'useTypoMetrics': contract[9],
                           **cached_reports[key]})
        for output, destination in prepared:
            link_copy(output, destination)
        write_report(stage, reports)
    finally:
        shutil.rmtree(outputs, ignore_errors=True)
    return {'mapped': len(jobs), 'generated': len(cache),
            'preservedSlots': len(reports) - len(jobs)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('module', type=Path)
    parser.add_argument('stage', type=Path)
    args = parser.parse_args()
    try:
        result = build(args.module, args.stage)
        print(json.dumps(result, ensure_ascii=False))
        if result['preservedSlots']:
            print(f"ColorOS：{result['preservedSlots']} 个槽位保留来源度量，详见字体度量报告", file=sys.stderr)
        return 0
    except Exception as error:
        print(f'ColorOS 字体处理失败：{error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
