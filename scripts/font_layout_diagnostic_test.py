#!/usr/bin/env python3
"""Read-only layout evidence: active/next separation, provenance and omissions."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock
import zipfile

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))
import font_layout_diagnostic as diag  # noqa: E402


def make_font(path: Path, top: int = 700) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    builder = FontBuilder(1000, isTTF=True)
    names = [".notdef"] + [f"g{i}" for i in range(len(diag.PROBES))]
    builder.setupGlyphOrder(names)
    builder.setupCharacterMap({ord(char): names[i + 1] for i, char in enumerate(diag.PROBES)})
    glyphs = {".notdef": TTGlyphPen(None).glyph()}
    for name in names[1:]:
        pen = TTGlyphPen(None)
        pen.moveTo((40, 20))
        pen.lineTo((540, 20))
        pen.lineTo((540, top))
        pen.lineTo((40, top))
        pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (600, 40) for name in names})
    builder.setupHorizontalHeader(ascent=900, descent=-200)
    builder.setupNameTable({"familyName": "Private-user-original-family",
                            "styleName": "Regular", "uniqueFontIdentifier": "Private-font-id",
                            "fullName": "Private-user-original-family Regular",
                            "psName": "Private-user-original-family-Regular"})
    builder.setupOS2(sTypoAscender=900, sTypoDescender=-200, usWinAscent=900, usWinDescent=200)
    builder.setupPost()
    builder.setupMaxp()
    builder.save(path)


def inventory_for(path: Path, logical: str) -> dict:
    metrics = diag.probe_font(path, 0)["metrics"]
    entry = {"slotName": Path(logical).name, "path": logical, "format": "TTF",
             "metrics": metrics, "faceIndex": 0, "actualPath": "/private/user-selected-font.ttf"}
    return {"schema": "device-font-inventory-v1", "state": "ready", "inventoryRevision": 1,
            "buildKey": "private-build-fingerprint", "buildFingerprint": "private-build-fingerprint",
            "slots": {logical: entry}, "slotCount": 1, "mainSlotPath": logical,
            "mainSlot": copy.deepcopy(entry)}


class LayoutDiagnosticTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luoshu-layout-diagnostic-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / "module"
        self.logical = "/system/fonts/MiSansVF.ttf"
        self.active = self.module / ".luoshu-payload" / self.logical.lstrip("/")
        self.mounted = self.root / self.logical.lstrip("/")
        self.next = self.module / ".luoshu-next-payload" / self.logical.lstrip("/")
        make_font(self.active, 700)
        make_font(self.next, 1100)
        self.mounted.parent.mkdir(parents=True)
        os.link(self.active, self.mounted)
        self.inventory_path = self.module / "config/device_font_inventory.json"
        self.inventory_path.parent.mkdir(parents=True)
        self.data = inventory_for(self.active, self.logical)
        self.inventory_path.write_text(json.dumps(self.data), encoding="utf-8")
        build = mock.patch.object(diag, "current_build_key", return_value="private-build-fingerprint")
        build.start()
        self.addCleanup(build.stop)

    def collect(self, apps=False, budget=3):
        return diag.Collector(self.module, self.root, budget).collect(include_apps=apps)

    def test_active_payload_is_probed_once_and_sources_remain_unchanged(self):
        originals = {path: hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in (self.active, self.mounted, self.next, self.inventory_path)}
        with mock.patch.object(diag, "probe_font", wraps=diag.probe_font) as probe:
            report = self.collect()
        self.assertEqual(report["status"], "complete")
        slot = report["slots"][0]
        self.assertEqual(slot["activePayload"]["profile"], slot["mountedInCollector"]["profile"])
        self.assertEqual(probe.call_count, 1)
        profile = report["profiles"][0]
        self.assertEqual(profile["probes"]["中"]["bounds"], [40, 20, 540, 700])
        self.assertEqual(profile["metrics"]["head"]["yMax"], 700)
        self.assertEqual(slot["stock"]["glyphs"]["status"], "trusted-stock-file-unavailable")
        for path, digest in originals.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
        text = json.dumps(report)
        for secret in ("private-build-fingerprint", "Private-user-original-family", "/private/",
                       ".luoshu-next-payload", str(self.root)):
            self.assertNotIn(secret, text)
        self.assertFalse(report["limitations"]["appSelectedTypefaceCollected"])

    def test_missing_live_never_substitutes_next(self):
        self.active.unlink()
        self.mounted.unlink()
        report = self.collect()
        self.assertEqual(report["slots"][0]["activePayload"]["status"], "missing")
        self.assertEqual(report["profiles"], [])
        self.assertTrue(self.next.is_file())

    def test_missing_and_stale_inventory_are_reported_without_invented_stock(self):
        self.inventory_path.unlink()
        report = self.collect()
        self.assertEqual(report["inventory"]["status"], "missing")
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["slots"][0]["stock"]["status"], "missing-inventory-slot")
        self.data["buildKey"] = "old-build"
        self.inventory_path.write_text(json.dumps(self.data), encoding="utf-8")
        report = self.collect()
        self.assertEqual(report["inventory"]["status"], "build-mismatch")
        self.assertNotIn("metrics", report["slots"][0]["stock"])

    def test_zero_descent_and_trusted_stock_probe_remain_distinct(self):
        entry = self.data["slots"][self.logical]
        entry["metrics"]["hhea"]["descent"] = 0
        self.data["mainSlot"] = copy.deepcopy(entry)
        self.inventory_path.write_text(json.dumps(self.data), encoding="utf-8")
        lower = self.root / "data/adb/luoshu/self-mount/lower/system-fonts/MiSansVF.ttf"
        make_font(lower, 820)
        report = self.collect()
        slot = report["slots"][0]
        self.assertEqual(slot["stock"]["metrics"]["hhea"]["descent"], 0)
        profile_id = slot["stock"]["glyphs"]["profile"]
        profile = next(p for p in report["profiles"] if p["id"] == profile_id)
        self.assertEqual(profile["probes"]["岁"]["bounds"][3], 820)

    def test_processing_report_comes_only_from_active_and_exports_allowlisted_fields(self):
        filename = ".luoshu-metrics-report.json"
        active_report = self.module / ".luoshu-payload" / filename
        active_report.write_text(json.dumps({"schema": "luoshu-slot-metrics-v1", "slots": [{
            "slot": self.logical, "metricsSource": "stock", "layoutBoundsSource": "source",
            "cjkRoutingSource": "stock-fallback", "cjkRoutingReason": "stock-latin-primary",
            "removedCjkMappings": 123,
            "source": "/sdcard/LuoShu/fonts/Private-original.ttf"}]}), encoding="utf-8")
        (self.module / ".luoshu-next-payload" / filename).write_text(json.dumps({
            "schema": "luoshu-slot-metrics-v1", "slots": [{"slot": self.logical,
                "metricsSource": "fallback", "layoutBoundsSource": "stock"}]}), encoding="utf-8")
        report = self.collect()
        observed = report["slots"][0]["processing"]
        self.assertEqual(observed["metricsSource"], "stock")
        self.assertEqual(observed["layoutBoundsSource"], "source")
        self.assertEqual(observed["cjkRoutingSource"], "stock-fallback")
        self.assertEqual(observed["cjkRoutingReason"], "stock-latin-primary")
        self.assertEqual(observed["removedCjkMappings"], 123)
        self.assertNotIn("Private-original", json.dumps(report))

    def test_processing_cjk_fields_reject_unknown_labels_and_invalid_counts(self):
        path = self.module / ".luoshu-payload/.luoshu-metrics-report.json"
        for count in (True, -1, 0x110001, "42", 1.5, None):
            path.write_text(json.dumps({"schema": "luoshu-slot-metrics-v1", "slots": [{
                "slot": self.logical, "cjkRoutingSource": "private-source-name",
                "cjkRoutingReason": {"private-file-path": "/sdcard/private-font.ttf"},
                "removedCjkMappings": count}]}), encoding="utf-8")
            report = self.collect()
            observed = report["slots"][0]["processing"]
            self.assertEqual(observed["cjkRoutingSource"], "unknown")
            self.assertEqual(observed["cjkRoutingReason"], "unknown")
            self.assertNotIn("removedCjkMappings", observed)
            self.assertNotIn("private-source-name", json.dumps(report))
            self.assertNotIn("private-font.ttf", json.dumps(report))

    def test_stock_coverage_uses_validated_allowlisted_fields_only(self):
        coverage = {"hasHan": True, "hasLatin": True, "hanCount": 6, "latinCount": 4,
                    "unicodeCount": 18, "cjkPunctuation": [0x3002],
                    "privateSource": "/sdcard/private-font.ttf"}
        entry = self.data["slots"][self.logical]
        entry["metrics"]["coverage"] = coverage
        self.data["mainSlot"] = copy.deepcopy(entry)
        self.inventory_path.write_text(json.dumps(self.data), encoding="utf-8")
        report = self.collect()
        observed = report["slots"][0]["stock"]["metrics"]["coverage"]
        self.assertEqual(observed, {key: coverage[key] for key in diag.COVERAGE_FIELDS})
        self.assertNotIn("privateSource", json.dumps(report))
        self.assertNotIn("private-font.ttf", json.dumps(report))
        coverage["hanCount"] = True
        self.data["mainSlot"] = copy.deepcopy(entry)
        self.inventory_path.write_text(json.dumps(self.data), encoding="utf-8")
        report = self.collect()
        self.assertEqual(report["inventory"]["status"], "invalid")
        self.assertNotIn("metrics", report["slots"][0]["stock"])

    def test_apk_lists_font_candidates_without_reading_members_or_install_tokens(self):
        apk = self.root / "data/app/private-install-token/base.apk"
        apk.parent.mkdir(parents=True)
        with zipfile.ZipFile(apk, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("assets/fonts/Stopwatch.ttf", b"not executed or decompressed")
            archive.writestr("assets/MiClock.otf", b"unused bytes")
            archive.writestr("res/font/timer.ttf", b"unused bytes")
            archive.writestr("assets/fonts/../../private.ttf", b"unused bytes")
            archive.writestr("assets/messages.json", b"private-data")
            archive.writestr("classes.dex", b"unused bytes")
        def pm(args, timeout=0.6):
            self.assertEqual(args[:2], ["pm", "path"])
            self.assertIn(args[2], diag.PACKAGES)
            return ("ok", "package:/data/app/private-install-token/base.apk\n")
        with mock.patch.object(diag, "command", side_effect=pm), \
                mock.patch.object(zipfile.ZipFile, "open", side_effect=AssertionError("must not read APK members")):
            report = self.collect(apps=True)
        self.assertEqual(len(report["apps"]), 4)
        names = report["apps"][0]["apks"][0]["fontAssets"]
        self.assertEqual(names, ["assets/MiClock.otf", "assets/fonts/Stopwatch.ttf", "res/font/timer.ttf"])
        for secret in ("private-install-token", "messages.json", "classes.dex", "private-data"):
            self.assertNotIn(secret, json.dumps(report))

    def test_budget_preserves_partial_results_instead_of_claiming_success(self):
        def slow(_path, _face):
            time.sleep(0.2)
            raise AssertionError("deadline did not interrupt")
        start = time.monotonic()
        with mock.patch.object(diag, "probe_font", side_effect=slow):
            report = self.collect(budget=0.04)
        self.assertLess(time.monotonic() - start, 0.18)
        self.assertEqual(report["status"], "partial")
        self.assertIn("time-budget-exhausted", report["errors"])
        self.assertEqual(report["profiles"][0]["status"], "interrupted")

    def test_selection_keeps_main_slot_plus_at_most_twenty_four_others(self):
        for n in range(45):
            os.link(self.active, self.active.with_name(f"Roboto-UI-{n}.ttf"))
        report = self.collect()
        self.assertEqual(report["selection"]["selectedCount"], 25)
        self.assertEqual(report["slots"][0]["slot"], self.logical)
        self.assertGreater(report["selection"]["omittedCount"], 0)
        self.assertEqual(report["profileCount"], 1)


if __name__ == "__main__":
    unittest.main()
