#!/usr/bin/env python3
"""Live wrapper integration with isolated mount APIs; no real mounts or device I/O."""
import importlib.util
import builtins
from contextlib import ExitStack
import hashlib
import io
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('live_copy', ROOT / 'common/font_live_payload.py')
copy_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(copy_module)


class PayloadIOMeter:
    """Count returned file API bytes, including copyfile's Linux sendfile path.

    These are logical bytes through real reads/copies, not physical disk traffic.
    Open lifetimes include hashing/writes and overlap, so they are not additive.
    """
    def __init__(self, source, cache, temporary):
        self.roots = {'source': source, 'cache': cache, 'temporary': temporary}
        self.data = {role: {'opens': 0, 'readCalls': 0, 'readBytes': 0,
                            'writeBytes': 0, 'openSeconds': 0.0}
                     for role in self.roots}
        self.data.update(copyCalls=0, copySeconds=0.0, linkCalls=0,
                         cleanupCalls=0, cleanupSeconds=0.0)

    def role(self, name):
        if isinstance(name, int):
            name = os.readlink('/proc/self/fd/' + str(name))
        path = Path(name)
        for role, root in self.roots.items():
            if path.is_relative_to(root):
                return role

    def __enter__(self):
        meter = self
        original_path_open, original_open = Path.open, builtins.open
        original_copy, original_link = shutil.copyfile, os.link
        original_cleanup = shutil.rmtree

        class Stream:
            def __init__(self, stream, role):
                self.stream, self.role, self.started = stream, role, time.perf_counter()
                self.closed = False
                meter.data[role]['opens'] += 1

            def __getattr__(self, name):
                return getattr(self.stream, name)

            def __enter__(self):
                self.stream.__enter__()
                return self

            def __exit__(self, *args):
                try:
                    return self.stream.__exit__(*args)
                finally:
                    if not self.closed:
                        meter.data[self.role]['openSeconds'] += time.perf_counter() - self.started
                        self.closed = True

            def read(self, *args):
                value = self.stream.read(*args)
                meter.data[self.role]['readCalls'] += 1
                meter.data[self.role]['readBytes'] += len(value)
                return value

            def readinto(self, *args):
                size = self.stream.readinto(*args)
                meter.data[self.role]['readCalls'] += 1
                meter.data[self.role]['readBytes'] += size or 0
                return size

            def write(self, value):
                size = self.stream.write(value)
                meter.data[self.role]['writeBytes'] += size
                return size

        def opened(original, name, *args, **kwargs):
            stream = original(name, *args, **kwargs)
            mode = kwargs.get('mode', args[0] if args else 'r')
            role = self.role(name)
            return Stream(stream, role) if role and 'b' in mode else stream

        def copied(*args, **kwargs):
            self.data['copyCalls'] += 1
            started = time.perf_counter()
            try:
                return original_copy(*args, **kwargs)
            finally:
                self.data['copySeconds'] += time.perf_counter() - started

        def linked(*args, **kwargs):
            self.data['linkCalls'] += 1
            return original_link(*args, **kwargs)

        def cleaned(*args, **kwargs):
            self.data['cleanupCalls'] += 1
            started = time.perf_counter()
            try:
                return original_cleanup(*args, **kwargs)
            finally:
                self.data['cleanupSeconds'] += time.perf_counter() - started

        self.stack = ExitStack()
        self.stack.enter_context(patch.object(Path, 'open', lambda name, *a, **k: opened(original_path_open, name, *a, **k)))
        self.stack.enter_context(patch.object(builtins, 'open', lambda name, *a, **k: opened(original_open, name, *a, **k)))
        self.stack.enter_context(patch.object(shutil, 'copyfile', copied))
        self.stack.enter_context(patch.object(os, 'link', linked))
        self.stack.enter_context(patch.object(shutil, 'rmtree', cleaned))
        if hasattr(os, 'sendfile'):
            original_sendfile = os.sendfile
            def sent(outfd, infd, *args, **kwargs):
                size = original_sendfile(outfd, infd, *args, **kwargs)
                source_role, destination_role = self.role(infd), self.role(outfd)
                if source_role:
                    self.data[source_role]['readCalls'] += 1
                    self.data[source_role]['readBytes'] += size
                if destination_role:
                    self.data[destination_role]['writeBytes'] += size
                return size
            self.stack.enter_context(patch.object(os, 'sendfile', sent))
        self.started = time.perf_counter()
        return self.data

    def __exit__(self, *args):
        self.data['prepareSeconds'] = time.perf_counter() - self.started
        return self.stack.__exit__(*args)

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

    def copy_fixture(self):
        source = self.module / 'copy-source'
        fonts = source / 'system/fonts'
        fonts.mkdir(parents=True)
        font = fonts / 'Roboto-Regular.ttf'
        font.write_bytes(bytes(range(256)) * (16 * 1024 * 1024 // 256))
        os.link(font, fonts / 'MiSansVF.ttf')
        xml = source / 'system/etc/fonts.xml'
        xml.parent.mkdir()
        xml.write_bytes(b'<font/>' * 1024)
        return source, self.module / 'cache/io-fixture', font.stat().st_size + xml.stat().st_size

    def warm_copy_fixture(self):
        def sfnt(top, fill):
            builder = FontBuilder(1000, isTTF=True)
            builder.setupGlyphOrder(['.notdef', 'A'])
            builder.setupCharacterMap({65: 'A'})
            glyphs = {}
            for name in ['.notdef', 'A']:
                pen = TTGlyphPen(None)
                pen.moveTo((0, 0)); pen.lineTo((500, 0))
                pen.lineTo((500, top)); pen.lineTo((0, top)); pen.closePath()
                glyphs[name] = pen.glyph()
            builder.setupGlyf(glyphs)
            builder.setupHorizontalMetrics({name: (600, 0) for name in glyphs})
            builder.setupHorizontalHeader(ascent=900, descent=-200)
            builder.setupOS2(sTypoAscender=900, sTypoDescender=-200,
                             usWinAscent=900, usWinDescent=200)
            builder.setupNameTable({'familyName': 'WarmIntegrityFixture', 'styleName': 'Regular'})
            builder.setupPost(); builder.setupMaxp()
            builder.font['head'].created = builder.font['head'].modified = 3_400_000_000
            padding = newTable('TEST'); padding.data = bytes([fill]) * (2 * 1024 * 1024)
            builder.font['TEST'] = padding
            output = io.BytesIO(); builder.save(output)
            data = output.getvalue()
            with TTFont(io.BytesIO(data), checkChecksums=2) as parsed:
                self.assertEqual(parsed.getBestCmap(), {65: 'A'})
                self.assertEqual(parsed['glyf']['A'].yMax, top)
            return data

        original, selected = sfnt(700, 65), sfnt(800, 66)
        self.assertEqual(len(original), len(selected))
        source = self.module / 'warm-source'; fonts = source / 'system/fonts'
        fonts.mkdir(parents=True)
        font = fonts / 'MiSansVF.ttf'; font.write_bytes(original)
        os.link(font, fonts / 'Roboto-Regular.ttf')
        cache = self.module / 'cache/warm-integrity'
        previous = copy_module.prepare(source, cache, 'io-boot', self.module / 'warm-seed')
        font.write_bytes(selected)
        return source, cache, font, previous, original, selected

    def record_warm_integrity(self, name, source, previous, generation=None, **details):
        artifact = os.environ.get('LUOSHU_WARM_INTEGRITY_ARTIFACT_DIR')
        if artifact:
            output = Path(artifact); output.mkdir(parents=True, exist_ok=True)
            relative = 'system/fonts/MiSansVF.ttf'
            def sha(path):
                return hashlib.sha256(path.read_bytes()).hexdigest()
            (output / (name + '.json')).write_text(json.dumps({
                'scope': 'fixed generated real SFNT; host helper integrity and logical I/O only',
                'sourceSha256': sha(source / relative),
                'previousOutputSha256': sha(previous / relative),
                'outputSha256': sha(generation / relative) if generation else None,
                'published': generation is not None, **details}, indent=2) + '\n')

    def test_warm_generation_miss_rejects_parent_swap_during_second_open(self):
        source, cache, font, previous, original, selected = self.warm_copy_fixture()
        temporary = self.module / 'warm-parent-copy'
        parent, parked, donor = font.parent, self.module / 'parked-fonts', self.module / 'donor-fonts'
        donor.mkdir(); (donor / font.name).write_bytes(original)
        os.link(donor / font.name, donor / 'Roboto-Regular.ttf')
        before = copy_module._source_identity(font.lstat())
        original_path_open, original_open = Path.open, builtins.open
        opens, result = [], None

        def opened(real_open, name, *args, **kwargs):
            mode = kwargs.get('mode', args[0] if args else 'r')
            if not isinstance(name, int) and Path(name) == font and mode == 'rb':
                opens.append(mode)
                if len(opens) == 2:
                    parent.rename(parked); donor.rename(parent)
                    try:
                        return real_open(name, *args, **kwargs)
                    finally:
                        parent.rename(donor); parked.rename(parent)
            return real_open(name, *args, **kwargs)

        try:
            with patch.object(Path, 'open', lambda name, *a, **k: opened(original_path_open, name, *a, **k)), \
                    patch.object(builtins, 'open', lambda name, *a, **k: opened(original_open, name, *a, **k)):
                with self.assertRaisesRegex(ValueError, 'source changed'):
                    result = copy_module.prepare(source, cache, 'io-boot', temporary)
        finally:
            self.record_warm_integrity('parent-swap', source, previous, result,
                sourceMetadataRestored=copy_module._source_identity(font.lstat()) == before,
                sourceReadOpens=len(opens))
        self.assertEqual(len(opens), 2)
        self.assertEqual(copy_module._source_identity(font.lstat()), before)
        self.assertEqual(font.read_bytes(), selected)
        self.assertEqual((previous / font.relative_to(source)).read_bytes(), original)
        self.assertFalse(temporary.exists())
        self.assertEqual(list(cache.glob('generation-*')), [previous])

    def test_warm_generation_miss_rejects_same_size_midstream_rewrite_with_restored_mtime(self):
        source, cache, font, previous, original, _ = self.warm_copy_fixture()
        temporary = self.module / 'warm-rewrite-copy'
        original_path_open, original_open = Path.open, builtins.open
        before = font.stat(); opens, changed = [], []

        class ChangedStream:
            def __init__(self, stream):
                self.stream = stream
            def __getattr__(self, name):
                return getattr(self.stream, name)
            def __enter__(self):
                self.stream.__enter__(); return self
            def __exit__(self, *args):
                return self.stream.__exit__(*args)
            def read(self, *args):
                data = self.stream.read(*args)
                if data and not changed:
                    with original_path_open(font, 'r+b') as output:
                        output.seek(1024 * 1024 + 128); output.write(b'Z')
                    os.utime(font, ns=(before.st_atime_ns, before.st_mtime_ns))
                    changed.append(True)
                return data

        def opened(real_open, name, *args, **kwargs):
            stream = real_open(name, *args, **kwargs)
            mode = kwargs.get('mode', args[0] if args else 'r')
            if not isinstance(name, int) and Path(name) == font and mode == 'rb':
                opens.append(mode)
                if len(opens) == 2:
                    return ChangedStream(stream)
            return stream

        with patch.object(Path, 'open', lambda name, *a, **k: opened(original_path_open, name, *a, **k)), \
                patch.object(builtins, 'open', lambda name, *a, **k: opened(original_open, name, *a, **k)), \
                patch.object(shutil, '_USE_CP_SENDFILE', False, create=True):
            with self.assertRaisesRegex(ValueError, 'source changed'):
                copy_module.prepare(source, cache, 'io-boot', temporary)
        self.assertEqual(changed, [True]); self.assertEqual(len(opens), 2)
        self.assertEqual((font.stat().st_size, font.stat().st_mtime_ns), (before.st_size, before.st_mtime_ns))
        self.assertEqual((previous / font.relative_to(source)).read_bytes(), original)
        self.assertFalse(temporary.exists())
        self.assertEqual(list(cache.glob('generation-*')), [previous])
        self.record_warm_integrity('midstream-rewrite', source, previous, mutationTriggered=True,
                                   sizeAndMtimeRestored=True)

    def test_warm_generation_miss_rechecks_earlier_alias_before_publication(self):
        source, cache, font, previous, original, _ = self.warm_copy_fixture()
        last = font.parent / 'ZZ-last.ttf'; last.write_bytes(original)
        alias = font.parent / 'Roboto-Regular.ttf'
        replacement = self.module / 'alias-replacement.ttf'; replacement.write_bytes(original)
        temporary = self.module / 'warm-alias-copy'
        real_chmod, changed = os.chmod, []

        def changed_alias(path, mode):
            result = real_chmod(path, mode)
            if path == temporary / last.relative_to(source):
                alias.unlink(); os.link(replacement, alias); changed.append(True)
            return result

        with patch.object(copy_module.os, 'chmod', changed_alias):
            with self.assertRaisesRegex(ValueError, 'source changed during preparation'):
                copy_module.prepare(source, cache, 'io-boot', temporary)
        self.assertEqual(changed, [True])
        self.assertEqual(alias.stat().st_ino, replacement.stat().st_ino)
        self.assertEqual((previous / font.relative_to(source)).read_bytes(), original)
        self.assertFalse(temporary.exists())
        self.assertEqual(list(cache.glob('generation-*')), [previous])
        self.record_warm_integrity('earlier-alias', source, previous, mutationTriggered=True)

    def test_warm_generation_miss_copy_error_preserves_previous_and_foreign_temp(self):
        source, cache, font, previous, original, _ = self.warm_copy_fixture()
        temporary, foreign = self.module / 'warm-error-copy', self.module / 'warm-foreign'
        foreign.mkdir(); (foreign / 'keep').write_text('foreign')
        with patch.object(copy_module.os, 'chmod', side_effect=OSError('warm fixture write failed')):
            with self.assertRaisesRegex(OSError, 'warm fixture write failed'):
                copy_module.prepare(source, cache, 'io-boot', temporary)
        self.assertFalse(temporary.exists())
        self.assertEqual(list(cache.glob('generation-*')), [previous])
        self.assertEqual((previous / font.relative_to(source)).read_bytes(), original)
        with self.assertRaises(FileExistsError):
            copy_module.prepare(source, cache, 'io-boot', foreign)
        self.assertEqual((foreign / 'keep').read_text(), 'foreign')
        self.assertEqual(list(cache.glob('generation-*')), [previous])
        self.record_warm_integrity('owned-error', source, previous, foreignSentinelPreserved=True)

    def test_warm_generation_miss_reads_twice_and_hit_verifies_without_staging_writes(self):
        source, cache, font, previous, original, selected = self.warm_copy_fixture()
        temporary, hit_tmp = self.module / 'warm-miss-copy', self.module / 'warm-hit-copy'
        rows = {}
        with PayloadIOMeter(source, cache, temporary) as rows['miss']:
            generation = copy_module.prepare(source, cache, 'io-boot', temporary)
        with PayloadIOMeter(source, cache, hit_tmp) as rows['hit']:
            same = copy_module.prepare(source, cache, 'io-boot', hit_tmp)
        needed = len(selected)
        self.assertEqual(rows['miss']['source']['readBytes'], 2 * needed)
        self.assertEqual(rows['miss']['source']['opens'], 2)
        self.assertEqual(rows['miss']['temporary']['writeBytes'], needed)
        self.assertEqual(rows['miss']['copyCalls'], 0)
        self.assertEqual(rows['miss']['linkCalls'], 1)
        self.assertEqual(rows['hit']['source']['readBytes'], needed)
        self.assertEqual(rows['hit']['source']['opens'], 1)
        self.assertEqual(rows['hit']['cache']['readBytes'], needed)
        self.assertEqual(rows['hit']['cache']['opens'], 1)
        self.assertEqual(rows['hit']['temporary']['writeBytes'], 0)
        self.assertEqual(rows['hit']['temporary']['opens'], 0)
        self.assertEqual(rows['hit']['copyCalls'], 0)
        self.assertEqual(generation, same)
        expected = hashlib.sha256()
        for name in ('MiSansVF.ttf', 'Roboto-Regular.ttf'):
            expected.update(('system/fonts/' + name).encode() + b'\0')
            expected.update(hashlib.sha256(selected).digest())
        self.assertEqual(generation.name, 'generation-' + expected.hexdigest())
        self.assertEqual(json.loads((generation / '.generation.json').read_text())['bytes'], needed)
        cached = generation / font.relative_to(source)
        self.assertEqual(cached.read_bytes(), selected)
        self.assertNotEqual(cached.stat().st_ino, font.stat().st_ino)
        self.assertEqual(cached.stat().st_ino, (generation / 'system/fonts/Roboto-Regular.ttf').stat().st_ino)
        self.assertEqual((previous / font.relative_to(source)).read_bytes(), original)
        self.assertFalse(temporary.exists()); self.assertFalse(hit_tmp.exists())
        self.record_warm_integrity('logical-io', source, previous, generation,
                                   uniqueSourceBytes=needed, stages=rows)

    def test_first_boot_generation_streams_source_once_and_warm_fully_verifies(self):
        source, cache, needed = self.copy_fixture()
        rows = {}
        cold_tmp, warm_tmp = self.module / 'copy-cold', self.module / 'copy-warm'
        with PayloadIOMeter(source, cache, cold_tmp) as rows['cold']:
            generation = copy_module.prepare(source, cache, 'io-boot', cold_tmp)
        with PayloadIOMeter(source, cache, warm_tmp) as rows['warm']:
            same = copy_module.prepare(source, cache, 'io-boot', warm_tmp)
        artifact = os.environ.get('LUOSHU_LIVE_IO_TEST_ARTIFACT_DIR')
        if artifact:
            output = Path(artifact); output.mkdir(parents=True, exist_ok=True)
            (output / 'logical-io.json').write_text(json.dumps({
                'scope': 'host prepare helper; actual returned read/sendfile bytes; no disk/device/full-switch claim',
                'helperSha256': hashlib.sha256((ROOT / 'common/font_live_payload.py').read_bytes()).hexdigest(),
                'uniqueSourceBytes': needed, 'stages': rows}, indent=2) + '\n')
        self.assertEqual(rows['cold']['source']['readBytes'], needed)
        self.assertEqual(rows['cold']['source']['opens'], 2)
        self.assertEqual(rows['cold']['temporary']['writeBytes'], needed)
        self.assertEqual(rows['cold']['copyCalls'], 0)
        self.assertEqual(rows['cold']['linkCalls'], 1)
        self.assertEqual(rows['warm']['source']['readBytes'], needed)
        self.assertEqual(rows['warm']['cache']['readBytes'], needed)
        self.assertEqual(rows['warm']['temporary']['writeBytes'], 0)
        self.assertEqual(rows['warm']['copyCalls'], 0)
        self.assertEqual(generation, same)
        expected = hashlib.sha256()
        for current, directories, files in os.walk(source):
            directories.sort()
            for name in sorted(files):
                path = Path(current) / name
                expected.update(str(path.relative_to(source)).encode() + b'\0')
                expected.update(hashlib.sha256(path.read_bytes()).digest())
        self.assertEqual(generation.name, 'generation-' + expected.hexdigest())
        self.assertFalse(cold_tmp.exists()); self.assertFalse(warm_tmp.exists())
        cached_font = generation / 'system/fonts/Roboto-Regular.ttf'
        self.assertNotEqual(cached_font.stat().st_ino, (source / 'system/fonts/Roboto-Regular.ttf').stat().st_ino)
        self.assertEqual(cached_font.stat().st_ino, (generation / 'system/fonts/MiSansVF.ttf').stat().st_ino)
        # Same size and restored mtime must not bypass the complete cache SHA.
        info = cached_font.stat()
        with cached_font.open('r+b') as stream:
            stream.write(b'X')
        os.utime(cached_font, ns=(info.st_atime_ns, info.st_mtime_ns))
        with self.assertRaisesRegex(ValueError, 'content mismatch'):
            copy_module.prepare(source, cache, 'io-boot', self.module / 'copy-corrupt')

    def test_first_boot_generation_rejects_source_fd_replacement(self):
        source = self.module / 'copy-source-race'
        source.mkdir()
        font = source / 'font.ttf'; font.write_bytes(b'first-content')
        replacement = self.module / 'replacement.ttf'; replacement.write_bytes(b'other-content')
        cache, temporary = self.module / 'cache/fd-race', self.module / 'copy-fd-race'
        original_open = Path.open
        def changed(path, *args, **kwargs):
            if path == font and (args[0] if args else kwargs.get('mode')) == 'rb':
                os.replace(replacement, font)
            return original_open(path, *args, **kwargs)
        with patch.object(Path, 'open', changed):
            with self.assertRaisesRegex(ValueError, 'source changed'):
                copy_module.prepare(source, cache, 'io-boot', temporary)
        self.assertFalse(temporary.exists())
        self.assertFalse(any(cache.glob('generation-*')))

    def test_first_boot_generation_rejects_midread_rewrite_and_cleans_partial_copy(self):
        source = self.module / 'copy-source-rewrite'; source.mkdir()
        font = source / 'font.ttf'; font.write_bytes(b'A' * (2 * 1024 * 1024))
        cache, temporary = self.module / 'cache/rewrite', self.module / 'copy-rewrite'
        original_open = Path.open
        class ChangedStream:
            def __init__(self, stream):
                self.stream, self.changed = stream, False
            def __getattr__(self, name):
                return getattr(self.stream, name)
            def __enter__(self):
                self.stream.__enter__(); return self
            def __exit__(self, *args):
                return self.stream.__exit__(*args)
            def read(self, *args):
                data = self.stream.read(*args)
                if data and not self.changed:
                    self.changed = True
                    info = font.stat()
                    with original_open(font, 'r+b') as output:
                        output.write(b'B')
                    os.utime(font, ns=(info.st_atime_ns, info.st_mtime_ns))
                return data
        def opened(path, *args, **kwargs):
            stream = original_open(path, *args, **kwargs)
            return ChangedStream(stream) if path == font and args == ('rb',) else stream
        with patch.object(Path, 'open', opened):
            with self.assertRaisesRegex(ValueError, 'source changed'):
                copy_module.prepare(source, cache, 'io-boot', temporary)
        self.assertFalse(temporary.exists())
        self.assertFalse(any(cache.glob('generation-*')))

    def test_first_boot_generation_copy_error_keeps_owned_cleanup_and_foreign_temp(self):
        source = self.module / 'copy-source-error'; source.mkdir()
        (source / 'font.ttf').write_bytes(b'font-bytes')
        cache, temporary = self.module / 'cache/error', self.module / 'copy-error'
        foreign = self.module / 'foreign-temp'; foreign.mkdir()
        (foreign / 'keep').write_text('foreign')
        with patch.object(copy_module.os, 'chmod', side_effect=OSError('fixture write failed')):
            with self.assertRaisesRegex(OSError, 'fixture write failed'):
                copy_module.prepare(source, cache, 'io-boot', temporary)
        self.assertFalse(temporary.exists())
        self.assertFalse(any(cache.glob('generation-*')))
        self.assertEqual((foreign / 'keep').read_text(), 'foreign')
        with self.assertRaises(FileExistsError):
            copy_module.prepare(source, cache, 'io-boot', foreign)
        self.assertEqual((foreign / 'keep').read_text(), 'foreign')

    def test_first_boot_generation_validates_late_existing_generation_without_overwriting(self):
        source = self.module / 'copy-source-late'; source.mkdir()
        font = source / 'font.ttf'; font.write_bytes(b'late-content')
        digest = hashlib.sha256(b'font.ttf\0' + hashlib.sha256(font.read_bytes()).digest()).hexdigest()
        cache, temporary = self.module / 'cache/late', self.module / 'copy-late'
        generation = cache / ('generation-' + digest)
        original_open = Path.open
        published_inode = []
        def late_generation(path, *args, **kwargs):
            if path == font and args == ('rb',) and not generation.exists():
                generation.mkdir()
                (generation / 'font.ttf').write_bytes(font.read_bytes())
                published_inode.append((generation / 'font.ttf').stat().st_ino)
                (generation / '.generation.json').write_text(json.dumps({
                    'schema': 'luoshu-live-font-v1', 'digest': digest, 'bootId': 'io-boot'}))
            return original_open(path, *args, **kwargs)
        with patch.object(Path, 'open', late_generation):
            result = copy_module.prepare(source, cache, 'io-boot', temporary)
        self.assertEqual(result, generation)
        inode = (generation / 'font.ttf').stat().st_ino
        self.assertEqual(inode, published_inode[0])
        self.assertFalse(temporary.exists())
        self.assertEqual((generation / 'font.ttf').read_bytes(), font.read_bytes())
        self.assertEqual((generation / 'font.ttf').stat().st_ino, inode)
        # An already present corrupt generation is rejected rather than replaced.
        (generation / 'font.ttf').write_bytes(b'bad-content!')
        with self.assertRaisesRegex(ValueError, 'content mismatch'):
            copy_module.prepare(source, cache, 'io-boot', self.module / 'copy-late-bad')
        self.assertEqual((generation / 'font.ttf').stat().st_ino, inode)
        self.assertEqual((generation / 'font.ttf').read_bytes(), b'bad-content!')

    def test_live_lock_refuses_concurrent_request_without_touching_generation(self):
        self.select('A'); self.assertTrue(self.run_live()[1]['liveApplied'])
        state = (self.config / 'font-live.conf').read_bytes()
        source = Path(self.state()['source'])
        font = source / 'system/fonts/Roboto-Regular.ttf'
        inode, content = font.stat().st_ino, font.read_bytes()
        lock = self.module / '.luoshu-state/tasks/font-live.lock'
        with lock.open('rb') as stream:
            copy_module.fcntl.flock(stream.fileno(), copy_module.fcntl.LOCK_EX | copy_module.fcntl.LOCK_NB)
            self.select('B')
            result, _ = self.run_live()
            self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.config / 'font-live.conf').read_bytes(), state)
        self.assertEqual(font.stat().st_ino, inode)
        self.assertEqual(font.read_bytes(), content)
        self.assertTrue(self.run_live()[1]['liveApplied'])
        self.assertEqual((self.module / 'visible/font').read_text(), 'B-font-bytes')

    def test_generation_publication_collision_does_not_overwrite_existing_record(self):
        source = self.module / 'copy-source-collision'; source.mkdir()
        (source / 'font.ttf').write_bytes(b'selected-content')
        cache, temporary = self.module / 'cache/collision', self.module / 'copy-collision'
        original_rename = Path.rename
        collision = []
        def collided(path, target):
            if path == temporary:
                generation = Path(target); generation.mkdir()
                (generation / 'font.ttf').write_bytes(b'existing-content')
                (generation / '.generation.json').write_text('existing-record')
                collision.append(generation)
            return original_rename(path, target)
        with patch.object(Path, 'rename', collided):
            with self.assertRaises(OSError):
                copy_module.prepare(source, cache, 'io-boot', temporary)
        self.assertFalse(temporary.exists())
        self.assertEqual((collision[0] / 'font.ttf').read_bytes(), b'existing-content')
        self.assertEqual((collision[0] / '.generation.json').read_text(), 'existing-record')


if __name__ == '__main__':
    unittest.main()
