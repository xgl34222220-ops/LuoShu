#!/usr/bin/env python3
"""Exercise the stock scanner with real zero-descender and malformed fonts."""
from __future__ import annotations

import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))
import font_inventory as inventory  # noqa: E402
import font_inventory_scan_v3 as scanner  # noqa: E402


def make_font(path: Path, descent: int = 0, ascent: int = 900) -> None:
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder([".notdef", "zero"])
    builder.setupCharacterMap({ord("0"): "zero"})
    empty = TTGlyphPen(None)
    digit = TTGlyphPen(None)
    digit.moveTo((40, 100))
    digit.lineTo((640, 100))
    digit.lineTo((640, 700))
    digit.lineTo((40, 700))
    digit.closePath()
    builder.setupGlyf({".notdef": empty.glyph(), "zero": digit.glyph()})
    builder.setupHorizontalMetrics({".notdef": (700, 0), "zero": (700, 40)})
    builder.setupHorizontalHeader(ascent=ascent, descent=descent)
    builder.setupNameTable({"familyName": "Stock Clock", "styleName": "Regular",
                            "uniqueFontIdentifier": "StockClock-Regular",
                            "fullName": "Stock Clock Regular", "psName": "StockClock-Regular"})
    builder.setupOS2(sTypoAscender=ascent, sTypoDescender=descent,
                     usWinAscent=max(0, ascent), usWinDescent=max(0, -descent))
    builder.setupPost()
    builder.setupMaxp()
    builder.save(path)


def fixture(metrics: dict) -> dict:
    logical = "/system/fonts/MiClock-Regular.ttf"
    entry = {"path": logical, "slotName": "MiClock-Regular.ttf", "format": "TTF",
             "metrics": metrics}
    return {"schema": inventory.SCHEMA, "inventoryRevision": 1, "state": "ready",
            "buildKey": "stock-metrics-test", "slots": {logical: copy.deepcopy(entry)},
            "slotCount": 1, "mainSlotPath": logical, "mainSlot": copy.deepcopy(entry)}


class StockMetricContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="luoshu-stock-metrics-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "MiClock-Regular.ttf"
        make_font(self.path)

    def scan_args(self, fonts: Path, etc: Path):
        args = scanner.build_parser().parse_args([
            "--scan", "--build-key", "stock-metrics-test",
            "--output", str(self.root / "inventory.json"),
        ])
        for specs in (scanner.PRIMARY_FONT_SPECS, scanner.PRIMARY_ETC_SPECS,
                      scanner.AUX_FONT_SPECS, scanner.AUX_ETC_SPECS):
            for spec in specs:
                setattr(args, spec[2], self.root / "missing" / spec[2])
        args.system_fonts, args.system_etc = fonts, etc
        return args

    def legacy_scan_fixture(self, trusted_lower: bool = False):
        if trusted_lower:
            fonts = self.root / "state/lower/system-fonts"
            etc = self.root / "state/lower/system-etc"
        else:
            fonts, etc = self.root / "live/fonts", self.root / "live/etc"
        fonts.mkdir(parents=True)
        etc.mkdir(parents=True)
        make_font(fonts / self.path.name)
        (etc / "fonts.xml").write_text(
            '<familyset><family name="sans-serif"><font weight="400">'
            'MiClock-Regular.ttf</font></family></familyset>', encoding="utf-8")
        args = self.scan_args(fonts, etc)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(scanner.scan(args), 0)
        previous = json.loads(args.output.read_text(encoding="utf-8"))
        previous.pop("metricsRevision")
        for entry in (*previous["slots"].values(), previous["mainSlot"]):
            entry["metrics"].pop("head")
        args.output.write_text(json.dumps(previous), encoding="utf-8")
        return args, args.output.read_bytes()

    def test_zero_descender_read_preserves_actual_bounds_and_file(self) -> None:
        original = self.path.read_bytes()
        fmt, metrics = inventory._read_metrics(self.path)
        self.assertEqual(fmt, "TTF")
        self.assertEqual(metrics["hhea"]["descent"], 0)
        self.assertEqual(metrics["hhea"]["ascent"], 900)
        self.assertEqual({key: metrics["head"][key] for key in ("xMin", "yMin", "xMax", "yMax")},
                         {"xMin": 40, "yMin": 100, "xMax": 640, "yMax": 700})
        self.assertIn("flags", metrics["head"])
        self.assertIn("lowestRecPPEM", metrics["head"])
        inventory.validate_inventory(fixture(metrics), "stock-metrics-test")
        self.assertEqual(self.path.read_bytes(), original, "a stock scan must never rewrite the font")

    def test_v3_scan_keeps_zero_descender_slot_as_main(self) -> None:
        fonts = self.root / "fonts"
        fonts.mkdir()
        self.path.rename(fonts / self.path.name)
        etc = self.root / "etc"
        etc.mkdir()
        (etc / "fonts.xml").write_text(
            '<familyset><family name="sans-serif"><font weight="400">'
            'MiClock-Regular.ttf</font></family></familyset>', encoding="utf-8")
        args = self.scan_args(fonts, etc)
        args.force = True
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(scanner.scan(args), 0)
        result = json.loads(args.output.read_text(encoding="utf-8"))
        inventory.validate_inventory(result, "stock-metrics-test")
        self.assertEqual(result["inventoryRevision"], 1)
        self.assertEqual(result["slotCount"], 1)
        self.assertEqual(result["mainSlot"]["metrics"]["hhea"]["descent"], 0)
        self.assertEqual(result["mainSlot"]["metrics"]["head"]["yMin"], 100)
        self.assertEqual(result["mainSlot"]["metrics"]["head"]["yMax"], 700)

    def test_legacy_metrics_automatically_refresh_once_from_stock_lower(self) -> None:
        args, previous = self.legacy_scan_fixture(trusted_lower=True)
        self.assertFalse(scanner._can_reuse(json.loads(previous), "stock-metrics-test"))
        env = {"LUOSHU_SELF_MOUNT_STATE_ROOT": str(self.root / "state"), "LUOSHU_STOCK_VIEW_VERIFIED": ""}
        with mock.patch.dict(scanner.os.environ, env), mock.patch.object(inventory, "MIRROR_PREFIXES", ()):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(scanner.scan(args), 0)
            refreshed = json.loads(args.output.read_text(encoding="utf-8"))
            self.assertEqual(refreshed["inventoryRevision"], 1)
            self.assertEqual(refreshed["metricsRevision"], scanner.METRICS_REVISION)
            self.assertEqual(refreshed["mainSlot"]["metrics"]["head"]["yMax"], 700)
            self.assertTrue(scanner._can_reuse(refreshed, "stock-metrics-test"))
            # A successful upgrade is frozen again rather than rescanning every time.
            (args.system_fonts / self.path.name).unlink()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(scanner.scan(args), 0)
            self.assertEqual(json.loads(stdout.getvalue())["status"], "reused")

    def test_metrics_refresh_cannot_read_unverified_live_fonts(self) -> None:
        args, previous = self.legacy_scan_fixture()
        env = {"LUOSHU_SELF_MOUNT_STATE_ROOT": str(self.root / "no-stock"), "LUOSHU_STOCK_VIEW_VERIFIED": ""}
        stderr = io.StringIO()
        with mock.patch.dict(scanner.os.environ, env), mock.patch.object(inventory, "MIRROR_PREFIXES", ()):
            with mock.patch.object(inventory, "_read_metrics") as reader, contextlib.redirect_stderr(stderr):
                self.assertEqual(scanner.scan(args), 2)
                reader.assert_not_called()
        self.assertEqual(args.output.read_bytes(), previous)
        inventory.validate_inventory(json.loads(previous), "stock-metrics-test")
        self.assertTrue(json.loads(stderr.getvalue())["retainedInventory"])
        self.assertTrue(json.loads(stderr.getvalue())["metricsRefreshPending"])

    def test_failed_lower_rescan_retains_old_valid_inventory_and_retry(self) -> None:
        args, previous = self.legacy_scan_fixture(trusted_lower=True)
        (args.system_fonts / self.path.name).write_bytes(b"broken stock font")
        env = {"LUOSHU_SELF_MOUNT_STATE_ROOT": str(self.root / "state"), "LUOSHU_STOCK_VIEW_VERIFIED": ""}
        with mock.patch.dict(scanner.os.environ, env), mock.patch.object(inventory, "MIRROR_PREFIXES", ()):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(scanner.scan(args), 2)
            self.assertEqual(args.output.read_bytes(), previous)
            make_font(args.system_fonts / self.path.name)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(scanner.scan(args), 0)
        self.assertEqual(json.loads(args.output.read_text())["metricsRevision"], scanner.METRICS_REVISION)

    def test_verified_pre_mount_hook_can_refresh_without_lower(self) -> None:
        args, previous = self.legacy_scan_fixture()
        args.force = True  # Matches stock_scan from the existing early-boot hook.
        make_font(args.system_fonts / self.path.name, ascent=950)
        with mock.patch.dict(scanner.os.environ, {"LUOSHU_STOCK_VIEW_VERIFIED": "1"}):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(scanner.scan(args), 0)
        refreshed = json.loads(args.output.read_text(encoding="utf-8"))
        self.assertEqual(refreshed["mainSlot"]["metrics"]["hhea"]["ascent"], 950)
        self.assertNotEqual(args.output.read_bytes(), previous)

    def test_partial_upgrade_does_not_erase_previously_known_slots(self) -> None:
        args, _previous = self.legacy_scan_fixture(trusted_lower=True)
        data = json.loads(args.output.read_text(encoding="utf-8"))
        known = copy.deepcopy(data["mainSlot"])
        known["path"] = "/system/fonts/MiClock-Missing.ttf"
        known["slotName"] = "MiClock-Missing.ttf"
        data["slots"][known["path"]] = known
        data["slotCount"] = len(data["slots"])
        args.output.write_text(json.dumps(data), encoding="utf-8")
        previous = args.output.read_bytes()
        env = {"LUOSHU_SELF_MOUNT_STATE_ROOT": str(self.root / "state"), "LUOSHU_STOCK_VIEW_VERIFIED": ""}
        with mock.patch.dict(scanner.os.environ, env), mock.patch.object(inventory, "MIRROR_PREFIXES", ()):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(scanner.scan(args), 2)
        self.assertEqual(args.output.read_bytes(), previous)

    def test_negative_descent_remains_valid_but_positive_and_invalid_ascent_do_not(self) -> None:
        for descent, ascent, accepted in ((-250, 900, True), (0, 900, True),
                                          (1, 900, False), (-250, 0, False), (-250, -1, False)):
            with self.subTest(descent=descent, ascent=ascent):
                make_font(self.path, descent=descent, ascent=ascent)
                if accepted:
                    _, metrics = inventory._read_metrics(self.path)
                    inventory.validate_inventory(fixture(metrics))
                else:
                    with self.assertRaises(inventory.InventoryError):
                        inventory._read_metrics(self.path)

    def test_legacy_inventory_without_head_remains_readable(self) -> None:
        _, metrics = inventory._read_metrics(self.path)
        metrics.pop("head")
        inventory.validate_inventory(fixture(metrics))
        metrics["hhea"]["descent"] = -250
        inventory.validate_inventory(fixture(metrics))

    def test_both_slot_and_main_reject_malformed_or_missing_baseline(self) -> None:
        _, metrics = inventory._read_metrics(self.path)
        invalid = (("descent", 1), ("descent", -32769), ("descent", -0.5),
                   ("descent", True), ("descent", None), ("descent", "invalid"),
                   ("descent", float("nan")), ("descent", float("inf")),
                   ("ascent", 0), ("ascent", -1), ("ascent", 32768),
                   ("upem", 0), ("upem", 15), ("upem", 16385))
        for target in ("slot", "main"):
            for field, value in (*invalid, ("descent", "missing")):
                with self.subTest(target=target, field=field, value=value):
                    data = fixture(metrics)
                    entry = data["mainSlot"] if target == "main" else next(iter(data["slots"].values()))
                    fields = entry["metrics"] if field == "upem" else entry["metrics"]["hhea"]
                    if value == "missing":
                        fields.pop(field)
                    else:
                        fields[field] = value
                    with self.assertRaises(inventory.InventoryError):
                        inventory.validate_inventory(data)

    def test_present_bounds_must_be_well_formed(self) -> None:
        _, metrics = inventory._read_metrics(self.path)
        for key, value in (("yMin", 701), ("xMax", 0), ("yMax", 32768), ("yMin", -32769),
                           ("yMin", 0.5), ("yMax", None)):
            with self.subTest(key=key, value=value):
                invalid = copy.deepcopy(metrics)
                invalid["head"][key] = value
                with self.assertRaises(inventory.InventoryError):
                    inventory.validate_inventory(fixture(invalid))


if __name__ == "__main__":
    unittest.main()
