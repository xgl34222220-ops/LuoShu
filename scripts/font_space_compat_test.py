#!/usr/bin/env python3
"""Regression for common/font_space_compat.py and its three builder call sites.

A user font that lacks U+0020 or U+2005 used to reach the device without a
real blank glyph (tofu or a zero-width space). The builders now append a
dedicated blank glyph only when one is missing. Fonts that already carry both
spaces must come out byte-for-byte identical, and repairing a font must never
touch existing glyph IDs, outlines, advances or the weight metadata.

Usage: font_space_compat_test.py [--font DejaVuSans.ttf]
``--font`` enables the device slot builder integration case (CI passes the
same DejaVu fixture as device_font_slot_build_test.py).
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / "common"
sys.path.insert(0, str(COMMON))
sys.path.insert(0, str(ROOT / "scripts"))

import font_space_compat  # noqa: E402
from font_space_compat import ensure_space_glyphs  # noqa: E402

SLOT_FONT: Path | None = None
UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
LOWER = "abcdefghijklmnopqrstuvwxyz"
DIGITS = "0123456789"
CJK = "中文字体系统默认洛书汉字国一的。田日口"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def font_bytes(font: TTFont) -> bytes:
    buffer = io.BytesIO()
    font.save(buffer, reorderTables=False)
    return buffer.getvalue()


def box_tt(x0=60, y0=0, x1=540, y1=700):
    pen = TTGlyphPen(None)
    pen.moveTo((x0, y0)); pen.lineTo((x1, y0)); pen.lineTo((x1, y1)); pen.lineTo((x0, y1)); pen.closePath()
    return pen.glyph()


def blank_tt():
    return TTGlyphPen(None).glyph()


LATIN_EXT = "".join(chr(codepoint) for codepoint in range(0x00C0, 0x0180))


def make_tt(path: Path, *, chars: str = UPPER + LOWER + DIGITS + LATIN_EXT, spaces: tuple[int, ...] = (0x20, 0x2005),
            weight: int = 400, family: str = "SpaceFixture", upem: int = 1000, cjk: str = "") -> Path:
    cmap = {ord(char): f"u{ord(char):04X}" for char in chars + cjk}
    for codepoint in spaces:
        cmap[codepoint] = "space" if codepoint == 0x20 else f"uni{codepoint:04X}"
    order = [".notdef", *dict.fromkeys(cmap.values())]
    glyphs = {name: box_tt() for name in order}
    for codepoint in spaces:
        glyphs[cmap[codepoint]] = blank_tt()
    cjk_names = {f"u{ord(char):04X}" for char in cjk}
    metrics = {name: ((upem if name in cjk_names else 600), 60) for name in order}
    for codepoint in spaces:
        metrics[cmap[codepoint]] = (upem // 3, 0)
    fb = FontBuilder(upem, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=int(upem * 1.044), descent=-int(upem * 0.282))
    fb.setupOS2(sTypoAscender=int(upem * 0.89), sTypoDescender=-int(upem * 0.11), usWinAscent=int(upem * 1.044),
                usWinDescent=int(upem * 0.282), usWeightClass=weight)
    fb.setupNameTable({"familyName": family, "styleName": "Regular"})
    fb.setupPost()
    fb.setupMaxp()
    fb.save(str(path))
    return path


def make_variable_tt(path: Path, *, spaces: tuple[int, ...]) -> Path:
    from fontTools.ttLib.tables.TupleVariation import TupleVariation

    chars = UPPER + DIGITS
    cmap = {ord(char): f"u{ord(char):04X}" for char in chars}
    for codepoint in spaces:
        cmap[codepoint] = "space" if codepoint == 0x20 else f"uni{codepoint:04X}"
    order = [".notdef", *dict.fromkeys(cmap.values())]
    glyphs = {name: box_tt() for name in order}
    for codepoint in spaces:
        glyphs[cmap[codepoint]] = blank_tt()
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({name: (600, 60) for name in order})
    fb.setupHorizontalHeader(ascent=1000, descent=-250)
    fb.setupOS2(usWeightClass=400)
    fb.setupNameTable({"familyName": "SpaceVar", "styleName": "Regular"})
    fb.setupPost()
    fb.setupFvar([("wght", 100, 400, 900, "Weight")], [])
    variations = {}
    for name in order:
        if glyphs[name].numberOfContours > 0:
            deltas = [(20, 0), (-20, 0), (-20, 0), (20, 0), (0, 0), (0, 0), (0, 0), (0, 0)]
            variations[name] = [TupleVariation({"wght": (0.0, 1.0, 1.0)}, deltas)]
        else:
            variations[name] = []
    fb.setupGvar(variations)
    fb.setupMaxp()
    fb.save(str(path))
    return path


def _cff_box(width: int):
    pen = T2CharStringPen(width, None)
    pen.moveTo((60, 0)); pen.lineTo((540, 0)); pen.lineTo((540, 700)); pen.lineTo((60, 700)); pen.closePath()
    return pen.getCharString()


def make_cff(path: Path, *, spaces: tuple[int, ...] = (), cid: bool = False) -> Path:
    chars = UPPER + DIGITS
    names = [".notdef", *(f"cid{index:05d}" if cid else f"u{ord(char):04X}" for index, char in enumerate(chars, 1))]
    cmap = {ord(char): names[index] for index, char in enumerate(chars, 1)}
    for codepoint in spaces:
        name = f"cid{len(names):05d}" if cid else ("space" if codepoint == 0x20 else f"uni{codepoint:04X}")
        names.append(name)
        cmap[codepoint] = name
    space_names = {cmap[codepoint] for codepoint in spaces}
    charstrings = {name: (T2CharStringPen(250, None).getCharString() if name in space_names else _cff_box(600))
                   for name in names}
    fb = FontBuilder(1000, isTTF=False)
    fb.setupGlyphOrder(names)
    fb.setupCharacterMap(cmap)
    fb.setupCFF("SpaceCFF-Regular", {"FullName": "SpaceCFF Regular"}, charstrings, {})
    fb.setupHorizontalMetrics({name: (250 if name in space_names else 600, 60) for name in names})
    fb.setupHorizontalHeader(ascent=1000, descent=-250)
    fb.setupOS2(usWeightClass=400)
    fb.setupNameTable({"familyName": "SpaceCFF", "styleName": "Regular"})
    fb.setupPost()
    fb.setupMaxp()
    if cid:
        _make_cid_keyed(fb.font)
    fb.save(str(path))
    return path


def _make_cid_keyed(font: TTFont) -> None:
    """Turn the single-FontDict name-keyed CFF into an Identity CID-keyed CFF."""
    from fontTools.cffLib import FDArrayIndex, FDSelect, FontDict

    cff = font["CFF "].cff
    top = cff.topDictIndex[0]
    order = font.getGlyphOrder()
    top.ROS = ("Adobe", "Identity", 0)
    top.CIDCount = len(order)
    fd = FontDict()
    fd.setCFF2(False)
    fd.Private = top.Private
    fd.FontName = "SpaceCFF-Regular-FD0"
    fd_array = FDArrayIndex()
    fd_array.append(fd)
    top.FDArray = fd_array
    selector = FDSelect()
    selector.format = 3
    selector.gidArray = [0] * len(order)
    top.FDSelect = selector
    top.CharStrings.fdSelect = selector
    top.CharStrings.fdArray = fd_array
    top.rawDict.pop("Private", None)
    if "Private" in top.__dict__:
        del top.__dict__["Private"]
    for name in order:
        top.CharStrings[name].private = fd.Private


class EnsureSpaceGlyphsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def load(self, path: Path) -> TTFont:
        font = TTFont(str(path), lazy=False, recalcTimestamp=False)
        self.addCleanup(font.close)
        return font

    def snapshot_existing(self, font: TTFont) -> dict:
        order = list(font.getGlyphOrder())
        if "glyf" in font:
            outlines = {name: font["glyf"][name].compile(font["glyf"]) for name in order}
        else:
            top = font["CFF "].cff.topDictIndex[0]
            outlines = {}
            for name in order:
                charstring = top.CharStrings[name]
                charstring.decompile()
                outlines[name] = tuple(charstring.program)
        return {
            "order": order,
            "outlines": outlines,
            "hmtx": {name: font["hmtx"][name] for name in order},
            "weight": font["OS/2"].usWeightClass,
            "cmap": dict(font.getBestCmap()),
        }

    def assert_existing_preserved(self, before: dict, after: TTFont) -> None:
        order = list(after.getGlyphOrder())
        self.assertEqual(order[:len(before["order"])], before["order"], "existing glyph IDs moved")
        self.assertEqual(after["OS/2"].usWeightClass, before["weight"], "weight class changed")
        cmap = after.getBestCmap()
        for codepoint, name in before["cmap"].items():
            self.assertEqual(cmap.get(codepoint), name, f"U+{codepoint:04X} remapped")
        for name in before["order"]:
            self.assertEqual(after["hmtx"][name], before["hmtx"][name], f"{name} advance changed")
            if "glyf" in after:
                self.assertEqual(after["glyf"][name].compile(after["glyf"]), before["outlines"][name],
                                 f"{name} outline changed")
            else:
                charstring = after["CFF "].cff.topDictIndex[0].CharStrings[name]
                charstring.decompile()
                self.assertEqual(tuple(charstring.program), before["outlines"][name], f"{name} outline changed")

    def assert_blank(self, font: TTFont, codepoint: int, advance: int) -> str:
        name = font.getBestCmap().get(codepoint)
        self.assertTrue(name and name != ".notdef", f"U+{codepoint:04X} still missing")
        self.assertEqual(font["hmtx"][name][0], advance)
        glyph_set = font.getGlyphSet()
        from fontTools.pens.recordingPen import RecordingPen
        pen = RecordingPen()
        glyph_set[name].draw(pen)
        self.assertFalse([op for op, _ in pen.value if op not in ("moveTo", "endPath", "closePath")],
                         f"U+{codepoint:04X} glyph is not blank: {pen.value}")
        return name

    def test_complete_font_is_untouched_and_cli_copies_bytes(self):
        source = make_tt(self.root / "complete.ttf")
        font = self.load(source)
        before = font_bytes(font)
        report = ensure_space_glyphs(font)
        self.assertEqual(report["status"], "unchanged", report)
        self.assertEqual(font_bytes(font), before)

        output = self.root / "out" / "complete.ttf"
        result = subprocess.run([sys.executable, str(COMMON / "font_space_compat.py"), "--input", str(source),
                                 "--output", str(output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "unchanged")
        self.assertEqual(sha256(output), sha256(source))

    def test_truetype_missing_both_spaces(self):
        source = make_tt(self.root / "nospace.ttf", spaces=(), weight=700)
        font = self.load(source)
        before = self.snapshot_existing(font)
        report = ensure_space_glyphs(font)
        self.assertEqual(report["status"], "repaired", report)
        self.assertEqual([item["codepoint"] for item in report["added"]], ["U+0020", "U+2005"])
        output = self.root / "fixed.ttf"
        font.save(str(output))
        fixed = self.load(output)
        self.assert_existing_preserved(before, fixed)
        self.assertEqual(len(fixed.getGlyphOrder()), len(before["order"]) + 2)
        self.assertEqual(fixed["maxp"].numGlyphs, len(before["order"]) + 2)
        for codepoint in (0x20, 0x2005):
            name = self.assert_blank(fixed, codepoint, 250)
            self.assertEqual(fixed["glyf"][name].numberOfContours, 0)
        # every Unicode subtable got the mapping, not just the best one
        for table in fixed["cmap"].tables:
            if table.isUnicode() and table.format != 14:
                self.assertIn(0x20, table.cmap)

    def test_truetype_missing_only_u2005_and_cli(self):
        source = make_tt(self.root / "no2005.ttf", spaces=(0x20,))
        output = self.root / "out" / "no2005.ttf"
        result = subprocess.run([sys.executable, str(COMMON / "font_space_compat.py"), "--input", str(source),
                                 "--output", str(output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "repaired", report)
        self.assertEqual([item["codepoint"] for item in report["added"]], ["U+2005"])
        fixed = self.load(output)
        self.assert_existing_preserved(self.snapshot_existing(self.load(source)), fixed)
        self.assertEqual(fixed.getBestCmap()[0x20], "space")
        self.assert_blank(fixed, 0x2005, 250)

    def test_name_keyed_cff(self):
        source = make_cff(self.root / "name.otf", spaces=())
        font = self.load(source)
        before = self.snapshot_existing(font)
        report = ensure_space_glyphs(font)
        self.assertEqual(report["status"], "repaired", report)
        self.assertEqual([item["glyph"] for item in report["added"]], ["luoshuSpace0020", "luoshuSpace2005"])
        output = self.root / "name-fixed.otf"
        font.save(str(output))
        fixed = self.load(output)
        self.assertNotIn("glyf", fixed)
        self.assert_existing_preserved(before, fixed)
        for codepoint in (0x20, 0x2005):
            self.assert_blank(fixed, codepoint, 250)

    def test_cid_keyed_cff(self):
        source = make_cff(self.root / "cid.otf", spaces=(), cid=True)
        font = self.load(source)
        top = font["CFF "].cff.topDictIndex[0]
        self.assertTrue(hasattr(top, "ROS"), "fixture is not CID-keyed")
        before = self.snapshot_existing(font)
        report = ensure_space_glyphs(font)
        self.assertEqual(report["status"], "repaired", report)
        count = len(before["order"])
        self.assertEqual([item["glyph"] for item in report["added"]], [f"cid{count:05d}", f"cid{count + 1:05d}"])
        output = self.root / "cid-fixed.otf"
        font.save(str(output))
        fixed = self.load(output)
        fixed_top = fixed["CFF "].cff.topDictIndex[0]
        self.assertTrue(hasattr(fixed_top, "ROS"))
        self.assertEqual(len(fixed_top.FDSelect), count + 2)
        self.assert_existing_preserved(before, fixed)
        for codepoint in (0x20, 0x2005):
            self.assert_blank(fixed, codepoint, 250)

    def test_variable_font_reuses_space_without_new_glyphs(self):
        source = make_variable_tt(self.root / "var.ttf", spaces=(0x20,))
        font = self.load(source)
        order = list(font.getGlyphOrder())
        report = ensure_space_glyphs(font)
        self.assertEqual(report["status"], "repaired", report)
        self.assertEqual(report["added"], [])
        self.assertEqual(report["reused"], [{"codepoint": "U+2005", "glyph": "space", "source": "U+0020"}])
        output = self.root / "var-fixed.ttf"
        font.save(str(output))
        fixed = self.load(output)
        self.assertEqual(list(fixed.getGlyphOrder()), order)
        self.assertEqual(fixed.getBestCmap()[0x2005], "space")

    def test_variable_font_without_any_space_is_left_alone(self):
        source = make_variable_tt(self.root / "var-none.ttf", spaces=())
        font = self.load(source)
        before = font_bytes(font)
        report = ensure_space_glyphs(font)
        self.assertEqual(report["status"], "skipped", report)
        self.assertEqual(len(report["unresolved"]), 2)
        self.assertEqual(font_bytes(font), before)

    def test_font_without_unicode_cmap_is_skipped_unmodified(self):
        source = make_tt(self.root / "mac-only.ttf", spaces=())
        font = self.load(source)
        font["cmap"].tables = [table for table in font["cmap"].tables if not table.isUnicode()]
        if not font["cmap"].tables:
            from fontTools.ttLib.tables._c_m_a_p import cmap_format_6
            table = cmap_format_6(6)
            table.platformID, table.platEncID, table.language = 1, 0, 0
            table.cmap = {ord("A"): "u0041"}
            font["cmap"].tables = [table]
        before = font_bytes(font)
        report = ensure_space_glyphs(font)
        self.assertEqual(report["status"], "skipped", report)
        self.assertEqual(font_bytes(font), before)


class BuilderIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def _materialize(self, module, source: Path, output: Path, weight: int):
        return module.materialize(source, output, "latin", weight, {})

    def test_font_instance_complete_font_output_is_byte_identical(self):
        import font_instance

        source = make_tt(self.root / "complete.ttf", weight=500)
        with_call = self.root / "with.ttf"
        report = self._materialize(font_instance, source, with_call, 500)
        self.assertEqual(report["spaceCompatibility"]["status"], "unchanged", report)
        original = font_instance.ensure_space_glyphs
        font_instance.ensure_space_glyphs = lambda font: {"status": "unchanged"}
        try:
            without_call = self.root / "without.ttf"
            self._materialize(font_instance, source, without_call, 500)
        finally:
            font_instance.ensure_space_glyphs = original
        self.assertEqual(sha256(with_call), sha256(without_call))

    def test_font_instance_repairs_missing_space_and_keeps_weight(self):
        import font_instance

        source = make_tt(self.root / "nospace.ttf", spaces=(), weight=600)
        output = self.root / "instance.ttf"
        report = self._materialize(font_instance, source, output, 600)
        self.assertEqual(report["spaceCompatibility"]["status"], "repaired", report)
        self.assertEqual(report["weight"], 600)
        fixed = TTFont(str(output))
        self.addCleanup(fixed.close)
        self.assertEqual(fixed["OS/2"].usWeightClass, 600)
        cmap = fixed.getBestCmap()
        self.assertIn(0x20, cmap)
        self.assertIn(0x2005, cmap)

    def _composite(self, cjk: Path, latin: Path, output: Path) -> dict:
        result = subprocess.run([sys.executable, str(COMMON / "composite_font.py"), "--cjk", str(cjk),
                                 "--latin", str(latin), "--digit", str(latin), "--output", str(output)],
                                env=os.environ.copy(), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout.strip().splitlines()[-1])

    def test_composite_repairs_missing_space(self):
        cjk = make_tt(self.root / "cjk.ttf", spaces=(), cjk=CJK, family="Base")
        latin = make_tt(self.root / "latin.ttf", spaces=(), family="Latin")
        output = self.root / "composite.ttf"
        report = self._composite(cjk, latin, output)
        self.assertEqual(report["spaceCompatibility"]["status"], "repaired", report)
        fixed = TTFont(str(output))
        self.addCleanup(fixed.close)
        cmap = fixed.getBestCmap()
        self.assertIn(0x20, cmap)
        self.assertIn(0x2005, cmap)

    def test_composite_with_spaces_reports_unchanged(self):
        cjk = make_tt(self.root / "cjk.ttf", cjk=CJK, family="Base")
        latin = make_tt(self.root / "latin.ttf", family="Latin")
        report = self._composite(cjk, latin, self.root / "composite.ttf")
        self.assertEqual(report["spaceCompatibility"]["status"], "unchanged", report)

    def test_slot_builder(self):
        if SLOT_FONT is None:
            self.skipTest("--font not given")
        import device_font_slot_build as builder
        import device_font_slot_build_base as builder_base
        import device_font_slot_plan as planner
        import device_font_template as template_engine
        from clock_fixture import with_clock_glyphs

        complete = with_clock_glyphs(SLOT_FONT, self.root / "source-clock.ttf")
        stripped = self.root / "source-nospace.ttf"
        font = TTFont(str(complete), recalcTimestamp=False)
        try:
            for table in font["cmap"].tables:
                if table.isUnicode() and hasattr(table, "cmap"):
                    table.cmap.pop(0x20, None)
                    table.cmap.pop(0x2005, None)
            font.save(str(stripped))
        finally:
            font.close()

        def plan_for(source: Path) -> dict:
            info = template_engine.inspect_font(source, -1, hash_fonts=True)
            target = copy.deepcopy(info)
            target["path"] = "/system/fonts/Clockopia.ttf"
            template = {
                "schema": "device-font-template-v1",
                "captureRevision": 2,
                "fingerprint": "space-compat-fixture",
                "slots": [{
                    "family": "clock-family", "familyNormalized": "clock-family", "weight": 400,
                    "style": "normal", "index": 0, "axes": "", "roles": ["clock"],
                    "sourceXml": "/system/etc/fonts.xml", "resolvedPath": "/system/fonts/Clockopia.ttf",
                    "replaceable": True, "font": target,
                }],
            }
            plan = planner.build_plan(template, info)
            slot = plan["slots"][0]
            self.assertEqual(slot["status"], "ready", slot)
            return slot

        slot = plan_for(complete)
        with_call = self.root / "slot-with.ttf"
        report = builder.build_slot(complete, -1, slot, with_call)
        self.assertEqual(report["spaceCompatibility"]["status"], "unchanged", report)
        original = builder_base.ensure_space_glyphs
        builder_base.ensure_space_glyphs = lambda font: {"status": "unchanged"}
        try:
            without_call = self.root / "slot-without.ttf"
            builder.build_slot(complete, -1, slot, without_call)
        finally:
            builder_base.ensure_space_glyphs = original
        self.assertEqual(sha256(with_call), sha256(without_call))

        stripped_slot = plan_for(stripped)
        output = self.root / "slot-fixed.ttf"
        report = builder.build_slot(stripped, -1, stripped_slot, output)
        self.assertEqual(report["status"], "ok", report)
        self.assertEqual(report["spaceCompatibility"]["status"], "repaired", report)
        fixed = TTFont(str(output))
        self.addCleanup(fixed.close)
        cmap = fixed.getBestCmap()
        self.assertEqual(cmap.get(0x20), "luoshuSpace0020")
        self.assertEqual(cmap.get(0x2005), "luoshuSpace2005")
        self.assertEqual(fixed["hmtx"]["luoshuSpace0020"][0], round(fixed["head"].unitsPerEm / 4))


def main() -> int:
    global SLOT_FONT
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", type=Path)
    args, rest = parser.parse_known_args()
    if args.font is not None:
        if not args.font.is_file():
            parser.error(f"--font not found: {args.font}")
        SLOT_FONT = args.font
    program = unittest.main(argv=[sys.argv[0], *rest], exit=False, verbosity=1)
    return 0 if program.result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
