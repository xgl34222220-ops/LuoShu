#!/usr/bin/env python3
"""Exercise real HyperOS staging followed by the real generic coverage helper."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import unittest

ROOT = Path(os.environ.get("LUOSHU_TEST_SOURCE_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / "common"))
import hyperos_cjk_routing_test as routing
from hyperos_cjk_routing_test import LATIN, make_font
import device_font_slot_trace as trace


class CoverageRomProtectionTest(unittest.TestCase):
    def setUp(self):
        self.fixture = routing.RoutingTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        (f.module / "logs").mkdir()
        f.default_pair()
        dynamic = f.stock("MiSansVF_Overlay.ttf", (LATIN, 48), ())
        dynamic.update(source="hyperos-rom-reference",
                       metricsReferencePath="/system/fonts/Roboto-Regular.ttf")
        f.stock("Roboto-Bold.ttf", (LATIN, 48))["weight"] = 700
        f.stock("NotoSansArabic-Regular.ttf", (LATIN, 48), ())
        for name in ("MiSansVF_Overlay.ttf", "Roboto-Bold.ttf", "NotoSansArabic-Regular.ttf"):
            make_font(f.fonts / name)
        # The ROM pass intentionally removes all three generic initial aliases.
        # A real weight-specific source is absent, even though that alias exists.
        f.build()
        self.protected = {
            "/system/fonts/MiSansVF_Overlay.ttf",
            "/system/fonts/Roboto-Bold.ttf",
            "/system/fonts/NotoSansArabic-Regular.ttf",
        }
        for logical in self.protected:
            self.assertFalse((f.stage / logical.lstrip("/")).exists())
        # An ordinary inventory slot omitted from the fixed ROM name set still
        # needs the generic coverage pass, so it cannot simply be disabled.
        f.stock("ExtraUI.ttf", (LATIN, 48))
        self.extra = "/system/fonts/ExtraUI.ttf"
        self.inventory = json.loads((f.module / "config/device_font_inventory.json").read_text())
        self.inventory["slots"] = f.slots
        self.inventory.update(mainSlotPath="/system/fonts/MiSansVF.ttf",
                              mainSlot=f.slots["/system/fonts/MiSansVF.ttf"], romKind="hyperos")
        for entry in self.inventory["slots"].values():
            entry.setdefault("partition", "system")
            entry.setdefault("source", "xml")
        (f.module / "config/device_font_inventory.json").write_text(json.dumps(self.inventory))
        store = f.fonts / ".luoshu-font-store"
        store.mkdir(exist_ok=True)
        for name in ("regular.font", "mix-composite.font"):
            shutil.copyfile(f.fonts / "400.ttf", store / name)
        common = f.module / "common"
        common.mkdir(exist_ok=True)
        for name in ("font_inventory.py", "font_slot_coverage.py", "font_metrics_normalize.py",
                     "device_font_slot_trace.py"):
            shutil.copyfile(ROOT / "common" / name, common / name)
        launcher = common / "python/bin/luoshu-python"
        launcher.parent.mkdir(parents=True)
        launcher.write_text("#!/bin/sh\nunset PYTHONHOME PYTHONPATH\nexec " +
                            shlex.quote(sys.executable) + ' "$@"\n')
        launcher.chmod(0o755)

    def run_coverage(self, mode, plan=False):
        f = self.fixture
        env = {**os.environ, "LUOSHU_REAL_MODDIR": str(f.module)}
        if plan:
            path = f.module / "config/plan.txt"
            path.write_text("".join(item + "\n" for item in sorted(self.protected | {self.extra})))
            env["LUOSHU_COVERAGE_PLAN"] = str(path)
        result = subprocess.run(["sh", str(ROOT / "common/coverage_payload_remediate.sh"),
                                 str(f.stage), mode, "Fixture"],
                                env=env, text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr +
                         (f.module / "logs/fontswitch.log").read_text())
        summary = json.loads(result.stdout.strip().splitlines()[-1])["data"]
        self.assertEqual(summary["preserved"], 3)
        self.assertEqual(summary["added"], 1)
        if plan:
            self.assertEqual(summary["requested"], 4)
            self.assertEqual(summary["matched"], 4)
        self.assertTrue((f.stage / self.extra.lstrip("/")).is_file())
        for logical in self.protected:
            self.assertFalse((f.stage / logical.lstrip("/")).exists(), logical)
        result = trace.build_physical_trace(self.inventory, f.stage, prepared=True)
        slots = {item["path"]: item for item in result["slots"]}
        for logical in self.protected:
            self.assertEqual(slots[logical]["category"], "protected")
            self.assertFalse(slots[logical]["safeToRetry"])
        self.assertEqual(result["summary"]["issues"], 0)

    def test_direct_switch_preserves_rom_omissions_and_fills_other_slots(self):
        self.run_coverage("direct")

    def test_composite_explicit_repair_preserves_dynamic_script_and_real_weight(self):
        self.run_coverage("mix", plan=True)

    def test_trace_recognizes_rom_preserves_before_generic_pass(self):
        result = trace.build_physical_trace(self.inventory, self.fixture.stage)
        slots = {item["path"]: item for item in result["slots"]}
        for logical in self.protected:
            self.assertEqual(slots[logical]["category"], "protected")
            self.assertFalse(slots[logical]["safeToRetry"])
        self.assertTrue(slots[self.extra]["safeToRetry"])

    def test_policy_rejects_foreign_traversal_and_noncanonical_paths(self):
        bad = ["/data/outside.ttf", "/system/fonts/../outside.ttf",
               "/system//fonts/ExtraUI.ttf", "system/fonts/ExtraUI.ttf", 3]
        self.inventory["slots"][bad[1]] = {}
        report = self.fixture.stage / ".luoshu-metrics-report.json"
        report.write_text(json.dumps({"schema": "luoshu-slot-metrics-v1",
                                     "preservedDynamicAliases": bad + [self.extra]}))
        self.assertEqual(trace.rom_preserved_index(self.fixture.stage, self.inventory, strict=True),
                         {self.extra: "ROM 动态字体别名保持原厂"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
