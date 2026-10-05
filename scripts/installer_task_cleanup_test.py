#!/usr/bin/env python3
"""Exercise the installer wrapper through the real old-task cancellation path.

Usage: python3 scripts/installer_task_cleanup_test.py [extracted-module-tree]

Only the device installer core/private-mount helpers and Android Python binary
are replaced. Actual customize.sh, runtime-path migration, background_task.sh,
task_scope.sh and task_scope.py run together. All copied files start at 0644,
including a bundled-path shell shim which clears Android Python environment
variables before executing host Python. No runtime/scope Python override is used.
This is a Linux host regression, not Android ELF/loader or on-device validation.
Every live PID in a fixture belongs to a subprocess started by this test.
"""

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    "customize.sh",
    "common/runtime_paths.sh",
    "common/runtime_paths_lock.py",
    "common/background_task.sh",
    "common/task_scope.sh",
    "common/task_scope.py",
)
MODULE_ROOT = ROOT

PYTHON_SHIM = r'''#!/bin/sh
[ "${LUOSHU_RUNTIME_PATHS_PYTHON+x}" != x ] || exit 90
[ "${LUOSHU_TASK_SCOPE_PYTHON+x}" != x ] || exit 91
[ "$(CDPATH= cd -- "$PYTHONHOME" && pwd -P)" = "$MODPATH/common/python" ] || exit 92
[ "$PYTHONPATH" = "$PYTHONHOME/lib/python3.14:$PYTHONHOME/lib/python3.14/site-packages" ] || exit 93
case "$LD_LIBRARY_PATH" in "$PYTHONHOME/lib:$PYTHONHOME/lib/python3.14/lib-dynload"*) ;; *) exit 94 ;; esac
[ ! -e "$MODPATH/.fixture-core-ran" ] || exit 95
case "${1##*/}" in
    runtime_paths_lock.py)
        [ "$1" = "$MODPATH/common/runtime_paths_lock.py" ] || exit 96
        printf 'runtime-python\n' >> "$MODPATH/.fixture-events"
        ;;
    task_scope.py)
        [ "$(CDPATH= cd -- "${1%/*}" && pwd -P)/${1##*/}" = "$MODPATH/common/task_scope.py" ] || exit 97
        [ "$2" = cancel-all ] && [ "$3" = "$LUOSHU_OLD_MOD" ] || exit 98
        printf 'cancel-all-python\n' >> "$MODPATH/.fixture-events"
        if [ "${LUOSHU_TEST_SCOPE_LAUNCH_FAILURE:-}" = true ]; then
            printf 'fixture task Python launch refused\n' >&2
            exit 126
        fi
        ;;
    *) exit 99 ;;
esac
unset PYTHONHOME PYTHONPATH LD_LIBRARY_PATH
exec "$LUOSHU_TEST_HOST_PYTHON" "$@"
'''

CORE_SENTINEL = r'''#!/bin/sh
[ "${LUOSHU_RUNTIME_PATHS_PYTHON+x}" != x ] || return 81
[ "${LUOSHU_TASK_SCOPE_PYTHON+x}" != x ] || return 82
[ -x "$MODPATH/common/python/bin/luoshu-python" ] || return 83
[ ! -x "$MODPATH/common/task_scope.sh" ] || return 84
[ "$(readlink "$MODPATH/config")" = '.luoshu-state/config' ] || return 85
[ "$(cat "$MODPATH/.luoshu-state/paths-v1.conf")" = 'schema=luoshu-runtime-paths-v1' ] || return 86
[ "$(sed -n '1p' "$MODPATH/.fixture-events")" = runtime-python ] || return 87
[ "$(sed -n '2p' "$MODPATH/.fixture-events")" = cancel-all-python ] || return 88
[ -z "${LUOSHU_TEST_REMOVED_PIDFILE:-}" ] || [ ! -e "$LUOSHU_TEST_REMOVED_PIDFILE" ] || return 89
printf 'core\n' >> "$MODPATH/.fixture-events"
printf 'reached\n' > "$MODPATH/.fixture-core-ran"
return 0
'''

