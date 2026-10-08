#!/usr/bin/env python3
"""Restore stock ColorOS layout metrics on existing isolated payload aliases.

The legacy mapper chooses the font and weight for each alias. This pass retains
those choices and completes missing upright text slots from the stock inventory.
Only existing stock files are admitted; retained glyph shapes and ROM XML stay
intact. New CJK mappings in Latin UI use only a proven staged stock fallback.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from font_inventory import FONT_EXTENSIONS, _heuristic_candidate
from font_inventory_scan import _is_ui_family
from hyperos_metrics_batch import (bitmap_bottom_slot, contract_for_slot, link_copy,
                                  read_inventory, write_metrics, compact_routed_source,
                                  _cjk_routing, _staged_cjk_fallback,
                                  inventory_font_roots as font_roots,
                                  inventory_completion_jobs)


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
    descriptor, temporary_name = tempfile.mkstemp(prefix=report.name + '.tmp.', dir=stage)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump({'schema': 'luoshu-slot-metrics-v1',
                       'romKind': 'coloros', 'slots': slots},
                      stream, ensure_ascii=False)
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
    preserved_stock_aliases = []
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
            stock_collection = slot.get('format') in {'TTC', 'OTC'} or slot.get('faceIndex', 0) != 0
            contract = contract_for_slot(inventory, logical)
            if contract[-1] != 'stock' and not stock_collection:
                report['reason'] = 'invalid-stock-metrics'
                continue
            with source.open('rb') as stream:
                signature = stream.read(4)
            if signature == b'ttcf':
                # A collection may be addressed at a nonzero face index by ROM
                # XML. The single-face writer must not silently discard faces.
                report['reason'] = 'collection-metrics-preserved'
                continue
            if stock_collection:
                # The alias already contains the single-face replacement, so
                # its header cannot prove the stock XML's collection/index
                # contract. Remove only this staged alias after all generation
                # succeeds; its absence exposes the untouched stock collection.
                # `seen` also prevents completion from recreating the alias.
                report['reason'] = 'stock-collection-slot-preserved'
                preserved_stock_aliases.append(source)
                continue
            jobs.append((source, source, contract, report))

    # The old filename table cannot anticipate OEM renames or partition moves.
    # Complete only current, trusted inventory slots, using their real physical
    # existence and stock metrics rather than another ROM-specific target list.
    for source, destination, contract in inventory_completion_jobs(module, stage, inventory, seen):
        logical = '/' + destination.relative_to(stage).as_posix()
        report = {'slot': logical, 'metricsSource': 'preserved', 'slotSource': 'stock-inventory'}
        reports.append(report)
        jobs.append((source, destination, contract, report))

    cjk_fallback = _staged_cjk_fallback(inventory, [job[:3] for job in jobs], stage)
    outputs = Path(tempfile.mkdtemp(prefix='.coloros-metrics-', dir=stage))
    cache = {}
    cached_reports = {}
    compact_sources = {}
    prepared = []
    try:
        # Pin every source/contract result before replacing any hard-linked alias.
        # Reading a later source after an earlier replacement can change its
        # frame or weight, especially when the same basename spans partitions.
        for source, destination, contract, report in jobs:
            stat = source.stat()
            routing, stock_punctuation, routing_reason = _cjk_routing(inventory, report['slot'], cjk_fallback)
            align_bottom = bitmap_bottom_slot(inventory, report['slot'], contract)
            source_key = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns,
                          routing, stock_punctuation)
            key = (*source_key, contract, align_bottom)
            if key not in cache:
                output = outputs / f'{len(cache)}.font'
                metric_source, compact_removed = source, 0
                if routing:
                    if source_key not in compact_sources:
                        compact_sources[source_key] = compact_routed_source(
                            source, outputs / f'source-{len(compact_sources)}.font',
                            routing, stock_punctuation)
                    metric_source, compact_removed = compact_sources[source_key]
                cached_reports[key] = write_metrics(metric_source, output, contract,
                                                   cjk_fallback_codepoints=routing,
                                                   stock_cjk_punctuation=stock_punctuation,
                                                   align_bitmap_bottom=align_bottom)
                cached_reports[key]['removedCjkMappings'] += compact_removed
                cache[key] = output
            prepared.append((cache[key], destination))
            report.update({'metricsSource': 'stock', 'referenceUpem': contract[0],
                           'hhea': list(contract[1:4]), 'typo': list(contract[4:7]),
                           'win': list(contract[7:9]), 'useTypoMetrics': contract[9],
                           'cjkRoutingSource': 'stock-fallback' if routing else 'source',
                           'cjkRoutingReason': routing_reason,
                           **cached_reports[key]})
        for output, destination in prepared:
            link_copy(output, destination)
        for alias in preserved_stock_aliases:
            alias.unlink(missing_ok=True)
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
