#!/usr/bin/env python3
"""Exercise display reset, upgrade codes, tag separation and real release helpers."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from release_version_policy import version_info, read_properties
from sync_update_metadata import build_metadata, advance_fallback_channel


class RefactorVersionTest(unittest.TestCase):
    def test_requested_sequence(self):
        versions = ['v1.0.0', 'v1.1.1', 'v2.0.0', 'v2.2.2', 'v3.0.0', 'v3.3.3', 'v4.0.0']
        for current, following in zip(versions, versions[1:]):
            self.assertEqual(version_info(current, 'refactor')['nextStable'], following)

    def test_display_reset_is_an_upgrade_from_both_delivered_versions(self):
        info = version_info('v1.0.0', 'refactor')
        self.assertEqual(info['version'], 'v1.0.0')
        self.assertEqual(info['versionCode'], 60000)
        self.assertEqual(info['appVersionCode'], 6000001)
        for old in ('v4.4.4', 'v5.0.0-Beta1'):
            self.assertGreater(info['versionCode'], version_info(old)['versionCode'])
            self.assertGreater(info['appVersionCode'], version_info(old)['appVersionCode'])

    def test_future_codes_strictly_increase(self):
        codes = [version_info(v, 'refactor')['versionCode'] for v in ('v1.0.0','v1.1.1','v2.0.0','v2.2.2','v3.0.0','v3.3.3')]
        self.assertEqual(codes, [60000, 60101, 70000, 70202, 80000, 80303])
        self.assertTrue(all(a < b for a, b in zip(codes, codes[1:])))

    def test_refactor_tags_and_notes_never_overwrite_legacy(self):
        for version in ('v1.0.0', 'v4.0.0', 'v4.4.4'):
            old, new = version_info(version), version_info(version, 'refactor')
            self.assertNotEqual(old['tag'], new['tag'])
            self.assertNotEqual(old['notesFile'], new['notesFile'])
            self.assertEqual(new['tag'], 'refactor-' + version)

    def test_old_version_scheme_is_unchanged(self):
        self.assertEqual(version_info('v4.4.4')['versionCode'], 40404)
        self.assertEqual(version_info('v5.0.0-Beta1')['versionCode'], 50000)
        self.assertEqual(version_info('v4.4.4')['tag'], 'v4.4.4')

    def test_unknown_series_or_malformed_or_unrequested_number_rejected(self):
        for series, version in [('other','v1.0.0'), ('refactor','v1.0.1'), ('refactor','v2.1.1'), ('refactor','v0.0.0'), ('refactor','v01.0.0'), ('refactor','v1.0.0;echo bad'), ('refactor','v1.0'), ('','v1.100.0'), ('','v999999.0.0')]:
            with self.subTest(series=series, version=version):
                with self.assertRaises(ValueError):
                    version_info(version, series)

    def test_stable_is_not_accidentally_marked_prerelease(self):
        self.assertFalse(version_info('v1.0.0', 'refactor')['prerelease'])
        self.assertTrue(version_info('v1.0.0-Beta1', 'refactor')['prerelease'])

    def test_cli_rejects_reset_internal_code(self):
        with tempfile.TemporaryDirectory() as d:
            prop=Path(d)/'module.prop'
            prop.write_text('version=v1.0.0\nversionCode=10000\nversionSeries=refactor\n')
            result=subprocess.run([sys.executable,str(ROOT/'scripts/release_version_policy.py'),'--module',str(prop),'--check'],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('60000',result.stderr)

    def test_duplicate_version_fields_are_not_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            prop=Path(d)/'module.prop'
            prop.write_text('version=v1.0.0\nversion=v2.0.0\n')
            with self.assertRaises(ValueError):
                read_properties(prop)

    def test_repository_properties_match_policy_and_real_shell_helper(self):
        props=read_properties(ROOT/'module.prop')
        info=version_info(props['version'],props.get('versionSeries',''))
        self.assertEqual(int(props['versionCode']),info['versionCode'])
        policy=json.loads((ROOT/'config/stable_version_policy.json').read_text())
        self.assertEqual(policy['currentStable'],info['version'])
        self.assertEqual(policy['nextStable'],info['nextStable'])
        result=subprocess.run(['sh','-c','. ./scripts/version.sh; printf "%s|%s|%s|%s" "$LUOSHU_VERSION" "$LUOSHU_RELEASE_TAG" "$LUOSHU_RELEASE_NOTES" "$LUOSHU_APP_VERSION_CODE"'],cwd=ROOT,capture_output=True,text=True,check=True)
        self.assertEqual(result.stdout,f"{info['version']}|{info['tag']}|{info['notesFile']}|{info['appVersionCode']}")
        self.assertTrue((ROOT/info['notesFile']).is_file())
        self.assertNotIn('<!-- prerelease -->',(ROOT/info['notesFile']).read_text())

    def test_metadata_uses_refactor_assets_and_advances_both_old_channels(self):
        info=version_info('v1.0.0','refactor')
        metadata=build_metadata(repository='xgl34222220-ops/LuoShu',version=info['version'],version_code=info['versionCode'],tag=info['tag'],notes_file=info['notesFile'])
        self.assertIn('/refactor-v1.0.0/LuoShu-v1.0.0.zip',metadata['zipUrl'])
        self.assertIn('/refactor-v1.0.0/RELEASE_NOTES_refactor-v1.0.0.md',metadata['changelog'])
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'update.json'
            for old in (40404,50000):
                p.write_text(json.dumps({'version':'v5.0.0-Beta1','versionCode':old}))
                self.assertTrue(advance_fallback_channel(metadata,p))
                self.assertEqual(json.loads(p.read_text()),metadata)
            p.write_text(json.dumps({'version':'v1.1.1','versionCode':60101}))
            self.assertFalse(advance_fallback_channel(metadata,p))

    def test_actual_readiness_gate_recognizes_epoch(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(['sh','scripts/pre_release_readiness.sh','--target','v1.0.0','--enforce','--output',d],cwd=ROOT,check=True,capture_output=True,text=True)
            report=json.loads((Path(d)/'readiness.json').read_text())
            self.assertEqual(next(x for x in report['checks'] if x['id']=='version-code')['severity'],'ready')


if __name__ == '__main__':
    unittest.main(verbosity=2)
