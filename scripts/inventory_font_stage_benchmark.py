#!/usr/bin/env python3
"""Benchmark complete inventory mapping using externally supplied real fonts.

Preparation is separate from timed mapping. No font binaries are bundled.
Use --engine-root with an isolated previous revision of stage/source/helper
to compare the same inventory and input. Output font hashes prove equivalence.
"""
from __future__ import annotations
import argparse
import functools
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'common'))


def ranges(points):
    result = []
    for point in sorted(points):
        if result and point == result[-1][1] + 1:
            result[-1][1] = point
        else:
            result.append([point, point])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--stock', type=Path)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--contracts', type=int, default=24)
    parser.add_argument('--aliases', type=int, default=6)
    parser.add_argument('--engine-root', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--profile-phases', action='store_true')
    args = parser.parse_args()
    if args.engine_root:
        sys.path.insert(0, str(args.engine_root))
    import font_inventory
    import inventory_font_stage as engine
    from fontTools.ttLib import TTFont
    os.environ['LUOSHU_BUILD_KEY'] = 'inventory-stage-benchmark'
    module = args.fixture / 'module'
    if args.prepare:
        if not args.stock or not args.source or args.fixture.exists():
            parser.error('preparation requires stock/source and a fresh fixture directory')
        (module / 'config').mkdir(parents=True)
        source = args.fixture / 'source' / args.source.name
        source.parent.mkdir()
        shutil.copyfile(args.source, source)
        slots, roots = {}, []
        with TTFont(args.stock, lazy=True, recalcBBoxes=False, recalcTimestamp=False) as original:
            char_facts = font_inventory._cmap_metrics(original)
            char_ranges = ranges(char_facts['points'])
        for index in range(args.contracts):
            actual = args.fixture / 'stock' / f'contract-{index}'
            actual.mkdir(parents=True)
            original = actual / 'text-0.otf'
            with TTFont(args.stock, lazy=True, recalcBBoxes=False, recalcTimestamp=False) as font:
                font['hhea'].ascent += index
                font['OS/2'].sTypoAscender += index
                font.save(original, reorderTables=None)
            with TTFont(original, lazy=True, recalcTimestamp=False) as font:
                serialized_facts = {**char_facts, 'cmapSha256': hashlib.sha256(font.reader['cmap']).hexdigest()}
                fmt, metrics = font_inventory._read_metrics_uncached(original, _font=font, _cmap=serialized_facts)
            evidence = {'sha256': hashlib.sha256(original.read_bytes()).hexdigest(),
                        'cmapSha256': metrics['stockCmapSha256'],
                        'codepointSha256': metrics['stockCodepointSha256'], 'codepointRanges': char_ranges}
            logical_root = f'/system/fonts/contract-{index}'
            roots.append({'partition': 'system', 'logical': logical_root, 'actual': str(actual)})
            for alias in range(args.aliases):
                path = actual / f'text-{alias}.otf'
                if alias:
                    os.link(original, path)
                logical = logical_root + '/' + path.name
                slots[logical] = {'format': fmt, 'weight': metrics['weightClass'], 'style': 'normal',
                                 'metrics': metrics, 'stockSource': evidence, 'families': ['sans-serif']}
        inventory = {'schema': 'device-font-inventory-v1', 'state': 'ready', 'inventoryRevision': 1,
                     'scannerRevision': 10, 'metricsRevision': 5, 'buildKey': os.environ['LUOSHU_BUILD_KEY'],
                     'slots': slots, 'sourceRoots': roots, 'mainSlotPath': next(iter(slots))}
        (module / 'config/device_font_inventory.json').write_text(json.dumps(inventory))
        (args.fixture / 'source-path.txt').write_text(str(source))
        return
    if args.output is None:
        parser.error('timed run requires --output')
    source = Path((args.fixture / 'source-path.txt').read_text())
    timings = {}
    if args.profile_phases:
        def instrument(owner, name, label):
            original = getattr(owner, name)
            @functools.wraps(original)
            def timed(*args, **kwargs):
                started = time.monotonic()
                try:
                    return original(*args, **kwargs)
                finally:
                    value = timings.setdefault(label, {'calls': 0, 'seconds': 0.0})
                    value['calls'] += 1
                    value['seconds'] += time.monotonic() - started
            setattr(owner, name, timed)
        for name in ('preservation_digest', 'file_digest', 'inspect_faces', 'supplement', 'write_metrics',
                     'replacement_points', 'replacement_counts', 'has_unicode_variations', 'link_copy'):
            instrument(engine, name, name)
        for name in ('__init__', 'pick', 'materialize'):
            instrument(engine.SourcePool, name, 'SourcePool.' + name)
        instrument(engine.StockSourceResolver, 'resolve', 'StockSourceResolver.resolve')
    stage = args.output.with_suffix('.stage')
    if stage.exists():
        parser.error('output stage already exists; use a fresh output basename')
    started = time.monotonic()
    summary = engine.run(module, stage, 'direct', source)
    seconds = time.monotonic() - started
    manifest = json.loads((stage / '.luoshu-inventory-output-manifest.json').read_text())
    report = {'seconds': seconds, 'maxRssKb': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              'summary': summary, 'outputHashes': manifest['files'], 'phases': timings}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({key: value for key, value in report.items() if key != 'outputHashes'}, indent=2))


if __name__ == '__main__':
    main()
