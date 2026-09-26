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
    parser.add_argument('--mode', choices=('direct', 'mix'), default='direct',
                        help='mix treats source as an already composed fixed-weight anchor')
    args = parser.parse_args()
    if args.engine_root:
        sys.path.insert(0, str(args.engine_root))
    import font_inventory
    import inventory_font_stage as engine
    from fontTools.ttLib import TTFont, TTCollection
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
        with args.stock.open('rb') as stream:
            collection = stream.read(4) == b'ttcf'
        options = {'lazy': True, 'recalcBBoxes': False, 'recalcTimestamp': False}
        facts = []
        with TTCollection(args.stock, **options) if collection else TTFont(args.stock, **options) as original:
            for font in original.fonts if collection else [original]:
                char_facts = font_inventory._cmap_metrics(font)
                facts.append((char_facts, ranges(char_facts['points'])))
        for index in range(args.contracts):
            actual = args.fixture / 'stock' / f'contract-{index}'
            actual.mkdir(parents=True)
            extension = '.ttc' if collection else '.otf'
            original = actual / ('text-0' + extension)
            with TTCollection(args.stock, **options) if collection else TTFont(args.stock, **options) as container:
                for font in container.fonts if collection else [container]:
                    font['hhea'].ascent += index
                    font['OS/2'].sTypoAscender += index
                if collection:
                    container.save(original, shareTables=True)
                else:
                    container.save(original, reorderTables=None)
            stock_digest = hashlib.sha256(original.read_bytes()).hexdigest()
            faces = []
            for face_index, (char_facts, char_ranges) in enumerate(facts):
                with TTFont(original, fontNumber=face_index, **options) as font:
                    serialized_facts = {**char_facts, 'cmapSha256': hashlib.sha256(font.reader['cmap']).hexdigest()}
                    fmt, metrics = font_inventory._read_metrics_uncached(original, _font=font, _cmap=serialized_facts)
                evidence = {'sha256': stock_digest, 'cmapSha256': metrics['stockCmapSha256'],
                            'codepointSha256': metrics['stockCodepointSha256'], 'codepointRanges': char_ranges}
                faces.append({'faceIndex': face_index, 'weight': metrics['weightClass'], 'style': 'normal',
                              'metrics': metrics, 'stockSource': evidence, 'families': ['sans-serif']})
            logical_root = f'/system/fonts/contract-{index}'
            roots.append({'partition': 'system', 'logical': logical_root, 'actual': str(actual)})
            for alias in range(args.aliases):
                path = actual / (f'text-{alias}' + extension)
                if alias:
                    os.link(original, path)
                logical = logical_root + '/' + path.name
                slots[logical] = {'format': 'TTC' if collection else fmt, **faces[0]}
                if collection:
                    slots[logical]['faces'] = faces
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
                result = None
                try:
                    result = original(*args, **kwargs)
                    return result
                finally:
                    seconds = time.monotonic() - started
                    value = timings.setdefault(label, {'calls': 0, 'seconds': 0.0})
                    value['calls'] += 1
                    value['seconds'] += seconds
                    if label == 'supplement' and isinstance(result, dict):
                        details = {key: result.get(key) for key in ('glyphCount', 'preparedSourceCacheHit',
                            'outlineSourceCacheHit', 'convertedSourceGlyphs', 'selectedVariantFallbacks')}
                        details.update(seconds=seconds, stockFaceIndex=kwargs.get('stock_face_index'))
                        cache = kwargs.get('prepared_cache') or {}
                        details.update(preparedCacheBytes=sum(len(item[0]) for item in cache.get('entries', {}).values()),
                            outlineCacheBytes=sum(item['size'] for item in cache.get('outline_entries', {}).values()))
                        value.setdefault('faces', []).append(details)
                        print(json.dumps({'supplement': details}), flush=True)
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
    if args.mode == 'mix':
        store = stage / 'system/fonts/.luoshu-font-store'
        store.mkdir(parents=True)
        anchor = store / 'mix-composite.font'
        shutil.copyfile(source, anchor)
        with TTFont(source, lazy=True) as font:
            weight = int(font['OS/2'].usWeightClass)
        (store / '.luoshu-mix-source-weights.json').write_text(json.dumps({
            'schema': 'luoshu-mix-source-weights-v1', 'sources': {'mix-composite.font': {
                **{role + 'Weight': weight for role in ('cjk', 'latin', 'digit')},
                **{role + 'Mode': 'fixed' for role in ('cjk', 'latin', 'digit')},
                'digest': hashlib.sha256(anchor.read_bytes()).hexdigest()}}}))
    started = time.monotonic()
    summary = engine.run(module, stage, args.mode, source if args.mode == 'direct' else None)
    seconds = time.monotonic() - started
    max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    manifest = json.loads((stage / '.luoshu-inventory-output-manifest.json').read_text())
    outputs, details_cache = {}, {}
    for logical in sorted(manifest['files']):
        output = stage / logical[1:]
        key = engine.identity(output)
        if key not in details_cache:
            with output.open('rb') as stream:
                collection = stream.read(4) == b'ttcf'
            with TTCollection(output, lazy=True) if collection else TTFont(output, lazy=True) as container:
                faces = container.fonts if collection else [container]
                cff_tables = {(font.reader.tables['CFF '].offset, font.reader.tables['CFF '].length)
                              for font in faces if 'CFF ' in font}
                details_cache[key] = {'bytes': output.stat().st_size,
                    'faces': len(faces), 'glyphCounts': [font['maxp'].numGlyphs for font in faces],
                    'uniqueCffTables': len(cff_tables),
                    'uniqueCffBytes': sum(length for _offset, length in cff_tables)}
        outputs[logical] = details_cache[key]
    report = {'seconds': seconds, 'maxRssKb': max_rss, 'summary': summary,
              'outputHashes': manifest['files'], 'outputDetails': outputs,
              'uniqueOutputBytes': sum(row['bytes'] for row in details_cache.values()), 'phases': timings}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({key: value for key, value in report.items() if key != 'outputHashes'}, indent=2))


if __name__ == '__main__':
    main()
