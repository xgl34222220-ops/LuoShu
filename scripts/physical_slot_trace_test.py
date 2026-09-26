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

from fontTools.ttLib import TTCollection, TTFont

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

    def test_archived_replaceable_count_cannot_shrink_from_15_to_11(self):
        self.inventory["scannerRevision"] = 11
        self.inventory["slots"][self.name]["replacementRoles"] = ["latin", "digit"]
        extra = []
        for index in range(14):
            logical = f"/system/fonts/Face{index}.ttf"
            self.inventory["slots"][logical] = {"replacementRoles": ["latin"], "weight": 700}
            destination = self.payload / logical.lstrip("/")
            os.link(self.font, destination)
            extra.append(logical)
        before = self.result()
        self.assertEqual(before["summary"]["replaceableSlots"], 15)
        self.assertEqual(before["summary"]["pending"], 15)
        missing = extra[:4]
        for logical in missing:
            (self.payload / logical.lstrip("/")).unlink()
        (self.payload / ".luoshu-metrics-report.json").write_text(json.dumps({
            "schema": "luoshu-slot-metrics-v1", "engine": "inventory-font-stage-v1",
            "preservedFonts": {logical: "source-weight-missing:700" for logical in missing}}))
        after = self.result()
        self.assertEqual(after["summary"]["replaceableSlots"], 15)
        self.assertEqual(after["summary"]["pending"], 11)
        self.assertEqual(after["summary"]["sourceUnavailable"], 4)
        self.assertEqual(after["summary"]["issues"], 4)
        self.assertEqual(after["summary"]["replaceableEstimatedSlots"], 0)
        self.assertTrue(all(row["intrinsicallyReplaceable"] for row in after["slots"]))

    def test_old_measured_inventory_counts_partial_latin_and_digits_by_actual_presence(self):
        self.inventory["slots"] = {
            "/system/fonts/Partial.ttf": {"metrics": {"coverage": {"latinCount": 1, "hanCount": 0}}},
            "/system/fonts/Clock.ttf": {"metrics": {"fontTraits": {"digitCount": 1}}},
            "/system/fonts/OtherScript.ttf": {"metrics": {"coverage": {"latinCount": 0, "hanCount": 0},
                                                               "fontTraits": {"letterScripts": {"Arab": 100}}}},
        }
        result = self.result()
        self.assertEqual(result["summary"]["replaceableSlots"], 2)
        self.assertEqual(result["summary"]["replaceableEstimatedSlots"], 0)
        by_path = {row["path"]: row for row in result["slots"]}
        self.assertEqual(by_path["/system/fonts/Clock.ttf"]["replacementRoles"], ["digit"])
        self.assertFalse(by_path["/system/fonts/OtherScript.ttf"]["intrinsicallyReplaceable"])

    def test_dynamic_and_runtime_paths_are_unique_unreplaced_observations(self):
        self.inventory["slots"][self.name]["replacementRoles"] = ["latin"]
        dynamic = {"path": "/data/themes/fonts/selected.ttf", "reason": "mutable-theme-font",
                   "faces": [{"faceIndex": 0, "format": "TTF", "weight": 400, "replacementRoles": ["latin"],
                              "variationAxes": {"wght": {"min": 100, "max": 900, "default": 400}}}]}
        runtime = {"path": "/apex/com.example.fonts/font.ttf", "reason": "runtime-font-container",
                   "faces": [{"faceIndex": 0, "format": "TTF", "replacementRoles": ["digit"]}]}
        self.inventory["dynamicFontFiles"] = [dynamic, dynamic, {"path": self.name}]
        self.inventory["runtimeFontFiles"] = [runtime, runtime, dynamic]
        self.verify()
        result = self.result()
        summary = result["summary"]
        self.assertEqual((summary["replaceableSlots"], summary["replaced"], summary["dynamicSlots"],
                          summary["runtimeSlots"], summary["stockCensusSlots"]), (1, 1, 1, 1, 1))
        self.assertEqual(summary["inventorySlots"], 3)
        by_path = {row["path"]: row for row in result["slots"]}
        for path in (dynamic["path"], runtime["path"]):
            self.assertFalse(by_path[path]["intrinsicallyReplaceable"])
            self.assertFalse(by_path[path]["safeToRetry"])
            self.assertEqual(by_path[path]["category"], "issue")
            self.assertIn("尚未替换", by_path[path]["reason"])
        self.assertTrue(by_path[dynamic["path"]]["variable"])
        self.assertEqual(by_path[runtime["path"]]["source"], "runtime-font")
        plan = self.root / "observed.plan"
        trace.atomic_write_plan(result, plan)
        self.assertEqual(plan.read_text(), "")

    def test_prepared_tree_never_inherits_live_confirmation(self):
        self.verify()
        result = self.result(confirmed=True, prepared=True)
        self.assertEqual(result["verificationState"], "pending-reboot")
        self.assertEqual(result["summary"]["replaced"], 0)

    def test_all_census_files_are_visible_but_never_repair_targets(self):
        self.verify()
        emoji = "/system/fonts/Emoji.ttf"
        unreadable = "/vendor/assets/Unknown.ttf"
        unmeasured = "/product/typefaces/Unmeasured.otf"
        alias = "/system/fonts/Theme.ttf"
        self.inventory["preservedFonts"] = {
            emoji: {"reason": "color-font"}, unreadable: {"reason": "unreadable-stock-font"},
            alias: {"reason": "dynamic-font-alias"},
        }
        candidates = {"schema": trace.CANDIDATE_SCHEMA, "paths": [
            {"path": self.name, "candidate": True},
            {"path": emoji, "candidate": False, "reason": "specialized-name"},
            {"path": unreadable, "candidate": True, "reason": "visible-font-path"},
            {"path": unmeasured, "candidate": True, "reason": "visible-font-path"},
            {"path": unmeasured, "candidate": True, "reason": "visible-font-path"},
        ]}
        result = self.result(candidates=candidates)
        by_path = {row["path"]: row for row in result["slots"]}
        self.assertEqual(set(by_path), {self.name, emoji, unreadable, unmeasured, alias})
        summary = result["summary"]
        self.assertEqual((summary["inventorySlots"], summary["textInventorySlots"],
                          summary["censusSlots"], summary["censusOnlySlots"]), (5, 1, 5, 4))
        self.assertEqual((summary["replaced"], summary["protected"], summary["issues"],
                          summary["replaceableSlots"], summary["sourceUnavailable"]), (1, 2, 2, 1, 0))
        self.assertEqual(summary["inventorySlots"], sum(summary[key] for key in
                                                     ("replaced", "protected", "pending", "issues")))
        self.assertEqual(by_path[emoji]["reason"], "彩色或表情字体，保持原厂")
        self.assertEqual(by_path[unreadable]["category"], "issue")
        self.assertEqual(by_path[unreadable]["reasonCode"], "unreadable-stock-font")
        for path in (emoji, unreadable, unmeasured, alias):
            self.assertFalse(by_path[path]["safeToRetry"])
            self.assertTrue(by_path[path]["reason"])
        plan = self.root / "repair.plan"
        trace.atomic_write_plan(result, plan)
        self.assertEqual(plan.read_text(), "")

    def partial_collection(self):
        other = self.root / "retained.ttf"
        make_font(other, ascent=1100, descent=-300)
        path = self.font.with_suffix('.ttc')
        collection = TTCollection()
        collection.fonts = [TTFont(self.font), TTFont(other)]
        try:
            collection.save(path)
        finally:
            collection.close()
        self.font.unlink()
        self.font = path
        self.name = '/system/fonts/Primary.ttc'
        self.target = self.visible / self.name.lstrip('/')
        shutil.copyfile(self.font, self.target)
        self.inventory['slots'] = {self.name: {'weight': 400, 'families': ['sans-serif']}}
        (self.payload / verifier.MANIFEST).write_text(json.dumps({
            'schema': 'inventory-font-output-v1', 'files': {
                self.name: hashlib.sha256(self.font.read_bytes()).hexdigest()}}))
        (self.payload / '.luoshu-metrics-report.json').write_text(json.dumps({
            'schema': 'luoshu-slot-metrics-v1', 'engine': 'inventory-font-stage-v1',
            'preservedFonts': {}, 'partialSlots': [self.name], 'slots': [
                {'slot': self.name, 'faceIndex': 0, 'state': 'replaced',
                 'replacedRoleCounts': {'cjk': 500, 'latin': 52, 'digit': 10}},
                {'slot': self.name, 'faceIndex': 1, 'state': 'retained-stock',
                 'reason': 'source-weight-missing', 'replacedRoleCounts': {}},
            ]}))

    def test_verified_collection_bytes_do_not_claim_every_face_replaced(self):
        self.partial_collection()
        self.verify()
        result = self.result()
        slot = result['slots'][0]
        self.assertEqual(result['verificationState'], 'partial')
        self.assertEqual((slot['state'], slot['category'], slot['safeToRetry']), ('partial', 'issue', False))
        self.assertFalse(slot['sourceUnavailable'])
        summary = result['summary']
        self.assertEqual((summary['replaced'], summary['partial'], summary['issues'],
                          summary['sourceUnavailable'], summary['replaceableSlots']), (0, 1, 1, 0, 1))
        self.assertEqual(slot['retainedFaces'][0]['faceIndex'], 1)
        self.assertIn('真实字重', slot['retainedFaces'][0]['reason'])
        self.assertEqual(len(slot['routes']), 2)
        self.assertIn('第 1 面 · 已替换', slot['routes'][0]['family'])
        self.assertIn('中文 500 个字形', slot['routes'][0]['planReason'])
        self.assertIn('第 2 面 · 保留原厂', slot['routes'][1]['family'])
        plan = self.root / 'partial.plan'
        trace.atomic_write_plan(result, plan)
        self.assertEqual(plan.read_text(), '')

    def test_prepared_partial_collection_stays_pending(self):
        self.partial_collection()
        self.verify()
        result = self.result(prepared=True)
        self.assertEqual(result['verificationState'], 'pending-reboot')
        self.assertEqual(result['slots'][0]['state'], 'mapped-unverified')
        self.assertEqual(result['summary']['pending'], 1)
        self.assertEqual(result['summary']['partial'], 0)
        self.assertEqual(result['summary']['replaced'], 0)
        self.assertIn('待重启', result['slots'][0]['routes'][0]['family'])

    def test_partial_collection_payload_corruption_still_requests_repair(self):
        self.partial_collection()
        self.verify()
        self.font.write_bytes(self.font.read_bytes() + b'corruption')
        result = self.result(verify_payload=True)
        slot = result['slots'][0]
        self.assertEqual(slot['state'], 'mismatch')
        self.assertTrue(slot['safeToRetry'])
        self.assertEqual(slot['reasonCode'], 'payload-digest-mismatch')
        self.assertEqual(result['summary']['partial'], 0)
        plan = self.root / 'damaged.plan'
        trace.atomic_write_plan(result, plan)
        self.assertEqual(plan.read_text(), self.name + '\n')

    def test_partial_target_roles_are_distinct_from_retained_other_scripts(self):
        report_path = self.payload / '.luoshu-metrics-report.json'
        row = {'slot': self.name, 'faceIndex': 0, 'state': 'replaced',
               'replacedRoleCounts': {'cjk': 0, 'latin': 1, 'digit': 1},
               'retainedTargetRoleCounts': {'cjk': 32, 'latin': 51, 'digit': 9},
               'retainedStockCodepoints': 600}
        report = {'schema': 'luoshu-slot-metrics-v1', 'engine': 'inventory-font-stage-v1',
                  'preservedFonts': {}, 'slots': [row]}
        report_path.write_text(json.dumps(report))
        self.verify()
        result = self.result()
        slot = result['slots'][0]
        self.assertEqual(slot['state'], 'partial')
        self.assertEqual(slot['reasonCode'], 'target-characters-partially-replaced')
        self.assertFalse(slot['safeToRetry'])
        self.assertEqual(slot['retainedFaces'], [])
        self.assertEqual(slot['retainedTargetRoleCounts'], row['retainedTargetRoleCounts'])
        self.assertIn('英文 1 个字形', slot['routes'][0]['planReason'])
        self.assertIn('保留原厂：中文 32 个字形、英文 51 个字形、数字 9 个字形',
                      slot['routes'][0]['planReason'])
        self.assertIn('部分替换', slot['routes'][0]['family'])
        self.assertEqual(self.result(prepared=True)['slots'][0]['state'], 'mapped-unverified')
        # Retaining hundreds of Arabic/Greek glyphs alone is normal and must
        # not label an otherwise complete Chinese/Latin/digit replacement partial.
        row['retainedTargetRoleCounts'] = {'cjk': 0, 'latin': 0, 'digit': 0}
        report_path.write_text(json.dumps(report))
        self.assertEqual(self.result()['slots'][0]['state'], 'loaded')


if __name__ == "__main__":
    unittest.main()
