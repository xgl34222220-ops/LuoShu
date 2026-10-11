#!/usr/bin/env python3
"""Regression: lazy template capture must be byte-identical to the eager path.

The eager reference path is the pre-fix behaviour: every referenced face opened
with TTFont(lazy=False) and the PostScript name index built up front over every
face under the font roots. The lazy path must produce the same JSON bytes, must not
build the name index when every ref declares a file, and must not be slower.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "common"))
import device_font_template as mod  # noqa: E402  (installs script-aware roles)
import device_font_template_base as base  # noqa: E402

from fontTools.fontBuilder import FontBuilder  # noqa: E402
from fontTools.pens.ttGlyphPen import TTGlyphPen  # noqa: E402
from fontTools.ttLib import TTCollection, TTFont  # noqa: E402

PROBE_TEXT = (
    "AHIOXEFMNSTUVWYZBCDGLPQRJKxnoeacmursvkwzgjpqy0123456789"
    ".,;:_!?()[]{}+-=/%<>，。！？；：（）【】《》、—…永国中日田目口回"
)


def build_fixture_font(path: Path, family: str, style: str, scale: int) -> None:
    chars = sorted(set(PROBE_TEXT))
    glyph_order = [".notdef"] + [f"g{ord(ch):04X}" for ch in chars]
    cmap = {ord(ch): f"g{ord(ch):04X}" for ch in chars}
    glyphs = {}
    metrics = {}
    for position, name in enumerate(glyph_order):
        pen = TTGlyphPen(None)
        if name != ".notdef":
            top = 300 + (position * 37 + scale) % 500
            bottom = -((position * 13) % 180) if position % 5 == 0 else 0
            pen.moveTo((50, bottom))
            pen.lineTo((50, top))
            pen.lineTo((450 + scale % 50, top))
            pen.lineTo((450 + scale % 50, bottom))
            pen.closePath()
        glyphs[name] = pen.glyph()
        metrics[name] = (500 + (position % 7) * 10, 50)
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=900, descent=-250)
    fb.setupNameTable({"familyName": family, "styleName": style,
                       "psName": f"{family.replace(' ', '')}-{style}"})
    fb.setupOS2(sTypoAscender=880, sTypoDescender=-240, usWinAscent=950,
                usWinDescent=260, sCapHeight=700, sxHeight=500)
    fb.setupPost()
    fb.save(str(path))


def build_fixtures(tmp: Path, extra_fonts: list[Path]) -> tuple[Path, Path, Path]:
    system = tmp / "system"
    fonts = system / "fonts"
    etc = system / "etc"
    fonts.mkdir(parents=True)
    etc.mkdir(parents=True)
    build_fixture_font(fonts / "Roboto-Regular.ttf", "Roboto", "Regular", 1)
    build_fixture_font(fonts / "RobotoMono-Regular.ttf", "Roboto Mono", "Regular", 2)
    build_fixture_font(fonts / "NotoColorEmoji.ttf", "Noto Color Emoji", "Regular", 3)
    build_fixture_font(fonts / "NotoSansThai-Regular.ttf", "Noto Sans Thai", "Regular", 4)
    build_fixture_font(fonts / "OnlyByName.ttf", "Only By Name", "Regular", 5)
    face_a = tmp / "cjk-a.ttf"
    face_b = tmp / "cjk-b.ttf"
    build_fixture_font(face_a, "Noto Sans CJK SC", "Regular", 6)
    build_fixture_font(face_b, "Noto Sans CJK TC", "Regular", 7)
    collection = TTCollection()
    collection.fonts = [TTFont(str(face_a)), TTFont(str(face_b))]
    collection.save(str(fonts / "NotoSansCJK-Regular.ttc"))
    extra_names = []
    for source in extra_fonts:
        shutil.copy2(source, fonts / source.name)
        extra_names.append(source.name)

    def family(name_attr: str, body: str) -> str:
        return f"    <family {name_attr}>\n{body}    </family>\n"

    declared = "".join([
        family('name="sans-serif"', '        <font weight="400" style="normal">Roboto-Regular.ttf</font>\n'),
        family('name="monospace"', '        <font weight="400" style="normal">RobotoMono-Regular.ttf</font>\n'),
        family('lang="zh-Hans"', '        <font weight="400" style="normal" index="0">NotoSansCJK-Regular.ttc</font>\n'),
        family('lang="zh-Hant zh-Bopo"', '        <font weight="500" style="normal" index="1">NotoSansCJK-Regular.ttc</font>\n'),
        family('lang="th"', '        <font weight="400" style="normal">NotoSansThai-Regular.ttf</font>\n'),
        family('lang="und-Zsye"', '        <font weight="400" style="normal">NotoColorEmoji.ttf</font>\n'),
        family('name="sans-serif-missing"', '        <font weight="400" style="normal">Missing-Regular.ttf</font>\n'),
    ] + [
        family(f'name="google-sans-{position}"', f'        <font weight="{400 + 100 * (position % 3)}" style="normal">{name}</font>\n')
        for position, name in enumerate(extra_names)
    ])
    declared_xml = etc / "fonts.xml"
    declared_xml.write_text(f'<?xml version="1.0" encoding="utf-8"?>\n<familyset>\n{declared}</familyset>\n', encoding="utf-8")
    named_xml = etc / "font_fallback.xml"
    named_xml.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<familyset>\n'
        + declared
        + family('name="roboto-flex"', '        <font weight="400" name="OnlyByName-Regular" />\n')
        + '</familyset>\n',
        encoding="utf-8",
    )
    return declared_xml, named_xml, fonts


def render(xml: Path, fonts: Path, hash_fonts: bool, eager: bool) -> tuple[bytes, int, float]:
    calls = {"count": 0}
    original_index = base.build_postscript_index
    original_lazy_index = base.LazyPostScriptIndex
    original_inspect_lazy = base.INSPECT_LAZY

    def counting_index(roots):
        calls["count"] += 1
        return original_index(roots)

    base.build_postscript_index = counting_index
    if eager:
        base.INSPECT_LAZY = False
        base.LazyPostScriptIndex = lambda roots: base.build_postscript_index(roots)
    try:
        started = time.perf_counter()
        payload = mod.build_template([xml], [fonts], "fixture/fp", hash_fonts=hash_fonts)
        elapsed = time.perf_counter() - started
    finally:
        base.build_postscript_index = original_index
        base.LazyPostScriptIndex = original_lazy_index
        base.INSPECT_LAZY = original_inspect_lazy
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return data, calls["count"], elapsed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", action="append", default=[], help="extra real fonts, e.g. DejaVu")
    args = parser.parse_args()
    extra = [Path(item) for item in args.font if item and Path(item).is_file()]
    if extra:
        siblings = sorted(p for p in extra[0].parent.glob("*.ttf") if p not in extra)
        extra = list(dict.fromkeys(extra + siblings[:7]))
    assert base.INSPECT_LAZY is True, "template capture must open fonts lazily"

    with tempfile.TemporaryDirectory(prefix="luoshu-template-lazy-") as raw:
        declared_xml, named_xml, fonts = build_fixtures(Path(raw), extra)
        for xml in (declared_xml, named_xml):
            for hash_fonts in (False, True):
                old, old_calls, _ = render(xml, fonts, hash_fonts, eager=True)
                new, new_calls, _ = render(xml, fonts, hash_fonts, eager=False)
                assert old == new, f"lazy template differs from eager path: {xml.name} hash={hash_fonts}"
                assert old_calls == 1, old_calls
                expected_calls = 1 if xml == named_xml else 0
                assert new_calls == expected_calls, (xml.name, new_calls)
        payload = json.loads(new.decode("utf-8"))
        by_family = {slot["family"]: slot for slot in payload["slots"] if slot["family"]}
        assert by_family["roboto-flex"]["resolvedPath"].endswith("OnlyByName.ttf"), by_family["roboto-flex"]
        assert "font" in by_family["sans-serif"] and by_family["sans-serif"]["replaceable"]
        assert by_family["sans-serif-missing"]["fontError"]
        cjk = [slot for slot in payload["slots"] if slot["resolvedPath"].endswith(".ttc")]
        assert {slot["font"]["faceIndex"] for slot in cjk} == {0, 1}, cjk
        assert any("fallback-other" in slot["roles"] and "font" in slot for slot in payload["slots"])

        # Timing sanity, deliberately loose so it cannot flake on a busy runner:
        # best of three, lazy may not be meaningfully slower than eager.
        eager_best = min(render(declared_xml, fonts, False, eager=True)[2] for _ in range(3))
        lazy_best = min(render(declared_xml, fonts, False, eager=False)[2] for _ in range(3))
        assert lazy_best <= eager_best * 1.5 + 0.25, (lazy_best, eager_best)
        print(
            "device font template lazy capture: byte-identical "
            f"({len(payload['slots'])} slots, {len(extra)} real fonts); "
            f"eager {eager_best:.3f}s lazy {lazy_best:.3f}s"
        )


if __name__ == "__main__":
    main()
