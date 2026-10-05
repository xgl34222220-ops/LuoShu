#!/usr/bin/env python3
"""Keep a routed HyperOS theme font's layout contract with the active glyphs.

This is a single consumer view, never an edit to the user's theme font. Unlike
Google Sans provider fonts, theme fonts can be the primary CJK family too.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import tempfile

from fontTools.ttLib import TTFont
from hyperos_metrics_batch import contract_for_slot, write_metrics


@contextmanager
def _temporary_output(directory: Path):
    # Defer cancellation only across the create/record and unlink windows, so
    # every created file has an owner before the CLI signal handler can unwind.
    cancellation = {signal.SIGTERM, signal.SIGHUP, signal.SIGINT}
    previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, cancellation)
    fd = None
    temporary = None
    try:
        fd, name = tempfile.mkstemp(prefix='.theme-view-', dir=directory)
        temporary = Path(name)
        os.close(fd)
        fd = None
        signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
        yield temporary
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK, cancellation)
        try:
            if fd is not None:
                os.close(fd)
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)


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
    with _temporary_output(output.parent) as temporary:
        report = write_metrics(source, temporary, contract)
        os.replace(temporary, output)
    return {'status': 'ok', 'outputBytes': output.stat().st_size, **report}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--target', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    previous = {}

    def cancelled(number, _frame):
        raise SystemExit(128 + number)

    try:
        for number in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            previous[number] = signal.getsignal(number)
            signal.signal(number, cancelled)
        print(json.dumps(patch(args.source, args.target, args.output)))
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


if __name__ == '__main__':
    main()
