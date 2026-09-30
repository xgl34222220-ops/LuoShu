#!/usr/bin/env python3
"""Synthetic, redistributable fixtures for real composite variable families."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.otlLib.builder import buildStatTable
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
from fontTools.varLib.instancer import instantiateVariableFont

import universal_mixed_variable as engine

ORDER = [".notdef", "space", "A", "A.alt", "one", "han", "heart", "mark", "composite"]
CMAP = {32: "space", 65: "A", 49: "one", 0x4E2D: "han", 0x2764: "heart", 0x0301: "mark", 0x00C1: "composite"}


def make_master(path: Path, weight: int, *, constant=False, metrics_only=False, cff=False) -> None:
    builder = FontBuilder(1000, isTTF=not cff)
    builder.setupGlyphOrder(ORDER)
    builder.setupCharacterMap(CMAP)
    glyphs, metrics = {}, {}
    for name in ORDER:
        step = weight // 100 if not constant else 4
        # Different nonlinear sequences expose an endpoint-only or duplicated
        # master build. Han and the protected heart are deliberately fixed.
        width = 200 + step * step * 3 if name in {"A", "A.alt"} else 120 + step * 19 if name == "one" else 800 if name == "han" else 300
        if metrics_only:
            width = 300
        pen = T2CharStringPen(1000, None) if cff else TTGlyphPen(glyphs)
        if name == "composite" and not cff:
            pen.addComponent("A", (1, 0, 0, 1, 0, 0))
            pen.addComponent("mark", (1, 0, 0, 1, 150, 550))
        elif name not in {".notdef", "space"}:
            pen.moveTo((40, 0))
            pen.lineTo((40 + width, 0))
            pen.lineTo((40 + width, 700 if name != "mark" else 100))
            pen.lineTo((40, 700 if name != "mark" else 100))
            pen.closePath()
        glyphs[name] = pen.getCharString() if cff else pen.glyph()
        metrics[name] = (width + 120 + (step * 5 if metrics_only else 0), 40)
    if cff:
        builder.setupCFF("SyntheticMixed-Regular", {"FullName": "Synthetic Mixed"}, glyphs, {})
    else:
        builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics(metrics)
    builder.setupHorizontalHeader(ascent=900, descent=-200)
    # Static CJK metadata is intentionally 400 in ALL masters.
    builder.setupOS2(usWeightClass=400, sTypoAscender=900, sTypoDescender=-200, usWinAscent=900, usWinDescent=200)
    builder.setupNameTable({"familyName": "Synthetic Mixed", "styleName": "Regular", "fullName": "Synthetic Mixed Regular", "psName": "SyntheticMixed-Regular"})
    builder.setupPost()
    builder.setupMaxp()
    uvs = CmapSubtable.newSubtable(14)
    uvs.platformID, uvs.platEncID, uvs.language = 0, 5, 0
    uvs.cmap, uvs.uvsDict = {}, {0xFE0F: [(0x2764, "heart")]}
    builder.font["cmap"].tables.append(uvs)
    addOpenTypeFeaturesFromString(builder.font, """
        languagesystem DFLT dflt;
        feature salt { sub A by A.alt; } salt;
        feature kern { pos A one -25; } kern;
        table GDEF { GlyphClassDef [A A.alt one han heart composite], [], [mark], []; } GDEF;
    """)
    builder.save(path)


class VariableCompositeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.fonts = []
        for weight, style in zip(engine.WEIGHTS, engine.STYLES):
            path = self.root / f"LuoShuAutoMix-{style}.ttf"
            make_master(path, weight)
            self.fonts.append((weight, path))
        self.output = self.root / "Mixed-VF.ttf"

    def tearDown(self):
        self.tmp.cleanup()

    def mutate(self, weight, callback):
        path = dict(self.fonts)[weight]
        with TTFont(path, recalcTimestamp=False) as font:
            font.ensureDecompiled()
            callback(font)
            font.save(path)

    def assert_blocked(self, code, fonts=None):
        self.output.write_bytes(b"existing verified output")
        with self.assertRaises(engine.VariableFamilyError) as caught:
            engine.build_variable_family(self.fonts if fonts is None else fonts, self.output)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(self.output.read_bytes(), b"existing verified output")
        self.assertEqual(list(self.root.glob(f".{self.output.name}.*")), [])

    def test_true_geometry_fixed_components_and_roundtrips(self):
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for _, path in self.fonts}
        result = engine.build_variable_family(self.fonts, self.output)
        self.assertEqual(result["state"], "ready")
        self.assertEqual(result["variableGlyphCount"], 4)
        self.assertEqual(result["fixedGlyphCount"], 5)
        self.assertEqual(result["validatedWeights"], list(range(100, 901, 50)))
        self.assertEqual(before, {path: hashlib.sha256(path.read_bytes()).hexdigest() for _, path in self.fonts})
        with TTFont(self.output) as vf, TTFont(dict(self.fonts)[400]) as base:
            self.assertEqual([(a.axisTag, a.minValue, a.defaultValue, a.maxValue) for a in vf["fvar"].axes], [("wght", 100, 400, 900)])
            self.assertEqual(len(vf["fvar"].instances), 9)
            self.assertTrue(vf["gvar"].variations["A"])
            for tag in ("cmap", "GSUB", "GPOS", "GDEF"):
                self.assertEqual(vf.getTableData(tag), base.getTableData(tag))
            snapshots = {}
            for weight in (100, 350, 400, 750, 900):
                instance = instantiateVariableFont(vf, {"wght": weight})
                try:
                    self.assertEqual(instance["OS/2"].usWeightClass, weight)
                    snapshots[weight] = tuple(instance["glyf"]["A"].coordinates)
                    for name in ("han", "heart"):
                        self.assertEqual(engine._outline(instance, name), engine._outline(base, name))
                    lower = weight // 100 * 100
                    upper = lower + 100 if weight % 100 else lower
                    with TTFont(dict(self.fonts)[lower]) as a, TTFont(dict(self.fonts)[upper]) as b:
                        for name in ("A", "A.alt", "one", "composite"):
                            factor = .5 if upper != lower else 0
                            expected = [(x + (xx - x) * factor, y + (yy - y) * factor) for (x, y), (xx, yy) in zip(engine._outline(a, name), engine._outline(b, name))]
                            for actual, desired in zip(engine._outline(instance, name), expected):
                                self.assertLessEqual(max(abs(x-y) for x,y in zip(actual,desired)), 1)
                finally:
                    instance.close()
            self.assertEqual(len(set(snapshots.values())), len(snapshots))

    def test_stale_source_stat_and_style_are_rebuilt(self):
        def change(font):
            buildStatTable(font, [{"tag": "wdth", "name": "Width"}])
            font["name"].setName("Black", 2, 3, 1, 0x409)
        for weight, _ in self.fonts:
            self.mutate(weight, change)
        engine.build_variable_family(self.fonts, self.output)
        with TTFont(self.output) as font:
            self.assertEqual(font["name"].getDebugName(2), "Regular")
            self.assertEqual([axis.AxisTag for axis in font["STAT"].table.DesignAxisRecord.Axis], ["wght"])

    def test_constant_geometry_rejected(self):
        for weight, path in self.fonts:
            make_master(path, weight, constant=True)
        self.assert_blocked("no-variable-geometry")

    def test_metrics_only_diversity_is_not_outline_variation(self):
        for weight, path in self.fonts:
            make_master(path, weight, metrics_only=True)
        self.assert_blocked("no-variable-geometry")

    def test_contour_mismatch_rejected(self):
        def change(font):
            pen = TTGlyphPen(None)
            pen.moveTo((40, 0)); pen.lineTo((300, 0)); pen.lineTo((300, 700)); pen.closePath()
            font["glyf"]["A"] = pen.glyph()
        self.mutate(900, change)
        self.assert_blocked("incompatible-glyph-topology")

    def test_oncurve_mismatch_rejected(self):
        self.mutate(900, lambda font: font["glyf"]["A"].flags.__setitem__(1, 0))
        self.assert_blocked("incompatible-glyph-topology")

    def test_component_transform_mismatch_rejected(self):
        self.mutate(900, lambda font: setattr(font["glyf"]["composite"].components[0], "transform", [[.5, 0], [0, 1]]))
        self.assert_blocked("incompatible-glyph-topology")

    def test_cmap_rejected_including_protected_variation_selector(self):
        def change(font):
            for table in font["cmap"].tables:
                if table.format == 14:
                    table.uvsDict[0xFE0F] = [(0x2764, "A")]
        self.mutate(900, change)
        self.assert_blocked("incompatible-cmap")

    def test_layout_mismatch_rejected(self):
        def change(font):
            font["GPOS"].table.LookupList.Lookup[0].SubTable[0].PairSet[0].PairValueRecord[0].Value1.XAdvance = -50
        self.mutate(900, change)
        self.assert_blocked("incompatible-layout-or-data")

    def test_glyph_order_mismatch_rejected(self):
        self.mutate(900, lambda font: font.setGlyphOrder([*ORDER[:-2], ORDER[-1], ORDER[-2]]))
        self.assert_blocked("incompatible-glyph-order")

    def test_upem_mismatch_rejected(self):
        self.mutate(900, lambda font: setattr(font["head"], "unitsPerEm", 2000))
        self.assert_blocked("incompatible-upem")

    def test_cff_rejected(self):
        make_master(dict(self.fonts)[900], 900, cff=True)
        self.assert_blocked("non-glyf-master")

    def test_variable_input_rejected(self):
        def change(font):
            builder = FontBuilder(font=font)
            builder.setupFvar([("wght", 100, 400, 900, "Weight")], [])
            builder.setupGvar({name: [] for name in ORDER})
        self.mutate(900, change)
        self.assert_blocked("non-static-master")

    def test_missing_and_duplicate_weights_rejected(self):
        self.assert_blocked("invalid-master-weights", self.fonts[:-1])
        self.assert_blocked("invalid-master-weights", self.fonts[:-1] + [self.fonts[0]])

    def test_resource_budget_rejects_before_loading_masters(self):
        with patch.object(engine, "_available_memory", return_value=1024 * 1024), patch.object(engine, "TTFont", side_effect=AssertionError("must not load")):
            self.assert_blocked("resource-budget-exceeded")
        with patch.object(engine, "MAX_MASTER_BYTES", 1):
            self.assert_blocked("resource-budget-exceeded")

    def test_source_master_cannot_be_overwritten(self):
        before = self.fonts[0][1].read_bytes()
        with self.assertRaises(engine.VariableFamilyError) as caught:
            engine.build_variable_family(self.fonts, self.fonts[0][1])
        self.assertEqual(caught.exception.code, "output-is-master")
        self.assertEqual(before, self.fonts[0][1].read_bytes())

    def test_empty_gvar_postbuild_rejected(self):
        real_build = engine.build_variable
        def fake_build(*args, **kwargs):
            vf, model, names = real_build(*args, **kwargs)
            vf["gvar"].variations = {name: [] for name in vf.getGlyphOrder()}
            return vf, model, names
        with patch.object(engine, "build_variable", fake_build):
            self.assert_blocked("no-variable-geometry")

    def test_nonempty_but_wrong_gvar_postbuild_rejected(self):
        real_build = engine.build_variable
        def broken_build(*args, **kwargs):
            vf, model, names = real_build(*args, **kwargs)
            variation = vf["gvar"].variations["A"][0]
            variation.coordinates[0] = (1234, 5678)
            return vf, model, names
        with patch.object(engine, "build_variable", broken_build):
            self.assert_blocked("roundtrip-geometry-mismatch")

    def test_discovery_cli_and_ambiguous_master(self):
        self.assertEqual(engine.find_masters(self.root), self.fonts)
        self.assertEqual(engine.discover_masters(self.root, "LuoShuAutoMix"), self.fonts)
        proc = subprocess.run([sys.executable, str(ROOT / "common/universal_mixed_variable.py"), "--fonts-dir", str(self.root), "--output", str(self.output)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["state"], "ready")
        duplicate = self.root / "LuoShuAutoMix-Thin.otf"
        duplicate.write_bytes(self.fonts[0][1].read_bytes())
        with self.assertRaises(engine.VariableFamilyError) as caught:
            engine.find_masters(self.root)
        self.assertEqual(caught.exception.code, "missing-or-ambiguous-master")
        proc = subprocess.run([sys.executable, str(ROOT / "common/universal_mixed_variable.py"), "--fonts-dir", str(self.root), "--output", str(self.output)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["state"], "blocked")


if __name__ == "__main__":
    unittest.main(verbosity=2)
