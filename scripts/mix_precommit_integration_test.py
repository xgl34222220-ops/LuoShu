#!/usr/bin/env python3
"""Exercise the real prepare/finalize entry points while inventory mapping is in flight."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
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
        (self.module / "common/python/bin").mkdir(parents=True)
        shutil.copyfile(ROOT / "common/mix_stage_watchdog.py", self.module / "common/mix_stage_watchdog.py")
        self.script("common/python/bin/luoshu-python", f'#!/bin/sh\nunset PYTHONHOME PYTHONPATH LD_LIBRARY_PATH\nexec {sys.executable} "$@"\n')
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

    def test_nonstandard_auto_weight_anchor_reaches_inventory_mapper(self):
        (self.stage / "system/fonts/MiSansVF.ttf").unlink()
        anchors = self.stage / "system/fonts/.luoshu-font-store"
        anchors.mkdir()
        (anchors / "wght-550.font").write_text("real-550-composite")
        (anchors / ".luoshu-mix-source-weights.json").write_text('{"schema":"luoshu-mix-source-weights-v1"}')
        self.script("common/inventory_font_stage.sh", """#!/bin/sh
cp "$1/system/fonts/.luoshu-font-store/wght-550.font" "$1/system/fonts/Detected.ttf"
""")
        result = self.run_router("finalize")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.module / ".luoshu-payload-next/system/fonts/Detected.ttf").read_text(), "real-550-composite")

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

    def test_failed_commit_restores_previous_queued_payload_and_selection(self):
        next_path = self.module / ".luoshu-payload-next"
        (next_path / "system/fonts").mkdir(parents=True)
        (next_path / "system/fonts/Previous.ttf").write_bytes(b"previous-selected-font")
        old_state = "state=prepared\nfont=Previous\nrequestId=previous-request\n"
        (self.module / "config/font-payload-next.conf").write_text(old_state)
        (self.module / "config/active_font.conf").write_text("Previous\n")
        (self.module / "config/text_reboot_required.conf").write_text("font=Previous\nbootId=old\n")
        real_mv = shutil.which("mv")
        # Fail after NEXT_STATE has changed, but before the active selection can
        # be written. Rollback must restore all three metadata files and the tree.
        self.script("bin/mv", f'''#!/bin/sh
"{real_mv}" "$@" || exit $?
for target do :; done
if [ "$target" = "$MODDIR/config/font-payload-next.conf" ] && [ ! -e "$MODDIR/commit-write-failed" ]; then
    touch "$MODDIR/commit-write-failed"
    rm -f "$MODDIR/config/active_font.conf"
    ln -s /dev/full "$MODDIR/config/active_font.conf"
fi
''')
        result = self.run_router("finalize")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((next_path / "system/fonts/Previous.ttf").read_bytes(), b"previous-selected-font")
        self.assertEqual((self.module / "config/font-payload-next.conf").read_text(), old_state)
        self.assertEqual((self.module / "config/active_font.conf").read_text(), "Previous\n")
        self.assertEqual((self.module / "config/text_reboot_required.conf").read_text(), "font=Previous\nbootId=old\n")
        self.assertTrue((self.stage / "system/fonts/MiSansVF.ttf").is_file())
        self.assertFalse(list(self.module.glob(".luoshu-mix-commit.*")))
        self.assertFalse((self.module / ".mix-stage-finalize.lock").exists())
        # Retrying only the now-ready atomic commit does not regenerate fonts.
        result = self.run_router("finalize")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len((self.module / "mapping-calls").read_text().splitlines()), 1)
        self.assertTrue((next_path / "system/fonts/MiSansVF.ttf").is_file())

    def test_abandoned_lock_initializer_and_reclaimer_are_recovered(self):
        lock = self.module / ".mix-stage-finalize.lock"
        lock.mkdir()
        (lock / "pid.99999999.tmp").write_text("99999999\n")
        (lock / "reclaim.99999998").mkdir()
        result = self.run_router("prepare-finalize")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len((self.module / "mapping-calls").read_text().splitlines()), 1)
        self.assertFalse(lock.exists())

    def test_two_dead_owner_reclaimers_do_not_remove_new_live_owner(self):
        lock = self.module / ".mix-stage-finalize.lock"
        lock.mkdir()
        (lock / "pid").write_text("99999999\n")
        workers = [subprocess.Popen(["sh", str(ROUTER), command], env=self.env,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                   for command in ("prepare-finalize", "finalize", "finalize", "prepare-finalize")]
        try:
            for worker in workers:
                out, err = worker.communicate(timeout=10)
                self.assertEqual(worker.returncode, 0, out + err)
            self.assertEqual(len((self.module / "mapping-calls").read_text().splitlines()), 1)
            self.assertFalse(lock.exists())
        finally:
            for worker in workers:
                if worker.poll() is None:
                    worker.kill()
                worker.wait()

    def test_paused_stale_rmdir_cannot_admit_another_mapper(self):
        lock = self.module / '.mix-stage-finalize.lock'
        lock.mkdir()
        (lock / 'pid').write_text('99999999\n')
        real_rmdir = shutil.which('rmdir')
        self.script('bin/rmdir', f'''#!/bin/sh
if [ "$1" = "$MODDIR/.mix-stage-finalize.lock" ] && mkdir "$MODDIR/rmdir-paused" 2>/dev/null; then
    while [ ! -e "$MODDIR/release-rmdir" ]; do sleep 0.05; done
fi
exec "{real_rmdir}" "$@"
''')
        workers = []
        try:
            workers.append(subprocess.Popen(['sh', str(ROUTER), 'prepare-finalize'],
                env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
            self.wait_for(self.module / 'rmdir-paused')
            workers.append(subprocess.Popen(['sh', str(ROUTER), 'finalize'],
                env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
            # Old code lets this peer reclaim the empty directory after its
            # one-second initializer grace, then start mapping before the stale
            # rmdir resumes. Kernel ownership keeps it outside the mutation.
            time.sleep(1.3)
            self.assertFalse((self.module / 'mapping-entered').exists())
            (self.module / 'release-rmdir').touch()
            for worker in workers:
                out, err = worker.communicate(timeout=8)
                self.assertEqual(worker.returncode, 0, out + err)
            self.assertEqual(len((self.module / 'mapping-calls').read_text().splitlines()), 1)
        finally:
            (self.module / 'release-rmdir').touch()
            for worker in workers:
                if worker.poll() is None:
                    worker.kill()
                worker.wait()

    def test_start_does_not_pass_kernel_lock_to_detached_generation(self):
        (self.module / 'config/axes_task.conf').write_text('state=failed\n')
        shutil.copyfile(ROOT / 'common/legacy_v14_4/payload_clone.sh',
                        self.module / 'common/legacy_v14_4/payload_clone.sh')
        self.script('common/legacy_v14_4/v14_mix.sh', '''#!/bin/sh
( while [ ! -e "$LUOSHU_REAL_MODDIR/release-daemon" ]; do sleep 0.05; done ) </dev/null >/dev/null 2>&1 &
printf '{"status":"ok"}\n'
''')
        try:
            result = subprocess.run(['sh', str(ROUTER), 'start', 'CJK', 'Latin', 'Digit'],
                env=self.env, capture_output=True, text=True, timeout=4)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            request = (self.module / 'config/mix-stage-next.conf').read_text().splitlines()[0].split('=', 1)[1]
            result = self.run_router('prepare-finalize', request=request, timeout=3)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('生成结果为空', result.stdout)
            self.assertNotIn('正在提交', result.stdout)
        finally:
            (self.module / 'release-daemon').touch()

    def test_recovery_does_not_delete_an_active_inventory_transaction(self):
        self.script('common/inventory_font_stage.sh', '''#!/bin/sh
touch "$LUOSHU_REAL_MODDIR/mapping-entered"
while [ ! -e "$LUOSHU_REAL_MODDIR/release-mapping" ]; do sleep 0.05; done
test -s "$1/system/fonts/MiSansVF.ttf"
''')
        first = subprocess.Popen(['sh', str(ROUTER), 'prepare-finalize'],
            env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.wait_for(self.module / 'mapping-entered')
            result = self.run_router('recover', timeout=4)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('正在提交', result.stdout)
            self.assertTrue((self.stage / 'system/fonts/MiSansVF.ttf').is_file())
            self.assertTrue((self.module / 'config/mix-stage-next.conf').is_file())
            (self.module / 'release-mapping').touch()
            out, error = first.communicate(timeout=5)
            self.assertEqual(first.returncode, 0, out + error)
        finally:
            (self.module / 'release-mapping').touch()
            if first.poll() is None:
                first.kill()
            first.wait()

    def check_finalize_worker_drops_inherited_lock(self, detached_helper):
        (self.stage / '.luoshu-precommit-ready.conf').write_text(
            'state=ready\nrequestId=request-test\n')
        (self.module / 'router-functions.sh').write_text(
            ROUTER.read_text().split('_cmd="${1:-config}"', 1)[0])
        if detached_helper:
            shutil.copyfile(ROOT / 'common/background_task.sh',
                            self.module / 'common/background_task.sh')
        self.script('spawn-finalize.sh', f'''#!/bin/sh
if [ "$1" = finalize-worker ]; then exec timeout 3 sh "{ROUTER}" "$@"; fi
unset LUOSHU_MIX_KERNEL_LOCK_HELD
. "$MODDIR/router-functions.sh"
ensure_mix_finalize_worker axes-test
''')
        result = subprocess.run([sys.executable,
            str(ROOT / 'common/mix_stage_watchdog.py'), '--module', str(self.module),
            '--lock', '--wait', '1', '--', 'sh', str(self.module / 'spawn-finalize.sh')],
            env=self.env, capture_output=True, text=True, timeout=4)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.wait_for(self.module / '.luoshu-payload-next/system/fonts/MiSansVF.ttf', seconds=2)

    def test_fallback_finalize_worker_does_not_keep_parent_kernel_lock(self):
        self.check_finalize_worker_drops_inherited_lock(False)

    def test_detached_finalize_worker_does_not_keep_parent_kernel_lock(self):
        self.check_finalize_worker_drops_inherited_lock(True)

    def failing_mapper(self):
        self.script("common/inventory_font_stage.sh", """#!/bin/sh
