#!/usr/bin/env python3
"""Restore stock ColorOS layout metrics on existing isolated payload aliases.

The legacy mapper chooses the font and weight for each alias. This pass retains
those choices and touches only metrics; it does not add slots or rebuild glyphs.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from font_inventory import FONT_EXTENSIONS, LOGICAL_FONT_ROOTS, _heuristic_candidate
from font_inventory_scan import _is_ui_family
from hyperos_metrics_batch import contract_for_slot, link_copy, read_inventory, write_metrics


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
    for partition, logical_root in LOGICAL_FONT_ROOTS:
        root = stage / partition / 'fonts'
        if not root.is_dir():
            continue
        for source in sorted(root.iterdir()):
            if not source.is_file() or source.suffix.lower() not in FONT_EXTENSIONS:
                continue
            logical = str(logical_root / source.name)
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
            jobs.append((source, contract, report))

    outputs = Path(tempfile.mkdtemp(prefix='.coloros-metrics-', dir=stage))
    cache = {}
    cached_reports = {}
    prepared = []
    try:
        # Pin every source/contract result before replacing any hard-linked alias.
        # Reading a later source after an earlier replacement can change its
        # frame or weight, especially when the same basename spans partitions.
        for source, contract, report in jobs:
            stat = source.stat()
            key = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, contract)
            if key not in cache:
                output = outputs / f'{len(cache)}.font'
                cached_reports[key] = write_metrics(source, output, contract)
                cache[key] = output
            prepared.append((cache[key], source))
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
