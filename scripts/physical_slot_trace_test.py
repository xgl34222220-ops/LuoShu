#!/usr/bin/env python3
"""Coverage reflects runtime bytes; repair plans reflect payload corruption."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))
import device_font_slot_trace as trace
import physical_font_load_verify as verifier
from stock_metric_contract_test import make_font


class PhysicalTraceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luoshu-physical-trace-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / "module"
        self.payload = self.module / ".luoshu-payload"
        self.visible = self.root / "visible"
        self.name = "/system/fonts/Primary.ttf"
        self.font = self.payload / self.name.lstrip("/")
        self.font.parent.mkdir(parents=True)
        make_font(self.font, ascent=950, descent=-250)
        self.target = self.visible / self.name.lstrip("/")
        self.target.parent.mkdir(parents=True)
        shutil.copyfile(self.font, self.target)
        (self.payload / verifier.MANIFEST).write_text(json.dumps({
            "schema": "inventory-font-output-v1", "files": {
                self.name: hashlib.sha256(self.font.read_bytes()).hexdigest()}}))
        self.inventory = {"schema": trace.INVENTORY_SCHEMA, "scannerRevision": 9,
                          "slots": {self.name: {"weight": 400, "families": ["sans-serif"]}}}
        self.env = patch.dict(os.environ, {"LUOSHU_VISIBLE_ROOT": str(self.visible),
                                          "LUOSHU_TEST_BOOT_ID": "trace-boot"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def result(self, **kwargs):
        return trace.build_physical_trace(self.inventory, self.payload,
                                         active_font="selected", **kwargs)

    def verify(self):
        verifier.save_result(self.module,
                             verifier.verify(self.module, self.payload, "selected"), True)

    def test_global_mount_confirmation_is_not_font_evidence(self):
        result = self.result(confirmed=True)
        self.assertEqual(result["summary"]["replaced"], 0)
        self.assertEqual(result["verificationState"], "pending")

    def test_complete_visible_bytes_confirm_slot(self):
        self.verify()
        result = self.result()
        self.assertEqual(result["summary"]["replaced"], 1)
        self.assertEqual(result["verificationState"], "verified")

    def test_visible_mismatch_cannot_be_repaired_by_generating_same_font(self):
        self.target.write_bytes(self.target.read_bytes() + b"different")
        self.verify()
        result = self.result(confirmed=True, verify_payload=True)
        slot = result["slots"][0]
        self.assertEqual(result["verificationState"], "failed")
        self.assertEqual(slot["state"], "mismatch")
        self.assertFalse(slot["safeToRetry"])

    def test_payload_corruption_is_in_repair_plan(self):
        self.verify()
        self.font.write_bytes(self.font.read_bytes() + b"damaged")
        result = self.result(verify_payload=True)
        plan = self.root / "repair.plan"
        trace.atomic_write_plan(result, plan)
        self.assertEqual(plan.read_text(), self.name + "\n")
        self.assertEqual(result["slots"][0]["reasonCode"], "payload-digest-mismatch")
        self.assertEqual(result["verificationState"], "failed")

    def test_missing_payload_is_in_repair_plan(self):
        self.font.unlink()
        result = self.result(verify_payload=True)
        self.assertEqual(result["summary"]["remediable"], 1)
        self.assertEqual(result["slots"][0]["state"], "mapping-missing")

    def test_source_insufficiency_is_not_system_protection(self):
        self.font.unlink()
        (self.payload / ".luoshu-metrics-report.json").write_text(json.dumps({
            "schema": "luoshu-slot-metrics-v1", "engine": "inventory-font-stage-v1",
            "preservedFonts": {self.name: "source-weight-missing:700"}}))
        result = self.result()
        self.assertEqual(result["summary"]["protected"], 0)
        self.assertEqual(result["summary"]["sourceUnavailable"], 1)
        self.assertFalse(result["slots"][0]["safeToRetry"])

    def test_prepared_tree_never_inherits_live_confirmation(self):
        self.verify()
        result = self.result(confirmed=True, prepared=True)
        self.assertEqual(result["verificationState"], "pending-reboot")
        self.assertEqual(result["summary"]["replaced"], 0)


if __name__ == "__main__":
    unittest.main()
