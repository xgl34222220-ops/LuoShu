#!/usr/bin/env python3
"""Migration regression: old ROM omissions cannot override measured capability."""
from __future__ import annotations

import json
import unittest

from coverage_inventory_integration_test import (
    ARABIC, LATIN, REGULAR, BOLD, HEAVY, SCRIPT, NESTED,
    CoverageFixture, text_font, trace,
)


class CoverageRomProtectionTest(unittest.TestCase):
    def setUp(self):
        self.f = CoverageFixture()
        self.addCleanup(self.f.close)
        # These old name-based exclusions are deliberately wrong for this source.
        # They are input migration state, never authority for the new engine.
        (self.f.stage / ".luoshu-metrics-report.json").write_text(json.dumps({
            "schema": "luoshu-slot-metrics-v1",
            "preservedDynamicAliases": [REGULAR],
            "preservedWeightAliases": [BOLD],
            "preservedStockAliases": [SCRIPT, NESTED],
        }))
        (self.f.stage / ".luoshu-coverage-preserved.tsv").write_text(
            f"{REGULAR}\tdynamic-font-alias\n{BOLD}\tsource-weight-missing\n"
            f"{SCRIPT}\tspecialized-name\n{NESTED}\tspecialized-name\n")
        self.live_before = self.f.snapshot_live()

    def run_coverage(self, mode="direct", plan=None, source=True):
        result = self.f.invoke(mode, plan=plan, source=source)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.f.snapshot_live(), self.live_before)
        report = self.f.report()
        self.assertIn("inventory", report["engine"])
        return report.get("preservedFonts", report.get("preserved", {}))

    def assert_restored(self):
        for logical in (REGULAR, BOLD, NESTED):
            self.assertTrue(self.f.path(logical).is_file(), logical)
        result = trace.build_physical_trace(self.f.inventory, self.f.stage, prepared=True)
        slots = {slot["path"]: slot for slot in result["slots"]}
        for logical in (REGULAR, BOLD, NESTED):
            self.assertNotEqual(slots[logical]["category"], "protected", slots[logical])
        self.assertEqual(result["summary"]["issues"], 0)

    def test_direct_reassesses_old_dynamic_weight_and_filename_protection(self):
        preserved = self.run_coverage()
        self.assert_restored()
        self.assertNotIn(REGULAR, preserved)
        self.assertNotIn(BOLD, preserved)
        self.assertNotIn(NESTED, preserved)
        self.assertEqual(preserved[SCRIPT], "source-script-coverage-missing")
        self.assertEqual(preserved[HEAVY], "source-weight-missing")

    def test_mix_plan_reassesses_every_requested_old_rom_omission(self):
        self.f.seed_mix()
        preserved = self.run_coverage("mix", plan=[REGULAR, BOLD, SCRIPT, NESTED])
        self.assert_restored()
        self.assertEqual(preserved[SCRIPT], "source-script-coverage-missing")
        self.assertFalse(self.f.path(SCRIPT).exists())

    def test_new_source_script_capability_restores_previously_preserved_font(self):
        # Real Arabic cmap capability is added to the selected face; changing
        # ROM labels or filename allowlists is unnecessary.
        text_font(self.f.source, points=LATIN | ARABIC)
        preserved = self.run_coverage()
        self.assert_restored()
        self.assertTrue(self.f.path(SCRIPT).is_file())
        self.assertNotIn(SCRIPT, preserved)

    def test_cached_direct_repair_uses_real_source_anchors_without_rom_mapper(self):
        self.f.seed_mix()
        preserved = self.run_coverage(source=False)
        self.assert_restored()
        self.assertEqual(preserved[HEAVY], "source-weight-missing")

    def test_report_cannot_inject_foreign_traversal_or_noncanonical_paths(self):
        self.run_coverage()
        bad = ["/data/outside.ttf", "/system/fonts/../outside.ttf",
               "/system//fonts/ExtraUI.ttf", "system/fonts/ExtraUI.ttf"]
        self.f.inventory["slots"][bad[1]] = {}
        report = self.f.report()
        report["preservedFonts"] = {path: "source-weight-missing" for path in bad + [HEAVY]}
        report["preserved"] = report["preservedFonts"]
        report["preservedWeightAliases"] = bad + [HEAVY]
        (self.f.stage / ".luoshu-metrics-report.json").write_text(json.dumps(report))
        self.assertEqual(trace.rom_preserved_index(self.f.stage, self.f.inventory, strict=True),
                         {HEAVY: "source-weight-missing"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
