#!/usr/bin/env python3
"""Exercise the real prepare/finalize entry points while inventory mapping is in flight."""
from __future__ import annotations

import json
import os
import shutil
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
        self.script("common/inventory_font_stage.sh", '''#!/bin/sh
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
                             "Inventory mapping was run concurrently for one composite")
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

    def run_router(self, command, request="request-test", timeout=8):
        return subprocess.run(["sh", str(ROUTER), command],
            env={**self.env, "LUOSHU_MIX_REQUEST_ID": request},
            capture_output=True, text=True, timeout=timeout)

    def test_source_only_stage_reaches_inventory_mapper(self):
        (self.stage / "system/fonts/MiSansVF.ttf").unlink()
        anchors = self.stage / "system/fonts/.luoshu-font-store"
        anchors.mkdir()
        (anchors / "mix-composite.font").write_text("composite-source")
        self.script("common/inventory_font_stage.sh", '''#!/bin/sh
[ "$2" = mix ] || exit 1
cp "$1/system/fonts/.luoshu-font-store/mix-composite.font" "$1/system/fonts/Detected.ttf"
''')
        result = self.run_router("finalize")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.module / ".luoshu-payload-next/system/fonts/Detected.ttf").read_text(),
                         "composite-source")

    def test_missing_inventory_mapper_cannot_commit_core_only_tree(self):
        (self.module / "common/inventory_font_stage.sh").unlink()
        result = self.run_router("finalize")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.module / ".luoshu-payload-next").exists())
        self.assertFalse((self.stage / ".luoshu-precommit-ready.conf").exists())

    def test_old_worker_cannot_prepare_or_commit_new_ready_stage(self):
        (self.stage / ".luoshu-precommit-ready.conf").write_text(
            "state=ready\nrequestId=request-test\n")
        state = self.module / "config/mix-finalize-state.conf"
        state.write_text("state=ready\ntask=axes-test\nmessage=current-task\n")
        for command in ("prepare-finalize", "finalize"):
            result = self.run_router(command, request="request-old")
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(state.read_text(),
                "state=ready\ntask=axes-test\nmessage=current-task\n")
            self.assertTrue((self.stage / "system/fonts/MiSansVF.ttf").is_file())
            self.assertFalse((self.module / ".luoshu-payload-next").exists())
        self.assertFalse((self.module / "mapping-calls").exists())

    def test_old_worker_cannot_claim_other_already_committed_next(self):
        result = self.run_router("finalize")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for command in ("prepare-finalize", "finalize"):
            result = self.run_router(command, request="request-old")
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("requestId=request-test\n",
                      (self.module / "config/font-payload-next.conf").read_text())

    def test_recovery_requires_matching_generation_manifest(self):
        next_path = self.module / ".luoshu-payload-next"
        self.stage.rename(next_path)
        (next_path / ".luoshu-mix-generation.conf").write_text(
            "requestId=request-old\ncompositeHash=old\n")
        result = self.run_router("finalize")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.module / "config/font-payload-next.conf").exists())
        self.assertTrue((self.module / "config/mix-stage-next.conf").is_file())

    def test_recovery_replaces_previous_state_after_directory_rename(self):
        self.stage.rename(self.module / ".luoshu-payload-next")
        state = self.module / "config/font-payload-next.conf"
        state.write_text("state=prepared\nfont=mix\nrequestId=request-old\n")
        result = self.run_router("finalize")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("requestId=request-test\n", state.read_text())
        self.assertFalse((self.module / "config/mix-stage-next.conf").exists())
        self.assertFalse((self.module / "mapping-calls").exists())

    def test_second_start_does_not_erase_running_stage(self):
        before = (self.stage / "system/fonts/MiSansVF.ttf").read_bytes()
        result = subprocess.run(["sh", str(ROUTER), "start", "Other", "Latin", "Digit"],
            env=self.env, capture_output=True, text=True, timeout=8)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.stage / "system/fonts/MiSansVF.ttf").read_bytes(), before)
        self.assertIn("requestId=request-test\n",
                      (self.module / "config/mix-stage-next.conf").read_text())

    def test_same_second_starts_have_distinct_request_ids(self):
        (self.module / "config/axes_task.conf").write_text("state=failed\n")
        shutil.copyfile(ROOT / "common/legacy_v14_4/payload_clone.sh",
                        self.module / "common/legacy_v14_4/payload_clone.sh")
        self.script("bin/date", "#!/bin/sh\necho 1700000000\n")
        self.script("common/legacy_v14_4/v14_mix.sh",
                    "#!/bin/sh\necho '{\"status\":\"ok\"}'\n")
        requests = []
        for _ in range(2):
            result = subprocess.run(["sh", str(ROUTER), "start", "CJK", "Latin", "Digit"],
                env=self.env, capture_output=True, text=True, timeout=8)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            requests.append((self.module / "config/mix-stage-next.conf").read_text().splitlines()[0])
        self.assertNotEqual(requests[0], requests[1])

    def test_lock_initialization_window_cannot_start_second_mapping(self):
        real_mkdir = shutil.which("mkdir")
        self.script("bin/mkdir", f'''#!/bin/sh
"{real_mkdir}" "$@" || exit $?
if [ "$1" = "$MODDIR/.mix-stage-finalize.lock" ] && [ ! -e "$MODDIR/delayed-lock" ]; then
    touch "$MODDIR/delayed-lock"
    sleep 0.35
fi
''')
        first = subprocess.Popen(["sh", str(ROUTER), "prepare-finalize"],
            env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.wait_for(self.module / "delayed-lock")
            result = self.run_router("finalize")
            out, error = first.communicate(timeout=8)
            self.assertEqual(first.returncode, 0, out + error)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(len((self.module / "mapping-calls").read_text().splitlines()), 1)
        finally:
            if first.poll() is None:
                first.kill()
            first.wait()

    def test_failed_mapping_releases_lock_for_retry(self):
        self.script("common/inventory_font_stage.sh", "#!/bin/sh\nexit 1\n")
        result = subprocess.run(["sh", str(ROUTER), "prepare-finalize"],
            env=self.env, capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.module / ".mix-stage-finalize.lock").exists())
        self.assertFalse((self.stage / ".luoshu-precommit-ready.conf").exists())
        self.script("common/inventory_font_stage.sh", "#!/bin/sh\nexit 0\n")
        result = subprocess.run(["sh", str(ROUTER), "finalize"],
            env=self.env, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.module / ".luoshu-payload-next/system/fonts/MiSansVF.ttf").is_file())

    def test_timed_out_finalize_releases_its_lock(self):
        self.script("common/inventory_font_stage.sh", "#!/bin/sh\nsleep 30\n")
        result = subprocess.run(["timeout", "1", "sh", str(ROUTER), "finalize"],
            env=self.env, capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.module / ".mix-stage-finalize.lock").exists())
        self.assertFalse((self.module / ".luoshu-payload-next").exists())

    def test_timed_out_prepare_releases_its_lock(self):
        self.script("common/inventory_font_stage.sh", "#!/bin/sh\nsleep 30\n")
        result = subprocess.run(["timeout", "1", "sh", str(ROUTER), "prepare-finalize"],
            env=self.env, capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.module / ".mix-stage-finalize.lock").exists())
        self.assertFalse((self.stage / ".luoshu-precommit-ready.conf").exists())
        self.assertFalse((self.module / ".luoshu-payload-next").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
