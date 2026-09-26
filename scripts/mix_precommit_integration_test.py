#!/usr/bin/env python3
"""Exercise the real prepare/finalize entry points while ROM work is in flight."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "common/legacy_v14_4/mix_router.sh"


class PrecommitOwnershipTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luoshu-precommit-")
        self.addCleanup(self.temp.cleanup)
        self.module = Path(self.temp.name)
        for path in ("config", "common/legacy_v14_4", "logs", "cache", "bin",
                     ".luoshu-mix-stage/system/fonts"):
            (self.module / path).mkdir(parents=True, exist_ok=True)
        (self.module / "module.prop").write_text("id=LuoShu\n")
        self.stage = self.module / ".luoshu-mix-stage"
        (self.stage / "system/fonts/MiSansVF.ttf").write_text("new-composite")
        identity = "requestId=request-test\ncjk=CJK\nlatin=Latin\ndigit=Digit\n"
        (self.module / "config/mix-stage-next.conf").write_text(
            identity + "previousFont=default\npreviousLegacy=false\n")
        (self.stage / ".luoshu-mix-generation.conf").write_text(
            identity + "compositeHash=composite-test\n")
        (self.module / "config/axes_task.conf").write_text(
            "task=axes-test\nstate=running\npercent=90\n")
        self.script("bin/getprop", '#!/bin/sh\n[ "$1" != ro.mi.os.version.name ] || echo HyperOS\n')
        self.script("common/hyperos_stage_complete.sh", '''#!/bin/sh
printf '%s\n' "$$" >> "$LUOSHU_REAL_MODDIR/mapping-calls"
touch "$LUOSHU_REAL_MODDIR/mapping-entered"
sleep 1
test -s "$1/system/fonts/MiSansVF.ttf"
''')
        self.env = {**os.environ, "MODDIR": str(self.module),
                    "LUOSHU_REAL_MODDIR": str(self.module),
                    "LUOSHU_MIX_REQUEST_ID": "request-test",
                    "PATH": str(self.module / "bin") + os.pathsep + os.environ["PATH"]}

    def script(self, relative, text):
        path = self.module / relative
        path.write_text(text)
        path.chmod(0o755)

    def wait_for(self, path, seconds=5):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if path.exists():
                return
            time.sleep(0.02)
        self.fail(f"Missing synchronization marker: {path}")

    def test_prepare_and_monitor_finalize_share_one_mapping_pass(self):
        workers = []
        try:
            workers.append(subprocess.Popen(["sh", str(ROUTER), "prepare-finalize"],
                env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
            self.wait_for(self.module / "mapping-entered")
            for command in ("finalize", "prepare-finalize", "finalize"):
                workers.append(subprocess.Popen(["sh", str(ROUTER), command],
                    env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
            results = [(worker, *worker.communicate(timeout=15)) for worker in workers]
            self.assertEqual(len((self.module / "mapping-calls").read_text().splitlines()), 1,
                             "ROM completion was run concurrently for one composite")
            for worker, out, error in results:
                self.assertEqual(worker.returncode, 0, out + error)
                self.assertEqual(json.loads(out)["status"], "ok", out)
            self.assertTrue((self.module / ".luoshu-payload-next/system/fonts/MiSansVF.ttf").is_file())
            self.assertFalse((self.module / ".mix-stage-finalize.lock").exists())
        finally:
            for worker in workers:
                if worker.poll() is None:
                    worker.kill()
                worker.wait()

    def test_failed_mapping_releases_lock_for_retry(self):
        self.script("common/hyperos_stage_complete.sh", "#!/bin/sh\nexit 1\n")
        result = subprocess.run(["sh", str(ROUTER), "prepare-finalize"],
            env=self.env, capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.module / ".mix-stage-finalize.lock").exists())
        self.assertFalse((self.stage / ".luoshu-precommit-ready.conf").exists())
        self.script("common/hyperos_stage_complete.sh", "#!/bin/sh\nexit 0\n")
        result = subprocess.run(["sh", str(ROUTER), "finalize"],
            env=self.env, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.module / ".luoshu-payload-next/system/fonts/MiSansVF.ttf").is_file())

    def test_timed_out_prepare_releases_its_lock(self):
        self.script("common/hyperos_stage_complete.sh", "#!/bin/sh\nsleep 30\n")
        result = subprocess.run(["timeout", "1", "sh", str(ROUTER), "prepare-finalize"],
            env=self.env, capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.module / ".mix-stage-finalize.lock").exists())
        self.assertFalse((self.stage / ".luoshu-precommit-ready.conf").exists())
        self.assertFalse((self.module / ".luoshu-payload-next").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
