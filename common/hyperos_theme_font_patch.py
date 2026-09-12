#!/usr/bin/env python3
"""Keep a routed HyperOS theme font's layout contract with the active glyphs.

This is a single consumer view, never an edit to the user's theme font. Unlike
Google Sans provider fonts, theme fonts can be the primary CJK family too.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

from fontTools.ttLib import TTFont
from hyperos_metrics_batch import contract_for_slot, write_metrics


def patch(source: Path, target: Path, output: Path) -> dict:
    if output.resolve() in {source.resolve(), target.resolve()}:
        raise ValueError('refusing to replace source or theme font')
    for path in (source, target):
        with path.open('rb') as stream:
            if stream.read(4) not in (b'\x00\x01\x00\x00', b'OTTO', b'true'):
                raise ValueError('theme view requires a single-face font')
    with TTFont(target, lazy=True, recalcBBoxes=False, recalcTimestamp=False) as font:
        head, hhea, os2 = font['head'], font['hhea'], font['OS/2']
        metrics = {
            'upem': int(head.unitsPerEm),
            'head': {'yMin': int(head.yMin), 'yMax': int(head.yMax)},
            'hhea': {'ascent': int(hhea.ascent), 'descent': int(hhea.descent),
                     'lineGap': int(hhea.lineGap)},
            'os2': {'typoAscender': int(os2.sTypoAscender),
                    'typoDescender': int(os2.sTypoDescender),
                    'typoLineGap': int(os2.sTypoLineGap),
                    'winAscent': int(os2.usWinAscent), 'winDescent': int(os2.usWinDescent),
                    'fsSelection': int(os2.fsSelection)},
        }
    contract = contract_for_slot({'slots': {'theme': {'metrics': metrics}}}, 'theme')
    if contract[-1] != 'stock' or contract[10] is None:
        raise ValueError('invalid current theme layout contract')
    with TTFont(source, lazy=True, recalcBBoxes=False, recalcTimestamp=False) as font:
        if not set(range(48, 58)) <= set(font.getBestCmap() or {}):
            raise ValueError('active source has no complete decimal digits')
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.theme-view-', dir=output.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        report = write_metrics(source, temporary, contract)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return {'status': 'ok', 'outputBytes': output.stat().st_size, **report}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--target', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(patch(args.source, args.target, args.output)))


if __name__ == '__main__':
    main()
