#!/usr/bin/env python3
"""Real bytes, namespace evidence and cache lifetime regression coverage."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('physical_verify', ROOT / 'common/physical_font_load_verify.py')
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


class PhysicalLoadTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        self.payload = self.module / '.luoshu-payload'
        self.visible = self.root / 'visible'
        self.logical = '/system/fonts/Test.ttf'
        self.data = b'A' * 65536 + b'original-middle' + b'Z' * 65536
        for root in (self.payload, self.visible):
            target = root / self.logical.lstrip('/')
            target.parent.mkdir(parents=True)
            target.write_bytes(self.data)
        (self.module / 'config').mkdir()
        (self.module / 'config/active_font.conf').write_text('mix\n')
        (self.module / 'config/self-mount.conf').write_text('state=mounted\n')
        (self.module / 'config/font-payload-boot.conf').write_text('state=confirmed\nfont=mix\n')
        self.write_manifest({self.logical: hashlib.sha256(self.data).hexdigest()})
        self.env = patch.dict(os.environ, LUOSHU_VISIBLE_ROOT=str(self.visible), LUOSHU_TEST_BOOT_ID='boot-a')
        self.env.start()
        self.addCleanup(self.env.stop)

    def write_manifest(self, files):
        (self.payload / verify.MANIFEST).write_text(json.dumps({'schema': 'inventory-font-output-v1', 'files': files}))

    def run_verify(self):
        result = verify.verify(self.module, self.payload, 'mix')
        verify.save_result(self.module, result, True)
        return result

    def test_complete_visible_bytes_and_metadata_only_cache(self):
        result = self.run_verify()
        self.assertEqual(result['state'], 'verified', result)
        self.assertEqual(result['files'][self.logical]['state'], 'verified')
        with patch.object(verify, 'digest', side_effect=AssertionError('status hashed a font')):
            self.assertEqual(verify.load_cached_verification(self.module, self.payload, 'mix')['state'], 'verified')

    def test_xml_inventory_font_without_standard_suffix_is_verified(self):
        from fontTools.fontBuilder import FontBuilder
        from fontTools.pens.ttGlyphPen import TTGlyphPen
        font = FontBuilder(1000, isTTF=True)
        font.setupGlyphOrder(['.notdef', 'A'])
        pen = TTGlyphPen(None)
        pen.moveTo((10, 0)); pen.lineTo((100, 700)); pen.lineTo((200, 0)); pen.closePath()
        font.setupGlyf({name: pen.glyph() for name in ('.notdef', 'A')})
        font.setupHorizontalMetrics({name: (500, 0) for name in ('.notdef', 'A')})
        font.setupHorizontalHeader(ascent=800, descent=-200)
        font.setupCharacterMap({65: 'A'})
        font.setupNameTable({'familyName': 'XML Fixture', 'styleName': 'Regular'})
        font.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
        font.setupPost()
        logical = '/system/fonts/OEMText.font'
        target = self.payload / logical.lstrip('/')
        font.save(target)
        (self.visible / logical.lstrip('/')).write_bytes(target.read_bytes())
        (self.module / 'config/stock-fonts.xml').write_text(
            '<familyset><family name="sans-serif"><font weight="400">OEMText.font</font></family></familyset>')
        (self.module / 'config/device_font_inventory.json').write_text(json.dumps({
            'schema': 'device-font-inventory-v1', 'slots': {logical: {
                'source': 'xml', 'format': 'TTF', 'families': ['sans-serif']}}}))
        self.write_manifest({logical: hashlib.sha256(target.read_bytes()).hexdigest()})
        result = self.run_verify()
        self.assertEqual(result['state'], 'verified', result)
        self.assertEqual(result['files'][logical]['state'], 'verified')
        self.assertEqual(verify.load_cached_verification(self.module, self.payload, 'mix')['state'], 'verified')
        with self.assertRaises(ValueError):
            verify.logical_path('/system/fonts/../../data/evil.font')

    def test_middle_corruption_cannot_be_overridden_by_mounted_flags(self):
        target = self.visible / self.logical.lstrip('/')
        target.write_bytes(b'A' * 65536 + b'CORRUPTED-MIDDL!' + b'Z' * 65536)
        result = self.run_verify()
        self.assertEqual(result['state'], 'failed', result)
        self.assertEqual(result['files'][self.logical]['reason'], 'runtime-visible-digest-mismatch')
        self.assertEqual((self.payload / self.logical.lstrip('/')).read_bytes(), self.data)
        self.assertEqual((self.module / 'config/active_font.conf').read_text(), 'mix\n')

    def test_payload_corruption_is_not_success_even_when_visible_matches_it(self):
        for root in (self.payload, self.visible):
            (root / self.logical.lstrip('/')).write_bytes(b'changed-font')
        result = self.run_verify()
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(result['files'][self.logical]['reason'], 'payload-digest-mismatch')

    def test_upgrade_reapply_marker_blocks_old_payload_success_and_cache(self):
        self.run_verify()
        marker = self.module / 'config/font-payload-rebuild-pending.conf'
        for reason in ('font-builder-changed', 'schema-upgrade', 'unknown-upgrade'):
            marker.write_text(f'font=mix\nreason={reason}\n')
            with patch.object(verify, 'digest', side_effect=AssertionError('old payload deep hashed')):
                result = self.run_verify()
            self.assertEqual(result['state'], 'pending')
            self.assertEqual(result['reason'], 'font-payload-reapply-required')
            self.assertEqual(verify.load_cached_verification(self.module, self.payload, 'mix')['state'], 'pending')
            self.assertTrue(marker.is_file())
        marker.write_text('font=mix\nreason=coverage-remediate\n')
        self.assertEqual(self.run_verify()['state'], 'verified')
        marker.write_text('font=Other\nreason=font-builder-changed\n')
        self.assertEqual(self.run_verify()['state'], 'verified')

    def test_prepared_next_boot_never_verifies_previous_live_bytes(self):
        (self.module / '.luoshu-payload-next').mkdir()
        (self.module / 'config/font-payload-next.conf').write_text('state=prepared\nfont=mix\n')
        with patch.object(verify, 'digest', side_effect=AssertionError('verified old live payload')):
            result = self.run_verify()
        self.assertEqual(result['state'], 'pending')
        self.assertEqual(result['reason'], 'prepared-payload-awaiting-reboot')

    def test_legacy_unbound_verified_flag_is_not_reused(self):
        (self.module / 'config/device-font-load-verification.conf').write_text(
            'state=verified\nmode=mount-confirmed\nactiveFont=mix\n')
        self.assertEqual(verify.load_cached_verification(self.module, self.payload, 'mix')['state'], 'pending')

    def test_no_runtime_namespace_cannot_be_verified_by_private_su_view(self):
        with patch.object(verify, 'runtime_namespaces', return_value=[]):
            result = self.run_verify()
        self.assertEqual(result['state'], 'pending')
        self.assertEqual(result['files'][self.logical]['state'], 'unconfirmed')

    def test_all_runtime_namespaces_must_match(self):
        other = self.root / 'zygote'
        path = other / self.logical.lstrip('/')
        path.parent.mkdir(parents=True)
        path.write_bytes(b'old-default-font')
        roots = verify.runtime_namespaces() + [{'kind': 'explicit', 'root': str(other), 'identity': verify.identity(other)[:2]}]
        with patch.object(verify, 'runtime_namespaces', return_value=roots):
            result = self.run_verify()
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(len(result['files'][self.logical]['observations']), 2)

    def test_cached_success_expires_on_boot_active_manifest_or_visible_change(self):
        self.run_verify()
        with patch.dict(os.environ, LUOSHU_TEST_BOOT_ID='boot-b'):
            self.assertEqual(verify.load_cached_verification(self.module, self.payload, 'mix')['state'], 'pending')
        self.assertEqual(verify.load_cached_verification(self.module, self.payload, 'different')['state'], 'pending')
        manifest = self.payload / verify.MANIFEST
        original = manifest.read_text()
        manifest.write_text(original + '\n')
        self.assertEqual(verify.load_cached_verification(self.module, self.payload, 'mix')['state'], 'pending')
        manifest.write_text(original)
        (self.visible / self.logical.lstrip('/')).write_bytes(b'changed')
        self.assertEqual(verify.load_cached_verification(self.module, self.payload, 'mix')['state'], 'pending')

    def test_aliases_and_visible_bind_inode_hash_only_once(self):
        second = '/product/fonts/Alias.ttf'
        source = self.payload / self.logical.lstrip('/')
        for root in (self.payload, self.visible):
            alias = root / second.lstrip('/')
            alias.parent.mkdir(parents=True)
            os.link(source, alias)
        target = self.visible / self.logical.lstrip('/')
        target.unlink()
        os.link(source, target)
        self.write_manifest({name: hashlib.sha256(self.data).hexdigest() for name in (self.logical, second)})
        original_open = Path.open
        reads = []
        def count_open(path, *args, **kwargs):
            if args and args[0] == 'rb' and path.suffix == '.ttf':
                reads.append(path)
            return original_open(path, *args, **kwargs)
        with patch.object(Path, 'open', count_open):
            result = self.run_verify()
        self.assertEqual(result['state'], 'verified')
        self.assertEqual(len(reads), 1, reads)

    def test_boot_cleanup_respects_foreground_lock_generation_and_stages(self):
        common = self.module / 'common'
        binary = common / 'python/bin/luoshu-python'
        binary.parent.mkdir(parents=True)
        binary.write_text('#!/bin/sh\nunset PYTHONHOME\nexec python3 "$@"\n')
        binary.chmod(0o755)
        for name in ('physical_font_load_verify.py', 'font_switch_lock.sh'):
            (common / name).write_text((ROOT / 'common' / name).read_text())
        verifier = (ROOT / 'common/device_font_load_verify.sh').read_text()
        (self.module / 'service.sh').write_text((ROOT / 'service.sh').read_text())
        (self.module / 'config/font_runtime_legacy_v14_4.conf').write_text('font=mix\n')
        commands = self.root / 'bin'
        commands.mkdir()
        getprop = commands / 'getprop'
        getprop.write_text('#!/bin/sh\necho 1\n')
        getprop.chmod(0o755)
        env = dict(os.environ, PATH=str(commands) + os.pathsep + os.environ['PATH'])
        cases = {
            'stable': '',
            'busy': '',
            'selection-changed': 'echo Other > "$MODDIR/config/active_font.conf"',
            'generation-changed': 'echo requestId=new > "$MODDIR/config/font-payload-activated.conf"',
            'prepared-next': 'mkdir -p "$MODDIR/.luoshu-payload-next"; printf "state=prepared\\nfont=mix\\n" > "$MODDIR/config/font-payload-next.conf"',
        }
        for name, change in cases.items():
            with self.subTest(name=name):
                (self.module / 'config/active_font.conf').write_text('mix\n')
                (self.module / 'config/font-payload-activated.conf').write_text('requestId=original\n')
                retired = self.module / '.luoshu-retired'
                retired.mkdir(exist_ok=True)
                (retired / 'saved').write_text('retain when busy or changed')
                stage = self.module / '.luoshu-payload-stage.concurrent'
                stage.mkdir(exist_ok=True)
                (stage / 'building').write_text('never delete another transaction')
                lock = self.module / '.font_switch.lock'
                if name == 'busy':
                    lock.mkdir()
                    (lock / 'pid').write_text(str(os.getpid()) + '\n')
                tail = '\n_saved_verify_rc=$?\n'
                if change:
                    tail += '[ "$1" != verify ] || { ' + change + '; }\n'
                tail += 'exit "$_saved_verify_rc"\n'
                (common / 'device_font_load_verify.sh').write_text(verifier + tail)
                done = subprocess.run(['sh', str(self.module / 'service.sh')], env=env,
                                      capture_output=True, text=True, timeout=5)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertTrue((stage / 'building').is_file())
                self.assertEqual(retired.exists(), name != 'stable')
                if name == 'busy':
                    self.assertEqual((lock / 'pid').read_text(), str(os.getpid()) + '\n')
                    (lock / 'pid').unlink()
                    lock.rmdir()
                else:
                    self.assertFalse(lock.exists(), 'service leaked cleanup lock')

    def test_physical_boot_service_retains_payload_on_visible_mismatch(self):
        common = self.module / 'common'
        binary = common / 'python/bin/luoshu-python'
        binary.parent.mkdir(parents=True)
        binary.write_text('#!/bin/sh\nunset PYTHONHOME\nexec python3 "$@"\n')
        binary.chmod(0o755)
        for name in ('physical_font_load_verify.py', 'device_font_load_verify.sh'):
            (common / name).write_text((ROOT / 'common' / name).read_text())
        (self.module / 'service.sh').write_text((ROOT / 'service.sh').read_text())
        (self.module / 'config/font_runtime_legacy_v14_4.conf').write_text('font=mix\n')
        (self.module / 'config/text_reboot_required.conf').write_text('font=mix\n')
        retired = self.module / '.luoshu-retired'
        retired.mkdir()
        (retired / 'previous-font').write_text('retain rollback copy')
        (self.visible / self.logical.lstrip('/')).write_bytes(b'original-default-font')
        commands = self.root / 'bin'
        commands.mkdir()
        getprop = commands / 'getprop'
        getprop.write_text('#!/bin/sh\necho 1\n')
        getprop.chmod(0o755)
        env = dict(os.environ, PATH=str(commands) + os.pathsep + os.environ['PATH'])
        done = subprocess.run(['sh', str(self.module / 'service.sh')], env=env,
                              capture_output=True, text=True, timeout=5)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('state=failed', (self.module / 'config/device-font-load-verification.conf').read_text())
        self.assertTrue((retired / 'previous-font').is_file())
        self.assertTrue((self.module / 'config/text_reboot_required.conf').is_file())
        self.assertEqual((self.payload / self.logical.lstrip('/')).read_bytes(), self.data)
        self.assertEqual((self.module / 'config/active_font.conf').read_text(), 'mix\n')

    def test_shell_entry_uses_strict_helper_and_status_never_full_hashes(self):
        common = self.module / 'common'
        binary = common / 'python/bin/luoshu-python'
        binary.parent.mkdir(parents=True)
        binary.write_text('#!/bin/sh\nunset PYTHONHOME\nexec python3 "$@"\n')
        binary.chmod(0o755)
        for name in ('physical_font_load_verify.py', 'device_font_load_verify.sh'):
            (common / name).write_text((ROOT / 'common' / name).read_text())
        env = dict(os.environ, MODDIR=str(self.module), MODULE_DIR=str(self.module))
        script = common / 'device_font_load_verify.sh'
        passed = subprocess.run(['sh', str(script), 'verify'], env=env, capture_output=True, text=True)
        self.assertEqual(passed.returncode, 0, passed.stderr)
        state = self.module / 'config/device-font-load-verification.conf'
        self.assertIn('state=verified', state.read_text())
        (self.visible / self.logical.lstrip('/')).write_bytes(b'default')
        stale = subprocess.run(['sh', str(script), 'status'], env=env, capture_output=True, text=True)
        self.assertEqual(stale.returncode, 2, stale.stderr)
        self.assertIn('state=pending', state.read_text())
        failed = subprocess.run(['sh', str(script), 'verify'], env=env, capture_output=True, text=True)
        self.assertEqual(failed.returncode, 1, failed.stderr)
        self.assertIn('state=failed', state.read_text())


if __name__ == '__main__':
    unittest.main()
