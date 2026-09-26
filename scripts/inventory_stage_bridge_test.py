#!/usr/bin/env python3
"""Run the shell bridge with external scanner/engine processes and real paths."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "common/inventory_font_stage.sh"


class InventoryStageBridgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="luoshu inventory bridge ")
        self.addCleanup(self.tmp.cleanup)
        self.module = Path(self.tmp.name) / "module"
        self.common = self.module / "common"
        self.config = self.module / "config"
        self.stage = self.module / ".luoshu-payload-stage.test"
        (self.common / "python/bin").mkdir(parents=True)
        self.config.mkdir()
        self.stage.mkdir()
        launcher = self.common / "python/bin/luoshu-python"
        launcher.write_text("#!/bin/sh\nunset PYTHONHOME PYTHONPATH LD_LIBRARY_PATH\nexec " +
                            shlex.quote(sys.executable) + ' "$@"\n')
        launcher.chmod(0o755)
        (self.common / "stock_inventory_scan.py").write_text('''
import pathlib, sys
module = pathlib.Path(__file__).resolve().parent.parent
with (module / "validation-calls").open("a") as f: f.write("validate\\n")
p = module / "config/device_font_inventory.json"
sys.exit(0 if p.exists() and p.read_text() == "current-stock" else 2)
''')
        (self.common / "inventory_font_stage.py").write_text('''
import json, pathlib, sys
module = pathlib.Path(__file__).resolve().parent.parent
(module / "engine-args.json").write_text(json.dumps(sys.argv[1:]))
print(json.dumps({"status": "ok"}))
''')
        (self.common / "font_manager.sh").write_text('''#!/bin/sh
[ "$1" = action ] && [ "$2" = stock_scan ] || exit 4
printf 'scan\n' >> "$MODDIR/scan-calls"
[ "${TEST_SCAN_FAIL:-0}" != 1 ] || exit 3
printf current-stock > "$MODDIR/config/device_font_inventory.json"
echo '{"status":"ok","scan":true}'
''')
        self.env = {**os.environ, "LUOSHU_REAL_MODDIR": str(self.module)}

    def run_bridge(self, *args, **env):
        return subprocess.run(["sh", str(BRIDGE), *(str(x) for x in args)],
                              env={**self.env, **env}, text=True, capture_output=True,
                              timeout=5)

    def test_current_inventory_is_reused_without_scan(self):
        (self.config / "device_font_inventory.json").write_text("current-stock")
        source = self.module / "source with spaces.otf"
        result = self.run_bridge(self.stage, "direct", "中文 family", source)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.module / "scan-calls").exists())
        args = json.loads((self.module / "engine-args.json").read_text())
        self.assertEqual(args[args.index("--source") + 1], str(source))
        self.assertEqual(args[args.index("--family") + 1], "中文 family")
        self.assertEqual(json.loads(result.stdout), {"status": "ok"})

    def test_old_inventory_refreshes_once_then_generates(self):
        (self.config / "device_font_inventory.json").write_text("old-revision")
        result = self.run_bridge(self.stage, "mix", "mix")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.module / "scan-calls").read_text(), "scan\n")
        self.assertEqual(len((self.module / "validation-calls").read_text().splitlines()), 2)
        self.assertEqual(json.loads(result.stdout), {"status": "ok"})

    def test_ensure_only_refreshes_without_generating(self):
        result = self.run_bridge("--ensure-inventory")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.module / "scan-calls").exists())
        self.assertFalse((self.module / "engine-args.json").exists())

    def test_failed_scan_does_not_generate(self):
        result = self.run_bridge(self.stage, "direct", "Demo", TEST_SCAN_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.module / "engine-args.json").exists())
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_invalid_scanner_result_does_not_generate(self):
        (self.common / "font_manager.sh").write_text("#!/bin/sh\nexit 0\n")
        result = self.run_bridge(self.stage, "direct", "Demo")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.module / "engine-args.json").exists())

    def test_explicit_plan_is_forwarded(self):
        plan = self.config / "coverage plan.txt"
        plan.write_text("/system/fonts/Regular.ttf\n")
        result = self.run_bridge(self.stage, "mix", "mix", LUOSHU_COVERAGE_PLAN=str(plan))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        args = json.loads((self.module / "engine-args.json").read_text())
        self.assertEqual(args[args.index("--plan") + 1], str(plan))

    def test_live_or_symlink_stages_rejected_before_scan(self):
        live = self.module / ".luoshu-payload"
        live.mkdir()
        symlink = self.module / ".luoshu-payload-next"
        symlink.symlink_to(live)
        for path in (live, symlink, str(self.stage) + "/../.luoshu-payload"):
            with self.subTest(path=path):
                result = self.run_bridge(path, "direct", "Demo")
                self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.module / "validation-calls").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