printf '%s\n' "$$" >> "$LUOSHU_REAL_MODDIR/mapping-calls"
touch "$LUOSHU_REAL_MODDIR/mapping-entered"
sleep 0.2
printf '%s\n' '通用字体生成失败：merger changed the retained stock glyph order' >&2
exit 1
""")

    def test_failed_mapping_is_terminal_for_request_and_next_request_can_retry(self):
        self.failing_mapper()
        result = self.run_router("prepare-finalize")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("merger changed the retained stock glyph order", json.loads(result.stdout)["message"])
        self.assertFalse((self.module / ".mix-stage-finalize.lock").exists())
        self.assertTrue((self.stage / ".luoshu-precommit-failed.conf").exists())
        # Even changing the helper cannot silently retry this failed request.
        self.script("common/inventory_font_stage.sh", "#!/bin/sh\nprintf 'called\\n' >> \"$LUOSHU_REAL_MODDIR/mapping-calls\"\nexit 0\n")
        for command in ("finalize", "prepare-finalize", "finalize"):
            result = self.run_router(command)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("merger changed the retained stock glyph order", json.loads(result.stdout)["message"])
        self.assertEqual(len((self.module / "mapping-calls").read_text().splitlines()), 1)
        self.assertFalse((self.module / ".luoshu-payload-next").exists())
        # A new explicit request has a new generation identity and may proceed.
        for path in (self.module / "config/mix-stage-next.conf", self.stage / ".luoshu-mix-generation.conf"):
            path.write_text(path.read_text().replace("request-test", "request-next"))
        result = self.run_router("finalize", request="request-next")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.module / ".luoshu-payload-next/system/fonts/MiSansVF.ttf").is_file())
        self.assertEqual(len((self.module / "mapping-calls").read_text().splitlines()), 2)

    def test_parallel_failed_prepare_and_monitor_map_once_and_keep_cause(self):
        self.failing_mapper()
        workers = [subprocess.Popen(["sh", str(ROUTER), "prepare-finalize"],
                   env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)]
        try:
            self.wait_for(self.module / "mapping-entered")
            for command in ("finalize", "prepare-finalize", "finalize"):
                workers.append(subprocess.Popen(["sh", str(ROUTER), command],
                    env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
            for worker in workers:
                out, err = worker.communicate(timeout=10)
                self.assertNotEqual(worker.returncode, 0, out + err)
                self.assertIn("merger changed the retained stock glyph order", json.loads(out)["message"])
            self.assertEqual(len((self.module / "mapping-calls").read_text().splitlines()), 1)
            self.assertEqual((self.module / "logs/fontswitch.log").read_text().count("[MIX] precommit failed:"), 1)
            self.assertFalse((self.module / ".luoshu-payload-next").exists())
        finally:
            for worker in workers:
                if worker.poll() is None:
                    worker.kill()
                worker.wait()

    def test_repeated_status_never_generates_unprepared_or_failed_stage(self):
        self.failing_mapper()
        task = self.module / "config/axes_task.conf"
        task.write_text("task=axes-test\nstate=success\npercent=100\n")
        for _ in range(3):
            result = self.run_router("status")
            self.assertEqual(json.loads(result.stdout)["data"]["state"], "failed")
        self.assertFalse((self.module / "mapping-calls").exists())
        self.run_router("prepare-finalize")
        for _ in range(3):
            result = self.run_router("status")
            data = json.loads(result.stdout)["data"]
            self.assertEqual(data["state"], "failed")
            self.assertIn("merger changed the retained stock glyph order", data["message"])
        self.assertEqual(len((self.module / "mapping-calls").read_text().splitlines()), 1)

    def test_weighted_controller_owns_commit_and_surfaces_exact_mapper_failure(self):
        self.failing_mapper()
        shutil.copyfile(ROUTER, self.module / "common/legacy_v14_4/mix_router.sh")
        runtime = self.module / ".legacy-v14-runtime"
        (runtime / "common").mkdir(parents=True)
        for name in ("config", "cache", "logs"):
            (runtime / name).symlink_to(self.module / name, target_is_directory=True)
        shutil.copyfile(ROOT / "common/legacy_v14_4/font_mix_runtime.sh", runtime / "common/font_mix.sh")
        self.script(".legacy-v14-runtime/common/util_functions.sh", """detect_font_family() { printf '%s\n' "${1%%-*}"; }
