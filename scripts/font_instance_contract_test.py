#!/usr/bin/env python3
"""Real SFNT/outline regression tests; fixtures are generated, not bundled fonts."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTCollection, TTFont
from fontTools.ttLib.tables.TupleVariation import TupleVariation

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("luoshu_instance_under_test", ROOT / "common/font_instance.py")
instance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(instance)


def make_font(path: Path, weight: int = 400, *, variable: bool = False,
              width_only: bool = False, cff: bool = False,
              notdef_digits: bool = False) -> Path:
    points = [ord("A"), ord("a"), ord("中"), *range(48, 58)]
    names = [".notdef", *[f"u{cp:04X}" for cp in points]]
    builder = FontBuilder(1000, isTTF=not cff)
    builder.setupGlyphOrder(names)
    cmap = {cp: f"u{cp:04X}" for cp in points}
    if notdef_digits:
        cmap.update({cp: ".notdef" for cp in range(48, 58)})
    builder.setupCharacterMap(cmap)
    outlines = {}
    for name in names:
        pen = T2CharStringPen(600, None) if cff else TTGlyphPen(None)
        pen.moveTo((50, 0))
        pen.lineTo((150, 0))
        pen.lineTo((150, 700))
        pen.lineTo((50, 700))
        pen.closePath()
        outlines[name] = pen.getCharString() if cff else pen.glyph()
    if cff:
        builder.setupCFF("LuoShuFixture-Regular", {}, outlines, {})
    else:
        builder.setupGlyf(outlines)
    builder.setupHorizontalMetrics({name: (600, 50) for name in names})
    builder.setupHorizontalHeader(ascent=810, descent=-190)
    builder.setupNameTable({"familyName": "LuoShu Fixture", "styleName": "Regular",
                            "uniqueFontIdentifier": "LuoShuFixture-Regular",
                            "fullName": "LuoShu Fixture Regular",
                            "psName": "LuoShuFixture-Regular"})
    builder.setupOS2(usWeightClass=weight, sTypoAscender=810, sTypoDescender=-190,
                     usWinAscent=810, usWinDescent=190)
    builder.setupPost()
    if variable:
        axes = [] if width_only else [("wght", 100, 400, 900, "Weight")]
        axes.append(("wdth", 75, 100, 125, "Width"))
        builder.setupFvar(axes, [])
        variations = {}
        for name in names:
            values = []
            if not width_only:
                values += [TupleVariation({"wght": (0, 1, 1)},
                            [(0, 0), (200, 0), (200, 0), (0, 0)] + [(0, 0)] * 4),
                           TupleVariation({"wght": (-1, -1, 0)},
                            [(0, 0), (-60, 0), (-60, 0), (0, 0)] + [(0, 0)] * 4)]
            values.append(TupleVariation({"wdth": (0, 1, 1)},
                            [(0, 0), (50, 0), (50, 0), (0, 0)] + [(0, 0)] * 4))
            variations[name] = values
        builder.setupGvar(variations)
    builder.save(path)
    builder.font.close()
    return path


def outline(path: Path, cp: int = 48):
    with TTFont(path) as font:
        glyph = font["glyf"][font.getBestCmap()[cp]]
        return tuple(glyph.getCoordinates(font["glyf"])[0])


def metrics(path: Path):
    with TTFont(path) as font:
        return (font["hhea"].ascent, font["hhea"].descent, font["hhea"].lineGap,
                font["OS/2"].sTypoAscender, font["OS/2"].sTypoDescender)


class FontInstanceContractTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.static = make_font(self.root / "static.ttf")
        self.variable = make_font(self.root / "variable.ttf", variable=True)

    def build(self, name="out.ttf", source=None, weight=400, axes=None):
        path = self.root / name
        result = instance.materialize(source or self.variable, path, "digit", weight,
                                       axes or {}, preserve_metrics=True)
        return path, result

    def test_weight_argument_controls_real_outline(self):
        regular, _ = self.build("regular.ttf", weight=400)
        bold, result = self.build("bold.ttf", weight=700)
        self.assertNotEqual(outline(regular), outline(bold))
        self.assertEqual(result["location"]["wght"], 700)
        self.assertEqual(result["weight"], 700)

    def test_explicit_and_implicit_weight_match(self):
        implicit, _ = self.build("implicit.ttf", weight=700)
        explicit, _ = self.build("explicit.ttf", weight=700, axes={"wght": 700})
        self.assertEqual(outline(implicit), outline(explicit))

    def test_explicit_axis_takes_precedence(self):
        explicit, result = self.build(weight=300, axes={"wght": 700})
        expected, _ = self.build("expected.ttf", weight=700)
        self.assertEqual(outline(explicit), outline(expected))
        self.assertEqual(result["requestedWeight"], 700)

    def test_other_axis_defaults_are_preserved(self):
        _, result = self.build(weight=700)
        self.assertEqual(result["location"]["wdth"], 100)

    def test_multiple_axes_change_real_outlines(self):
        normal, _ = self.build("normal.ttf", weight=700)
        wide, result = self.build("wide.ttf", weight=700, axes={"wdth": 125})
        self.assertNotEqual(outline(normal), outline(wide))
        self.assertEqual(result["location"], {"wght": 700.0, "wdth": 125.0})

    def test_all_variable_axes_are_removed(self):
        output, _ = self.build()
        with TTFont(output) as font:
            self.assertNotIn("fvar", font)
            self.assertNotIn("gvar", font)

    def test_weight_clamps_to_real_font_range(self):
        _, result = self.build(weight=1000)
        self.assertEqual(result["weight"], 900)
        self.assertEqual(result["requestedWeight"], 1000)
        self.assertFalse(result["weightMatched"])

    def test_weight_clamps_low(self):
        _, result = self.build(weight=1)
        self.assertEqual(result["weight"], 100)

    def test_static_face_is_not_relabelled_bold(self):
        output, result = self.build(source=self.static, weight=700, axes={"wght": 700})
        self.assertEqual(outline(output), outline(self.static))
        self.assertEqual(result["weight"], 400)
        self.assertEqual(result["sourceWeight"], 400)
        self.assertEqual(result["requestedWeight"], 700)
        self.assertEqual(result["weightMode"], "source-face")
        self.assertEqual(result["ignoredAxes"], ["wght"])
        self.assertFalse(result["weightMatched"])
        with TTFont(output) as font:
            self.assertEqual(font["OS/2"].usWeightClass, 400)

    def test_width_only_variable_does_not_fake_weight(self):
        source = make_font(self.root / "width.ttf", variable=True, width_only=True)
        _, result = self.build(source=source, weight=700, axes={"wght": 700, "wdth": 125})
        self.assertEqual(result["weight"], 400)
        self.assertEqual(result["ignoredAxes"], ["wght"])

    def test_unknown_axis_is_reported(self):
        _, result = self.build(axes={"opsz": 14})
        self.assertEqual(result["ignoredAxes"], ["opsz"])

    def test_valid_small_digit_font_is_accepted(self):
        output, result = self.build(source=self.static)
        self.assertLess(output.stat().st_size, 4096)
        self.assertEqual(result["status"], "ok")
        instance.validate_output(output)

    def test_small_cff_font_is_accepted(self):
        source = make_font(self.root / "cff.otf", cff=True)
        output, result = self.build(source=source)
        with TTFont(output) as font:
            self.assertIn("CFF ", font)
        self.assertLess(result["size"], 4096)

    def collection(self, *paths):
        path = self.root / "family.ttc"
        fonts = [TTFont(p) for p in paths]
        collection = TTCollection()
        collection.fonts = fonts
        try:
            collection.save(path)
        finally:
            collection.close()
        return path

    def test_ttc_selects_actual_static_weight(self):
        bold = make_font(self.root / "bold-source.ttf", weight=700)
        source = self.collection(self.static, bold)
        _, result = self.build(source=source, weight=700)
        self.assertEqual(result["face"], 1)
        self.assertEqual(result["weight"], 700)

    def test_ttc_considers_variable_reachable_range(self):
        semibold = make_font(self.root / "semi.ttf", weight=600)
        source = self.collection(semibold, self.variable)
        _, result = self.build(source=source, weight=700)
        self.assertEqual(result["face"], 1)
        self.assertEqual(result["weight"], 700)
        self.assertTrue(result["variable"])

    def test_notdef_does_not_count_as_digit_coverage(self):
        empty = make_font(self.root / "notdef.ttf", weight=700, notdef_digits=True)
        source = self.collection(empty, self.static)
        _, result = self.build(source=source, weight=700)
        self.assertEqual(result["face"], 1)

    def test_source_bytes_unchanged(self):
        before = hashlib.sha256(self.variable.read_bytes()).hexdigest()
        self.build(weight=700)
        self.assertEqual(hashlib.sha256(self.variable.read_bytes()).hexdigest(), before)

    def test_preserve_metrics_is_respected(self):
        output, result = self.build(source=self.static)
        self.assertEqual(metrics(output), metrics(self.static))
        self.assertEqual(result["metrics"], {"mode": "preserved"})

    def test_same_source_output_is_rejected(self):
        before = self.static.read_bytes()
        with self.assertRaises(instance.InstanceError):
            instance.materialize(self.static, self.static, "digit", 700, {}, preserve_metrics=True)
        self.assertEqual(self.static.read_bytes(), before)

    def test_bad_font_preserves_previous_result(self):
        old, _ = self.build()
        before = old.read_bytes()
        corrupt = self.root / "bad.ttf"
        corrupt.write_bytes(b"invalid" * 100)
        with self.assertRaises(Exception):
            self.build(source=corrupt)
        self.assertEqual(old.read_bytes(), before)

    def test_validation_failure_is_atomic(self):
        old, _ = self.build()
        before = old.read_bytes()
        with patch.object(instance, "validate_output", side_effect=instance.InstanceError("fixture rejection")):
            with self.assertRaises(instance.InstanceError):
                self.build(weight=700)
        self.assertEqual(old.read_bytes(), before)
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_nonfinite_axes_rejected_in_cli_parser(self):
        for value in ("nan", "inf", "-inf", "1e999"):
            with self.subTest(value=value), self.assertRaises(instance.InstanceError):
                instance.parse_axis_spec(f"wght={value}")

    def test_nonfinite_axes_rejected_in_python_api(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value), self.assertRaises(instance.InstanceError):
                self.build(axes={"wdth": value})

    def test_duplicate_axis_rejected(self):
        with self.assertRaises(instance.InstanceError):
            instance.parse_axis_spec("wght=400,wght=700")

    def test_bad_axis_tag_rejected(self):
        with self.assertRaises(instance.InstanceError):
            instance.parse_axis_spec("weight=700")

    def test_cli_reports_errors_as_json(self):
        proc = subprocess.run([sys.executable, str(ROOT / "common/font_instance.py"),
                               "--input", str(self.static), "--output", str(self.root / "out.ttf"),
                               "--role", "digit", "--axes", "wght=nan", "--preserve-metrics"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stderr)["status"], "error")

    def test_legacy_cli_uses_shared_implementation_preserving_metrics(self):
        output = self.root / "legacy.ttf"
        proc = subprocess.run([sys.executable, str(ROOT / "common/legacy_v14_4/font_instance.py"),
                               "--input", str(self.variable), "--output", str(output),
                               "--role", "digit", "--weight", "700"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["weight"], 700)
        self.assertEqual(result["metrics"], {"mode": "preserved"})
        expected, _ = self.build(weight=700)
        self.assertEqual(outline(output), outline(expected))

    def test_legacy_symlink_runtime_resolves_shared_engine(self):
        runtime = self.root / "runtime/common"
        runtime.mkdir(parents=True)
        entry = runtime / "font_instance.py"
        entry.symlink_to(ROOT / "common/legacy_v14_4/font_instance.py")
        proc = subprocess.run([sys.executable, str(entry), "--input", str(self.variable),
                               "--output", str(self.root / "symlink.ttf"), "--role", "digit", "--weight", "700"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["weight"], 700)


if __name__ == "__main__":
    unittest.main(verbosity=2)
