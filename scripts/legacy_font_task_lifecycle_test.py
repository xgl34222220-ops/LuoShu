#!/usr/bin/env python3
"""Real Linux task trees exercise the legacy engine, monitor and prewarm exits."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


def alive(pid: int) -> bool:
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()[0] != "Z"
    except (FileNotFoundError, ProcessLookupError):
        return False


class LegacyFontTaskLifecycle(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luoshu-legacy-scope-")
        self.addCleanup(self.temp.cleanup)
        self.module = Path(self.temp.name) / "module"
        self.public = Path(self.temp.name) / "public"
        (self.module / "common/legacy_v14_4").mkdir(parents=True)
        (self.module / "config").mkdir()
        (self.module / "logs").mkdir()
        (self.module / ".luoshu-payload/system/fonts").mkdir(parents=True)
        (self.module / ".luoshu-payload/system/fonts/Roboto-Regular.ttf").write_bytes(b"frozen-live" * 200)
        (self.module / "module.prop").write_text("id=LuoShu\nversion=test\n")
        (self.module / "config/device_font_inventory.json").write_text('{"state":"ready"}')
        (self.public / "fonts").mkdir(parents=True)
        for name in ("CJK", "Latin", "Digit", "Demo"):
            (self.public / "fonts" / (name + "-Regular.ttf")).write_bytes((name.encode() + b"font") * 400)
        for name in ("background_task.sh", "task_scope.sh", "task_scope.py", "runtime_paths.sh", "runtime_paths_lock.py", "font_switch_lock.sh"):
            shutil.copyfile(ROOT / "common" / name, self.module / "common" / name)
        for name in ("font_mix_engine.sh", "font_mix_runtime.sh", "font_switch_safe.sh", "payload_clone.sh"):
            shutil.copyfile(ROOT / "common/legacy_v14_4" / name, self.module / "common/legacy_v14_4" / name)
        shutil.copyfile(ROOT / "common/legacy_v14_4/font_mix_engine.sh", self.module / "common/font_mix_engine.sh")
        shutil.copyfile(ROOT / "common/legacy_v14_4/font_mix_runtime.sh", self.module / "common/font_mix.sh")
        utilities = '''get_weight_file() { printf '%s/fonts/%s-Regular.ttf\\n' "$LUOSHU_PUBLIC_DIR" "$1"; }
detect_font_family() { printf '%s\\n' "${1%%-*}"; }
ensure_public_storage() { return 0; }
check_coloros() { IS_COLOROS=false; }
check_hyperos() { IS_HYPEROS=false; }
'''
        checker = "font_validate() { FONT_CHECK_ERROR=''; return 0; }\n"
        mapper = '''_font_store_reset() { mkdir -p "$1/.luoshu-font-store"; }
_font_anchor() { cp "$1" "$2/.luoshu-font-store/$3.font"; printf '%s/.luoshu-font-store/%s.font\\n' "$2" "$3"; }
_font_alias() { cp "$1" "$2"; }
get_all_generic_files() { printf 'Roboto-Regular.ttf\\n'; }
_rom_exact_target_exists() { return 1; }
apply_font_by_rom() {
    mkdir -p "$2/.luoshu-font-store"
    if [ "${FIXTURE_PREWARM_HOLD:-}" = 1 ]; then
        "$LUOSHU_TASK_SCOPE_PYTHON" "$MODDIR/common/lifecycle-composite.py" --output "$2/Roboto-Regular.ttf"
        return $?
    fi
    cp "$1" "$2/.luoshu-font-store/regular.font"; cp "$1" "$2/Roboto-Regular.ttf"
}
'''
        for directory in (self.module / "common", self.module / "common/legacy_v14_4"):
            (directory / "util_functions.sh").write_text(utilities)
            (directory / "font_check.sh").write_text(checker)
            (directory / "rom_adapters.sh").write_text(mapper)
        (self.module / "common/composite_font.py").write_text("# lifecycle fixture only\n")
        (self.module / "common/luoshu_composite.sh").write_text('''#!/bin/sh
if [ "${1:-}" = --self-test ]; then printf 'ok\\n'; exit 0; fi
exec "$LUOSHU_TASK_SCOPE_PYTHON" "$MODDIR/common/lifecycle-composite.py" "$@"
''')
        (self.module / "common/lifecycle-composite.py").write_text('''import os,subprocess,sys,time
from pathlib import Path
child=subprocess.Popen([sys.executable,'-c','import json,os,signal,time; from pathlib import Path; signal.signal(signal.SIGTERM,signal.SIG_IGN); Path(os.environ["FIXTURE_CHILD_PID"]).write_text(json.dumps(dict(pid=os.getpid(),procPid=int(os.readlink("/proc/self"))))); time.sleep(120)'],start_new_session=True)
while not Path(os.environ['FIXTURE_CHILD_PID']).exists(): time.sleep(.01)
mode=os.environ.get('FIXTURE_MODE','success')
if mode=='hold':
    while True: time.sleep(.1)
if mode=='failed': sys.exit(7)
output=sys.argv[sys.argv.index('--output')+1]
Path(output).write_bytes(b'fixture-composite'*200)
print('{"status":"ok"}')
''')
        (self.module / "common/legacy_v14_4/mix_router.sh").write_text('''#!/bin/sh
if [ "${1:-}" = finalize ]; then
    "$LUOSHU_TASK_SCOPE_PYTHON" -c 'import json,os; from pathlib import Path; p=Path(os.environ["FIXTURE_CHILD_PID"]); pid=json.loads(p.read_text())["procPid"]; alive=False; s=Path("/proc")/str(pid)/"stat"; alive=s.exists() and s.read_text().rsplit(") ",1)[1].split()[0]!="Z"; Path(os.environ["FIXTURE_FINALIZE"]).write_text("bad-child-alive" if alive else "committed")'
fi
''')
        self.childfile = Path(self.temp.name) / "child.pid"
        self.finalize = Path(self.temp.name) / "finalize"
        self.env = {**os.environ, "MODDIR": str(self.module), "LUOSHU_REAL_MODDIR": str(self.module),
                    "LUOSHU_PUBLIC_DIR": str(self.public), "LUOSHU_TASK_SCOPE_PYTHON": sys.executable,
                    "LUOSHU_RUNTIME_PATHS_PYTHON": sys.executable,
                    "LUOSHU_TASK_TIMEOUT_SECONDS": "8", "LUOSHU_MIX_TASK_TIMEOUT": "8",
                    "LUOSHU_MIX_MONITOR_TIMEOUT": "10", "FIXTURE_CHILD_PID": str(self.childfile),
                    "FIXTURE_FINALIZE": str(self.finalize)}
        self.addCleanup(self.stop_owned_fixture)

    def stop_owned_fixture(self):
        if self.childfile.exists():
            child = json.loads(self.childfile.read_text())
            if alive(child["procPid"]):
                os.kill(child["pid"], signal.SIGKILL)
        # Only supervisors created by this isolated fixture are cancelled.
        tasks = self.module / ".luoshu-state/tasks"
        for owner in tasks.glob("*.owner.json"):
            record = json.loads(owner.read_text())
            subprocess.run([sys.executable, str(self.module / "common/task_scope.py"),
                            "cancel", record["pidfile"], record["task"]],
                           env=self.env, capture_output=True, timeout=8)

    def call(self, script: str, *args: str, mode="success", extra_env=None):
        result = subprocess.run(["sh", str(self.module / "common" / script), *args],
                                env={**self.env, "FIXTURE_MODE": mode, **(extra_env or {})}, capture_output=True,
                                text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def wait_terminal(self, filename="mix_task.conf", limit=10, expected_task=None):
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            path = self.module / "config" / filename
            values = dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line) if path.exists() else {}
            if (expected_task is None or values.get("task") == expected_task) and values.get("state") in {"success", "failed", "cancelled"}:
                return values
            time.sleep(.04)
        self.fail("legacy task did not reach a bounded terminal state")

    def assert_child_retired(self):
        if not self.childfile.exists():
            details = {}
            for name in ("config/mix_task.conf", "logs/fontswitch.log", ".luoshu-state/tasks/legacy-mix-switch.lock/pid"):
                path = self.module / name
                if path.exists():
                    details[name] = path.read_text()
            self.fail("fixture did not run: " + json.dumps(details, ensure_ascii=False))
        self.assertFalse(alive(json.loads(self.childfile.read_text())["procPid"]), "legacy task published terminal state while its reparented child was alive")
        self.assertEqual((self.module / ".luoshu-payload/system/fonts/Roboto-Regular.ttf").read_bytes(), b"frozen-live" * 200)

    def assert_cleaned_scopes(self):
        tasks = self.module / ".luoshu-state/tasks"
        deadline = time.monotonic() + 3
        while list(tasks.glob("*.owner.json")) and time.monotonic() < deadline:
            time.sleep(.03)
        self.assertFalse(list(tasks.glob("*.owner.json")), "task still has a live supervision owner")
        self.assertFalse(list(tasks.glob("*.pid")), "finished task kept its PID record")
        proofs = list(tasks.glob("*.cleanup.json"))
        self.assertTrue(proofs)
        for proof in proofs:
            record = json.loads(proof.read_text())
            self.assertTrue(record["cleaned"], record)
            self.assertEqual(record["leftoverPids"], [], record)
        self.assertFalse(list((self.module / ".luoshu-state/tmp").glob("task-*")), "supervisor left task staging behind")

    def test_01_success_retires_child_before_terminal(self):
        self.call("font_mix_engine.sh", "start", "CJK", "Latin", "Digit")
        self.assertEqual(self.wait_terminal()["state"], "success")
        self.assert_child_retired()
        self.assert_cleaned_scopes()

    def test_02_failed_build_retires_child_before_terminal(self):
        self.call("font_mix_engine.sh", "start", "CJK", "Latin", "Digit", mode="failed")
        self.assertEqual(self.wait_terminal()["state"], "failed")
        self.assert_child_retired()
        self.assert_cleaned_scopes()

    def test_03_runtime_finalizes_only_clean_engine(self):
        self.call("font_mix.sh", "start", "CJK", "Latin", "Digit")
        self.assertEqual(self.wait_terminal("mix-finalize-state.conf")["state"], "success")
        self.assertEqual(self.finalize.read_text(), "committed")
        self.assert_child_retired()
        self.assert_cleaned_scopes()

    def test_04_cancel_waits_for_cleanup(self):
        response = self.call("font_mix_engine.sh", "start", "CJK", "Latin", "Digit", mode="hold")
        task = json.loads(response.stdout)["data"]["task"]
        deadline = time.monotonic() + 3
        while not self.childfile.exists() and time.monotonic() < deadline:
            time.sleep(.03)
        cancelled = self.call("font_mix_engine.sh", "cancel", task)
        self.assertEqual(json.loads(cancelled.stdout)["data"]["cleaned"], True)
        self.assertEqual(self.wait_terminal()["state"], "cancelled")
        self.assert_child_retired()
        self.assert_cleaned_scopes()

    def test_05_prewarm_drops_all_pid_sidecars_on_normal_exit(self):
        self.call("legacy_v14_4/font_switch_safe.sh", "action", "prewarm-start", "Demo")
        deadline = time.monotonic() + 8
        cache = self.module / ".luoshu-state/cache/safe-switch-cache"
        while not list(cache.glob("*/cache.conf")) and time.monotonic() < deadline:
            time.sleep(.04)
        self.assertTrue(list(cache.glob("*/cache.conf")), "prewarm fixture did not complete")
        time.sleep(.15)
        # .pid.lock retains one stable flock inode; it is not an owner/PID.
        leftovers = [p for p in self.module.rglob("font-prewarm-*.pid*") if not p.name.endswith((".cleanup.json", ".pid.lock"))]
        self.assertFalse(leftovers, "completed prewarm left PID/identity sidecars")
        self.assertEqual((self.module / ".luoshu-payload/system/fonts/Roboto-Regular.ttf").read_bytes(), b"frozen-live" * 200)
        self.assert_cleaned_scopes()

    def test_06_timeout_retires_children_and_staging(self):
        self.call("font_mix_engine.sh", "start", "CJK", "Latin", "Digit", mode="hold",
                  extra_env={"LUOSHU_MIX_TASK_TIMEOUT": "1"})
        self.assertEqual(self.wait_terminal()["state"], "failed")
        self.assert_child_retired()
        self.assert_cleaned_scopes()

    def test_07_runtime_cancel_retires_monitor_and_engine(self):
        response = self.call("font_mix.sh", "start", "CJK", "Latin", "Digit", mode="hold")
        task = json.loads(response.stdout)["data"]["task"]
        deadline = time.monotonic() + 3
        while not self.childfile.exists() and time.monotonic() < deadline:
            time.sleep(.03)
        self.call("font_mix.sh", "cancel", task)
        self.assertEqual(self.wait_terminal("mix-finalize-state.conf")["state"], "cancelled")
        self.assertFalse(self.finalize.exists(), "cancelled monitor committed a payload")
        self.assert_child_retired()
        self.assert_cleaned_scopes()

    def test_08_prewarm_cancel_retires_reparented_font_worker(self):
        process = subprocess.Popen(["sh", str(self.module / "common/legacy_v14_4/font_switch_safe.sh"),
                                    "action", "prewarm-start", "Demo"],
                                   env={**self.env, "FIXTURE_MODE": "hold", "FIXTURE_PREWARM_HOLD": "1"},
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: process.poll() is None and process.kill())
        deadline = time.monotonic() + 3
        while not self.childfile.exists() and time.monotonic() < deadline:
            time.sleep(.03)
        self.assertTrue(self.childfile.exists())
        tasks = self.module / ".luoshu-state/tasks"
        owners = list(tasks.glob("font-prewarm-*.pid.owner.json"))
        self.assertEqual(len(owners), 1)
        owner = json.loads(owners[0].read_text())
        cancelled = subprocess.run(["sh", str(self.module / "common/task_scope.sh"), "cancel",
                                    owner["pidfile"], owner["task"]],
                                   env=self.env, capture_output=True, text=True, timeout=8)
        self.assertEqual(cancelled.returncode, 0, cancelled.stdout + cancelled.stderr)
        self.assertTrue(json.loads(cancelled.stdout)["data"]["cleaned"])
        process.communicate(timeout=8)
        self.assertNotEqual(process.returncode, 0)
        self.assert_child_retired()
        self.assert_cleaned_scopes()
        # Cancellation must release the prewarm transaction lock as well.
        self.call("legacy_v14_4/font_switch_safe.sh", "action", "prewarm-start", "Demo")
        self.assertTrue(list((self.module / ".luoshu-state/cache/safe-switch-cache").glob("*/cache.conf")))
        self.assert_cleaned_scopes()

    def test_09_cancelled_engine_can_start_next_task(self):
        first = self.call("font_mix_engine.sh", "start", "CJK", "Latin", "Digit", mode="hold")
        first_task = json.loads(first.stdout)["data"]["task"]
        deadline = time.monotonic() + 3
        while not self.childfile.exists() and time.monotonic() < deadline:
            time.sleep(.03)
        self.call("font_mix_engine.sh", "cancel", first_task)
        self.assert_child_retired()
        self.assert_cleaned_scopes()
        self.childfile.unlink()
        second = self.call("font_mix_engine.sh", "start", "CJK", "Latin", "Digit", mode="failed")
        second_task = json.loads(second.stdout)["data"]["task"]
        self.assertNotEqual(second_task, first_task)
        self.assertEqual(self.wait_terminal(expected_task=second_task)["state"], "failed")
        self.assert_child_retired()
        self.assert_cleaned_scopes()


if __name__ == "__main__":
    unittest.main()
