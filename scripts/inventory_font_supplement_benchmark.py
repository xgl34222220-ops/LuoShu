#!/usr/bin/env python3
"""Reproduce full CJK supplementation using local, unbundled font fixtures.

First:  script --stock Noto.otf --source selected.otf --prepare-source
Then:   script --stock Noto.otf --source selected.otf --output completed.otf
Run preparation separately so its cost does not contaminate supplement RSS.
"""
import argparse
import json
from pathlib import Path
import resource
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'common'))
from fontTools.ttLib import TTFont
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from inventory_font_supplement import supplement, _subset, replacement_codepoints
from font_slot_coverage import preferred_unicode_codepoints
from inventory_font_supplement_test import outline, shape


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stock', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--prepare-source', action='store_true')
    args = parser.parse_args()
    if args.prepare_source:
        if args.source.exists():
            parser.error('preparation will not overwrite an existing source')
        with TTFont(args.stock, recalcBBoxes=False, recalcTimestamp=False) as font:
            _subset(font, replacement_codepoints(preferred_unicode_codepoints(font)))
            if 'CFF ' not in font:
                parser.error('preparation fixture currently expects a static CFF stock')
            glyphs = font.getGlyphSet()
            name = font.getBestCmap()[ord('A')]
            top = font['CFF '].cff[0]
            old = top.CharStrings[name]
            width = font['hmtx'].metrics[name][0]
            pen = T2CharStringPen(width - old.private.nominalWidthX, glyphs, roundTolerance=0)
            glyphs[name].draw(TransformPen(pen, (1, 0, 0, 1, 100, 0)))
            top.CharStrings[name] = pen.getCharString(private=old.private, globalSubrs=old.globalSubrs)
            font.save(args.source)
        return
    if args.output is None:
        parser.error('--output is required for the timed run')
    started = time.monotonic()
    result = supplement(args.source, args.stock, args.output)
    result.pop('sourceCodepoints', None)
    result['seconds'] = time.monotonic() - started
    result['maxRssKb'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    evidence = {}
    with TTFont(args.stock) as stock, TTFont(args.source) as source, TTFont(args.output) as output:
        for char in 'A中0ΑΩあガ한':
            cp = ord(char)
            if cp not in stock.getBestCmap():
                continue
            donor = source if cp in source.getBestCmap() else stock
            evidence[char] = outline(donor, donor.getBestCmap()[cp]) == outline(output, output.getBestCmap()[cp])
        evidence['AChangedFromStock'] = (outline(stock, stock.getBestCmap()[65])
                                       != outline(output, output.getBestCmap()[65]))
    for text in ['ΑΒΩ', 'あいうえお', 'ガギグ', '한글', '각']:
        evidence[text] = shape(args.stock, text) == shape(args.output, text)
    result['outlineAndShapingEvidence'] = evidence
    if not all(evidence.values()):
        raise AssertionError(evidence)
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    args.output.with_suffix('.benchmark.json').write_text(encoded + '\n')
    print(encoded)


if __name__ == '__main__':
    main()
