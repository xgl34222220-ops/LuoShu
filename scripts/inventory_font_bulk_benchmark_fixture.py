#!/usr/bin/env python3
"""Prepare a heterogeneous cold-switch benchmark from externally supplied fonts.

This is a synthetic inventory, not a captured device inventory. Font content,
coverage and layout are real; the path aliases and Latin scopes are fixtures.
Run inventory_font_stage_benchmark.py against the resulting directory.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'common'))
from fontTools import subset
from fontTools.ttLib import TTCollection, TTFont
import font_inventory
from inventory_font_stage_benchmark import ranges


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('fixture', 'source', 'stock-cjk', 'stock-text'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--text-paths', type=int, default=80)
    parser.add_argument('--collection-aliases', type=int, default=53)
    parser.add_argument('--faces', type=int, default=5)
    args = parser.parse_args()
    if args.fixture.exists() or min(args.text_paths, args.collection_aliases, args.faces) < 1:
        parser.error('use a fresh fixture and positive counts')
    module = args.fixture / 'module'
    (module / 'config').mkdir(parents=True)
    source = args.fixture / 'source' / args.source.name
    source.parent.mkdir()
    shutil.copyfile(args.source, source)
    stock_dir = args.fixture / 'stock'
    stock_dir.mkdir()
    slots = {}

    def record(path, logical, count=1):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        faces = []
        for index in range(count):
            with TTFont(path, fontNumber=index, lazy=True, recalcTimestamp=False) as font:
                facts = font_inventory._cmap_metrics(font)
                facts['cmapSha256'] = hashlib.sha256(font.reader['cmap']).hexdigest()
                fmt, metrics = font_inventory._read_metrics_uncached(path, _font=font, _cmap=facts)
            faces.append({'faceIndex': index, 'weight': metrics['weightClass'], 'style': 'normal',
                'metrics': metrics, 'families': ['sans-serif'], 'stockSource': {'sha256': digest,
                    'cmapSha256': metrics['stockCmapSha256'],
                    'codepointSha256': metrics['stockCodepointSha256'],
                    'codepointRanges': ranges(facts['points'])}})
        slot = {'format': 'TTC' if count > 1 else fmt, **faces[0]}
        if count > 1:
            slot['faces'] = faces
        slots[logical] = slot
        return slot

    with TTFont(args.stock_text, lazy=True) as font:
        available = set(font.getBestCmap())
    for index in range(args.text_paths):
        # Different real Latin/digit intersections and retained scripts prevent
        # one synthetic font copied 133 times from hiding per-target work.
        latin = set(range(65, 65 + 12 + index % 15)) | set(range(97, 123))
        other = set(range(0x391, 0x391 + 1 + index // 15)) | set(range(0x627, 0x630))
        points = (latin | other | set(range(48, 58)) | {32}) & available
        path = stock_dir / f'00-text-{index:03d}.ttf'
        with TTFont(args.stock_text, recalcTimestamp=False) as font:
            options = subset.Options()
            options.layout_features = ['*']
            options.name_IDs = ['*']
            options.glyph_names = True
            worker = subset.Subsetter(options=options)
            worker.populate(unicodes=points)
            worker.subset(font)
            font.save(path, reorderTables=False)
        record(path, '/system/fonts/' + path.name)
    collection_path = stock_dir / 'NotoSansCJK-000.ttc'
    with TTCollection(args.stock_cjk, lazy=True) as source_collection:
        if len(source_collection.fonts) < args.faces:
            parser.error('stock collection has too few faces')
        target = TTCollection()
        target.fonts = source_collection.fonts[:args.faces]
        target.save(collection_path, shareTables=True)
    logical = '/system/fonts/' + collection_path.name
    collection_slot = record(collection_path, logical, args.faces)
    for index in range(1, args.collection_aliases):
        alias = stock_dir / f'NotoSansCJK-{index:03d}.ttc'
        os.link(collection_path, alias)
        slots['/system/fonts/' + alias.name] = collection_slot
    inventory = {'schema': 'device-font-inventory-v1', 'state': 'ready',
        'inventoryRevision': 1, 'scannerRevision': 10, 'metricsRevision': 5,
        'buildKey': 'inventory-stage-benchmark', 'slots': slots, 'mainSlotPath': logical,
        'sourceRoots': [{'partition': 'system', 'logical': '/system/fonts', 'actual': str(stock_dir)}]}
    (module / 'config/device_font_inventory.json').write_text(json.dumps(inventory))
    (args.fixture / 'source-path.txt').write_text(str(source))
    print(json.dumps({'paths': len(slots), 'textPaths': args.text_paths,
                      'collectionAliases': args.collection_aliases, 'faces': args.faces}))


if __name__ == '__main__':
    main()
