#!/usr/bin/env python3
"""Keep strict per-slot metrics equivalent without recompiling donor outlines."""
from __future__ import annotations

from pathlib import Path
import contextlib
import io
import json
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))
import font_metrics_normalize as metrics
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont, TTCollection, getTableClass


def make_source(path, cff=False, variable=False):
    points = [*range(32, 127), *range(0x4E00, 0x4F00)]
    cmap = {cp: f"uni{cp:04X}" for cp in points}
    order = [".notdef", *cmap.values()]
    builder = FontBuilder(1000, isTTF=not cff)
    builder.setupGlyphOrder(order)
    builder.setupCharacterMap(cmap)
    glyphs = {}
    for name in order:
        pen = T2CharStringPen(650, None) if cff else TTGlyphPen(None)
        pen.moveTo((30, -80)); pen.lineTo((590, -80))
        pen.lineTo((590, 780)); pen.lineTo((30, 780)); pen.closePath()
        glyphs[name] = pen.getCharString() if cff else pen.glyph()
    if cff:
        builder.setupCFF("RawMetricsFixture", {"FullName": "RawMetricsFixture"}, glyphs, {})
    else:
        builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (650, 30) for name in order})
    builder.setupHorizontalHeader(ascent=1500, descent=-600)
    builder.setupOS2(sTypoAscender=1500, sTypoDescender=-600,
                     usWinAscent=1500, usWinDescent=600)
    builder.setupNameTable({"familyName": "Raw metrics fixture", "styleName": "Regular"})
    builder.setupPost(); builder.setupMaxp()
    if variable:
        builder.setupFvar([("wght", 100, 400, 900, "Weight")], [])
        builder.setupGvar({name: [] for name in order})
    builder.save(path)


