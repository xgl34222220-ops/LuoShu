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

from fontTools.ttLib import TTCollection, TTFont
from font_inventory import (FONT_EXTENSIONS, FontRoot, _heuristic_candidate,
                            _pick_actual_root, _stock_font_path)
from font_inventory_scan import _is_ui_family
from hyperos_metrics_batch import (bitmap_bottom_slot, contract_for_slot, link_copy,
                                  read_inventory, write_metrics, compact_routed_source,
                                  _cjk_routing, prepare_cjk_routing, cjk_routing_report,
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


def trusted_stock_roots(module: Path, stage: Path, roots: dict[str, Path]) -> list[FontRoot]:
    """Select scanner lower/mirror or explicit stock views, never a live alias."""
    selected = []
    excluded = (module.resolve(), stage.resolve())
    live_roots = {root.resolve() for root in roots.values()}
    for partition, logical in roots.items():
        explicit = os.environ.get(f'LUOSHU_{partition.upper()}_FONTS_ROOT')
        try:
            actual = _pick_actual_root(logical, Path(explicit) if explicit else None, True)
            physical = actual.resolve(strict=True)
            if (not physical.is_dir() or physical in live_roots or
                    any(physical == root or root in physical.parents for root in excluded)):
                continue
        except (OSError, RuntimeError):
            continue
        selected.append(FontRoot(partition, logical, actual))
    return selected


def collection_structure(path: Path, cache: dict) -> tuple[int, bool, str | None]:
    """Read each distinct SFNT once; check all face directories and core tables.

    This is a structural/index check, not glyph coverage or Android load proof.
    Outline table extents are checked without drawing or scanning every glyph.
    """
    stat = path.stat()
    key = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
    if key in cache:
        return cache[key]
    fonts = []
    count, is_collection = 0, False
    try:
        with path.open('rb') as stream:
            is_collection = stream.read(4) == b'ttcf'
            stream.seek(0)
            if is_collection:
                fonts = TTCollection(stream, lazy=True,
                                     recalcTimestamp=False).fonts
            else:
                fonts = [TTFont(stream, lazy=True, recalcTimestamp=False)]
            count = len(fonts)
            if not count:
                raise ValueError('empty-collection')
            for font in fonts:
                for table in font.reader.tables.values():
                    if not 0 <= table.offset <= table.offset + table.length <= stat.st_size:
                        raise ValueError('invalid-table-extent')
                for tag in ('head', 'maxp', 'hhea', 'OS/2', 'cmap', 'hmtx'):
                    font[tag]
                if (font['head'].magicNumber != 0x5F0F3CF5 or
                        not 16 <= font['head'].unitsPerEm <= 16384):
                    raise ValueError('invalid-sfnt-head')
                glyph_count = font['maxp'].numGlyphs
                if glyph_count < 1 or not 1 <= font['hhea'].numberOfHMetrics <= glyph_count:
                    raise ValueError('invalid-horizontal-metrics')
                if 'glyf' in font:
                    locations = font['loca'].locations
                    if (font['head'].indexToLocFormat not in (0, 1) or
                            len(locations) != glyph_count + 1 or locations[0] != 0 or
                            any(a > b for a, b in zip(locations, locations[1:])) or
                            locations[-1] > font.reader.tables['glyf'].length):
                        raise ValueError('invalid-outline-extent')
                elif 'CFF ' in font or 'CFF2' in font:
                    tag = 'CFF ' if 'CFF ' in font else 'CFF2'
                    if len(font[tag].cff.topDictIndex[0].CharStrings.charStrings) != glyph_count:
                        raise ValueError('invalid-charstring-count')
                else:
                    raise ValueError('missing-outline-table')
        result = (count, is_collection, None)
    except Exception as error:
        result = (count, is_collection, type(error).__name__)
    finally:
        for font in fonts:
            font.close()
    cache[key] = result
    return result


def stock_collection_contract(logical: str, slot: dict, selected: list[FontRoot],
                              cache: dict) -> tuple[int, bool]:
    """Resolve within trusted scanner views before accepting any staged TTC."""
    path = Path(logical)
    root = next((root for root in selected if root.logical == path.parent), None)
    if root is None:
        raise ValueError(f'原厂字体集合没有可信 lower/mirror 目录：{logical}')
    try:
        stock = _stock_font_path(root, root.actual / path.name, selected)
        count, collection, error = collection_structure(stock, cache)
    except (OSError, RuntimeError) as error:
        raise ValueError(f'原厂字体集合无法读取：{logical}') from error
    if error is not None:
        raise ValueError(f'原厂字体集合结构无效：{logical} ({error})')
    index = slot.get('faceIndex', 0)
    if type(index) is not int or not 0 <= index < count:
        raise ValueError(f'原厂字体索引超出实际 face 范围：{logical}')
    declared = slot.get('format')
    if ((declared in {'TTC', 'OTC'} and not collection) or
            (declared in {'TTF', 'OTF'} and collection)):
        raise ValueError(f'原厂字体集合与清单格式不一致：{logical}')
    return count, collection


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
    stock_roots = None
    structure_cache = {}
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
            face_index = slot.get('faceIndex', 0)
            stock_collection = (slot.get('format') in {'TTC', 'OTC'} or
                                type(face_index) is not int or face_index != 0)
            contract = contract_for_slot(inventory, logical)
            if contract[-1] != 'stock' and not stock_collection:
                report['reason'] = 'invalid-stock-metrics'
                continue
            with source.open('rb') as stream:
                signature = stream.read(4)
            if signature == b'ttcf' or stock_collection:
                if stock_roots is None:
                    stock_roots = trusted_stock_roots(module, stage, roots)
                stock_count, stock_is_collection = stock_collection_contract(
                    logical, slot, stock_roots, structure_cache)
                staged_count, staged_collection, staged_error = (1, False, None)
                if signature == b'ttcf':
                    staged_count, staged_collection, staged_error = collection_structure(
                        source, structure_cache)
                report.update({'stockFaceCount': stock_count,
                               'stockFaceIndex': slot.get('faceIndex', 0),
                               'stagedFaceCount': staged_count,
                               'collectionProof': 'all-face-sfnt-structure'})
                if (staged_error is None and staged_count == stock_count and
                        staged_collection == stock_is_collection):
                    report['reason'] = 'collection-metrics-preserved'
                else:
                    # Only remove the isolated alias after all jobs succeed.
                    # `seen` prevents completion from recreating it. Stock bytes
                    # and XML are untouched; this does not prove coverage.
                    report['reason'] = 'stock-collection-slot-preserved'
                    report['collectionMismatch'] = staged_error or 'face-count-or-container'
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

    outputs = Path(tempfile.mkdtemp(prefix='.coloros-metrics-', dir=stage))
    cache = {}
    cached_reports = {}
    compact_sources = {}
    prepared = []
    try:
        cjk_fallback, fallback_outputs, routing_evidence = prepare_cjk_routing(
            inventory, [job[:3] for job in jobs], stage, outputs, writer=write_metrics)
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
            if key not in cache and destination in fallback_outputs:
                cache[key], cached_reports[key] = fallback_outputs[destination]
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
                           **cjk_routing_report(report['slot'], routing_reason, routing_evidence),
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
