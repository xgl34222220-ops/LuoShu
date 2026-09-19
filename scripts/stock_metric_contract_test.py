#!/usr/bin/env python3
"""Exercise the stock scanner with real zero-descender and malformed fonts."""
from __future__ import annotations

import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection, TTFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))
import font_inventory as inventory  # noqa: E402
import font_inventory_scan_v3 as scanner  # noqa: E402
from hyperos_physical_policy import safe_physical_font_name  # noqa: E402


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

    def physical_scan_fixture(self, *, coloros: bool = False, trusted_lower: bool = False):
        prefix = self.root / "state/lower" if trusted_lower else self.root / "physical"
        fonts, etc = prefix / "system-fonts", prefix / "system-etc"
        fonts.mkdir(parents=True)
        etc.mkdir(parents=True)
        main = "SysSans-Hans-Regular.ttf" if coloros else "MiSansVF.ttf"
        make_font(fonts / main, descent=-282, ascent=1044)
        values = {"NotoSansSC-VF.otf": (1250, -300), "NotoSansTC-Regular.otf": (1190, -290),
                  "NotoSans-Regular.ttf": (930, -250), "MiLanProVF.ttf": (980, -220),
                  "XiaomiSansVF.ttf": (1150, -310), "DroidSans.ttf": (1020, -260),
                  # Restored UI targets must retain their own stock contracts.
                  "DroidSansMono.ttf": (1100, -240), "DroidSansFallback.ttf": (980, -270),
                  "NotoSansMono-Regular.ttf": (1024, -256),
                  "NotoSansDisplay-Regular.otf": (1040, -280),
                  "NotoSansSemiCondensed-Regular.ttf": (950, -210),
                  "NotoSansVF.ttf": (1080, -300)}
        for name, (ascent, descent) in values.items():
            path = fonts / name
            make_font(path, ascent=ascent, descent=descent)
            if name.startswith(("NotoSansSC", "NotoSansTC")):
                with TTFont(path) as font:
                    for table in font["cmap"].tables:
                        if table.isUnicode():
                            table.cmap[0x4E2D] = "zero"
                    font.save(path)
        (etc / "font_fallback.xml").write_text(
            f'<familyset><family name="sans-serif"><font>{main}</font></family>'
            '<family lang="zh-Hans"><font>NotoSansSC-VF.otf</font></family>'
            '<family lang="zh-Hant"><font>NotoSansTC-Regular.otf</font></family>'
            '</familyset>', encoding="utf-8")
        args = self.scan_args(fonts, etc)
        return args, values

    def test_hyperos_collects_physical_cjk_fallback_and_hidden_oem_contracts(self) -> None:
        args, values = self.physical_scan_fixture()
        original = {name: (args.system_fonts / name).read_bytes() for name in values}
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(scanner.scan(args), 0)
        result = json.loads(args.output.read_text())
        self.assertEqual(result["romKind"], "hyperos")
        self.assertEqual(result["hyperosCoverageRevision"], scanner.HYPEROS_COVERAGE_REVISION)
        for name, (ascent, descent) in values.items():
            with self.subTest(name=name):
                entry = result["slots"][f"/system/fonts/{name}"]
                self.assertEqual(entry["source"], "hyperos-physical")
                self.assertEqual((entry["metrics"]["hhea"]["ascent"], entry["metrics"]["hhea"]["descent"]),
                                 (ascent, descent))
                self.assertIn("head", entry["metrics"])
                self.assertTrue(inventory.valid_coverage(entry["metrics"]["coverage"]))
                self.assertEqual((args.system_fonts / name).read_bytes(), original[name])
        self.assertTrue(result["slots"]["/system/fonts/NotoSansSC-VF.otf"]["metrics"]["coverage"]["hasHan"])
        self.assertTrue(scanner._can_reuse(result, "stock-metrics-test"))

    def test_coloros_keeps_original_scope_with_unused_xiaomi_and_cjk_files(self) -> None:
        args, _values = self.physical_scan_fixture(coloros=True)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(scanner.scan(args), 0)
        result = json.loads(args.output.read_text())
        self.assertEqual(result["romKind"], "coloros")
        self.assertEqual(set(result["slots"]), {"/system/fonts/SysSans-Hans-Regular.ttf"})
        result.pop("hyperosCoverageRevision")
        self.assertTrue(scanner._can_reuse(result, "stock-metrics-test"),
                        "this HyperOS-only refresh must not invalidate ColorOS metrics")

    def add_unused_misans_to_coloros(self, args) -> None:
        make_font(args.system_fonts / "MiSansVF.ttf", ascent=1044, descent=-282)
        xml = args.system_etc / "font_fallback.xml"
        xml.write_text(xml.read_text().replace(
            "</familyset>", '<family name="system-ui"><font>MiSansVF.ttf</font></family></familyset>'
        ))

    def assert_coloros_with_misans_does_not_expand(self, args) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(scanner.scan(args), 0)
        result = json.loads(args.output.read_text())
        self.assertEqual(set(result["slots"]), {
            "/system/fonts/SysSans-Hans-Regular.ttf", "/system/fonts/MiSansVF.ttf",
        })
        self.assertEqual(result["mainSlotPath"], "/system/fonts/SysSans-Hans-Regular.ttf")
        self.assertEqual(result["romKind"], "coloros")
        self.assertTrue(scanner._can_reuse(result, "stock-metrics-test"))

    def test_initial_coloros_scan_with_misans_does_not_expand_hyperos_scope(self) -> None:
        args, _values = self.physical_scan_fixture(coloros=True)
        self.add_unused_misans_to_coloros(args)
        self.assert_coloros_with_misans_does_not_expand(args)

    def test_existing_coloros_inventory_with_misans_does_not_expand_hyperos_scope(self) -> None:
        args, _values = self.physical_scan_fixture(coloros=True)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(scanner.scan(args), 0)
        previous = json.loads(args.output.read_text())
        previous.pop("hyperosCoverageRevision")
        self.assertEqual(previous["romKind"], "coloros")
        args.output.write_text(json.dumps(previous))
        self.add_unused_misans_to_coloros(args)
        args.force = True  # Matches an installer/manual rescan of a valid old inventory.
        self.assert_coloros_with_misans_does_not_expand(args)

    def test_property_detected_coloros_retires_legacy_alias_even_when_inventory_was_generic(self) -> None:
        args, _previous = self.legacy_scan_fixture()
        data = json.loads(args.output.read_text(encoding="utf-8"))
        data["romKind"] = "generic"
        stale_path = "/system/fonts/SysFont-Static-Regular.ttf"
        stale = copy.deepcopy(data["mainSlot"])
        stale["path"] = stale_path
        stale["slotName"] = "SysFont-Static-Regular.ttf"
        stale["source"] = "heuristic"
        data["slots"][stale_path] = stale
        data["slotCount"] = len(data["slots"])
        data["metricsRevision"] = scanner.METRICS_REVISION - 1
        args.output.write_text(json.dumps(data), encoding="utf-8")
        args.force = True

        def fake_getprop(name: str) -> str:
            return "V16.1.0" if name == "ro.build.version.oplusrom" else ""

        with mock.patch.object(inventory, "_getprop", side_effect=fake_getprop), \
             mock.patch.dict(scanner.os.environ, {"LUOSHU_STOCK_VIEW_VERIFIED": "1"}):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(scanner.scan(args), 0)
        refreshed = json.loads(args.output.read_text(encoding="utf-8"))
        self.assertEqual(refreshed["romKind"], "coloros")
        self.assertNotIn(stale_path, refreshed["slots"])
        self.assertIn(stale_path, refreshed["retiredAbsentUpgradeSlots"])

    def test_fresh_install_scan_ignores_contaminated_previous_inventory(self) -> None:
        args, _values = self.physical_scan_fixture(coloros=True)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(scanner.scan(args), 0)
        previous = json.loads(args.output.read_text(encoding="utf-8"))
        stale_path = "/system/fonts/SysFont-Static-Regular.ttf"
        stale = copy.deepcopy(previous["mainSlot"])
        stale["path"] = stale_path
        stale["slotName"] = "SysFont-Static-Regular.ttf"
        stale["source"] = "heuristic"
        previous["slots"][stale_path] = stale
        previous["slotCount"] = len(previous["slots"])
        args.output.write_text(json.dumps(previous), encoding="utf-8")
        args.force = True

        def fake_getprop(name: str) -> str:
            return "V16.1.0" if name == "ro.build.version.oplusrom" else ""

        with mock.patch.object(inventory, "_getprop", side_effect=fake_getprop), \
             mock.patch.dict(scanner.os.environ, {"LUOSHU_FRESH_STOCK_SCAN": "1"}):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(scanner.scan(args), 0)

        refreshed = json.loads(args.output.read_text(encoding="utf-8"))
        self.assertEqual(refreshed["romKind"], "coloros")
        self.assertNotIn(stale_path, refreshed["slots"])
        self.assertFalse(refreshed.get("retiredAbsentUpgradeSlots"),
                         "fresh install scan must not depend on previous inventory retirement")

    def test_coloros_upgrade_retires_overlay_only_alias_absent_from_verified_stock(self) -> None:
        args, _values = self.physical_scan_fixture(coloros=True)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(scanner.scan(args), 0)
        previous = json.loads(args.output.read_text())

        stale_path = "/system/fonts/SysFont-Static-Regular.ttf"
        stale = copy.deepcopy(previous["mainSlot"])
        stale["path"] = stale_path
        stale["slotName"] = "SysFont-Static-Regular.ttf"
        stale["source"] = "heuristic"
        previous["slots"][stale_path] = stale
        previous["slotCount"] = len(previous["slots"])
        previous["metricsRevision"] = scanner.METRICS_REVISION - 1
        args.output.write_text(json.dumps(previous), encoding="utf-8")
        args.force = True

        with mock.patch.dict(scanner.os.environ, {"LUOSHU_STOCK_VIEW_VERIFIED": "1"}):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(scanner.scan(args), 0)
        refreshed = json.loads(args.output.read_text(encoding="utf-8"))
        self.assertNotIn(stale_path, refreshed["slots"])
        self.assertIn(stale_path, refreshed["retiredAbsentUpgradeSlots"])

    def test_hyperos_extra_collection_obeys_mapper_partitions_and_font_exclusions(self) -> None:
        args, _values = self.physical_scan_fixture()
        excluded = ("NotoSansCJKJP.otf", "NotoSansCJKKR.otf", "NotoSansArabic-Regular.ttf",
                    "NotoSansThai-Regular.ttf", "NotoSans-RegularItalic.ttf", "NotoSansSymbols.ttf",
                    "NotoSansSC-Regular.ttc", "NotoSansEmoji.ttf", "NotoSansAdlam-VF.ttf",
                    "NotoSansAhom-Regular.otf", "NotoSansCuneiform-Regular.ttf",
                    "NotoSansEgyptianHieroglyphs-Regular.ttf", "MiSansOdiaVF.ttf",
                    "NotoSansSemiCondensed-Icons.ttf", "NotoSansMono-Italic.ttf")
        for name in excluded:
            make_font(args.system_fonts / name)
        disguised_collection = "NotoSansCollection.ttf"
        with TTFont(args.system_fonts / "MiSansVF.ttf") as font:
            collection = TTCollection()
            collection.fonts = [font]
            collection.save(args.system_fonts / disguised_collection)
        for partition in ("mi_ext", "product", "oplus_product"):
            directory = self.root / partition / "fonts"
            directory.mkdir(parents=True)
            make_font(directory / "NotoSansSC-Regular.otf", ascent=1190, descent=-290)
            setattr(args, f"{partition}_fonts", directory)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(scanner.scan(args), 0)
        slots = json.loads(args.output.read_text())["slots"]
        for name in (*excluded, disguised_collection):
            self.assertNotIn(f"/system/fonts/{name}", slots)
        self.assertIn("/system/fonts/DroidSansMono.ttf", slots)
        self.assertIn("/system/fonts/NotoSansSemiCondensed-Regular.ttf", slots)
        self.assertIn("/mi_ext/fonts/NotoSansSC-Regular.otf", slots)
        self.assertIn("/product/fonts/NotoSansSC-Regular.otf", slots)
        self.assertNotIn("/oplus_product/fonts/NotoSansSC-Regular.otf", slots)

    def test_hyperos_additional_alias_reads_stock_partition_and_rejects_theme_target(self) -> None:
        args, _values = self.physical_scan_fixture()
        product = self.root / "stock-product/fonts"
        product.mkdir(parents=True)
        make_font(product / "OriginalCjk.ttf", ascent=1270, descent=-330)
        args.product_fonts = product
        alias = args.system_fonts / "NotoSansSC-VF.otf"
        alias.unlink()
        alias.symlink_to("/product/fonts/OriginalCjk.ttf")
        theme = self.root / "theme-font.ttf"
        make_font(theme, ascent=1600, descent=-500)
        theme_alias = args.system_fonts / "NotoSansTheme.ttf"
        theme_alias.symlink_to(theme)
        with mock.patch.object(inventory, "_read_metrics", wraps=inventory._read_metrics) as reader:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(scanner.scan(args), 0)
        result = json.loads(args.output.read_text())
        entry = result["slots"]["/system/fonts/NotoSansSC-VF.otf"]
        self.assertEqual(entry["slotName"], "NotoSansSC-VF.otf")
        self.assertEqual(entry["metrics"]["hhea"]["ascent"], 1270)
        self.assertEqual(entry["metrics"]["hhea"]["descent"], -330)
        self.assertNotIn("/system/fonts/NotoSansTheme.ttf", result["slots"])
        paths = [Path(call.args[0]) for call in reader.call_args_list]
        self.assertIn(product / "OriginalCjk.ttf", paths)
        self.assertNotIn(theme, paths)
        self.assertNotIn(alias, paths)

    def test_hyperos_dynamic_webview_alias_is_preserved_without_reading_data(self) -> None:
        args, _values = self.physical_scan_fixture()
        logical = "/system/fonts/MiSansVF_Overlay.ttf"
        target = "/data/system/fonts/theme_webview/Roboto-Regular.ttf"
        overlay = args.system_fonts / "MiSansVF_Overlay.ttf"
        overlay.symlink_to(target)
        with mock.patch.object(inventory, "_read_metrics", wraps=inventory._read_metrics) as reader:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(scanner.scan(args), 0)
        result = json.loads(args.output.read_text())
        self.assertNotIn(logical, result["slots"])
        self.assertEqual(result["preservedDynamicAliases"][logical], {
            "source": "hyperos-framework-symlink", "target": target})
        self.assertTrue(scanner._can_reuse(result, "stock-metrics-test"))
        paths = [Path(call.args[0]) for call in reader.call_args_list]
        self.assertNotIn(Path(target), paths)
        self.assertNotIn(overlay, paths)

        # Test6's valid-shaped Roboto assumption migrates to a preserved alias;
        # no other old slot may disappear through this exception.
        previous = copy.deepcopy(result)
        previous["hyperosCoverageRevision"] = 1
        previous.pop("preservedDynamicAliases")
        previous["slots"][logical] = {**copy.deepcopy(previous["mainSlot"]),
            "path": logical, "slotName": "MiSansVF_Overlay.ttf",
            "source": "hyperos-rom-reference",
            "metricsReferencePath": "/system/fonts/Roboto-Regular.ttf"}
        previous["slotCount"] = len(previous["slots"])
        args.output.write_text(json.dumps(previous))
        with mock.patch.dict(scanner.os.environ, {"LUOSHU_STOCK_VIEW_VERIFIED": "1"}):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(scanner.scan(args), 0)
        refreshed = json.loads(args.output.read_text())
        self.assertNotIn(logical, refreshed["slots"])
        self.assertIn(logical, refreshed["preservedDynamicAliases"])
        self.assertTrue(scanner._can_reuse(refreshed, "stock-metrics-test"))

        overlay.unlink()
        overlay.symlink_to("/data/system/fonts/theme_webview/Other.ttf")
        args.output = self.root / "different-theme-target.json"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(scanner.scan(args), 0)
        different = json.loads(args.output.read_text())
        self.assertNotIn(logical, different["slots"])
        self.assertNotIn(logical, different["preservedDynamicAliases"])

        # A real Overlay font on another ROM keeps its own original contract.
        overlay.unlink()
        make_font(overlay, ascent=1110, descent=-310)
        args.output = self.root / "static-overlay.json"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(scanner.scan(args), 0)
        static = json.loads(args.output.read_text())
        self.assertEqual(static["slots"][logical]["metrics"]["hhea"]["ascent"], 1110)
        self.assertNotIn(logical, static["preservedDynamicAliases"])

    def old_physical_inventory(self, args) -> bytes:
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(scanner.scan(args), 0)
        data = json.loads(args.output.read_text())
        data.pop("hyperosCoverageRevision")
        data["slots"] = {path: entry for path, entry in data["slots"].items()
                         if entry["source"] != "hyperos-physical"}
        data["slotCount"] = len(data["slots"])
        args.output.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue(scanner._has_current_metrics(data), "this fixture already has Test4 metrics")
        self.assertFalse(scanner._can_reuse(data, "stock-metrics-test"))
        return args.output.read_bytes()

    def test_hyperos_coverage_upgrade_requires_stock_lower_even_with_current_metrics(self) -> None:
        args, _values = self.physical_scan_fixture()
        previous = self.old_physical_inventory(args)
        env = {"LUOSHU_SELF_MOUNT_STATE_ROOT": str(self.root / "no-stock"), "LUOSHU_STOCK_VIEW_VERIFIED": ""}
        with mock.patch.dict(scanner.os.environ, env), mock.patch.object(inventory, "MIRROR_PREFIXES", ()):
            with mock.patch.object(inventory, "_read_metrics") as reader, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(scanner.scan(args), 2)
                reader.assert_not_called()
        self.assertEqual(args.output.read_bytes(), previous)

    def test_hyperos_coverage_upgrade_adds_slots_from_verified_lower_and_then_reuses(self) -> None:
        args, values = self.physical_scan_fixture(trusted_lower=True)
        self.old_physical_inventory(args)
        env = {"LUOSHU_SELF_MOUNT_STATE_ROOT": str(self.root / "state"), "LUOSHU_STOCK_VIEW_VERIFIED": ""}
        with mock.patch.dict(scanner.os.environ, env), mock.patch.object(inventory, "MIRROR_PREFIXES", ()):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(scanner.scan(args), 0)
            data = json.loads(args.output.read_text())
            self.assertTrue(scanner._can_reuse(data, "stock-metrics-test"))
            self.assertEqual(data["metricsRevision"], 3)
            self.assertTrue(all(f"/system/fonts/{name}" in data["slots"] for name in values))
            with mock.patch.object(inventory, "_read_metrics") as reader, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(scanner.scan(args), 0)
                reader.assert_not_called()

    def test_hyperos_partial_coverage_upgrade_retains_old_inventory(self) -> None:
        args, _values = self.physical_scan_fixture(trusted_lower=True)
        previous = self.old_physical_inventory(args)
        (args.system_fonts / "MiSansVF.ttf").write_bytes(b"invalid original font")
        env = {"LUOSHU_SELF_MOUNT_STATE_ROOT": str(self.root / "state"), "LUOSHU_STOCK_VIEW_VERIFIED": ""}
        with mock.patch.dict(scanner.os.environ, env), mock.patch.object(inventory, "MIRROR_PREFIXES", ()):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(scanner.scan(args), 2)
        self.assertEqual(args.output.read_bytes(), previous)

    def test_hyperos_physical_name_policy_matches_actual_shell_mapper(self) -> None:
        names = ("MiSansVF.ttf", "MiSansNewVF.otf", "MiSansLatinVF.ttf", "XiaomiSansVF.ttf", "MiLanProVF.ttf",
                 "NotoSansSC-VF.otf", "NotoSansTC-Regular.otf", "NotoSans-Regular.ttf", "DroidSans.ttf", "DroidSans.otf",
                 "MiClock.otf", "MitypeMonoVF.ttf", "GoogleSansText-VF.ttf", "RobotoFlex-Regular.ttf",
                 "Clockopia.ttf", "100.ttf", "350.ttf", "950.ttf", "NotoSansCJKJP.otf", "NotoSansCJKKR.otf",
                 "MiSansJPVF.ttf", "MiSansKrVF.ttf", "NotoSans-RegularItalic.ttf", "NotoSansSymbols.ttf",
                 "NotoSansSC.ttc", "NotoSansArabic.ttf", "MiSansThaiVF.ttf", "NotoSansDevanagari.ttf",
                 "NotoSansVietnamese.ttf", "NotoSansJapanese.ttf", "NotoSansHangul.ttf", "NotoSansEmoji.ttf",
                 "NotoSansAdlam-VF.ttf", "NotoSansAhom-Regular.otf", "NotoSansCuneiform-Regular.ttf",
                 "NotoSansEgyptianHieroglyphs-Regular.ttf", "MiSansOdiaVF.ttf", "DroidSansMono.ttf",
                 "NotoSansUI.ttf", "NotoSansCJKsc-Regular.otf", "NotoSansCJKTC-VF.otf",
                 "NotoSansHK-Regular.otf", "NotoSansHant-Regular.otf", "DroidSans-Regular.ttf",
                 "SysSans-Hans-Regular.ttf", "Roboto-Regular.TTF", "misansnew.ttf")
        command = '\n'.join((
            '. "$1"', 'shift', 'for name in "$@"', 'do',
            '    if _lhcc_safe_dynamic_name "$name"; then echo yes; else echo no; fi', 'done',
        ))
        result = subprocess.run(
            ["sh", "-c", command, "policy-check", str(ROOT / "common/legacy_v14_4/hyperos_full_coverage.sh"), *names],
            env={**os.environ, "LUOSHU_REAL_MODDIR": str(ROOT)}, capture_output=True, text=True, check=True,
        )
        actual = [value == "yes" for value in result.stdout.splitlines()]
        self.assertEqual(len(actual), len(names))
        self.assertEqual(actual, [safe_physical_font_name(name) for name in names])


if __name__ == "__main__":
    unittest.main()
