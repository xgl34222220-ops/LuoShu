#!/usr/bin/env python3
"""Exercise real APK packaging metadata gates with an isolated SDK analyzer."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = 'io.github.xgl34222220.luoshu'

class ApkMetadataTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='luoshu-apk-metadata-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'module'
        self.bin = Path(self.temp.name) / 'bin'
        self.bin.mkdir(); (self.root / 'scripts').mkdir(parents=True)
        for name in ('build.sh', 'version.sh', 'release_version_policy.py'):
            shutil.copyfile(ROOT / 'scripts' / name, self.root / 'scripts' / name)
        shutil.copyfile(ROOT / 'module.prop', self.root / 'module.prop')
        props = dict(line.split('=', 1) for line in (self.root / 'module.prop').read_text().splitlines() if '=' in line)
        self.code = int(props['versionCode']) * 100 + 1
        self.zip = self.root / 'dist' / ('LuoShu-' + props['version'] + '.zip')
        for name in ('scripts/check.sh', 'scripts/prune_python_runtime.sh', 'customize.sh',
                     'common/helper.sh', 'common/python/bin/luoshu-python', 'system/bin/luoshud'):
            path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('#!/bin/sh\nexit 0\n')
        (self.root / 'scripts/module_payload_manifest.txt').write_text('module.prop\ncustomize.sh\ncommon\nsystem\n')
        for name in ('sh', 'dirname', 'basename', 'sed', 'head', 'python3', 'rm', 'mkdir', 'cp',
                     'sha256sum', 'awk', 'chmod', 'find', 'grep', 'zip', 'unzip', 'wc', 'tr'):
            command = shutil.which(name); self.assertIsNotNone(command)
            (self.bin / name).symlink_to(command)
        self.apk = Path(self.temp.name) / 'candidate.apk'
        self.calls = Path(self.temp.name) / 'calls'
        self.apk.write_text(f'package={PACKAGE}\nversionCode={self.code}\n')
        self.analyzer = self.bin / 'apkanalyzer'
        self.analyzer.write_text('''#!/bin/sh
printf '%s\\n' "$*" >> "$MOCK_CALLS"
[ "$1" = manifest ] && [ "$2" != "$MOCK_FAIL" ] || exit 9
case "$2" in
 application-id) sed -n 's/^package=//p' "$3" ;;
 version-code) sed -n 's/^versionCode=//p' "$3" ;;
 *) exit 9 ;;
esac
''')
        self.analyzer.chmod(0o755)

    def build(self, *, package='', code='', fail=''):
        env = {key: value for key, value in os.environ.items() if not key.startswith('LUOSHU_')}
        env.update(PATH=str(self.bin), LUOSHU_APP_APK=str(self.apk), LUOSHU_APP_PACKAGE=package,
                   LUOSHU_APP_VERSION_CODE=str(code), MOCK_FAIL=fail, MOCK_CALLS=str(self.calls))
        return subprocess.run([str(self.bin / 'sh'), str(self.root / 'scripts/build.sh')], cwd=self.root,
                              env=env, capture_output=True, text=True, timeout=15)

    def reject(self, result, code):
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertFalse(self.zip.exists()); self.assertFalse((self.root / 'dist/LuoShu').exists())

    def test_wrong_actual_code_cannot_be_hidden_by_environment(self):
        self.apk.write_text(f'package={PACKAGE}\nversionCode={self.code - 100}\n')
        self.reject(self.build(package=PACKAGE, code=self.code), 67)
        self.assertEqual(len(self.calls.read_text().splitlines()), 2)

    def test_wrong_actual_code_without_assertion(self):
        self.apk.write_text(f'package={PACKAGE}\nversionCode={self.code - 100}\n')
        self.reject(self.build(), 67)

    def test_assertions_are_compared_to_actual_fields(self):
        self.reject(self.build(code=self.code - 100), 67)
        self.reject(self.build(package='io.example.wrong'), 68)

    def test_wrong_actual_package_cannot_be_hidden(self):
        self.apk.write_text(f'package=io.example.wrong\nversionCode={self.code}\n')
        self.reject(self.build(package=PACKAGE, code=self.code), 68)

    def test_failed_analyzer_does_not_use_assertions(self):
        for field in ('application-id', 'version-code'):
            with self.subTest(field=field): self.reject(self.build(package=PACKAGE, code=self.code, fail=field), 66)

    def test_invalid_actual_fields_are_rejected(self):
        for package, code in ((PACKAGE, ''), (PACKAGE, 'invalid'), ('', str(self.code))):
            with self.subTest(package=package, code=code):
                self.apk.write_text(f'package={package}\nversionCode={code}\n')
                self.reject(self.build(package=PACKAGE, code=self.code), 66)

    def test_correct_actual_metadata_is_packaged(self):
        result = self.build(package=PACKAGE, code=self.code)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(self.calls.read_text().splitlines()), 2)
        with zipfile.ZipFile(self.zip) as archive:
            self.assertEqual(archive.read('bundled/LuoShu-App.apk'), self.apk.read_bytes())
            props = archive.read('bundled/app.prop').decode()
            self.assertIn(f'package={PACKAGE}\n', props); self.assertIn(f'versionCode={self.code}\n', props)

    def test_no_analyzer_supports_explicit_metadata(self):
        self.analyzer.unlink()
        result = self.build(package=PACKAGE, code=self.code)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_no_analyzer_expected_default_remains_supported(self):
        self.analyzer.unlink()
        result = self.build(package=PACKAGE)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_no_analyzer_rejects_wrong_asserted_code(self):
        self.analyzer.unlink(); self.reject(self.build(package=PACKAGE, code=self.code - 100), 67)

if __name__ == '__main__': unittest.main()
