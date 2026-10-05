#!/usr/bin/env python3
"""Live wrapper integration with isolated mount APIs; no real mounts or device I/O."""
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('live_copy', ROOT / 'common/font_live_payload.py')
copy_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(copy_module)

# The unchanged atomic-mount tests cover kernel mount policy. This fixture tests
# the new source lifetime, journal, restoration and truthful result boundary.
MOUNT_FIXTURE = r'''
_luoshu_self_state_root() { printf '%s/mock-mount-state\n' "$MODDIR"; }
luoshu_private_self_mount_ensure() {
    _fixture_font=$(head -n1 "$MODDIR/config/active_font.conf")
    mkdir -p "$MODDIR/visible" "$MODDIR/mock-mount-state"
    printf '%s\n' "$_fixture_font" >> "$MODDIR/calls"
    if [ "$_fixture_font" = default ]; then
        printf 'stock' > "$MODDIR/visible/font"
        printf 'state=idle\n' > "$MODDIR/config/self-mount.conf"
        : > "$MODDIR/mock-mount-state/mounts.list"
        return 0
    fi
    _fixture_source=$(_lfrp_payload_root)
    _fixture_content=$(cat "$_fixture_source/system/fonts/Roboto-Regular.ttf")
    printf '%s' "$_fixture_content" > "$MODDIR/visible/font"
    if [ "${FIXTURE_BAD_FONT:-}" = "$_fixture_font" ]; then
        printf partial > "$MODDIR/visible/font"
        printf 'state=failed\n' > "$MODDIR/config/self-mount.conf"
        return 1
    fi
    if [ -f "$MODDIR/kill-on-restore" ] && [ "$_fixture_font" = A ]; then
        rm -f "$MODDIR/kill-on-restore"
        kill -KILL $$
    fi
    if [ "${FIXTURE_SIGNAL_FONT:-}" = "$_fixture_font" ]; then
        printf partial > "$MODDIR/visible/font"
        kill -TERM $$
    fi
    if [ "${FIXTURE_KILL_FONT:-}" = "$_fixture_font" ]; then
        printf partial > "$MODDIR/visible/font"
        kill -KILL $$
    fi
    printf 'state=mounted\n' > "$MODDIR/config/self-mount.conf"
    printf '%s\n' "$_fixture_source" > "$MODDIR/config/self-mount-required.conf"
    printf '%s\n' "$MODDIR/visible/font" > "$MODDIR/mock-mount-state/mounts.list"
    return 0
}
_luoshu_atomic_verify_manifest() {
    [ -f "$1" ] || return 1
    _fixture_expected=$(head -n1 "$1")
    cmp -s "$_fixture_expected/system/fonts/Roboto-Regular.ttf" "$MODDIR/visible/font"
}
'''


class LiveSwitchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.module = Path(self.temp.name) / 'module'
        common = self.module / 'common'
        common.mkdir(parents=True)
        (self.module / 'module.prop').write_text('id=LuoShu\n')
        for name in ['runtime_paths.sh', 'runtime_paths_lock.py', 'task_scope.sh', 'task_scope.py',
                     'font_switch_lock.sh', 'font_next_transaction.sh', 'font_live_payload.py', 'font_live_switch.sh']:
            shutil.copy2(ROOT / 'common' / name, common / name)
        (common / 'mount_compat.sh').write_text(MOUNT_FIXTURE)
        # Namespace entry is mocked too; the wrapper's production refusal on an
        # unreadable PID 1 namespace must not cause this fixture to touch it.
        bin_dir = self.module / 'fixture-bin'
        bin_dir.mkdir()
        real_readlink = shutil.which('readlink')
        readlink = bin_dir / 'readlink'
        readlink.write_text('#!/bin/sh\ncase "$1" in /proc/self/ns/mnt|/proc/1/ns/mnt) printf "mnt:[fixture]\\n" ;; *) exec ' + str(real_readlink) + ' "$@" ;; esac\n')
        readlink.chmod(0o755)
        real_mv = shutil.which('mv')
        mv = bin_dir / 'mv'
        mv.write_text('#!/bin/sh\nif { [ "${3:-}" = "$MODDIR/config/font-live.conf" ] || [ "${3:-}" = "$MODDIR/.luoshu-state/config/font-live.conf" ]; } && [ -f "$MODDIR/arm-state-mv" ]; then\n  _action=$(cat "$MODDIR/arm-state-mv"); rm -f "$MODDIR/arm-state-mv"\n  [ "$_action" != fail ] || exit 1\n  ' + str(real_mv) + ' "$@" || exit $?\n  kill -"$_action" "$PPID"; exit 0\nfi\nexec ' + str(real_mv) + ' "$@"\n')
        mv.chmod(0o755)
        self.env = dict(os.environ, PATH=str(bin_dir) + ':' + os.environ['PATH'], MODDIR=str(self.module), LUOSHU_TASK_SCOPE_PYTHON=sys.executable,
                        LUOSHU_RUNTIME_PATHS_PYTHON=sys.executable, LUOSHU_LIVE_PAYLOAD_PYTHON=sys.executable)
        subprocess.run(['sh', '-c', '. "$MODDIR/common/runtime_paths.sh"; luoshu_runtime_paths_init "$MODDIR"'],
                       env=self.env, check=True, capture_output=True)
        self.config = self.module / 'config'
        (self.config / 'active_font.conf').write_text('default\n')
        fonts = self.module / '.luoshu-payload/system/fonts'
        fonts.mkdir(parents=True)
        (fonts / 'Roboto-Regular.ttf').write_text('boot-stock')
        self.boot_inode = (fonts / 'Roboto-Regular.ttf').stat().st_ino
        self.boot_bytes = (fonts / 'Roboto-Regular.ttf').read_bytes()

    def tearDown(self):
        self.temp.cleanup()

    def select(self, font, request=None):
        next_root = self.module / '.luoshu-payload-next'
        shutil.rmtree(next_root, ignore_errors=True)
        fonts = next_root / 'system/fonts'
        fonts.mkdir(parents=True)
        if font != 'default':
            (fonts / 'Roboto-Regular.ttf').write_text(font + '-font-bytes')
            os.link(fonts / 'Roboto-Regular.ttf', fonts / 'MiSansVF.ttf')
        (self.config / 'font-payload-next.conf').write_text(
            f'state=prepared\nfont={font}\nrequestId={request or font}\npreviousFont=default\n')
        (self.config / 'active_font.conf').write_text(font + '\n')
        (self.config / 'text_reboot_required.conf').write_text('font=' + font + '\n')

    def run_live(self, mode=None, **env):
        command = ['sh', str(self.module / 'common/font_live_switch.sh')]
        if mode:
            command.append(mode)
        result = subprocess.run(command, env=dict(self.env, **env), capture_output=True, text=True, timeout=20)
        data = [json.loads(row) for row in result.stdout.splitlines() if row.startswith('{')]
        return result, data[-1] if data else {}

    def state(self):
        return dict(row.split('=', 1) for row in (self.config / 'font-live.conf').read_text().splitlines())

    def assert_boot_unchanged(self):
        boot = self.module / '.luoshu-payload/system/fonts/Roboto-Regular.ttf'
        self.assertEqual(boot.stat().st_ino, self.boot_inode)
        self.assertEqual(boot.read_bytes(), self.boot_bytes)

    def test_repeat_a_b_a_and_source_inode_lifetime(self):
        self.select('A', 'A-first')
        result, data = self.run_live()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(data['liveApplied'])
        source_a = Path(self.state()['source'])
        self.assertNotEqual((source_a / 'system/fonts/Roboto-Regular.ttf').stat().st_ino,
                            (self.module / '.luoshu-payload-next/system/fonts/Roboto-Regular.ttf').stat().st_ino)
        self.assertEqual((source_a / 'system/fonts/Roboto-Regular.ttf').stat().st_ino,
                         (source_a / 'system/fonts/MiSansVF.ttf').stat().st_ino)
        self.select('B')
        self.assertTrue(self.run_live()[1]['liveApplied'])
        source_b = Path(self.state()['source'])
        self.select('A', 'A-last')
        self.assertTrue(self.run_live()[1]['liveApplied'])
        self.assertEqual(self.state()['source'], str(source_a))
        self.assertTrue(source_b.exists())
        self.assertEqual(self.state()['requestId'], 'A-last')
        self.assertEqual((self.module / 'visible/font').read_text(), 'A-font-bytes')
        self.assert_boot_unchanged()
        self.assertFalse((self.config / 'font-live-transaction.conf').exists())
        self.assertFalse(any((self.module / '.luoshu-state/tasks').glob('*.pid')))

    def test_failed_live_preserves_reboot_choice_and_restores_previous(self):
        self.select('A'); self.assertTrue(self.run_live()[1]['liveApplied'])
        self.select('C')
        result, data = self.run_live(FIXTURE_BAD_FONT='C')
        self.assertFalse(data['liveApplied'])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.state()['font'], 'A')
        self.assertEqual((self.module / 'visible/font').read_text(), 'A-font-bytes')
        self.assertEqual((self.config / 'active_font.conf').read_text(), 'C\n')
        self.assertIn('font=C', (self.config / 'font-payload-next.conf').read_text())
        self.assert_boot_unchanged()

    def test_term_rolls_back_and_finishes_owned_process_cleanup(self):
        self.select('A'); self.run_live()
        self.select('C')
        result, _ = self.run_live(FIXTURE_SIGNAL_FONT='C')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.module / 'visible/font').read_text(), 'A-font-bytes')
        self.assertFalse((self.config / 'font-live-transaction.conf').exists())
        self.assertFalse(any((self.module / '.luoshu-state/tasks').glob('*.pid')))

    def test_kill_retains_journal_then_explicit_recover_restores(self):
        self.select('A'); self.run_live()
        self.select('C')
        result, _ = self.run_live(FIXTURE_KILL_FONT='C')
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((self.config / 'font-live-transaction.conf').exists())
        (self.module / 'kill-on-restore').touch()
        self.assertNotEqual(self.run_live('recover')[0].returncode, 0)
        self.assertEqual((self.config / 'active_font.conf').read_text(), 'A\n')
        result, _ = self.run_live('recover')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.config / 'active_font.conf').read_text(), 'C\n')
        self.assertEqual((self.module / 'visible/font').read_text(), 'A-font-bytes')
        self.assertFalse((self.config / 'font-live-transaction.conf').exists())
        self.assertTrue(self.run_live()[1]['liveApplied'])
        self.assert_boot_unchanged()

    def test_default_live_restore_and_next_boot_choice(self):
        self.select('A'); self.run_live()
        self.select('default')
        result, data = self.run_live()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(data['liveApplied'])
        self.assertEqual((self.module / 'visible/font').read_text(), 'stock')
        self.assertEqual(self.state()['font'], 'default')
        self.assertIn('font=default', (self.config / 'font-payload-next.conf').read_text())

    def test_safe_switch_transaction_repeat_with_pending_reboot(self):
        legacy = self.module / 'common/legacy_v14_4'
        legacy.mkdir()
        for name in ['font_switch_safe.sh', 'payload_clone.sh']:
            shutil.copy2(ROOT / 'common/legacy_v14_4' / name, legacy / name)
        shutil.copy2(ROOT / 'common/font_next_transaction.sh', self.module / 'common/font_next_transaction.sh')
        shutil.copy2(ROOT / 'common/background_task.sh', self.module / 'common/background_task.sh')
        (legacy / 'util_functions.sh').write_text('detect_font_family() { printf "%s\\n" "${1%.*}"; }\n')
        (legacy / 'font_check.sh').write_text('font_validate() { return 0; }\n')
        (legacy / 'rom_adapters.sh').write_text('apply_font_by_rom() { mkdir -p "$2/.luoshu-font-store"; cp "$1" "$2/Roboto-Regular.ttf"; cp "$1" "$2/.luoshu-font-store/regular.font"; }\n')
        public = self.module / 'public'
        fonts = public / 'fonts'
        fonts.mkdir(parents=True)
        for font in ['A', 'B']:
            (fonts / (font + '.ttf')).write_text(font + '-font-bytes')
        for index, font in enumerate(['A', 'B', 'A']):
            result = subprocess.run(['sh', str(legacy / 'font_switch_safe.sh'), 'action', 'switch', font],
                env=dict(self.env, LUOSHU_PUBLIC_DIR=str(public), LUOSHU_SWITCH_REQUEST_ID='switch-' + str(index)),
                capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = json.loads(result.stdout.splitlines()[-1])['data']
            self.assertTrue(data['liveApplied'])
            self.assertTrue(data['rebootRequired'])
            self.assertEqual((self.config / 'active_font.conf').read_text(), font + '\n')
            self.assertIn('requestId=switch-' + str(index), (self.config / 'font-payload-next.conf').read_text())
            self.assertEqual((self.module / 'visible/font').read_text(), font + '-font-bytes')
        self.assertFalse((self.module / '.luoshu-state/backup/next-transaction').exists())
        self.assert_boot_unchanged()
        manifest = self.module / '.luoshu-state/tmp/test-mix-generation.conf'
        manifest.write_text('compositeHash=fixture-mix-digest\n')
        result = subprocess.run(['sh', str(legacy / 'font_switch_safe.sh'), 'action', 'switch', 'A'],
            env=dict(self.env, LUOSHU_PUBLIC_DIR=str(public), LUOSHU_SWITCH_ACTIVE_LABEL='mix',
                     LUOSHU_MIX_REQUEST_ID='mix-fixture', LUOSHU_MIX_EXPECTED_CJK='中文基底',
                     LUOSHU_MIX_EXPECTED_LATIN='LatinBase', LUOSHU_MIX_EXPECTED_DIGIT='DigitBase',
                     LUOSHU_MIX_MANIFEST=str(manifest)), capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        state = (self.config / 'font-payload-next.conf').read_text()
        for expected in ['font=mix', 'requestId=mix-fixture', 'cjk=中文基底', 'latin=LatinBase',
                         'digit=DigitBase', 'compositeHash=fixture-mix-digest']:
            self.assertIn(expected, state)
        receipt = (self.config / 'mix-commit.conf').read_text()
        self.assertIn('requestId=mix-fixture\n', receipt)
        self.assertIn('font=mix\n', receipt)

    def test_state_publication_failure_and_term_restore_previous_record(self):
        for action in ['fail', 'TERM']:
            with self.subTest(action=action):
                self.select('A', 'record-A'); self.assertTrue(self.run_live()[1]['liveApplied'])
                old_record = (self.config / 'font-live.conf').read_bytes()
                self.select('C', 'record-C')
                (self.module / 'arm-state-mv').write_text(action)
                result, _ = self.run_live()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((self.config / 'font-live.conf').read_bytes(), old_record)
                self.assertEqual((self.module / 'visible/font').read_text(), 'A-font-bytes')
                self.assertEqual((self.config / 'active_font.conf').read_text(), 'C\n')
                self.assertFalse((self.config / 'font-live-transaction.conf').exists())

    def test_kill_after_default_state_publication_keeps_completed_default(self):
        self.select('A'); self.run_live()
        self.select('default', 'default-after-A')
        (self.module / 'arm-state-mv').write_text('KILL')
        self.assertNotEqual(self.run_live()[0].returncode, 0)
        self.assertTrue((self.config / 'font-live-transaction.conf').exists())
        self.assertEqual(self.run_live('recover')[0].returncode, 0)
        self.assertEqual(self.state()['font'], 'default')
        self.assertEqual((self.module / 'visible/font').read_text(), 'stock')
        self.assertFalse((self.config / 'font-live-transaction.conf').exists())

    def shell_function(self, source, name):
        match = re.search(r'^' + re.escape(name) + r'\(\) \{.*?^\}', source.read_text(), re.M | re.S)
        self.assertIsNotNone(match, name)
        return match.group(0)

    def test_pending_default_then_mix_failure_restores_boot_baseline(self):
        # A default selection may be pending while this boot still uses A. The
        # next composite must carry A through generation and live rollback.
        self.select('default', 'default-pending')
        (self.config / 'font-payload-next.conf').write_text(
            'state=prepared\nfont=default\nrequestId=default-pending\npreviousFont=A\npreviousLegacy=true\n')
        router = ROOT / 'common/legacy_v14_4/mix_router.sh'
        functions = '\n'.join(self.shell_function(router, name) for name in [
            'read_value', 'mix_clone_source', 'clone_mix_tree', 'clear_mix_text_payload', 'prepare_mix_stage'])
        script = r'''
REALMOD="$MODDIR"
LIVE_PAYLOAD="$MODDIR/.luoshu-payload"
MIX_STAGE="$MODDIR/.luoshu-state/tmp/mix-stage"
NEXT_STATE="$MODDIR/config/font-payload-next.conf"
MIX_STAGE_STATE="$MODDIR/config/mix-stage-next.conf"
ACTIVE_CONF="$MODDIR/config/active_font.conf"
LEGACY_MODE="$MODDIR/config/font_runtime_legacy_v14_4.conf"
LOG_FILE="$MODDIR/logs/fontswitch.log"
. "$FIXTURE_CLONE"
''' + functions + '\nprepare_mix_stage Cjk Latin Digit wght=400 wght=400 wght=400\n'
        result = subprocess.run(['sh', '-c', script], env=dict(self.env,
            FIXTURE_CLONE=str(ROOT / 'common/legacy_v14_4/payload_clone.sh')),
            capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        stage_state = (self.config / 'mix-stage-next.conf').read_text()
        self.assertIn('previousFont=A\n', stage_state)
        self.assertIn('previousLegacy=true\n', stage_state)
        self.select('mix', 'mix-after-default')
        state = (self.config / 'font-payload-next.conf').read_text().replace(
            'previousFont=default\n', 'previousFont=A\npreviousLegacy=true\n')
        (self.config / 'font-payload-next.conf').write_text(state)
        result, data = self.run_live(FIXTURE_BAD_FONT='mix')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(data['liveApplied'])
        self.assertEqual(data['reason'], 'live-mount-failed-previous-restored')
        self.assertEqual((self.module / 'visible/font').read_text(), 'boot-stock')
        self.assertEqual((self.config / 'active_font.conf').read_text(), 'mix\n')
        self.assertFalse((self.config / 'font-live.conf').exists())
        self.assert_boot_unchanged()

    def test_explicit_cleanup_recovers_next_before_live_under_selection_lock(self):
        self.select('A', 'committed-A'); self.assertTrue(self.run_live()[1]['liveApplied'])
        old_next = (self.config / 'font-payload-next.conf').read_bytes()
        stage = self.module / '.luoshu-state/tmp/interrupted-selection'
        fonts = stage / 'system/fonts'; fonts.mkdir(parents=True)
        (fonts / 'Roboto-Regular.ttf').write_text('interrupted-B')
        state = self.module / '.luoshu-state/tmp/interrupted-next.conf'
        state.write_text('font=B\nrequestId=interrupted-B\npreviousFont=A\n')
        script = r'''
. "$MODDIR/common/font_next_transaction.sh"
luoshu_next_transaction_begin "$MODDIR" "$FIXTURE_STAGE" "$FIXTURE_STATE" || exit 1
printf 'B\n' > "$MODDIR/config/active_font.conf"
# Exit without commit simulates a dead publisher, not a live request to cancel.
'''
        result = subprocess.run(['sh', '-c', script], env=dict(self.env,
            FIXTURE_STAGE=str(stage), FIXTURE_STATE=str(state)), capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        journal = self.module / '.luoshu-state/backup/next-transaction'
        self.assertTrue(journal.exists())
        result, data = self.run_live('recover')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(data['reason'], 'live-cleaned')
        self.assertFalse(journal.exists())
        self.assertFalse((self.module / '.font_switch.lock').exists())
        self.assertEqual((self.config / 'font-payload-next.conf').read_bytes(), old_next)
        self.assertEqual((self.config / 'active_font.conf').read_text(), 'A\n')
        self.assertEqual((self.module / 'visible/font').read_text(), 'A-font-bytes')

    def test_task_writers_preserve_exact_committed_request_only(self):
        task = self.config / 'writer-fixture.conf'
        receipt = self.config / 'mix-commit.conf'
        journal_dir = self.module / '.luoshu-state/backup/next-transaction'
        for name in ['font_mix_engine.sh', 'v142_weighted_mix.sh', 'v143_auto_multiweight_mix.sh']:
            with self.subTest(writer=name):
                task.unlink(missing_ok=True)
                function = self.shell_function(ROOT / 'common/legacy_v14_4' / name, 'write_task')
                def write(request, task_id):
                    result = subprocess.run(['sh', '-c', function +
                        '\nwrite_task "$FIXTURE_TASK" success done Cjk Latin Digit 400 400 400 root child 1 2 100 1 2 100\n'],
                        env=dict(self.env, TASK_FILE=str(task), LUOSHU_MIX_REQUEST_ID=request,
                                 LUOSHU_REAL_MODDIR=str(self.module), FIXTURE_TASK=task_id),
                        capture_output=True, text=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    return dict(row.split('=', 1) for row in task.read_text().splitlines())
                receipt.write_text('font=mix\nrequestId=request-A\n')
                self.assertEqual(write('request-A', 'task-A')['committedRequestId'], 'request-A')
                receipt.write_text('font=mix\nrequestId=request-C\n')
                self.assertEqual(write('request-A', 'task-A')['committedRequestId'], 'request-A')
                self.assertEqual(write('request-B', 'task-B')['committedRequestId'], '')
                journal_dir.mkdir()
                self.assertEqual(write('request-C', 'task-C')['committedRequestId'], '')
                journal_dir.rmdir()
                self.assertEqual(write('request-C', 'task-C')['committedRequestId'], 'request-C')

    def test_previous_boot_pruning_space_guard_and_no_symlink_escape(self):
        source = self.module / '.luoshu-payload'
        cache = self.module / 'cache/copy-test'
        first = copy_module.prepare(source, cache, 'boot-old', self.module / 'tmp-copy-1')
        second = copy_module.prepare(source, cache, 'boot-new', self.module / 'tmp-copy-2')
        self.assertEqual(first, second)
        self.assertEqual(json.loads((second / '.generation.json').read_text())['bootId'], 'boot-new')
        source_file = source / 'system/fonts/Roboto-Regular.ttf'
        (source / '.luoshu-next-transaction.conf').write_text('requestId=first')
        same = copy_module.prepare(source, cache, 'boot-new', self.module / 'tmp-marker-1')
        (source / '.luoshu-next-transaction.conf').write_text('requestId=second')
        self.assertEqual(same, copy_module.prepare(source, cache, 'boot-new', self.module / 'tmp-marker-2'))
        self.assertFalse((same / '.luoshu-next-transaction.conf').exists())
        (same / 'system/fonts/Roboto-Regular.ttf').write_text('corrupt-cache')
        with self.assertRaisesRegex(ValueError, 'content mismatch'):
            copy_module.prepare(source, cache, 'boot-new', self.module / 'tmp-corrupt')
        source_file.write_text('new-content')
        with patch.object(copy_module.shutil, 'disk_usage', return_value=shutil._ntuple_diskusage(1, 1, 0)):
            with self.assertRaisesRegex(ValueError, 'free space'):
                copy_module.prepare(source, cache, 'boot-new', self.module / 'tmp-copy-3')
        source_file.unlink(); source_file.symlink_to('/etc/hosts')
        with self.assertRaisesRegex(ValueError, 'non-regular'):
            copy_module.prepare(source, cache, 'boot-new', self.module / 'tmp-copy-4')


if __name__ == '__main__':
    unittest.main()
