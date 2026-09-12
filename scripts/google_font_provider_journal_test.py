#!/usr/bin/env python3
"""Exercise provider mount ownership with real shell/stat and simulated bind views."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / 'common/google_font_provider_bridge.sh'


class ProviderJournalTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        self.config = self.module / 'config'
        self.config.mkdir(parents=True)
        self.proc = self.root / 'proc'
        self.target = '/data/fonts/provider.ttf'
        self.old = self.root / 'old.ttf'
        self.new = self.root / 'new.ttf'
        self.stock = self.root / 'stock.ttf'
        self.foreign = self.root / 'foreign.ttf'
        for path in (self.old, self.new, self.stock, self.foreign):
            path.write_bytes((path.stem.encode() + b'\0') * 512)
        for pid in (101, 102):
            directory = self.proc / str(pid)
            (directory / 'ns').mkdir(parents=True)
            (directory / 'ns/mnt').symlink_to(f'mnt:[{pid}]')
            view = directory / ('root' + self.target)
            view.parent.mkdir(parents=True)
            os.link(self.stock, view)
        self.journal = self.config / 'google-font-provider-namespaces.conf'
        self.events = self.root / 'events'
        self.env = {**os.environ, 'MODDIR': str(self.module),
                    'LUOSHU_PROC_ROOT': str(self.proc), 'TEST_ROOT': str(self.root),
                    'TEST_TARGET': self.target, 'TEST_OLD': str(self.old), 'TEST_NEW': str(self.new),
                    'TEST_STOCK': str(self.stock), 'TEST_FOREIGN': str(self.foreign)}

    def shell(self, command):
        script = '''
. "$1"
_gfp_unique_namespace_pids() { printf '%s\\n' ${TEST_PIDS:-101}; }
# Deferred consumer FD handling has its own tests. Here the only fake operations
# are kernel mount/unmount, represented by hardlinks with real inode identity.
_gfp_queue_all_consumers() { :; }
_gfp_mount_in_pid() {
    _mock_view="$LUOSHU_PROC_ROOT/$1/root$3"
    if [ -e "$_mock_view" ] && [ "$(_gfp_identity "$_mock_view")" != "$(_gfp_identity "$TEST_STOCK")" ]; then
        echo unexpected-stack >> "$TEST_ROOT/events"
        return 95
    fi
    rm -f "$_mock_view"
    ln "$2" "$_mock_view" || return 1
    _gfp_mount_mode=plain
    printf 'bind:%s:%s\\n' "$1" "${2##*/}" >> "$TEST_ROOT/events"
}
_gfp_unmount_in_pid() {
    printf 'unmount:%s\\n' "$1" >> "$TEST_ROOT/events"
    [ "${TEST_UNMOUNT_FAIL:-0}" != 1 ] || return 1
    _mock_view="$LUOSHU_PROC_ROOT/$1/root$2"
    rm -f "$_mock_view"
    ln "$TEST_STOCK" "$_mock_view"
}
''' + command
        result = subprocess.run(['sh', '-c', script, 'journal-test', str(BRIDGE)],
                                env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return self.events.read_text().splitlines() if self.events.exists() else []

    def view(self, pid=101):
        return self.proc / str(pid) / ('root' + self.target)

    def test_new_clone_removes_old_owned_layer_before_bind(self):
        events = self.shell('''
_gfp_mount_target 101 "$TEST_OLD" "$TEST_TARGET" || exit 10
_gfp_mount_target 101 "$TEST_NEW" "$TEST_TARGET" || exit 11
_gfp_restore_internal || exit 12
''')
        self.assertEqual(events, ['bind:101:old.ttf', 'unmount:101', 'bind:101:new.ttf', 'unmount:101'])
        self.assertEqual(self.view().stat().st_ino, self.stock.stat().st_ino)
        self.assertFalse(self.journal.exists())

    def test_unchanged_clone_does_not_unmount_or_stack(self):
        events = self.shell('''
_gfp_mount_target 101 "$TEST_OLD" "$TEST_TARGET" || exit 10
_gfp_mount_target 101 "$TEST_OLD" "$TEST_TARGET" || exit 11
''')
        self.assertEqual(events, ['bind:101:old.ttf'])
        self.assertEqual(len(self.journal.read_text().splitlines()), 1)

    def test_inherited_namespace_is_restored_without_prior_child_entry(self):
        events = self.shell('''
_gfp_mount_target 101 "$TEST_OLD" "$TEST_TARGET" || exit 10
rm "$LUOSHU_PROC_ROOT/102/root$TEST_TARGET"
ln "$TEST_OLD" "$LUOSHU_PROC_ROOT/102/root$TEST_TARGET"
TEST_PIDS='101 102'
_gfp_restore_internal || exit 11
''')
        self.assertEqual(events, ['bind:101:old.ttf', 'unmount:101', 'unmount:102'])
        self.assertEqual(self.view(102).stat().st_ino, self.stock.stat().st_ino)

    def test_foreign_replacement_is_never_unmounted(self):
        events = self.shell('''
_gfp_mount_target 101 "$TEST_OLD" "$TEST_TARGET" || exit 10
rm "$LUOSHU_PROC_ROOT/101/root$TEST_TARGET"
ln "$TEST_FOREIGN" "$LUOSHU_PROC_ROOT/101/root$TEST_TARGET"
_gfp_restore_internal || exit 11
''')
        self.assertEqual(events, ['bind:101:old.ttf'])
        self.assertEqual(self.view().stat().st_ino, self.foreign.stat().st_ino)

    def test_unmount_failure_preserves_journal_and_blocks_new_layer(self):
        events = self.shell('''
_gfp_mount_target 101 "$TEST_OLD" "$TEST_TARGET" || exit 10
cp "$MOUNTS" "$TEST_ROOT/before"
TEST_UNMOUNT_FAIL=1
_gfp_mount_target 101 "$TEST_NEW" "$TEST_TARGET"
[ "$?" = 1 ] || exit 11
_gfp_restore_internal
[ "$?" = 1 ] || exit 12
''')
        self.assertEqual(events, ['bind:101:old.ttf', 'unmount:101', 'unmount:101'])
        self.assertEqual(self.journal.read_bytes(), (self.root / 'before').read_bytes())
        self.assertEqual(self.view().stat().st_ino, self.old.stat().st_ino)

    def test_journal_rename_failure_rolls_back_new_layer(self):
        events = self.shell('''
_gfp_mount_target 101 "$TEST_OLD" "$TEST_TARGET" || exit 10
cp "$MOUNTS" "$TEST_ROOT/before"
mv() { [ "$3" != "$MOUNTS" ] || return 1; command mv "$@"; }
_gfp_mount_target 101 "$TEST_NEW" "$TEST_TARGET"
[ "$?" = 1 ] || exit 11
''')
        self.assertEqual(events, ['bind:101:old.ttf', 'unmount:101', 'bind:101:new.ttf', 'unmount:101'])
        self.assertEqual(self.view().stat().st_ino, self.stock.stat().st_ino)
        self.assertEqual(self.journal.read_bytes(), (self.root / 'before').read_bytes())

    def test_journal_open_failure_rolls_back_new_layer(self):
        events = self.shell('''
mkdir "${MOUNTS}.tmp.$$"
_gfp_mount_target 101 "$TEST_NEW" "$TEST_TARGET"
[ "$?" = 1 ] || exit 11
''')
        self.assertEqual(events, ['bind:101:new.ttf', 'unmount:101'])
        self.assertEqual(self.view().stat().st_ino, self.stock.stat().st_ino)

    def test_journal_rollback_does_not_remove_a_concurrent_foreign_view(self):
        events = self.shell('''
mv() {
    [ "$3" = "$MOUNTS" ] || { command mv "$@"; return $?; }
    rm "$LUOSHU_PROC_ROOT/101/root$TEST_TARGET"
    ln "$TEST_FOREIGN" "$LUOSHU_PROC_ROOT/101/root$TEST_TARGET"
    return 1
}
_gfp_mount_target 101 "$TEST_NEW" "$TEST_TARGET"
[ "$?" = 1 ] || exit 11
''')
        self.assertEqual(events, ['bind:101:new.ttf'])
        self.assertEqual(self.view().stat().st_ino, self.foreign.stat().st_ino)

    def test_unlinked_clone_keeps_owned_inode_until_restore(self):
        events = self.shell('''
_gfp_mount_target 101 "$TEST_OLD" "$TEST_TARGET" || exit 10
rm "$TEST_OLD"
_gfp_restore_internal || exit 11
''')
        self.assertEqual(events, ['bind:101:old.ttf', 'unmount:101'])
        self.assertEqual(self.view().stat().st_ino, self.stock.stat().st_ino)


if __name__ == '__main__':
    unittest.main()