detect_font_weight() { echo regular; }
is_variable_font() { return 1; }
""")
        self.script(".legacy-v14-runtime/common/font_check.sh", """font_validate() { FONT_CHECK_VARIABLE=false; FONT_CHECK_FORMAT=TTF; return 0; }
""")
        self.script(".legacy-v14-runtime/common/font_mix_engine.sh", """#!/bin/sh
[ "$1" = start ] || exit 1
printf '%s\n' "$LUOSHU_MIX_CONTROLLER_OWNS_COMMIT" > "$LUOSHU_REAL_MODDIR/controller-owns-commit"
cat > "$MODDIR/config/mix_task.conf" <<EOF_TASK
task=mix-child
state=success
cjk=$2
latin=$3
digit=$4
EOF_TASK
printf '%s\n' '{"status":"ok","data":{"task":"mix-child"}}'
""")
        public = self.module / "public"
        (public / "fonts").mkdir(parents=True)
        for family in ("CJK", "Latin", "Digit"):
            (public / "fonts" / (family + "-Regular.ttf")).write_text("font-source")
        task_root = self.module / "cache/axes-root"
        (self.module / "config/axes_task.conf").write_text(
            "task=axes-test\nstate=queued\npercent=0\ncjk=CJK\nlatin=Latin\ndigit=Digit\n"
            f"root={task_root}\nstarted={int(time.time())}\n"
            "cjkAxes=wght=400\nlatinAxes=wght=400\ndigitAxes=wght=400\n")
        result = subprocess.run(["sh", str(ROOT / "common/legacy_v14_4/v142_weighted_mix.sh"),
                                 "worker", "axes-test"],
                                env={**self.env, "MODDIR": str(runtime), "LUOSHU_PUBLIC_DIR": str(public)},
                                text=True, capture_output=True, timeout=12)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.module / "controller-owns-commit").read_text().strip(), "true")
        self.assertEqual(len((self.module / "mapping-calls").read_text().splitlines()), 1)
        state = (self.module / "config/axes_task.conf").read_text()
        self.assertIn("state=failed\n", state)
        self.assertIn("merger changed the retained stock glyph order", state)
        self.assertNotIn("legacy-v14 composite task finished", (self.module / "logs/fontswitch.log").read_text())
        self.assertFalse((self.module / ".luoshu-payload-next").exists())
        status = json.loads(self.run_router("status").stdout)["data"]
        self.assertEqual(status["state"], "failed")
        self.assertIn("merger changed the retained stock glyph order", status["message"])

    def test_late_legacy_monitor_preserves_failure_and_skips_second_mapping(self):
        self.failing_mapper()
        shutil.copyfile(ROUTER, self.module / "common/legacy_v14_4/mix_router.sh")
        self.run_router("prepare-finalize")
        (self.module / "config/mix_task.conf").write_text("task=mix-child\nstate=success\n")
        result = subprocess.run(["sh", str(ROOT / "common/legacy_v14_4/font_mix_runtime.sh"),
                                 "monitor", "mix-child"], env=self.env,
                                text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len((self.module / "mapping-calls").read_text().splitlines()), 1)
        self.assertIn("merger changed the retained stock glyph order",
                      (self.module / "config/mix-finalize-state.conf").read_text())

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
