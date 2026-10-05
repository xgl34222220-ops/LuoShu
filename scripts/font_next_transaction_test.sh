#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "${0%/*}/.." && pwd)
python3 - "$ROOT/common/font_next_transaction.sh" <<'PY'
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

HELPER = str(Path(sys.argv.pop()).resolve())
FILES = ['font-payload-next.conf', 'active_font.conf', 'text_reboot_required.conf',
         'font_runtime_legacy_v14_4.conf', 'font-payload-schema.conf',
         'device-font-engine.conf', 'device-font-installed.conf', 'device-font-dynamic-mount.conf',
         'device-font-load-verification.json', 'device-font-load-verification.conf',
         'font-payload-rebuild-pending.conf', 'font-payload-reapply-notified.conf',
         'device-font-cache-pending.conf']
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()

class NextTransactionTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='luoshu-next-transaction-')
        self.addCleanup(self.temporary.cleanup)
        self.module = Path(self.temporary.name) / 'module'
        self.config = self.module / '.luoshu-state/config'
        self.work = self.module / '.luoshu-state/tmp/task'
        self.backup = self.module / '.luoshu-state/backup'
        for directory in (self.config, self.work, self.backup): directory.mkdir(parents=True)
        self.next = self.module / '.luoshu-payload-next'; self.next.mkdir()
        (self.next / 'B.ttf').write_bytes(b'old pending B\0font')
        self.live = self.module / '.luoshu-payload'; self.live.mkdir()
        (self.live / 'A.ttf').write_bytes(b'boot A must stay immutable')
        self.stage = self.work / 'stage'; self.stage.mkdir()
        (self.stage / 'C.ttf').write_bytes(b'new pending C\0font')
        self.state = self.work / 'next-state.conf'
        self.state.write_bytes(b'state=prepared\nfont=C\nrequestId=test-C\npreviousFont=A\n')
        self.before = {}
        for index, name in enumerate(FILES):
            if index % 3 == 2: continue
            data = ('old-' + name + '\n').encode()
            (self.config / name).write_bytes(data); (self.config / name).chmod(0o640)
            self.before[name] = data
        self.journal = self.backup / 'next-transaction'

    def run_shell(self, body, timeout=8):
        return subprocess.run(['sh', '-c', '. "$1"; m="$2"; stage="$3"; newstate="$4"\n' + body,
                               'test', HELPER, str(self.module), str(self.stage), str(self.state)],
                              capture_output=True, text=True, timeout=timeout)

    def begin(self): return 'luoshu_next_transaction_begin "$m" "$stage" "$newstate"'

    def changed_selection(self):
        return '\n'.join('printf changed > "$m/.luoshu-state/config/' + name + '"' for name in FILES[1:])

    def assert_prior(self):
        self.assertEqual((self.next / 'B.ttf').read_bytes(), b'old pending B\0font')
        self.assertFalse((self.next / 'C.ttf').exists())
        for name in FILES:
            path = self.config / name
            if name in self.before:
                self.assertEqual(path.read_bytes(), self.before[name], name)
                self.assertEqual(path.stat().st_mode & 0o777, 0o640, name)
            else: self.assertFalse(path.exists(), name)
        self.assertEqual((self.live / 'A.ttf').read_bytes(), b'boot A must stay immutable')

    def test_success_replaces_next_and_commits_selection_without_touching_live(self):
        result = self.run_shell(self.begin() + ' || exit $?\n' + self.changed_selection() +
                                '\nluoshu_next_transaction_commit "$m"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.next / 'C.ttf').read_bytes(), b'new pending C\0font')
        self.assertFalse((self.next / 'B.ttf').exists()); self.assertFalse(self.journal.exists())
        self.assertEqual((self.config / FILES[0]).read_bytes(), self.state.read_bytes())
        self.assertEqual((self.live / 'A.ttf').read_bytes(), b'boot A must stay immutable')

    def test_rollback_restores_prior_bytes_modes_and_absences(self):
        result = self.run_shell(self.begin() + ' || exit $?\n' + self.changed_selection() +
                                '\nluoshu_next_transaction_rollback "$m"')
        self.assertEqual(result.returncode, 0, result.stderr); self.assert_prior()
        self.assertFalse(self.journal.exists())

    def test_stage_rename_failure_preserves_previously_prepared_B(self):
        result = self.run_shell('mv() { [ "$1" != "$stage" ] || return 19; command mv "$@"; }\n' + self.begin())
        self.assertEqual(result.returncode, 1); self.assert_prior()
        self.assertTrue((self.stage / 'C.ttf').exists()); self.assertFalse(self.journal.exists())

    def test_next_state_write_failure_restores_prior_payload_and_state(self):
        result = self.run_shell('cp() { [ "$2" != "$newstate" ] || return 20; command cp "$@"; }\n' + self.begin())
        self.assertEqual(result.returncode, 1); self.assert_prior(); self.assertFalse(self.journal.exists())

    def test_failed_rollback_retains_journal_and_retry_restores_selection(self):
        result = self.run_shell(self.begin() + ' || exit $?\n' + self.changed_selection() +
                                '\ncp() { case "$3" in */restore-state.conf) return 21 ;; esac; command cp "$@"; }\n'
                                'luoshu_next_transaction_rollback "$m"')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertTrue((self.journal / 'journal.conf').exists())
        retry = self.run_shell('luoshu_next_transaction_recover "$m"')
        self.assertEqual(retry.returncode, 0, retry.stderr); self.assert_prior()

    def hold_after_begin(self):
        ready = self.work / 'ready'
        body = self.begin() + ' || exit $?\n' + self.changed_selection() + \
               '\nprintf ready > "$m/.luoshu-state/tmp/task/ready"\nread hold'
        process = subprocess.Popen(['sh', '-c', '. "$1"; m="$2"; stage="$3"; newstate="$4"\n' + body,
                                   'test', HELPER, str(self.module), str(self.stage), str(self.state)],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.dispose, process)
        deadline = time.monotonic() + 5
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline: time.sleep(.02)
        self.assertTrue(ready.exists(), process.communicate(timeout=1) if process.poll() is not None else 'no ready')
        return process

    @staticmethod
    def dispose(process):
        if process.poll() is None: process.kill()
        process.communicate(timeout=3)

    def test_supervisor_loss_recovers_previous_pending_tuple(self):
        process = self.hold_after_begin(); process.kill(); process.communicate(timeout=3)
        result = self.run_shell('luoshu_next_transaction_recover "$m"')
        self.assertEqual(result.returncode, 0, result.stderr); self.assert_prior(); self.assertFalse(self.journal.exists())

    def test_second_publisher_cannot_recover_living_transaction(self):
        process = self.hold_after_begin()
        result = self.run_shell('luoshu_next_transaction_recover "$m"')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertTrue(self.journal.exists()); self.assertTrue((self.next / 'C.ttf').exists())
        process.kill(); process.communicate(timeout=3)
        self.assertEqual(self.run_shell('luoshu_next_transaction_recover "$m"').returncode, 0); self.assert_prior()

    def test_unrelated_exit_trap_cannot_rollback_dead_publisher_without_recovery_lock(self):
        process = self.hold_after_begin(); process.kill(); process.communicate(timeout=3)
        result = self.run_shell('luoshu_next_transaction_rollback "$m"')
        self.assertEqual(result.returncode, 2)
        self.assertTrue((self.next / 'C.ttf').exists()); self.assertTrue(self.journal.exists())
        result = self.run_shell('luoshu_next_transaction_recover "$m"')
        self.assertEqual(result.returncode, 0, result.stderr); self.assert_prior()

    def test_committed_cleanup_failure_never_rolls_selection_back(self):
        result = self.run_shell(self.begin() + ' || exit $?\n' + self.changed_selection() +
                                '\nrm() { [ "$2" != "$m/.luoshu-state/backup/next-transaction/payload" ] || return 23; command rm "$@"; }\n'
                                'luoshu_next_transaction_commit "$m"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('state=committed', (self.journal / 'journal.conf').read_text())
        self.assertTrue((self.next / 'C.ttf').exists())
        self.assertEqual(self.run_shell('luoshu_next_transaction_recover "$m"').returncode, 0)
        self.assertTrue((self.next / 'C.ttf').exists())
        self.assertEqual((self.config / 'active_font.conf').read_bytes(), b'changed'); self.assertFalse(self.journal.exists())

    def test_first_selection_failure_restores_original_absence(self):
        shutil.rmtree(self.next)
        for name in FILES: (self.config / name).unlink(missing_ok=True)
        result = self.run_shell(self.begin() + ' || exit $?\n' + self.changed_selection() +
                                '\nluoshu_next_transaction_rollback "$m"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.next.exists()); self.assertFalse(self.journal.exists())
        for name in FILES: self.assertFalse((self.config / name).exists())

    def test_external_symlink_and_parent_leaf_inputs_are_refused(self):
        outside = Path(self.temporary.name) / 'outside'; outside.mkdir()
        (self.work / 'linked').symlink_to(outside, target_is_directory=True)
        for path in (self.work / 'linked', self.work / '..', outside):
            result = self.run_shell('luoshu_next_transaction_begin "$m" ' + "'" + str(path) + "'" + ' "$newstate"')
            self.assertEqual(result.returncode, 1, str(path)); self.assert_prior()
        self.assertFalse(self.journal.exists())

    def test_corrupt_journal_is_preserved_without_mutating_pending_selection(self):
        self.journal.mkdir(); (self.journal / 'journal.conf').write_text('schema=invalid\nstate=publishing\n')
        result = self.run_shell('luoshu_next_transaction_recover "$m"')
        self.assertEqual(result.returncode, 1); self.assert_prior(); self.assertTrue(self.journal.exists())

    def test_kill_at_each_publish_boundary_recovers_previous_B(self):
        injections = [
            'mv() { [ "$1" != "$m/.luoshu-payload-next" ] || kill -KILL $$; command mv "$@"; }',
            'mv() { [ "$1" != "$stage" ] || kill -KILL $$; command mv "$@"; }',
            'cp() { [ "$2" != "$newstate" ] || kill -KILL $$; command cp "$@"; }',
        ]
        for injection in injections:
            with self.subTest(injection=injection):
                result = self.run_shell(injection + '\n' + self.begin())
                self.assertEqual(result.returncode, -signal.SIGKILL, result.stderr)
                recovery = self.run_shell('luoshu_next_transaction_recover "$m"')
                self.assertEqual(recovery.returncode, 0, recovery.stderr); self.assert_prior()
                self.assertFalse(self.journal.exists())
                if not self.stage.exists():
                    self.stage.mkdir(); (self.stage / 'C.ttf').write_bytes(b'new pending C\0font')

    def test_killed_snapshot_copy_never_changes_original_selection(self):
        result = self.run_shell('cp() { case "$3" in */files/*) kill -KILL $$ ;; esac; command cp "$@"; }\n' + self.begin())
        self.assertEqual(result.returncode, -signal.SIGKILL)
        recovery = self.run_shell('luoshu_next_transaction_recover "$m"')
        self.assertEqual(recovery.returncode, 0, recovery.stderr); self.assert_prior(); self.assertFalse(self.journal.exists())

    def mark_previous_boot(self):
        journal = self.journal / 'journal.conf'
        journal.write_text(journal.read_text().replace('boot=' + BOOT, 'boot=previous-boot'))

    def test_hard_reboot_adopting_new_C_does_not_restore_old_B_metadata(self):
        process = self.hold_after_begin(); process.kill(); process.communicate(timeout=3)
        self.mark_previous_boot()
        shutil.rmtree(self.live); self.next.rename(self.live)
        (self.config / 'active_font.conf').write_text('C\n')
        (self.config / 'font-payload-activated.conf').write_text('font=C\nrequestId=test-C\nbootId=' + BOOT + '\n')
        (self.config / 'font-payload-next.conf').unlink()
        result = self.run_shell('luoshu_next_transaction_recover "$m"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.next.exists()); self.assertFalse(self.journal.exists())
        self.assertEqual((self.config / 'active_font.conf').read_text(), 'C\n')
        self.assertFalse((self.config / 'font-payload-next.conf').exists())
        self.assertEqual((self.live / 'C.ttf').read_bytes(), b'new pending C\0font')

    def test_hard_reboot_adopting_default_uses_payload_identity_marker(self):
        self.state.write_text('state=prepared\nfont=default\nrequestId=test-default\n')
        process = self.hold_after_begin(); process.kill(); process.communicate(timeout=3)
        self.mark_previous_boot(); shutil.rmtree(self.live); self.next.rename(self.live)
        (self.config / 'active_font.conf').write_text('default\n')
        (self.config / 'font_runtime_legacy_v14_4.conf').unlink()
        (self.config / 'font-payload-next.conf').unlink()
        result = self.run_shell('luoshu_next_transaction_recover "$m"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.next.exists()); self.assertFalse(self.journal.exists())
        self.assertEqual((self.config / 'active_font.conf').read_text(), 'default\n')
        self.assertFalse((self.config / 'font-payload-next.conf').exists())

    def test_boot_adopting_old_B_before_rename_is_preserved(self):
        prior = b'state=prepared\nfont=B\nrequestId=test-B\n'
        (self.config / 'font-payload-next.conf').write_bytes(prior)
        result = self.run_shell('mv() { [ "$1" != "$m/.luoshu-payload-next" ] || kill -KILL $$; command mv "$@"; }\n' + self.begin())
        self.assertEqual(result.returncode, -signal.SIGKILL); self.mark_previous_boot()
        shutil.rmtree(self.live); self.next.rename(self.live)
        (self.config / 'active_font.conf').write_text('B\n')
        (self.config / 'font-payload-activated.conf').write_text('font=B\nrequestId=test-B\nbootId=' + BOOT + '\n')
        (self.config / 'font-payload-next.conf').unlink()
        result = self.run_shell('luoshu_next_transaction_recover "$m"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.next.exists()); self.assertFalse(self.journal.exists())
        self.assertEqual((self.config / 'active_font.conf').read_text(), 'B\n')
        self.assertFalse((self.config / 'font-payload-next.conf').exists())

    def test_identity_marker_replacement_preserves_hardlinked_live_inode(self):
        marker = self.live / '.luoshu-next-transaction.conf'
        original = b'schema=luoshu-next-payload-v1\nfont=A\nrequestId=test-A\n'
        marker.write_bytes(original); os.link(marker, self.stage / marker.name)
        result = self.run_shell(self.begin() + ' || exit $?\nluoshu_next_transaction_commit "$m"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(marker.read_bytes(), original)
        self.assertIn(b'requestId=test-C', (self.next / marker.name).read_bytes())

unittest.main()
PY
