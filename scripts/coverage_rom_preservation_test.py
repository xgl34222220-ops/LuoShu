#!/usr/bin/env python3
"""Migration regression: old ROM omissions cannot override measured capability."""
from __future__ import annotations

import json
import unittest
from fontTools.ttLib import TTFont

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
        preserved = self.f.report()["preservedFonts"]
        self.assertEqual(result["summary"]["issues"], len(preserved))
        self.assertEqual(result["summary"]["sourceUnavailable"], len(preserved))
        self.assertEqual(result["summary"]["remediable"], 0)

    def test_direct_reassesses_old_dynamic_weight_and_filename_protection(self):
        preserved = self.run_coverage()
        self.assert_restored()
        self.assertNotIn(REGULAR, preserved)
        self.assertNotIn(BOLD, preserved)
        self.assertNotIn(NESTED, preserved)
        self.assertNotIn(SCRIPT, preserved)
        self.assertTrue(self.f.path(SCRIPT).is_file())
        self.assertEqual(preserved[HEAVY], "source-weight-missing")

    def test_full_mix_reapply_reassesses_old_rom_omissions(self):
        self.f.seed_mix()
        preserved = self.run_coverage("mix")
        self.assert_restored()
        self.assertNotIn(SCRIPT, preserved)
        self.assertTrue(self.f.path(SCRIPT).is_file())

    def test_non_target_arabic_remains_stock_even_if_source_also_has_arabic(self):
        # User glyphs replace Chinese, Latin and digits. Arabic remains the
        # original stock script even when the selected file contains it too.
        text_font(self.f.source, points=LATIN | ARABIC, advance=999)
        preserved = self.run_coverage()
        self.assert_restored()
        self.assertTrue(self.f.path(SCRIPT).is_file())
        self.assertNotIn(SCRIPT, preserved)
        with TTFont(self.f.path(SCRIPT)) as font, TTFont(self.f.stock / SCRIPT.lstrip("/")) as stock:
            cmap = font.getBestCmap()
            self.assertEqual(font["hmtx"].metrics[cmap[65]][0], 999)
            self.assertEqual(font["hmtx"].metrics[cmap[0x627]],
                             stock["hmtx"].metrics[stock.getBestCmap()[0x627]])

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
