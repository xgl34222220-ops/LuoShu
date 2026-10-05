#!/usr/bin/env python3
"""Live wrapper integration with isolated mount APIs; no real mounts or device I/O."""
import importlib.util
import json
import os
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
                     'font_switch_lock.sh', 'font_live_payload.py', 'font_live_switch.sh']:
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

    def test_previous_boot_pruning_space_guard_and_no_symlink_escape(self):
        source = self.module / '.luoshu-payload'
        cache = self.module / 'cache/copy-test'
        first = copy_module.prepare(source, cache, 'boot-old', self.module / 'tmp-copy-1')
        second = copy_module.prepare(source, cache, 'boot-new', self.module / 'tmp-copy-2')
        self.assertEqual(first, second)
        self.assertEqual(json.loads((second / '.generation.json').read_text())['bootId'], 'boot-new')
        source_file = source / 'system/fonts/Roboto-Regular.ttf'
        source_file.write_text('new-content')
        with patch.object(copy_module.shutil, 'disk_usage', return_value=shutil._ntuple_diskusage(1, 1, 0)):
            with self.assertRaisesRegex(ValueError, 'free space'):
                copy_module.prepare(source, cache, 'boot-new', self.module / 'tmp-copy-3')
        source_file.unlink(); source_file.symlink_to('/etc/hosts')
        with self.assertRaisesRegex(ValueError, 'non-regular'):
            copy_module.prepare(source, cache, 'boot-new', self.module / 'tmp-copy-4')


if __name__ == '__main__':
    unittest.main()
