#!/usr/bin/env python3
"""HyperOS default sans-serif route (MiSansVF_Overlay -> theme_webview) early bind.

dali/K80 stock layout: /system/fonts/MiSansVF_Overlay.ttf is a symlink to
/data/system/fonts/theme_webview/Roboto-Regular.ttf, which early boot seeds with
a byte copy of ROM Roboto. system_server builds the shared font map from it
before boot-completed helpers run, so Latin/digits stay stock while Han falls
back to the replaced MiSans. Mounts are simulated by PATH shims (hardlink the
clone in place, keep the original aside) so inode ownership is real.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from hyperos_cjk_routing_test import make_font, HAN  # noqa: E402

MOUNT_SHIM = r'''#!/bin/sh
# Fake bind mount: keep the original aside, expose the source inode in place.
log="$TEST_ROOT/mount.log"; info="$TEST_ROOT/mountinfo"; stash="$TEST_ROOT/stash"
mkdir -p "$stash"
printf '%s\n' "$*" >> "$log"
case "$1" in
    --bind) src="$2"; dst="$3" ;;
    -o)
        case "$2" in
            bind) src="$3"; dst="$4" ;;
            *remount*) printf 'ro %s\n' "$3" >> "$TEST_ROOT/ro.log"; exit 0 ;;
            *) exit 1 ;;
        esac ;;
    *) exit 1 ;;
esac
[ "${FAIL_MOUNT:-0}" = 1 ] && exit 32
n=$(wc -l < "$info" 2>/dev/null || echo 0)
mv "$dst" "$stash/$n" || exit 1
ln "$src" "$dst" || { mv "$stash/$n" "$dst"; exit 1; }
printf '%s 1 0:0 / %s ro - bind none ro\n' "$n" "$dst" >> "$info"
'''

UMOUNT_SHIM = r'''#!/bin/sh
info="$TEST_ROOT/mountinfo"; stash="$TEST_ROOT/stash"
dst="$1"
line=$(awk -v t="$dst" '$5 == t {l=$0} END {print l}' "$info")
[ -n "$line" ] || exit 1
n=${line%% *}
rm -f "$dst" && mv "$stash/$n" "$dst" || exit 1
awk -v n="$n" '$1 != n' "$info" > "$info.new" && mv "$info.new" "$info"
printf 'umount %s\n' "$dst" >> "$TEST_ROOT/mount.log"
'''


def make_named_font(path, family, points):
    """make_font with a real family name, as a theme Roboto or theme-store font."""
    from fontTools.ttLib import TTFont
    make_font(path, points=points)
    font = TTFont(path)
    for record in font['name'].names:
        if record.nameID in (1, 4, 6, 16):
            record.string = family
    font.save(path)


class WebViewRouteTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        (self.module / 'config').mkdir(parents=True)
        (self.module / 'common').symlink_to(ROOT / 'common', target_is_directory=True)
        (self.module / 'config/active_font.conf').write_text('safe-test\n')
        self.fonts = self.root / 'system/fonts'
        self.fonts.mkdir(parents=True)
        # Stock Roboto: Latin only. Payload Roboto: user Latin + digits (more glyphs).
        self.stock = self.fonts / 'Roboto-Regular.ttf'
        make_font(self.stock, points=tuple(range(32, 127)))
        self.payload = self.module / '.luoshu-payload/system/fonts/Roboto-Regular.ttf'
        self.payload.parent.mkdir(parents=True)
        make_font(self.payload, points=(*range(32, 127), 0xA0, 0xB0))
        self.router = self.root / 'data/system/fonts/theme_webview/Roboto-Regular.ttf'
        self.router.parent.mkdir(parents=True)
        self.router.write_bytes(self.stock.read_bytes())
        self.alias = self.fonts / 'MiSansVF_Overlay.ttf'
        self.alias.symlink_to(self.router)
        self.theme_target = self.root / 'data/system/theme/fonts/Roboto-Regular.ttf'
        self.mountinfo = self.root / 'mountinfo'
        self.mountinfo.write_text('1 0 0:0 / / rw - rootfs rootfs rw\n')
        self.boot = self.root / 'boot_id'
        self.boot.write_text('boot-a\n')
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.command('mount', MOUNT_SHIM)
        self.command('umount', UMOUNT_SHIM)
        self.command('chcon', '#!/bin/sh\nexit 0\n')
        self.command('getprop', '#!/bin/sh\n[ "$1" = ro.mi.os.version.name ] && echo OS3.0\n')
        self.env = {**os.environ, 'MODDIR': str(self.module), 'TEST_ROOT': str(self.root),
                    'PATH': f'{self.bin}:{os.environ["PATH"]}',
                    'LUOSHU_WEBVIEW_ROUTE_ALIAS': str(self.alias),
                    'LUOSHU_WEBVIEW_ROUTE_ROUTER': str(self.router),
                    'LUOSHU_WEBVIEW_ROUTE_STOCK': str(self.stock),
                    'LUOSHU_WEBVIEW_ROUTE_THEME_TARGET': str(self.theme_target),
                    'LUOSHU_WEBVIEW_ROUTE_MOUNTINFO': str(self.mountinfo),
                    'LUOSHU_WEBVIEW_ROUTE_BOOT_ID': str(self.boot)}
        self.stock_bytes = self.stock.read_bytes()

    def command(self, name, body):
        path = self.bin / name
        path.write_text(body)
        path.chmod(0o755)

    def run_route(self, action, **extra):
        return subprocess.run(['sh', str(ROOT / 'common/hyperos_webview_route.sh'), action],
                              env={**self.env, **extra}, capture_output=True, text=True, timeout=20)

    def mounts(self):
        log = self.root / 'mount.log'
        return log.read_text().splitlines() if log.exists() else []

    def journal(self):
        return self.module / 'config/hyperos-webview-route.conf'

    def test_stock_copy_route_gets_payload_latin_then_restores_exactly(self):
        result = self.run_route('ensure')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.router.read_bytes(), self.payload.read_bytes())
        clone = self.module / 'config/hyperos-webview-route/route.ttf'
        self.assertEqual(os.stat(self.router).st_ino, os.stat(clone).st_ino)
        self.assertIn(f'ro {self.router}', (self.root / 'ro.log').read_text())
        self.assertTrue(self.journal().is_file())
        self.assertEqual(self.run_route('owned').returncode, 0)
        # Payload itself is never the bind source (its label must stay intact).
        self.assertNotEqual(os.stat(self.router).st_ino, os.stat(self.payload).st_ino)
        restored = self.run_route('restore')
        self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assertEqual(self.router.read_bytes(), self.stock_bytes)
        self.assertFalse(self.journal().exists())
        self.assertFalse((self.module / 'config/hyperos-webview-route').exists())
        self.assertNotEqual(self.run_route('owned').returncode, 0)

    def test_second_ensure_in_same_boot_does_not_stack(self):
        self.assertEqual(self.run_route('ensure').returncode, 0)
        self.assertEqual(self.run_route('ensure').returncode, 0)
        self.assertEqual(sum(1 for line in self.mounts() if line.startswith('--bind')), 1)

    def test_theme_font_on_route_is_never_covered(self):
        theme = self.root / 'theme.ttf'
        make_font(theme, points=(*range(32, 127), HAN))
        self.router.write_bytes(theme.read_bytes())
        self.assertEqual(self.run_route('ensure').returncode, 2)
        self.assertEqual(self.router.read_bytes(), theme.read_bytes())
        self.assertEqual(self.mounts(), [])

    def test_framework_symlink_route_is_left_to_framework(self):
        self.router.unlink()
        misans = self.fonts / 'MiSansVF.ttf'
        make_font(misans, points=(*range(32, 127), HAN))
        self.router.symlink_to(misans)
        self.assertEqual(self.run_route('ensure').returncode, 2)
        self.assertTrue(self.router.is_symlink())
        self.assertEqual(self.mounts(), [])

    def test_unexpected_alias_link_text_is_ignored(self):
        self.alias.unlink()
        self.alias.symlink_to(self.root / 'elsewhere.ttf')
        self.assertEqual(self.run_route('ensure').returncode, 2)
        self.assertEqual(self.mounts(), [])

    def test_default_font_disable_or_remove_restores(self):
        self.assertEqual(self.run_route('ensure').returncode, 0)
        (self.module / 'config/active_font.conf').write_text('default\n')
        self.assertEqual(self.run_route('ensure').returncode, 2)
        self.assertEqual(self.router.read_bytes(), self.stock_bytes)
        self.assertFalse(self.journal().exists())
        (self.module / 'config/active_font.conf').write_text('safe-test\n')
        self.assertEqual(self.run_route('ensure').returncode, 0)
        (self.module / 'disable').write_text('')
        self.assertEqual(self.run_route('ensure').returncode, 2)
        self.assertEqual(self.router.read_bytes(), self.stock_bytes)

    def test_foreign_mount_is_neither_stacked_nor_popped(self):
        with self.mountinfo.open('a') as stream:
            stream.write(f'9 1 0:0 / {self.router} ro - bind none ro\n')
        self.assertEqual(self.run_route('ensure').returncode, 2)
        self.assertEqual(self.mounts(), [])
        self.assertEqual(self.run_route('restore').returncode, 0)
        self.assertEqual(self.mounts(), [])

    def test_restore_keeps_a_layer_installed_after_ours(self):
        self.assertEqual(self.run_route('ensure').returncode, 0)
        other = self.root / 'other.ttf'
        make_font(other, points=tuple(range(32, 100)))
        subprocess.run([str(self.bin / 'mount'), '--bind', str(other), str(self.router)],
                       env=self.env, check=True)
        result = self.run_route('restore')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.router.read_bytes(), other.read_bytes())
        self.assertTrue(self.journal().exists(), 'journal must survive a foreign top layer')

    def test_previous_boot_journal_is_discarded_without_unmount(self):
        self.assertEqual(self.run_route('ensure').returncode, 0)
        # Simulate reboot: kernel mounts vanish, router back to stock copy.
        subprocess.run([str(self.bin / 'umount'), str(self.router)], env=self.env, check=True)
        before = len(self.mounts())
        self.boot.write_text('boot-b\n')
        self.assertEqual(self.run_route('ensure').returncode, 0)
        new = self.mounts()[before:]
        self.assertFalse(any(line.startswith('umount') for line in new))
        self.assertTrue(self.journal().read_text().startswith('boot-b|'))

    def test_bind_failure_leaves_route_and_no_journal(self):
        result = self.run_route('ensure', FAIL_MOUNT='1')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.router.read_bytes(), self.stock_bytes)
        self.assertFalse(self.journal().exists())

    def test_legacy_payload_hook_runs_before_self_mount(self):
        script = f'''
. "$MODDIR/common/legacy_v14_4/hyperos_full_coverage.sh"
LUOSHU_HYPEROS_CLOCK_PAYLOAD_ROOT="$MODDIR/.luoshu-payload" \
LUOSHU_SYSTEM_FONTS_ROOT="{self.fonts}" LUOSHU_SYSTEM_EXT_FONTS_ROOT=/nonexistent \
LUOSHU_PRODUCT_FONTS_ROOT=/nonexistent LUOSHU_MI_EXT_FONTS_ROOT=/nonexistent \
luoshu_hyperos_full_payload_ensure
'''
        result = subprocess.run(['sh', '-c', script], env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.router.read_bytes(), self.payload.read_bytes())
        # The ROM link itself stays a link; the overlay payload never covers it.
        self.assertTrue(self.alias.is_symlink())
        subprocess.run(['sh', str(ROOT / 'common/hyperos_webview_route.sh'), 'restore'], env=self.env, check=True)
        (self.module / 'config/hyperos-webview-route.disable').write_text('')
        result = subprocess.run(['sh', '-c', script], env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.router.read_bytes(), self.stock_bytes)

    def link_router_to_theme(self, family='Roboto', points=None, relative=False, pad_to=0):
        """Device layout: theme_webview -> /data/system/theme/fonts/Roboto-Regular.ttf.

        pad_to grows the tiny fixture to a real font's size (trailing bytes keep
        the sfnt header), so it is not mistaken for the DEFAULT-theme placeholder.
        """
        self.theme_target.parent.mkdir(parents=True, exist_ok=True)
        make_named_font(self.theme_target, family, points or (*range(32, 127), 0xA9))
        size = self.theme_target.stat().st_size
        if pad_to > size:
            with self.theme_target.open('ab') as stream:
                stream.write(b'\0' * (pad_to - size))
        self.router.unlink()
        if relative:
            self.router.symlink_to('../../theme/fonts/Roboto-Regular.ttf')
        else:
            self.router.symlink_to(self.theme_target)
        return self.theme_target.read_bytes()

    def log_text(self):
        log = self.module / 'logs/fontswitch.log'
        return log.read_text() if log.exists() else ''

    def test_symlink_chain_to_theme_engine_roboto_binds_final_target(self):
        original = self.link_router_to_theme()
        self.assertNotEqual(original, self.stock_bytes, 'device file is not the ROM stock copy')
        result = self.run_route('ensure')
        self.assertEqual(result.returncode, 0, result.stderr + self.log_text())
        clone = self.module / 'config/hyperos-webview-route/route.ttf'
        self.assertTrue(self.router.is_symlink(), 'framework router link must stay a link')
        self.assertEqual(os.readlink(self.router), str(self.theme_target))
        self.assertEqual(os.stat(self.theme_target).st_ino, os.stat(clone).st_ino)
        self.assertEqual(self.alias.read_bytes(), self.payload.read_bytes())
        self.assertIn(f'ro {self.theme_target}', (self.root / 'ro.log').read_text())
        self.assertTrue(self.journal().read_text().startswith(f'boot-a|{self.theme_target}|'))
        self.assertIn('theme engine Roboto accepted', self.log_text())
        self.assertNotIn('router-is-symlink', self.log_text())
        self.assertEqual(self.run_route('owned').returncode, 0)
        self.assertEqual(self.run_route('ensure').returncode, 0)
        self.assertEqual(sum(1 for line in self.mounts() if line.startswith('--bind')), 1)
        restored = self.run_route('restore')
        self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assertEqual(self.theme_target.read_bytes(), original)
        self.assertTrue(self.router.is_symlink())
        self.assertFalse(self.journal().exists())

    def test_relative_chain_to_theme_target_is_matched_by_inode(self):
        self.link_router_to_theme(relative=True)
        self.assertEqual(self.run_route('ensure').returncode, 0, self.log_text())
        self.assertTrue(self.journal().read_text().startswith(f'boot-a|{self.theme_target}|'))
        self.assertEqual(self.theme_target.read_bytes(), self.payload.read_bytes())
        self.assertEqual(self.run_route('restore').returncode, 0)

    def test_stock_copy_in_theme_dir_is_accepted(self):
        self.link_router_to_theme()
        self.theme_target.write_bytes(self.stock_bytes)
        self.assertEqual(self.run_route('ensure').returncode, 0, self.log_text())
        self.assertEqual(self.theme_target.read_bytes(), self.payload.read_bytes())

    def test_user_theme_store_font_behind_chain_is_skipped_and_logged(self):
        original = self.link_router_to_theme(family='FancyThemeSans', points=(*range(32, 127), HAN),
                                             pad_to=200000)
        self.assertEqual(self.run_route('ensure').returncode, 2)
        self.assertEqual(self.theme_target.read_bytes(), original)
        self.assertEqual(self.mounts(), [])
        self.assertIn('skip theme-font-is-user-theme', self.log_text())
        self.assertFalse(self.journal().exists())

    def make_placeholder(self, size=8936, magic=b'\x00\x01\x00\x00'):
        """HyperOS DEFAULT-theme "empty font theme": tiny sfnt, nearly no glyphs."""
        self.link_router_to_theme()
        data = magic + bytes(range(256)) * ((size // 256) + 1)
        self.theme_target.write_bytes(data[:size])
        return self.theme_target.read_bytes()

    def test_tiny_placeholder_theme_font_is_accepted_and_logged(self):
        self.make_placeholder()
        self.assertEqual(self.run_route('ensure').returncode, 0, self.log_text())
        self.assertEqual(self.theme_target.read_bytes(), self.payload.read_bytes())
        self.assertIn('theme engine placeholder accepted', self.log_text())
        self.assertIn('size=8936', self.log_text())
        self.assertTrue(self.journal().read_text().startswith(f'boot-a|{self.theme_target}|'))

    def test_tiny_non_sfnt_theme_file_is_skipped(self):
        original = self.make_placeholder(magic=b'PK\x03\x04')
        self.assertEqual(self.run_route('ensure').returncode, 2)
        self.assertEqual(self.theme_target.read_bytes(), original)
        self.assertEqual(self.mounts(), [])
        self.assertNotIn('placeholder accepted', self.log_text())

    def test_large_non_roboto_theme_font_is_still_skipped(self):
        original = self.make_placeholder(size=200000)
        self.assertEqual(self.run_route('ensure').returncode, 2)
        self.assertEqual(self.theme_target.read_bytes(), original)
        self.assertEqual(self.mounts(), [])
        self.assertIn('skip theme-font-is-user-theme', self.log_text())
        self.assertNotIn('placeholder accepted', self.log_text())

    def test_oversized_roboto_named_theme_font_is_skipped(self):
        original = self.link_router_to_theme(pad_to=70000)
        result = self.run_route('ensure', LUOSHU_WEBVIEW_ROUTE_THEME_MAX_BYTES='100')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.theme_target.read_bytes(), original)
        self.assertEqual(self.mounts(), [])

    def test_chain_to_other_file_loop_or_foreign_mount_is_skipped(self):
        self.link_router_to_theme()
        with self.mountinfo.open('a') as stream:
            stream.write(f'9 1 0:0 / {self.theme_target} ro - bind none ro\n')
        self.assertEqual(self.run_route('ensure').returncode, 2)
        self.assertIn('skip target-already-mounted-by-other', self.log_text())
        self.mountinfo.write_text('1 0 0:0 / / rw - rootfs rootfs rw\n')
        # Any other final file (e.g. a user path) is never accepted.
        other = self.root / 'data/other/Roboto-Regular.ttf'
        other.parent.mkdir(parents=True)
        make_named_font(other, 'Roboto', tuple(range(32, 127)))
        self.router.unlink(); self.router.symlink_to(other)
        self.assertEqual(self.run_route('ensure').returncode, 2)
        self.assertIn('skip router-target-not-accepted', self.log_text())
        # Loop / too deep chain.
        a = self.root / 'data/loop-a'; b = self.root / 'data/loop-b'
        a.symlink_to(b); b.symlink_to(a)
        self.router.unlink(); self.router.symlink_to(a)
        self.assertEqual(self.run_route('ensure').returncode, 2)
        self.assertIn('skip router-chain-too-deep-or-broken', self.log_text())
        self.assertEqual(self.mounts(), [])

    def test_theme_bridge_does_not_stack_on_theme_target_bind(self):
        self.link_router_to_theme()
        self.assertEqual(self.run_route('ensure').returncode, 0)
        env = {k: v for k, v in self.env.items() if k != 'LUOSHU_WEBVIEW_ROUTE_THEME_TARGET'}
        theme = subprocess.run(
            ['sh', '-c', '. "$MODDIR/common/hyperos_theme_font_bridge.sh"; _htf_active'],
            env={**env, 'LUOSHU_THEME_FONT_ALIAS': str(self.alias),
                 'LUOSHU_THEME_FONT_ROUTER': str(self.router),
                 'LUOSHU_THEME_FONT_TARGET': str(self.theme_target)},
            capture_output=True, text=True, timeout=20)
        self.assertNotEqual(theme.returncode, 0, 'theme bridge must not stack on the early theme bind')

    def test_theme_bridge_and_cleanup_entrypoints_know_the_route(self):
        self.assertEqual(self.run_route('ensure').returncode, 0)
        theme = subprocess.run(
            ['sh', '-c', '. "$MODDIR/common/hyperos_theme_font_bridge.sh"; _htf_active'],
            env={**self.env, 'LUOSHU_THEME_FONT_ALIAS': str(self.alias),
                 'LUOSHU_THEME_FONT_ROUTER': str(self.router),
                 'LUOSHU_THEME_FONT_TARGET': str(self.root / 'theme/Roboto-Regular.ttf')},
            capture_output=True, text=True, timeout=20)
        self.assertNotEqual(theme.returncode, 0, 'theme bridge must not stack on the early route bind')
        self.assertIn('hyperos_webview_route.sh', (ROOT / 'uninstall.sh').read_text())
        service = (ROOT / 'common/google_font_provider_service.sh').read_text()
        restore = service[service.index('provider_restore() {'):service.index('# The boot entry')]
        self.assertIn('hyperos_webview_route.sh" restore', restore)


if __name__ == '__main__':
    unittest.main(verbosity=2)
