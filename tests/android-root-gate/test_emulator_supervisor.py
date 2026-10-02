"""Host-only lifecycle unit tests; never count as Android qualification."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

RUNNER = Path(__file__).with_name('run_emulator.py')


class SupervisorTests(unittest.TestCase):
    def test_normal_exit_is_reaped(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / 'report.json'
            p = subprocess.run([sys.executable, str(RUNNER), '--root-supervisor',
                                '--binary', '/bin/true', '--cleanup-report', str(report)], timeout=5)
            self.assertEqual(p.returncode, 0)
            self.assertTrue(json.loads(report.read_text())['emulator_reaped'])

    def test_cancellation_reaps_direct_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / 'report.json'
            started = Path(tmp) / 'started'
            fake = Path(tmp) / 'fake-emulator'
            fake.write_text('#!' + sys.executable + '\nimport time\nfrom pathlib import Path\n'
                            + f'Path({str(started)!r}).write_text("ready")\ntime.sleep(30)\n')
            fake.chmod(0o700)
            p = subprocess.Popen([sys.executable, str(RUNNER), '--root-supervisor',
                                  '--binary', str(fake), '--cleanup-report', str(report)])
            try:
                deadline = time.monotonic() + 5
                while not started.exists() and time.monotonic() < deadline:
                    time.sleep(.025)
                self.assertTrue(started.exists())
                p.terminate()
                p.wait(timeout=5)
                self.assertTrue(json.loads(report.read_text())['emulator_reaped'])
            finally:
                if p.poll() is None:
                    p.terminate(); p.wait(timeout=25)
