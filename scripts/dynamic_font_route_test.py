#!/usr/bin/env python3
"""Real fonts and shell entrypoints for the Inventory dynamic-route consumer view."""
from pathlib import Path
import os
import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'common'))
from fontTools.ttLib import TTFont
from hyperos_cjk_routing_test import make_font, HAN, UVS_HAN
from dynamic_font_route_patch import patch, route_rows, authorized_target, build_view


class DynamicRouteViewTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        self.config = self.module / 'config'
        self.config.mkdir(parents=True)
        (self.config / 'active_font.conf').write_text('composite-test\n')
        (self.module / 'common').symlink_to(ROOT / 'common', target_is_directory=True)
        self.source = self.module / '.luoshu-payload/system/fonts/.luoshu-font-store/mix-composite.font'
        self.source.parent.mkdir(parents=True)
        points = (*range(32, 127), HAN, UVS_HAN)
        make_font(self.source, points=points, variable=True, uvs=True)
        self.target = self.root / 'data/theme/UnbrandedBody.ttf'
        self.target.parent.mkdir(parents=True)
        make_font(self.target, points=points)
        with TTFont(self.target, recalcBBoxes=False, recalcTimestamp=False) as font:
            font['hhea'].ascent = 920
            font['hhea'].descent = -230
            font['OS/2'].sTypoAscender = 900
            font['OS/2'].sTypoDescender = -220
            font['head'].yMin = -320
            font['head'].yMax = 1100
            font.save(self.target)
        self.router = self.root / 'data/font_router/UnbrandedBody.ttf'
        self.router.parent.mkdir()
        self.router.symlink_to(self.target)
        self.alias = self.root / 'system/fonts/UnbrandedAlias.ttf'
        self.alias.parent.mkdir(parents=True)
        self.alias.symlink_to(self.router)
        self.inventory = {"schema": "device-font-inventory-v1", "state": "ready",
                          "sourceRoots": [{"logical": str(self.alias.parent)}],
                          "dynamicFontRoutes": [{"alias": str(self.alias), "target": str(self.router), "status": "preserved"}]}
        self.save_inventory()
        self.proc = self.root / 'proc'
        for pid, name, ns in ((101, 'zygote64', 17), (102, 'com.android.chrome', 18),
                              (103, 'com.android.chrome:sandboxed_process0', 18),
                              (104, 'system_server', 19)):
            path = self.proc / str(pid)
            (path / 'ns').mkdir(parents=True)
            (path / 'root').mkdir()
            (path / 'cmdline').write_bytes(name.encode() + b'\0')
            (path / 'ns/mnt').symlink_to(f'mnt:[{ns}]')
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.command('pidof', 'exit 1\n')
        self.command('chcon', 'exit 0\n')
        self.env = {**os.environ, 'MODDIR': str(self.module), 'PATH': f'{self.bin}:{os.environ["PATH"]}',
                    'LUOSHU_DYNAMIC_DATA_ROOT': str(self.root / 'data'),
                    'TEST_ALIAS': str(self.alias), 'TEST_ROUTER': str(self.router), 'LUOSHU_PROC_ROOT': str(self.proc),
                    'LUOSHU_GOOGLE_FONT_PYTHON': sys.executable,
                    'TEST_ROOT': str(self.root)}

    def save_inventory(self):
        (self.config / 'device_font_inventory.json').write_text(json.dumps(self.inventory))

    def command(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/sh\n' + body)
        path.chmod(0o755)

    def shell(self, commands):
        return subprocess.run(['sh', '-c', '. "$MODDIR/common/dynamic_font_route_bridge.sh"\n_dfr_catalog || exit 81\nIFS="|" read -r key alias target < "$DFR_CATALOG"\n_dfr_select "$key" "$alias" "$target"\nDFR_ROUTER="$TEST_ROUTER"\n_dfr_active || true\n' + commands],
                              env=self.env, capture_output=True, text=True, timeout=15)

    def test_full_glyphs_variations_and_target_layout_are_retained(self):
        output = self.root / 'view.ttf'
        source_bytes, target_bytes = self.source.read_bytes(), self.target.read_bytes()
        patch(self.source, self.target, output)
        with TTFont(self.source) as source, TTFont(self.target) as target, TTFont(output) as view:
            self.assertEqual(source.getBestCmap(), view.getBestCmap())
            for tag in ('glyf', 'gvar', 'fvar'):
                self.assertEqual(source.reader[tag], view.reader[tag], tag)
            self.assertEqual(next(t.uvsDict for t in view['cmap'].tables if t.format == 14),
                             next(t.uvsDict for t in source['cmap'].tables if t.format == 14))
            self.assertEqual((view['hhea'].ascent, view['hhea'].descent), (920, -230))
            self.assertEqual((view['head'].yMin, view['head'].yMax), (-320, 1100))
            self.assertEqual(view['OS/2'].sTypoAscender, target['OS/2'].sTypoAscender)
        self.assertEqual(self.source.read_bytes(), source_bytes)
        self.assertEqual(self.target.read_bytes(), target_bytes)

    def test_output_can_never_replace_theme_file(self):
        with self.assertRaises(ValueError):
            patch(self.source, self.target, self.target)

    def test_exact_dynamic_route_only(self):
        self.assertEqual(self.shell('_dfr_active').returncode, 0)
        self.router.unlink()
        self.router.symlink_to(self.source)
        self.assertNotEqual(self.shell('_dfr_active').returncode, 0)
        self.assertEqual(self.shell('_dfr_fingerprint').stdout.strip(), 'dynamic-font:inactive')

    def test_relative_theme_router_remains_active(self):
        self.router.unlink()
        self.router.symlink_to('../theme/UnbrandedBody.ttf')
        self.alias.unlink()
        self.alias.symlink_to('../../data/font_router/UnbrandedBody.ttf')
        self.assertEqual(self.shell('_dfr_active').returncode, 0)

    def test_router_recreated_as_regular_font_is_repaired(self):
        self.router.unlink()
        self.router.write_bytes(self.target.read_bytes())
        result = self.shell('_dfr_active && printf "%s" "$DFR_TARGET"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, str(self.router))

    def test_inherited_clone_is_restored_in_new_chrome_namespace(self):
        commands = '''
_dfr_pids() { echo 101; }
_gfp_mount_in_pid() {
    view="$LUOSHU_PROC_ROOT/$1/root$3"
    mkdir -p "${view%/*}"
    ln "$2" "$view"
}
_dfr_apply || exit 10
# Chrome inherits the exact owned inode into a newly created namespace.
view="$LUOSHU_PROC_ROOT/102/root$DFR_TARGET"
mkdir -p "${view%/*}"
ln "$DFR_CLONE" "$view"
_dfr_pids() { echo 102; }
_gfp_unmount_in_pid() { echo "$1" >> "$TEST_ROOT/unmounted"; rm -f "$LUOSHU_PROC_ROOT/$1/root$2"; }
_dfr_restore || exit 11
'''
        result = self.shell(commands)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'unmounted').read_text().split(), ['102'])

    def test_missing_live_payload_never_uses_pending_selection(self):
        self.source.rename(self.source.with_name('unavailable.font'))
        pending = self.module / '.luoshu-payload-next/system/fonts/400.ttf'
        pending.parent.mkdir(parents=True)
        pending.write_bytes(self.target.read_bytes())
        result = self.shell('_dfr_source')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')

    def test_namespaces_deduplicate_chrome_and_exclude_system_server(self):
        result = self.shell('_dfr_pids')
        self.assertEqual(set(result.stdout.split()), {'101', '102'})

    def test_fingerprint_tracks_new_namespace_without_parsing_fonts(self):
        first = self.shell('_gfp_python() { exit 99; }; _dfr_fingerprint')
        self.assertEqual(first.returncode, 0)
        second = self.shell('_gfp_python() { exit 99; }; _dfr_fingerprint')
        self.assertEqual(first.stdout, second.stdout)
        namespace = self.proc / '102/ns/mnt'
        namespace.unlink()
        namespace.symlink_to('mnt:[99]')
        self.assertNotEqual(first.stdout, self.shell('_dfr_fingerprint').stdout)

    def test_changed_theme_does_not_accumulate_clones(self):
        original = self.target.read_bytes()
        for _ in range(4):
            replacement = self.target.with_suffix('.new')
            replacement.write_bytes(original)
            replacement.replace(self.target)
            result = self.shell('_dfr_prepare')
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLessEqual(len(list((self.config / 'dynamic-font-routes').glob('*/*.ttf'))), 2)

    def test_warm_apply_does_not_start_python_and_binds_preserve_theme(self):
        original = self.target.read_bytes()
        commands = '''
_gfp_mount_in_pid() {
    view="$LUOSHU_PROC_ROOT/$1/root$3"
    mkdir -p "${view%/*}"
    rm -f "$view"
    ln "$2" "$view"
}
_dfr_apply || exit 10
_gfp_python() { touch "$TEST_ROOT/unexpected-python"; return 1; }
_dfr_apply || exit 11
'''
        result = self.shell(commands)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / 'unexpected-python').exists())
        self.assertTrue(self.alias.is_symlink())
        self.assertTrue(self.router.is_symlink())
        self.assertEqual(self.target.read_bytes(), original)

    def test_restore_releases_only_recorded_inode_and_route_change_releases(self):
        commands = '''
_gfp_mount_in_pid() {
    view="$LUOSHU_PROC_ROOT/$1/root$3"
    mkdir -p "${view%/*}"
    rm -f "$view"
    ln "$2" "$view"
}
_gfp_unmount_in_pid() {
    echo "$1" >> "$TEST_ROOT/unmounted"
    rm -f "$LUOSHU_PROC_ROOT/$1/root$2"
}
_dfr_apply || exit 10
# Simulate a different module/ROM replacing one consumer's view.
view="$LUOSHU_PROC_ROOT/102/root$DFR_TARGET"
rm -f "$view"
cp "$DFR_TARGET" "$view"
rm "$DFR_ROUTER"
ln -s "$MODDIR/.luoshu-payload/system/fonts/MiSansVF.ttf" "$DFR_ROUTER"
_dfr_apply
[ "$?" = 2 ] || exit 11
'''
        result = self.shell(commands)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'unmounted').read_text().split(), ['101'])

    def test_donor_changes_replace_own_layer_and_unlink_does_not_lose_ownership(self):
        commands = '''
_dfr_pids() { echo 101; }
_gfp_mount_in_pid() {
    echo bind >> "$TEST_ROOT/events"
    view="$LUOSHU_PROC_ROOT/$1/root$3"
    mkdir -p "${view%/*}"
    [ ! -e "$view" ] || exit 51
    ln "$2" "$view"
}
_gfp_unmount_in_pid() {
    echo unmount >> "$TEST_ROOT/events"
    rm -f "$LUOSHU_PROC_ROOT/$1/root$2"
}
_dfr_apply || exit 10
source=$(_dfr_source)
cp "$source" "$source.new" && mv "$source.new" "$source"
_dfr_apply || exit 11
# Pruning a cache hardlink changes ctime while the mounted inode stays valid.
rm "$DFR_CLONE"
_dfr_restore || exit 12
'''
        result = self.shell(commands)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'events').read_text().split(), ['bind', 'unmount', 'bind', 'unmount'])

    def test_restore_removes_all_recorded_own_layers(self):
        commands = '''
_dfr_pids() { echo 101; }
_dfr_prepare || exit 10
cp "$DFR_CLONE" "$DFR_CACHE/second.ttf"
view="$LUOSHU_PROC_ROOT/101/root$DFR_TARGET"
mkdir -p "${view%/*}"
ln "$DFR_CACHE/second.ttf" "$view"
ns=$(readlink "$LUOSHU_PROC_ROOT/101/ns/mnt")
printf '%s|%s|%s|%s\n' "$ns" "$(_dfr_identity "$DFR_CLONE")" "$DFR_CLONE" "$DFR_TARGET" > "$DFR_MOUNTS"
printf '%s|%s|%s|%s\n' "$ns" "$(_dfr_identity "$DFR_CACHE/second.ttf")" "$DFR_CACHE/second.ttf" "$DFR_TARGET" >> "$DFR_MOUNTS"
layer=2
_gfp_unmount_in_pid() {
    echo unmount >> "$TEST_ROOT/events"
    rm -f "$view"
    [ "$layer" = 1 ] || ln "$DFR_CLONE" "$view"
    layer=$((layer - 1))
}
_dfr_restore || exit 11
'''
        result = self.shell(commands)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'events').read_text().split(), ['unmount', 'unmount'])

    def test_failed_unmount_keeps_journal_and_does_not_stack_new_donor(self):
        commands = '''
_dfr_pids() { echo 101; }
_gfp_mount_in_pid() {
    view="$LUOSHU_PROC_ROOT/$1/root$3"
    mkdir -p "${view%/*}"
    ln "$2" "$view"
}
_dfr_apply || exit 10
source=$(_dfr_source)
cp "$source" "$source.new" && mv "$source.new" "$source"
_gfp_unmount_in_pid() { return 1; }
_gfp_mount_in_pid() { touch "$TEST_ROOT/stacked"; return 0; }
_dfr_apply
[ "$?" = 1 ] && [ -s "$DFR_MOUNTS" ] || exit 11
_dfr_restore
[ "$?" = 1 ] && [ -s "$DFR_MOUNTS" ] || exit 12
'''
        result = self.shell(commands)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / 'stacked').exists())

    def test_mount_journal_failure_is_not_success(self):
        self.command('mv', '''
case "$*" in *namespaces.conf*) exit 1;; esac
exec /bin/mv "$@"
''')
        result = self.shell('''
_dfr_pids() { echo 101; }
_gfp_mount_in_pid() {
    view="$LUOSHU_PROC_ROOT/$1/root$3"
    mkdir -p "${view%/*}"
    ln "$2" "$view"
}
_dfr_apply
''')
        self.assertEqual(result.returncode, 1, result.stderr)

    def test_optional_regular_guard_runs_inside_target_namespace(self):
        # nsenter is mocked below. PID 1 is a stable proc fixture even on hosts
        # whose command runner exposes a different PID view to subprocesses.
        self.command('nsenter', 'while [ "$1" != -- ]; do shift; done\nshift\nexec "$@"\n')
        self.env['LUOSHU_GOOGLE_FONT_NS_SHELL'] = '/bin/sh'
        self.env['LUOSHU_PROC_ROOT'] = '/proc'
        result = self.shell('''
_gfp_mount_in_pid 1 "$DFR_TARGET" "$DFR_ROUTER" 1
[ "$?" = 1 ] && [ "$_gfp_mount_detail" = target-is-symlink ] || exit 10
_gfp_mount_in_pid 1 "$DFR_TARGET" "$DFR_ROUTER"
[ "$?" = 0 ] && [ "$_gfp_mount_mode" = already ] || exit 11
''')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_inventory_cannot_authorize_an_alias_outside_scanned_font_roots(self):
        self.inventory['dynamicFontRoutes'][0]['alias'] = '/sdcard/selected.ttf'
        self.assertEqual(route_rows(self.inventory), [])

    def test_route_moves_to_another_system_owned_data_directory(self):
        replacement = self.root / 'data/another_framework/font_files/BodyFont.bin'
        replacement.parent.mkdir(parents=True)
        replacement.write_bytes(self.target.read_bytes())
        self.router.unlink()
        self.router.symlink_to(replacement)
        result = self.shell('_dfr_prepare && printf "%s" "$DFR_TARGET"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, str(replacement))
        self.assertEqual(replacement.read_bytes(), self.target.read_bytes())

    def test_font_in_user_storage_is_never_replaced(self):
        unsafe = self.root / 'data/media/0/Documents/font.ttf'
        unsafe.parent.mkdir(parents=True)
        unsafe.write_bytes(self.target.read_bytes())
        self.router.unlink()
        self.router.symlink_to(unsafe)
        result = self.shell('''
_gfp_mount_in_pid() { touch "$TEST_ROOT/unexpected-bind"; }
_dfr_apply
''')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse((self.root / 'unexpected-bind').exists())

    def test_valid_header_without_text_cmap_is_preserved(self):
        make_font(self.target, points=(0xE001, 0xE002))
        result = self.shell('''
_gfp_mount_in_pid() { touch "$TEST_ROOT/unexpected-bind"; }
_dfr_apply
''')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse((self.root / 'unexpected-bind').exists())

    def test_non_font_regular_file_is_preserved_without_binding(self):
        self.target.write_bytes(b'not a font' * 300)
        result = self.shell('''
_gfp_mount_in_pid() { touch "$TEST_ROOT/unexpected-bind"; }
_dfr_apply
''')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse((self.root / 'unexpected-bind').exists())

    def test_two_unbranded_routes_apply_and_removed_inventory_route_is_restored(self):
        second = self.root / 'data/second/Numbers.ttf'
        second.parent.mkdir(parents=True)
        second.write_bytes(self.target.read_bytes())
        alias = self.alias.with_name('AnotherFontAlias.otf')
        alias.symlink_to(second)
        self.inventory['dynamicFontRoutes'].append({'alias': str(alias), 'target': str(second)})
        self.save_inventory()
        result = self.shell('''
_dfr_pids() { echo 101; }
_gfp_mount_in_pid() {
    view="$LUOSHU_PROC_ROOT/$1/root$3"
    mkdir -p "${view%/*}"
    ln "$2" "$view"
}
_gfp_unmount_in_pid() {
    echo "$2" >> "$TEST_ROOT/restored"
    rm -f "$LUOSHU_PROC_ROOT/$1/root$2"
}
_dfr_apply_all_internal || exit 11
[ "$(find "$DFR_BASE" -name namespaces.conf | wc -l)" = 2 ] || exit 12
# Atomic inventory refresh removes one route; it must not orphan its mounts.
"$PYTHON" -c 'import json,os; p=os.environ["MODDIR"]+"/config/device_font_inventory.json"; d=json.load(open(p)); d["dynamicFontRoutes"]=d["dynamicFontRoutes"][:1]; open(p,"w").write(json.dumps(d))'
_dfr_apply_all_internal || exit 13
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'restored').read_text().splitlines(), [str(second)])

    def test_own_view_never_becomes_stock_script_coverage_evidence(self):
        make_font(self.target, points=range(32, 127))
        key = route_rows(self.inventory)[0][0]
        cache = self.config / 'dynamic-font-routes' / key
        first, second = cache / 'first.ttf', cache / 'second.ttf'
        with mock.patch.dict(os.environ, {'LUOSHU_DYNAMIC_DATA_ROOT': str(self.root / 'data')}):
            build_view(self.module, self.alias, self.target, first)
            self.target.unlink()
            os.link(first, self.target)
            info = first.stat()
            (cache / 'namespaces.conf').write_text(
                f'mnt:[17]|{info.st_dev}:{info.st_ino}:{info.st_size}|{first}|{self.target}\n')
            # The old view contains Han from the previous source. The original
            # target was Latin, so the next Latin source remains replaceable.
            self.source.unlink()
            make_font(self.source, points=range(32, 127))
            build_view(self.module, self.alias, self.target, second)
        with TTFont(second) as result:
            self.assertNotIn(HAN, result.getBestCmap())


if __name__ == '__main__':
    unittest.main()
