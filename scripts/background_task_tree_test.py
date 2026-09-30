#!/usr/bin/env python3
"""Real process tests for cancellation, reparenting and switch-worker signals."""
import os
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from host_task_scope_fixture import install_task_scope

ROOT = Path(__file__).resolve().parents[1]


def alive(pid, proc_id=None):
    try:
        return Path(f"/proc/{proc_id or pid}/stat").read_text().split(") ", 1)[1].split()[0] != "Z"
    except FileNotFoundError:
        return False


class BackgroundTreeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.proc = self.root / "proc"
        self.proc.mkdir()
        # Some executor containers expose a procfs from an outer PID namespace.
        # The workers report their true identities; only the /proc/ps transport
        # is a fixture. Signals, reparenting and process termination remain real.
        ps = self.bin / "ps"
        ps.write_text(f"#!/bin/sh\ncat '{self.root / 'process-tree'}'\n")
        ps.chmod(0o755)
        self.env = {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}",
                    "LUOSHU_PROC_ROOT": str(self.proc)}

    def spawn(self, command, **kwargs):
        process = subprocess.Popen(command, start_new_session=True,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)

        def cleanup():
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)

        self.addCleanup(cleanup)
        return process

    def wait_for(self, predicate):
        end = time.monotonic() + 5
        while time.monotonic() < end:
            if predicate():
                return
            time.sleep(0.02)
        self.fail("condition not reached within five seconds")

    def worker_files(self):
        leaf = self.root / "fonttools-worker.py"
        leaf.write_text("import os, signal, time, json\nfrom pathlib import Path\n"
                        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                        f"Path({str(self.root / 'leaf.pid')!r}).write_text(str(os.getpid()))\n"
                        f"Path({str(self.root / 'leaf.json')!r}).write_text(json.dumps("
                        "[os.getpid(), os.getppid(), os.readlink('/proc/self')]))\n"
                        "while True: time.sleep(0.02)\n")
        middle = self.root / "middle.sh"
        middle.write_text("#!/bin/sh\n"
                          f"printf '%s %s ' \"$$\" \"$PPID\" > '{self.root / 'middle.info'}'\n"
                          f"IFS= read -r stat < /proc/self/stat\nprintf '%s\\n' \"${{stat%% *}}\" >> '{self.root / 'middle.info'}'\n"
                          f"{sys.executable} '{leaf}' &\nwait $!\n")
        manager = self.root / "manager.sh"
        manager.write_text("#!/bin/sh\ntrap 'exit 143' TERM\n"
                           f"printf '%s %s ' \"$$\" \"$PPID\" > '{self.root / 'manager.info'}'\n"
                           f"IFS= read -r stat < /proc/self/stat\nprintf '%s\\n' \"${{stat%% *}}\" >> '{self.root / 'manager.info'}'\n"
                           f"sh '{middle}' &\nwait $!\n")
        return manager

    def snapshot(self):
        self.wait_for(lambda: (self.root / "leaf.json").exists())
        records = [list(map(int, (self.root / f"{name}.info").read_text().split()))
                   for name in ("manager", "middle")]
        leaf = json.loads((self.root / "leaf.json").read_text())
        records.append(leaf)
        for pid, _, proc_id in records:
            folder = self.proc / str(pid)
            folder.mkdir(exist_ok=True)
            (folder / "stat").write_text(Path(f"/proc/{proc_id}/stat").read_text())
        (self.root / "process-tree").write_text("PID PPID\n" + "\n".join(
            f"{pid} {ppid}" for pid, ppid, _ in records))
        return leaf

    def test_kills_term_ignoring_grandchild_after_parent_exits(self):
        manager = self.worker_files()
        worker = self.spawn(["sh", str(manager)])
        sentinel = self.spawn([sys.executable, "-c", "import time; time.sleep(60)"])
        leaf, _, proc_id = self.snapshot()
        subprocess.run(["sh", "-c", '. "$1"; luoshu_terminate_task_tree "$2"', "sh",
                        str(ROOT / "common/background_task.sh"), str(worker.pid)],
                       env=self.env, check=True, timeout=5)
        self.wait_for(lambda: not alive(leaf, proc_id))
        self.assertIsNotNone(worker.poll())
        self.assertIsNone(sentinel.poll(), "cancellation killed an unrelated process")

    def test_old_boot_sidecar_does_not_kill_reused_pid(self):
        sentinel = self.spawn([sys.executable, "-c", "import time; time.sleep(60)", "old-task"])
        pidfile = self.root / "task.pid"
        pidfile.write_text(str(sentinel.pid))
        Path(str(pidfile) + ".task").write_text("old-task")
        Path(str(pidfile) + ".boot").write_text("previous-boot")
        subprocess.run(["sh", "-c", '. "$1"; luoshu_stop_task_pid "$2"', "sh",
                        str(ROOT / "common/background_task.sh"), str(pidfile)], check=True, timeout=5)
        self.assertIsNone(sentinel.poll())
        self.assertFalse(pidfile.exists())

    def test_switch_worker_term_exits_and_cleans_nested_generator(self):
        manager = self.worker_files()
        module = self.root / "module"
        (module / "common").mkdir(parents=True)
        (module / "config").mkdir()
        (module / "common/background_task.sh").symlink_to(ROOT / "common/background_task.sh")
        worker = self.spawn(["sh", str(ROOT / "common/font_switch_task.sh"),
                             "run", "signal-task", "custom-font", "1"],
                            env={**self.env, "MODDIR": str(module), "LUOSHU_FONT_MANAGER": str(manager)})
        leaf, _, proc_id = self.snapshot()
        worker.terminate()
        self.assertEqual(worker.wait(timeout=5), 143)
        self.wait_for(lambda: not alive(leaf, proc_id))
        task = (module / "config/switch_task.conf").read_text()
        self.assertIn("state=failed\n", task)
        self.assertIn("task=signal-task\n", task)
        self.assertFalse(list((module / "config").glob("*.progress.*")))

    def start_provider(self, stale_lock=False):
        manager = self.worker_files()
        module = self.root / "module"
        (module / "common").mkdir(parents=True)
        (module / "config").mkdir()
        (module / "config/active_font.conf").write_text("custom\n")
        install_task_scope(module)
        for name in ("font_switch_lock.sh",):
            (module / "common" / name).symlink_to(ROOT / "common" / name)
        (module / "common/google_font_provider_bridge.sh").write_text(
            f'case "$1" in fingerprint) echo current;; apply) exec sh "{manager}";; esac\n')
        getprop = self.bin / "getprop"
        getprop.write_text("#!/bin/sh\necho 1\n")
        getprop.chmod(0o755)
        if stale_lock:
            lock = module / ".google-font-provider.lock"
            lock.mkdir()
            # A reused live PID from another boot must neither block nor be killed.
            (lock / "pid").write_text(f"{os.getpid()}\nboot_id=previous-boot\n")
        service = self.spawn(["sh", str(ROOT / "common/google_font_provider_service.sh")],
                             env={**self.env, "MODDIR": str(module)})
        leaf, _, proc_id = self.snapshot()
        return module, service, leaf, proc_id

    def test_provider_service_term_reaps_active_generator_and_releases_singleton(self):
        module, service, leaf, proc_id = self.start_provider()
        sentinel = self.spawn([sys.executable, "-c", "import time; time.sleep(60)"])
        # A second invocation must not enter the generator or release the first
        # worker's singleton. Snapshot its complete identity, including token.
        lock = module / ".google-font-provider.lock/pid"
        owner = lock.read_text()
        duplicate = subprocess.run(
            ["sh", str(ROOT / "common/google_font_provider_service.sh")],
            env={**self.env, "MODDIR": str(module)}, timeout=5,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.assertEqual(duplicate.returncode, 0)
        self.assertEqual(lock.read_text(), owner)
        self.assertIsNone(service.poll())
        service.terminate()
        self.assertEqual(service.wait(timeout=5), 143)
        self.wait_for(lambda: not alive(leaf, proc_id))
        self.assertFalse((module / ".google-font-provider.lock").exists())
        self.assertIsNone(sentinel.poll(), "provider cancellation killed an unrelated process")

    def test_provider_reclaims_old_boot_identity_and_cancels_cleanly(self):
        module, service, leaf, proc_id = self.start_provider(stale_lock=True)
        self.assertNotIn("previous-boot", (module / ".google-font-provider.lock/pid").read_text())
        service.terminate()
        self.assertEqual(service.wait(timeout=5), 143)
        self.wait_for(lambda: not alive(leaf, proc_id))
        self.assertFalse((module / ".google-font-provider.lock").exists())

    def test_scoped_cancel_never_erases_or_kills_new_request_owner(self):
        pidfile = self.root / 'owned.pid'
        worker = self.root / 'cooperative.py'
        worker.write_text('import signal,time\nfrom pathlib import Path\n'
                          'def stop(sig,frame):\n'
                          f' Path({str(self.root / "stopping")!r}).write_text("yes")\n'
                          ' time.sleep(.4)\n raise SystemExit(0)\n'
                          'signal.signal(signal.SIGTERM,stop)\n'
                          f'Path({str(self.root / "scope-ready")!r}).write_text("yes")\n'
                          'while True: time.sleep(.05)\n')
        scope = self.spawn([sys.executable, str(ROOT / 'common/task_scope.py'),
                            '--pid-file', str(pidfile), '--task', 'old-request',
                            '--', sys.executable, str(worker)])
        pidfile.write_text(str(scope.pid))
        Path(str(pidfile)+'.task').write_text('old-request')
        Path(str(pidfile)+'.boot').write_text(Path('/proc/sys/kernel/random/boot_id').read_text())
        self.wait_for(lambda: (self.root / 'scope-ready').exists())
        cancel = self.spawn(['sh', '-c', '. "$1"; luoshu_stop_task_pid "$2"',
                             'cancel', str(ROOT / 'common/background_task.sh'), str(pidfile)])
        self.wait_for(lambda: (self.root / 'stopping').exists())
        sentinel = self.spawn([sys.executable, '-c', 'import time; time.sleep(60)', 'new-request'])
        pidfile.write_text(str(sentinel.pid))
        Path(str(pidfile)+'.task').write_text('new-request')
        cancel.wait(timeout=6)
        scope.wait(timeout=6)
        self.assertEqual(pidfile.read_text(), str(sentinel.pid))
        self.assertEqual(Path(str(pidfile)+'.task').read_text(), 'new-request')
        self.assertIsNone(sentinel.poll())

    def test_scope_deadline_kills_uncooperative_worker_within_cleanup_budget(self):
        code = "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"
        started = time.monotonic()
        result = subprocess.run(
            [sys.executable, str(ROOT / "common/task_scope.py"), "--timeout", "0.2", "--",
             sys.executable, "-c", code], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 124, result.stderr)
        report = json.loads(next(line.removeprefix("[TASK-CLEANUP] ")
                                 for line in result.stderr.splitlines()
                                 if line.startswith("[TASK-CLEANUP] ")))
        self.assertTrue(report["deadlineExceeded"])
        self.assertEqual(report["leftoverPids"], [])
        self.assertLess(time.monotonic() - started, 4.5)

    def test_provider_cancel_preserves_replacement_lock_token(self):
        module, service, leaf, proc_id = self.start_provider()
        lock = module / ".google-font-provider.lock/pid"
        owner = lock.read_text()
        # Same PID/starttime, newer token: stale cleanup may not remove it.
        replacement = "\n".join("token=replacement-owner" if line.startswith("token=")
                                else line for line in owner.splitlines()) + "\n"
        lock.write_text(replacement)
        service.terminate()
        self.assertEqual(service.wait(timeout=5), 143)
        self.wait_for(lambda: not alive(leaf, proc_id))
        self.assertEqual(lock.read_text(), replacement)


if __name__ == "__main__":
    unittest.main()
