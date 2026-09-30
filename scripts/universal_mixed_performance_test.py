#!/usr/bin/env python3
"""Synthetic CJK regression for lazy read-only compiler probes.

The default is a small correctness test. For a bounded host-only benchmark:
  python3 scripts/universal_mixed_performance_test.py --han 20000 --contours 16 --slots 20
No proprietary fonts, Android performance claims, or timing pass/fail thresholds.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import resource
import shutil
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'common'), str(ROOT / 'scripts')]
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
import device_font_template_base as template
import font_coverage
import font_source_profile
import minimal_xml_router
import universal_font_compiler as compiler
import universal_font_compiler_test as fixture
import universal_font_plan


def make_cjk_font(path: Path, han: int, contours: int) -> int:
    """Make independent multi-contour glyphs, including real coverage probes."""
    han_points = (list(range(0x4E00, 0xA000)) + list(range(0x3400, 0x4DC0))
                  + list(range(0x20000, 0x2A6E0)))
    points = set(range(0x20, 0x7F)) | set(han_points[:han]) | set(font_coverage.CJK_COMMON)
    for group in template.PROBE_GROUPS.values():
        points.update(group)
    cmap = {cp: f'u{cp:05X}' for cp in sorted(points)}
    order = ['.notdef', *cmap.values()]
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(order)
    builder.setupCharacterMap(cmap)
    glyphs = {}
    for index, name in enumerate(order):
        pen = TTGlyphPen(None)
        if index:
            for contour in range(contours):
                if contour == 0:
                    x, y, width, height = 40, -120, 530, 840
                else:
                    x = 55 + (contour % 8) * 58
                    y = -95 + (contour // 8) * 150
                    width, height = 35 + index % 7, 80 + index % 13
                pen.moveTo((x, y))
                pen.lineTo((x + width, y))
                pen.lineTo((x + width, y + height))
                pen.lineTo((x, y + height))
                pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (620, 40) for name in order})
    builder.setupHorizontalHeader(ascent=900, descent=-220)
    builder.setupOS2(usWeightClass=400, sTypoAscender=900, sTypoDescender=-220,
                     sTypoLineGap=0, usWinAscent=900, usWinDescent=220)
    builder.setupNameTable(dict(familyName='Synthetic LuoShu CJK', styleName='Regular',
                               fullName='Synthetic LuoShu CJK', psName='SyntheticLuoShuCJK-Regular'))
    builder.setupPost()
    builder.setupMaxp()
    builder.save(path)
    return len(order)


@contextmanager
def probe_open_mode(force_eager: bool):
    """Restore the previous eager behavior only inside the two probe readers."""
    original_open = compiler._open_face
    originals = {name: getattr(compiler, name)
                 for name in ('_stock_geometry_font', '_validate_output_face')}
    active = []
    calls = []

    def opened(path, face_index, *, lazy=False):
        if active:
            calls.append((active[-1], lazy))
            if force_eager:
                lazy = False
        return original_open(path, face_index, lazy=lazy)

    def wrap(name, original):
        def reader(*args, **kwargs):
            active.append(name)
            try:
                return original(*args, **kwargs)
            finally:
                active.pop()
        return reader

    compiler._open_face = opened
    for name, original in originals.items():
        setattr(compiler, name, wrap(name, original))
    try:
        yield calls
    finally:
        compiler._open_face = original_open
        for name, original in originals.items():
            setattr(compiler, name, original)


def run(root: Path, han: int, contours: int, slot_count: int) -> dict:
    source = root / 'source.ttf'
    glyph_count = make_cjk_font(source, han, contours)
    stock = root / 'stock.ttf'
    shutil.copyfile(source, stock)
    paths = [f'/system/fonts/Ui{index:03d}-Regular.ttf' for index in range(slot_count)]
    stocks = {path: stock for path in paths}
    topology = dict(schema='device-font-topology-v1', topologyRevision=2, state='ready',
                    buildKey='lazy-probe-test', romKind='hyperos', summary={}, families={},
                    xmlAliases=[], unresolvedXmlRefs=[], runtime={}, slots={
                        path: fixture.slot_from_stock(path, stock, family='sans-serif',
                                                      source_xml=None, declared=Path(path).name)
                        for path in paths})
    roles = dict(schema='device-font-roles-v1', roleRevision=1, state='ready',
                 buildKey='lazy-probe-test', romKind='hyperos',
                 slots={path: fixture.role_map('ui-sans') for path in paths})
    profile = font_source_profile.build([source])
    plan = universal_font_plan.build_plan(topology, roles, profile)
    route = minimal_xml_router.build_route_plan(plan, {}, None, False)
    results, durations = {}, {}
    for mode in ('eager', 'lazy'):
        started = time.monotonic()
        with probe_open_mode(force_eager=mode == 'eager') as calls:
            results[mode] = compiler.compile_all(plan, route, stocks, root / mode, False)
        durations[mode] = round(time.monotonic() - started, 4)
        fixture.assert_ready(results[mode])
        assert len(calls) == slot_count * 2, calls
        # Enforce the actual callsite choice, not merely a fast elapsed time.
        assert all(lazy is True for _, lazy in calls), calls
    eager, lazy = results['eager'], results['lazy']
    assert eager['summary'] == lazy['summary']
    assert eager['manifestId'] == lazy['manifestId']
    for left, right in zip(eager['artifacts'], lazy['artifacts']):
        assert left['sha256'] == right['sha256'], left['targetPath']
        assert left['report'] == right['report'], left['targetPath']
        assert Path(left['output']).read_bytes() == Path(right['output']).read_bytes()
    return dict(status='PASS',glyphs=glyph_count, pointsPerGlyph=contours * 4,
                sourceBytes=source.stat().st_size, slots=slot_count, seconds=durations,
                processPeakRssMiB=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
                outputHashesEqual=True, reportsEqual=True,
                scope='synthetic static physical TTF slots; host-only measurement')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--han', type=int, default=6000)
    parser.add_argument('--contours', type=int, default=8)
    parser.add_argument('--slots', type=int, default=2)
    args = parser.parse_args()
    if not 6000 <= args.han <= 30000 or not 1 <= args.contours <= 32 or not 1 <= args.slots <= 50:
        parser.error('supported bounds: 6000–30000 Han, 1–32 contours, 1–50 slots')
    # A reproducible developer test must not consume unbounded RAM or CPU.
    resource.setrlimit(resource.RLIMIT_AS, (1536 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (900, 910))
    with tempfile.TemporaryDirectory(prefix='luoshu-lazy-probe-') as raw:
        print(json.dumps(run(Path(raw), args.han, args.contours, args.slots), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