class RawMetricsTest(unittest.TestCase):
    def exercise(self, cff=False, collection=False, variable=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.font"
            make_source(source, cff=cff, variable=variable)
            if collection:
                donor = TTFont(source)
                ttc = TTCollection()
                ttc.fonts = [donor]
                source = root / "source.ttc"
                ttc.save(source)
                ttc.close()
            original = source.read_bytes()
            contract = {"source": "inventory", "slot": "Slot.ttf", "buildKey": "fixture",
                        "upem": 1000, "ascent": 900, "descent": -220,
                        "ascentRatio": .9, "descentRatio": .22}
            reference = root / "reference.font"
            font, _ = metrics.load_font(source)
            try:
                expected = metrics.normalize_font_metrics(font, target_contract=contract,
                                                         enclose_outlines=False)
                metrics.atomic_save(font, reference)
            finally:
                font.close()
            output = root / "output.font"
            tag = "CFF " if cff else "glyf"
            with contextlib.ExitStack() as stack:
                for unchanged in (tag, "hmtx", "cmap", "maxp", "post", "name"):
                    stack.enter_context(mock.patch.object(getTableClass(unchanged), "compile",
                        side_effect=AssertionError("strict slot recompiled " + unchanged)))
                report = metrics.normalize_path(source, output, target_contract=contract,
                                                strict_contract=True)
            for key, value in expected.items():
                self.assertEqual(report[key], value, key)
            kwargs = {"fontNumber": 0} if collection else {}
            with TTFont(source, lazy=True, **kwargs) as donor, TTFont(output) as result, TTFont(reference) as ref:
                for table in (tag, "cmap", "hmtx", *(('gvar', 'fvar') if variable else ())):
                    self.assertEqual(result.reader[table], donor.reader[table], table)
                for table in ("hhea", "OS/2"):
                    self.assertEqual(result.reader[table], ref.reader[table], table)
            self.assertEqual(source.read_bytes(), original)

    def test_ttf_preserves_outlines_and_matches_existing_metrics(self):
        self.exercise()

    def test_cff_preserves_outlines_and_matches_existing_metrics(self):
        self.exercise(cff=True)

    def test_ttc_extracts_the_selected_face_without_recompilation(self):
        self.exercise(collection=True)

    def test_variable_ttf_preserves_variation_tables(self):
        self.exercise(variable=True)

    def test_cff2_and_opaque_vendor_tables_keep_raw_bytes_and_valid_checksum(self):
        from fontTools.cffLib.CFFToCFF2 import convertCFFToCFF2
        from fontTools.ttLib.sfnt import calcChecksum
        from fontTools.ttLib.tables.DefaultTable import DefaultTable

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "source.otf", root / "output.otf"
            make_source(source, cff=True)
            with TTFont(source) as font:
                convertCFFToCFF2(font)
                vendor = DefaultTable("TEST")
                vendor.data = b"opaque vendor payload"
                font["TEST"] = vendor
                font.save(source)
            original = source.read_bytes()
            contract = {"source": "inventory", "upem": 1000,
                        "ascent": 900, "descent": 0,
                        "ascentRatio": .9, "descentRatio": 0}
            with mock.patch.object(getTableClass("CFF2"), "compile",
                    side_effect=AssertionError("strict slot recompiled CFF2")):
                metrics.normalize_path(source, output, target_contract=contract,
                                       strict_contract=True)
            with TTFont(source) as donor, TTFont(output, checkChecksums=2) as result:
                self.assertIn("CFF2", result)
                for tag in donor.reader.keys():
                    if tag not in {"head", "hhea", "OS/2", "MVAR"}:
                        self.assertEqual(result.reader[tag], donor.reader[tag], tag)
                # Force table decoding as well as raw comparisons: a byte copy
                # must still produce a complete, parseable standalone font.
                for tag in result.keys():
                    if tag != "GlyphOrder":
                        result[tag]
                self.assertEqual((result["hhea"].ascent, result["hhea"].descent), (900, 0))
            self.assertEqual(calcChecksum(output.read_bytes()), 0xB1B0AFBA)
            self.assertEqual(source.read_bytes(), original)

    def test_missing_contract_keeps_outline_enclosure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.ttf"
            make_source(source)
            with mock.patch.object(metrics, "_fast_contract_normalize",
                                   side_effect=AssertionError("missing stock metrics")):
                report = metrics.normalize_path(source, root / "out.ttf", inventory=root / "missing.json")
            self.assertTrue(report["outlineEnclosure"])

    def test_monospace_still_applies_width_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.ttf"
            make_source(source)
            with mock.patch.object(metrics, "_fast_contract_normalize",
                                   side_effect=AssertionError("mono is not a metrics-only alias")):
                report = metrics.normalize_path(source, root / "out.ttf", monospaced=True,
                                                 strict_contract=True)
            self.assertGreater(report["monoGlyphs"], 0)

    def test_clock_zero_descent_survives_batch_and_does_not_use_main_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "source.ttf", root / "clock.ttf"
            make_source(source)
            clock = {"path": "/system/fonts/Clock.ttf", "slotName": "Clock.ttf",
                     "metrics": {"upem": 1000, "hhea": {"ascent": 850, "descent": 0}}}
            main = {"slotName": "Main.ttf", "metrics": {
                "upem": 1000, "hhea": {"ascent": 1100, "descent": -300}}}
            inventory = root / "inventory.json"
            inventory.write_text(json.dumps({"schema": metrics.INVENTORY_SCHEMA,
                "state": "ready", "inventoryRevision": 1, "mainSlot": main,
                "slots": {clock["path"]: clock}}))
            manifest = root / "batch.tsv"
            manifest.write_text(f"{source}\t{output}\t-\t{clock['path']}\n")
            with mock.patch.object(metrics, "_device_build_key", return_value=""):
                self.assertEqual(metrics.load_inventory_contract(inventory, clock["path"])["descent"], 0)
                with contextlib.redirect_stdout(io.StringIO()) as log:
                    self.assertEqual(metrics.run_batch(manifest, inventory), 0)
            report = json.loads(log.getvalue())
            self.assertEqual(report["targetSlot"], "Clock.ttf")
            self.assertFalse(report["outlineEnclosure"])
            with TTFont(output) as font:
                self.assertEqual((font["hhea"].ascent, font["hhea"].descent), (850, 0))

    def test_missing_slot_contract_never_silently_uses_main_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.ttf"
            make_source(source)
            inventory = root / "inventory.json"
            inventory.write_text(json.dumps({"schema": metrics.INVENTORY_SCHEMA,
                "state": "ready", "inventoryRevision": 1, "slots": {},
                "mainSlot": {"slotName": "Main.ttf", "metrics": {
                    "upem": 1000, "hhea": {"ascent": 1100, "descent": -300}}}}))
            manifest = root / "batch.tsv"
            manifest.write_text(f"{source}\t{root / 'out.ttf'}\t-\t/system/fonts/Missing.ttf\n")
            with mock.patch.object(metrics, "_device_build_key", return_value="") as build_key:
                with contextlib.redirect_stdout(io.StringIO()) as log:
                    self.assertEqual(metrics.run_batch(manifest, inventory), 0)
            report = json.loads(log.getvalue())
            self.assertEqual(report["metricsSource"], "fixed-fallback")
            self.assertEqual(report["targetSlot"], "")
            self.assertEqual(build_key.call_count, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
