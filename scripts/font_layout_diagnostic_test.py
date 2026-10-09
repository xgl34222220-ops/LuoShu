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


class MixTimingDiagnosticTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luoshu-mix-diagnostic-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / "module"
        self.log = self.module / "logs/fontswitch.log"
        self.log.parent.mkdir(parents=True)
        self.boot = "12345678-1234-1234-1234-123456789abc"
        bootfile = self.root / "proc/sys/kernel/random/boot_id"
        bootfile.parent.mkdir(parents=True)
        bootfile.write_text(self.boot + "\n")
        self.request = "mix-request-1800000000-123"
        self.outer = "axes-1800000000-123"
        self.receipt = self.module / ".luoshu-state/tasks/axes_worker.pid.cleanup.json"
        self.receipt.parent.mkdir(parents=True)
        self.proof = dict(schema="task-cleanup-v2", task=self.outer, boot=self.boot, start="56789",
                          durationSeconds=1.25, result=0, cleaned=True, leftoverPids=[], cleanupErrors=[],
                          reason="completed", private="/private/source/path")
        self.receipt.write_text(json.dumps(self.proof))

    def event(self, kind="begin", **changes):
        fields = dict(schema="1", request=self.request, outer=self.outer, task=self.outer,
                      boot=self.boot, start="56789", component="worker", phase="worker_finalize",
                      unit="fixed", weight="fixed", clock="proc-uptime", event=kind,
                      method="finalize", uptimeSeconds="100.00" if kind == "begin" else "200.00")
        if kind == "end":
            fields.update(elapsedMs="100000", result="ok")
        fields.update(changes)
        return "[MIX-PHASE] " + " ".join(f"{name}={value}" for name, value in fields.items())

    def collect(self, lines=None):
        if lines is not None:
            self.log.write_text("\n".join(lines) + "\n")
        return diag.collect_mix_timings(self.module, self.root)

    def pair(self):
        return [self.event(), self.event("end")]

    def safe(self, **changes):
        fields = dict(task=self.outer, event="begin", phase="initialization", scope="safe-switch-worker",
                      clock="proc-uptime", uptime="110.00")
        fields.update(changes)
        return "[SAFE-TIMING] " + " ".join(f"{key}={value}" for key, value in fields.items())

    def safe_lines(self):
        return [self.safe(),
                f"[SAFE-TIMING] task={self.outer} event=end phase=initialization status=completed uptime=111.00 elapsedMs=1000",
                f"[SAFE-TIMING] task={self.outer} event=begin phase=map_rom uptime=111.00",
                f"[SAFE-TIMING] task={self.outer} event=end phase=map_rom status=completed uptime=112.00 elapsedMs=1000",
                f"[SAFE-TIMING] task={self.outer} event=total scope=safe-switch-worker status=completed result=0 uptime=112.00 elapsedMs=2000"]

    def test_exact_boot_start_task_proof_exports_anonymous_separate_scopes(self):
        report = self.collect(self.pair())
        latest = report["requests"][0]
        self.assertEqual(latest["phases"][0]["elapsedMs"], 100000)
        self.assertEqual(latest["backendTotal"]["durationSeconds"], 1.25)
        self.assertEqual(latest["backendTotal"]["clock"], "python-monotonic")
        self.assertEqual(report["phaseClock"], "proc-uptime")
        self.assertTrue(report["overlappingScopesAreNotAdditive"])
        for secret in (self.outer, self.request, self.boot, "56789", "/private/", str(self.root), "100.00"):
            self.assertNotIn(secret, json.dumps(report))

    def test_stale_receipt_task_boot_start_and_nonfinite_duration_never_match(self):
        for name, value in (("task", "axes-1800000000-999"), ("start", "999"),
                            ("boot", "00000000-0000-0000-0000-000000000000"),
                            ("durationSeconds", float("nan")), ("durationSeconds", float("inf")),
                            ("durationSeconds", 10 ** 400),
                            ("durationSeconds", True), ("result", True), ("durationSeconds", -1),
                            ("leftoverPids", [999]), ("cleanupErrors", ["private-error"])):
            with self.subTest(field=name, value=value):
                self.receipt.write_text(json.dumps({**self.proof, name: value}))
                report = self.collect(self.pair())
                self.assertEqual(report["requests"][0]["backendTotal"]["status"], "unavailable")
                self.assertNotIn("private-error", json.dumps(report))

    def test_missing_duration_parent_cleanup_duplicate_or_oversize_proof_unavailable(self):
        proof = {**self.proof, "reason": "parent-cleanup"}; del proof["durationSeconds"]
        for text in (json.dumps(proof), json.dumps(self.proof)[:-1] + ', "task": "axes-1800000000-123"}',
                     json.dumps({**self.proof, "padding": "x" * 16384})):
            with self.subTest(bytes=len(text)):
                self.receipt.write_text(text)
                self.assertEqual(self.collect(self.pair())["requests"][0]["backendTotal"]["status"], "unavailable")

    def test_cross_boot_events_unknown_start_and_conflicting_outer_are_not_totals(self):
        report = self.collect([self.event(boot="00000000-0000-0000-0000-000000000000")])
        self.assertEqual(report["status"], "unavailable")
        self.assertEqual(report["rejectedEvents"], 1)
        report = self.collect([self.event(start="unknown"), self.event("end", start="unknown")])
        self.assertEqual(report["requests"][0]["phases"][0]["status"], "complete")
        self.assertEqual(report["requests"][0]["backendTotal"]["status"], "unavailable")
        report = self.collect([self.event(), self.event("end", outer="axes-1800000000-456")])
        self.assertEqual(report["requests"], [])

    def test_cancelled_begin_is_incomplete_and_bad_end_is_unavailable(self):
        self.receipt.write_text(json.dumps({**self.proof, "result": 143, "reason": "cancelled"}))
        report = self.collect([self.event()])
        latest = report["requests"][0]
        self.assertEqual(latest["phases"][0]["status"], "incomplete")
        self.assertNotIn("elapsedMs", latest["phases"][0])
        self.assertEqual(latest["backendTotal"]["reason"], "cancelled")
        for end in (self.event("end", elapsedMs="1"), self.event("end", uptimeSeconds="99.00", elapsedMs="0")):
            self.assertEqual(self.collect([self.event(), end])["requests"][0]["phases"][0]["status"], "unavailable")
        report = self.collect([self.event(), self.event("end", start="999")])
        self.assertEqual(report["requests"][0]["phases"][0]["status"], "incomplete")

    def test_duplicate_unknown_private_fields_and_values_are_rejected(self):
        malformed = [self.event() + " task=" + self.outer, self.event(private="/private/font.ttf"),
                     self.event(phase="/private/name"), self.event(method="secret"),
                     self.event(task="/private/source"), self.event(clock="wall-clock"),
                     self.event("end", elapsedMs="86400001"), self.event(weight="630"),
                     self.event(uptimeSeconds="NaN")]
        report = self.collect(malformed)
        self.assertEqual(report["requests"], [])
        self.assertEqual(report["rejectedEvents"], len(malformed))
        self.assertNotIn("private", json.dumps(report))

    def test_safe_clock_and_total_do_not_prove_mix_scope_identity(self):
        lines = [self.event(), *self.safe_lines(), self.event("end")]
        latest = self.collect(lines)["requests"][0]
        safe = latest["safeSwitch"]
        self.assertEqual(safe["status"], "unavailable")
        self.assertEqual(safe["reason"], "identity-not-associated")
        self.assertNotIn("elapsedMs", safe)
        self.assertEqual(latest["backendTotal"]["durationSeconds"], 1.25)
        self.assertNotIn(self.outer, json.dumps(safe))
        # An old SAFE line before the current MIX group can share clock/task
        # text after reboot. Physical proximity cannot establish ownership.
        old = self.collect([*self.safe_lines(), *self.pair()])["requests"][0]["safeSwitch"]
        self.assertEqual(old, safe)

    def test_safe_wrong_task_window_clock_or_missing_proof_cannot_be_associated(self):
        lines = self.safe_lines()
        mutations = [[line.replace(self.outer, "axes-1800000000-999") for line in lines],
                     [line.replace("110.00", "99.00") for line in lines],
                     [line.replace("clock=proc-uptime", "clock=wall") for line in lines],
                     [line.replace("elapsedMs=2000", "elapsedMs=1") for line in lines]]
        for changed in mutations:
            self.assertEqual(self.collect([self.event(), *changed, self.event("end")])["requests"][0]["safeSwitch"]["status"], "unavailable")
        self.receipt.unlink()
        self.assertEqual(self.collect([self.event(), *lines, self.event("end")])["requests"][0]["safeSwitch"]["status"], "unavailable")

    def test_log_event_and_request_bounds_are_explicit(self):
        lines = []
        for index in range(4):
            for _ in range(40):
                lines += [self.event(request=f"mix-request-1800000000-{index}"),
                          self.event("end", request=f"mix-request-1800000000-{index}")]
        report = self.collect(lines)
        self.assertTrue(report["truncated"])
        self.assertEqual(len(report["requests"]), 3)
        self.assertLessEqual(sum(len(req["phases"]) for req in report["requests"]), diag.MIX_EVENT_LIMIT)
        report = self.collect(["x" * diag.MIX_LOG_BYTES, *self.pair()])
        self.assertTrue(report["truncated"])
        self.assertEqual(report["requests"][0]["phases"][0]["status"], "complete")

    def test_nonregular_symlink_and_outside_alias_are_never_read(self):
        outside = self.root / "private-outside"; outside.write_text("\n".join(self.pair()))
        self.log.symlink_to(outside)
        self.assertEqual(self.collect()["status"], "unavailable")
        self.log.unlink(); os.mkfifo(self.log)
        started = time.monotonic()
        self.assertEqual(self.collect()["status"], "unavailable")
        self.assertLess(time.monotonic() - started, .3)
        self.log.unlink(); self.collect(self.pair())
        self.receipt.unlink(); self.receipt.symlink_to(outside)
        self.assertEqual(self.collect()["requests"][0]["backendTotal"]["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