PRIVATE_SENTINEL = r'''#!/bin/sh
luoshu_private_unmount_module_view() { return 0; }
luoshu_private_install_migrate() {
    [ -f "$1/.fixture-core-ran" ] || return 1
    printf 'private\n' >> "$1/.fixture-events"
}
'''

# A real shell script at the legacy-owned exact path, without grandchildren.
# Its read blocks on a pipe owned by this test; TERM must stop it through the
# real cancel-all code. This avoids leaving an orphan if an assertion fails.
LEGACY_WORKER = r'''#!/bin/sh
trap 'printf "stopped\n" > "$LUOSHU_TEST_STOPPED"; exit 0' TERM INT
printf 'ready\n' > "$LUOSHU_TEST_READY"
IFS= read -r _fixture_wait
'''


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def snapshot(tree, exclude=()):
    """Record user data, directory layout, links and modes without following links."""
    excluded = set(exclude)
    result = {}
    for directory, subdirs, files in os.walk(tree, followlinks=False):
        for name in subdirs + files:
            path = Path(directory) / name
            relative = path.relative_to(tree).as_posix()
            if relative in excluded:
                continue
            mode = stat.S_IMODE(path.lstat().st_mode)
            if path.is_symlink():
                result[relative] = ("link", mode, os.readlink(path))
            elif path.is_dir():
                result[relative] = ("directory", mode)
            else:
                result[relative] = ("file", mode, path.read_bytes())
    return result


def process_identity(process):
    """Resolve only our Popen child, including hosts with an outer /proc mount."""
    namespace = os.readlink("/proc/self/ns/pid")
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if os.readlink(entry / "ns/pid") != namespace:
                continue
            local_pid = int(entry.name)
            for line in (entry / "status").read_text().splitlines():
                if line.startswith("NSpid:"):
                    local_pid = int(line.split()[-1])
                    break
            if local_pid != process.pid:
                continue
            fields = (entry / "stat").read_text().rsplit(") ", 1)[1].split()
            return dict(pid=process.pid, procPid=int(entry.name), start=fields[19],
                        boot=Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                        namespace=namespace)
        except (OSError, ValueError, IndexError):
            continue
    raise AssertionError("could not resolve test-created subprocess identity")


class InstallerTaskCleanupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for relative in SOURCES:
            if not (MODULE_ROOT / relative).is_file():
                raise AssertionError(f"missing test input: {MODULE_ROOT / relative}")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="luoshu-installer-cleanup-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.module = self.directory / "new module with spaces"
        self.old = self.directory / "old module with spaces"
        self.module.mkdir()
        self.old.mkdir()
        for relative in SOURCES:
            target = self.module / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(MODULE_ROOT / relative, target)
        write(self.module / "common/python/bin/luoshu-python", PYTHON_SHIM)
        write(self.module / "common/python/bin/unrelated-tool", "data only\n")
        write(self.module / "common/python/lib/python3.14/site-packages/fixture.py", "# data\n")
        write(self.module / ".luoshu-runtime/compat/v227/customize.sh", CORE_SENTINEL)
        write(self.module / "common/private_payload.sh", PRIVATE_SENTINEL)
        write(self.module / "config/active_font.conf", "new package default\n")
        write(self.module / "config/.hidden-preference", "keep new preference\n")
        write(self.old / "module.prop", "id=LuoShu\nversion=fixture\n")
        write(self.old / "config/active_font.conf", "用户原有字体\n")
        write(self.old / "config/nested/choice.conf", "keep this choice\n")
        write(self.old / "config/.hidden-preference", "keep old preference\n")
        write(self.old / "logs/user.log", "preserve old history\n")
        write(self.old / "system/fonts/fixture.ttf", "unchanged active font bytes\n")
        for path in self.module.rglob("*"):
            if path.is_file():
                path.chmod(0o644)
        self.env = dict(os.environ)
        for key in tuple(self.env):
            if key.startswith("LUOSHU_") or key in (
                    "CONFIG_DIR", "LOG_DIR", "TMPDIR", "MODDIR", "MODULE_DIR",
                    "PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH"):
                self.env.pop(key)
        self.env.update(MODPATH=str(self.module), LUOSHU_OLD_MOD=str(self.old),
                        LUOSHU_TEST_HOST_PYTHON=sys.executable)
        self.sentinel = self.start_process(
            [sys.executable, "-c", "import time; time.sleep(60)"])
        self.pidfile = self.old / "config/font-worker.pid"
        self.new_preferences = snapshot(self.module / "config")

    def start_process(self, command, **kwargs):
        process = subprocess.Popen(command, stdin=subprocess.PIPE,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   **kwargs)
        self.addCleanup(self.dispose, process)
        return process

    @staticmethod
    def dispose(process):
        # Popen.wait/poll checks and reaps our own children. Never use a PID from
        # a task record, process-name match or process group for fixture cleanup.
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        if process.stdin:
            process.stdin.close()

    def legacy_process(self):
        script = self.old / "common/font_switch_safe.sh"
        write(script, LEGACY_WORKER)
        script.chmod(0o644)
        ready = self.directory / "legacy-ready"
        stopped = self.directory / "legacy-stopped"
        env = dict(self.env, LUOSHU_TEST_READY=str(ready), LUOSHU_TEST_STOPPED=str(stopped))
        process = self.start_process(["sh", str(script)], env=env)
        deadline = time.monotonic() + 3
        while not ready.exists() and time.monotonic() < deadline:
            self.assertIsNone(process.poll(), "legacy fixture exited before readiness")
            time.sleep(.01)
        self.assertTrue(ready.exists(), "legacy fixture did not become ready")
        return process, stopped

    def register(self, process, *, owner=False, task="font_switch_safe.sh"):
        record = dict(process_identity(process), task=task)
        for suffix, key in (("", "pid"), (".task", "task"), (".boot", "boot"), (".start", "start")):
            write(Path(str(self.pidfile) + suffix), str(record[key]) + "\n")
        if owner:
            write(Path(str(self.pidfile) + ".owner.json"), json.dumps(record) + "\n")
        return record

    def invoke(self):
        self.assertEqual(stat.S_IMODE((self.module / "common/python/bin/luoshu-python").stat().st_mode), 0o644)
        result = subprocess.run(
            ["sh", "-c",
             'ui_print() { printf "UI:%s\\n" "$*"; }; '
             'abort() { ui_print "! $*"; return 1; }; . "$1"',
             "installer-task-cleanup-test", str(self.module / "customize.sh")],
            env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=20)
        self.assertIsNone(self.sentinel.poll(), "unrelated test-owned sentinel was killed")
        self.assertEqual(snapshot(self.module / "config"), self.new_preferences)
        self.assertEqual(stat.S_IMODE((self.module / "common/python/bin/luoshu-python").stat().st_mode), 0o755)
        # The shell runner is intentionally still 0644: background_task.sh must
        # invoke it with sh. Only Python actually needs an executable bit.
        for relative in ("common/task_scope.sh", "common/background_task.sh", "common/task_scope.py",
                         "common/python/bin/unrelated-tool", "common/python/lib/python3.14/site-packages/fixture.py"):
            self.assertEqual(stat.S_IMODE((self.module / relative).stat().st_mode), 0o644, relative)
        return result

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue((self.module / ".fixture-core-ran").is_file(), result.stdout)
        self.assertEqual((self.module / ".fixture-events").read_text().splitlines(),
                         ["runtime-python", "cancel-all-python", "core", "private"])

    def assert_rejected(self, result, before, detail=None, exclude=(), expectedcode=125):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertFalse((self.module / ".fixture-core-ran").exists(), result.stdout)
        self.assertEqual((self.module / ".fixture-events").read_text().splitlines(),
                         ["runtime-python", "cancel-all-python"])
        self.assertEqual(snapshot(self.old, exclude), before, "old records/configuration changed after rejection")
        ui_lines = [line[3:] for line in result.stdout.splitlines() if line.startswith("UI:")]
        ui = "\n".join(ui_lines)
        self.assertRegex(ui, rf"错误码\s*{expectedcode}(?!\d)", result.stdout)
        self.assertIn("旧字体任务尚未清理完成", ui, result.stdout)
        self.assertIn("任务记录已保留", ui, result.stdout)
        if detail:
            self.assertIn(detail, ui, "cleanup detail bypassed the manager UI: " + result.stdout)
        self.assertGreaterEqual(len(ui_lines), 3, "missing manager-visible cleanup diagnostic: " + result.stdout)

    def test_fresh_install_without_old_task_records_reaches_core(self):
        before = snapshot(self.old)
        self.assert_success(self.invoke())
        self.assertEqual(snapshot(self.old), before)
        self.assertFalse((self.old / ".luoshu-state").exists(), "old module was initialized/migrated")

    def test_verified_live_legacy_task_stops_before_core_and_preserves_userdata(self):
        process, stopped = self.legacy_process()
        record = self.register(process)
        self.env["LUOSHU_TEST_REMOVED_PIDFILE"] = str(self.pidfile)
        mutable = {self.pidfile.relative_to(self.old).as_posix() + suffix
                   for suffix in ("", ".task", ".start", ".boot", ".cleanup.json")}
        before = snapshot(self.old, mutable)
        self.assert_success(self.invoke())
        self.assertEqual(process.wait(timeout=2), 0)
        self.assertTrue(stopped.is_file(), "legacy process did not receive cooperative TERM")
        for suffix in ("", ".task", ".start", ".boot"):
            self.assertFalse(Path(str(self.pidfile) + suffix).exists())
        proof = json.loads(Path(str(self.pidfile) + ".cleanup.json").read_text())
        self.assertTrue(proof["cleaned"])
        self.assertEqual(proof["leftoverPids"], [])
        self.assertEqual(proof["schema"], "legacy-observed-tree-v1")
        self.assertEqual(proof["ownershipProof"], "boot-exact-command-live-start")
        for key in ("pid", "start", "boot", "task"):
            self.assertEqual(proof[key], record[key])
        self.assertEqual(snapshot(self.old, mutable), before)
        self.assertFalse((self.old / ".luoshu-state").exists(), "old module was initialized/migrated")

    def test_stale_current_boot_owner_does_not_signal_reused_pid(self):
        record = self.register(self.sentinel, owner=True, task="stale-fixture")
        record["start"] = str(int(record["start"]) + 1)
        write(Path(str(self.pidfile) + ".start"), record["start"] + "\n")
        write(Path(str(self.pidfile) + ".owner.json"), json.dumps(record) + "\n")
        before = snapshot(self.old)
        self.assert_rejected(self.invoke(), before, "cleanup-unknown")

    def test_current_boot_legacy_nonowned_process_is_not_signalled(self):
        self.register(self.sentinel)
        before = snapshot(self.old)
        self.assert_rejected(self.invoke(), before, "legacy-command-unconfirmed")

    def test_cleanup_python_launch_failure_is_distinct_from_ownership_failure(self):
        process, stopped = self.legacy_process()
        self.register(process)
        self.env["LUOSHU_TEST_SCOPE_LAUNCH_FAILURE"] = "true"
        before = snapshot(self.old)
        result = self.invoke()
        self.assert_rejected(result, before, "fixture task Python launch refused", expectedcode=126)
        ui = "\n".join(line[3:] for line in result.stdout.splitlines() if line.startswith("UI:"))
        self.assertIn("旧任务检查程序未能启动", ui)
        self.assertNotRegex(ui, r"错误码\s*125")
        self.assertIsNone(process.poll(), "cleanup ran despite failed interpreter launch")
        self.assertFalse(stopped.exists())

    def test_missing_boot_ownership_preserves_live_legacy_task(self):
        process, stopped = self.legacy_process()
        self.register(process)
        Path(str(self.pidfile) + ".boot").unlink()
        before = snapshot(self.old)
        self.assert_rejected(self.invoke(), before, "legacy-boot-missing")
        self.assertIsNone(process.poll())
        self.assertFalse(stopped.exists())

    def test_missing_task_ownership_preserves_live_legacy_task(self):
        process, stopped = self.legacy_process()
        self.register(process)
        Path(str(self.pidfile) + ".task").unlink()
        before = snapshot(self.old)
        self.assert_rejected(self.invoke(), before, "legacy-command-unconfirmed")
        self.assertIsNone(process.poll())
        self.assertFalse(stopped.exists())

    def test_malformed_owner_preserves_evidence_and_unrelated_process(self):
        self.register(self.sentinel)
        write(Path(str(self.pidfile) + ".owner.json"), "{broken ownership JSON\n")
        before = snapshot(self.old)
        self.assert_rejected(self.invoke(), before, "owner-record-invalid")

    def test_legacy_stale_start_preserves_live_process(self):
        process, stopped = self.legacy_process()
        record = self.register(process)
        write(Path(str(self.pidfile) + ".start"), str(int(record["start"]) + 1) + "\n")
        before = snapshot(self.old)
        self.assert_rejected(self.invoke(), before, "legacy-start-mismatch")
        self.assertIsNone(process.poll())
        self.assertFalse(stopped.exists())

    def test_legacy_invalid_boot_preserves_live_process(self):
        process, stopped = self.legacy_process()
        self.register(process)
        write(Path(str(self.pidfile) + ".boot"), "unknown\n")
        before = snapshot(self.old)
        self.assert_rejected(self.invoke(), before, "legacy-boot-invalid")
        self.assertIsNone(process.poll())
        self.assertFalse(stopped.exists())

    def test_failure_after_many_successes_is_visible_in_manager_ui(self):
        # cancel-all scans state/tasks before config. Put 15 safe previous-boot
        # owners there, then a failing current-boot registration in config.
        # Thus the real error follows more than a 12-line UI diagnostic limit.
        mutable = set()
        previous = dict(process_identity(self.sentinel),
                        boot="00000000-0000-0000-0000-000000000000")
        for index in range(15):
            pidfile = self.old / ".luoshu-state/tasks" / f"finished-{index:02}.pid"
            record = dict(previous, task=f"finished-{index:02}")
            for suffix, key in (("", "pid"), (".task", "task"), (".boot", "boot"), (".start", "start")):
                write(Path(str(pidfile) + suffix), str(record[key]) + "\n")
                mutable.add(pidfile.relative_to(self.old).as_posix() + suffix)
            write(Path(str(pidfile) + ".owner.json"), json.dumps(record) + "\n")
            mutable.add(pidfile.relative_to(self.old).as_posix() + ".owner.json")
        record = self.register(self.sentinel, owner=True, task="last-failed-fixture")
        record["start"] = str(int(record["start"]) + 1)
        write(Path(str(self.pidfile) + ".start"), record["start"] + "\n")
        write(Path(str(self.pidfile) + ".owner.json"), json.dumps(record) + "\n")
        before = snapshot(self.old, mutable)
        result = self.invoke()
        self.assert_rejected(result, before, "cleanup-unknown", exclude=mutable)
        self.assertIn("last-failed-fixture", result.stdout)
        for relative in mutable:
            self.assertFalse((self.old / relative).exists(), relative)
        logs = list((self.module / ".luoshu-state/tmp").glob("old-task-check.*.log"))
        self.assertEqual(len(logs), 1, "missing captured cleanup output")
        records = [json.loads(line) for line in logs[0].read_text().splitlines()]
        self.assertEqual([record["status"] for record in records[:15]], ["ok"] * 15)
        self.assertEqual(records[15]["status"], "error")
        self.assertNotIn('"status":"ok"', result.stdout,
                         "successful records should not crowd out the manager-visible error")


if __name__ == "__main__":
    if len(sys.argv) > 2:
        raise SystemExit(f"Usage: {sys.argv[0]} [extracted-module-tree]")
    if len(sys.argv) == 2:
        MODULE_ROOT = Path(sys.argv.pop()).resolve()
    unittest.main(verbosity=2)
