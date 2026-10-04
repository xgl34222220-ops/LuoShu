#!/usr/bin/env python3
"""Role-assigned composite (mix) on the Universal engine: profile, plan, compile."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))
sys.path.insert(0, str(ROOT / "scripts"))

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

import device_font_template as template_engine
import font_coverage
import font_source_profile
import universal_font_compiler_test as fixture

ASCII_POINTS = tuple(range(0x20, 0x7F))


def make_cjk_font(path: Path, *, family: str, variable: bool = False, y_max: int = 820) -> None:
    """A CJK base with >= MIN_CORE_HAN Han glyphs, the CJK probes and ASCII."""
    han = list(range(0x4E00, 0x4E00 + font_coverage.MIN_CORE_HAN + 64))
    points = sorted(set(han) | set(template_engine.PROBE_GROUPS["cjk"])
                    | set(template_engine.PROBE_GROUPS["punctuationFullwidth"]) | set(ASCII_POINTS))
    cmap = {cp: f"u{cp:04X}" for cp in points}
    order = [".notdef", *cmap.values()]
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(order)
    builder.setupCharacterMap(cmap)
    glyphs = {}
    for name in order:
        pen = TTGlyphPen(None)
        if name != ".notdef":
            pen.moveTo((60, -110))
            pen.lineTo((940, -110))
            pen.lineTo((940, y_max))
            pen.lineTo((60, y_max))
            pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (1000, 60) for name in order})
    builder.setupHorizontalHeader(ascent=880, descent=-120)
    builder.setupOS2(usWeightClass=400, sTypoAscender=880, sTypoDescender=-120,
                     sTypoLineGap=0, usWinAscent=880, usWinDescent=120)
    builder.setupNameTable({"familyName": family, "styleName": "Regular",
                            "fullName": family, "psName": family.replace(" ", "") + "-Regular"})
    builder.setupPost()
    builder.setupMaxp()
    if variable:
        builder.setupFvar([("wght", 100, 400, 900, "Weight")], [])
        builder.setupGvar({name: [] for name in order})
    builder.save(path)


def expect_error(fn, text: str) -> None:
    try:
        fn()
    except font_source_profile.ProfileError as error:
        assert text in str(error), error
    else:
        raise AssertionError(f"expected ProfileError containing {text!r}")


def test_profile(temp: Path) -> dict[str, Path]:
    cjk = temp / "UserCJK.ttf"
    latin = temp / "UserLatin.ttf"
    digit = temp / "UserDigit.ttf"
    make_cjk_font(cjk, family="User CJK", variable=True)
    fixture.make_font(latin, family="User Latin", variable=True)
    fixture.make_font(digit, family="User Digit", advance=560)

    roles = {"cjk": [cjk], "latin": [latin], "digit": [digit]}
    modes = {"cjk": "auto", "latin": "auto", "digit": "fixed"}
    axes = {"cjk": "wght=400", "latin": "wght=400", "digit": "wght=500"}
    profile = font_source_profile.build([], roles, modes, axes)
    font_source_profile.validate(profile)

    by_file = {Path(f["sourcePath"]).name: f for f in profile["files"]}
    assert by_file["UserCJK.ttf"]["faces"][0]["assignedRoles"] == ["cjk"]
    assert by_file["UserLatin.ttf"]["faces"][0]["assignedRoles"] == ["latin"]
    assert by_file["UserDigit.ttf"]["faces"][0]["assignedRoles"] == ["digit"]
    spec = profile["composite"]["roles"]
    assert spec["digit"] == {
        "mode": "fixed", "axes": {"wght": 500.0},
        "faceUids": [by_file["UserDigit.ttf"]["faces"][0]["uid"]],
    }, spec["digit"]

    # One file serving two roles is profiled once and carries both roles.
    shared = font_source_profile.build(
        [], {"cjk": [cjk], "latin": [latin], "digit": [latin]}, modes, axes
    )
    assert len(shared["files"]) == 2
    latin_face = next(f for f in shared["files"] if f["sourcePath"].endswith("UserLatin.ttf"))["faces"][0]
    assert latin_face["assignedRoles"] == ["digit", "latin"]

    # Same files, different assignment / mode / axes -> different identity.
    swapped = font_source_profile.build([], {"cjk": [cjk], "latin": [digit], "digit": [latin]}, modes, axes)
    remoded = font_source_profile.build([], roles, dict(modes, digit="auto"), axes)
    reaxed = font_source_profile.build([], roles, modes, dict(axes, digit="wght=600"))
    plain = font_source_profile.build([cjk, latin, digit])
    ids = {p["profileId"] for p in (profile, swapped, remoded, reaxed, plain)}
    assert len(ids) == 5, ids
    assert "composite" not in plain

    expect_error(lambda: font_source_profile.build([], {"cjk": [cjk], "latin": [latin]}, modes, axes), "数字")
    expect_error(lambda: font_source_profile.build([], roles, dict(modes, cjk="bogus"), axes), "组合模式无效")
    expect_error(lambda: font_source_profile.build([], roles, modes, dict(axes, cjk="weight=4")), "组合轴设置无效")
    return {"cjk": cjk, "latin": latin, "digit": digit}


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="luoshu-composite-") as raw:
        temp = Path(raw)
        test_profile(temp)
    print("universal_composite_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
