#!/usr/bin/env python3
"""Fixed-composite intent is explicit, hash-bound, and distinct from VF claims."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'common'), str(ROOT / 'scripts')]
import font_source_profile as profile
import universal_mixed_font as mixed
from universal_mixed_variable_test import make_master


def write_conf(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(f'{key}={value}\n' for key, value in values.items()))


class FixedSelectionTest(unittest.TestCase):
    def setUp(self):
        self.context = tempfile.TemporaryDirectory()
        self.root = Path(self.context.name)
        self.module = self.root / 'module'
        self.source = self.module / 'cache/generated/composite.ttf'
        self.source.parent.mkdir(parents=True)
        make_master(self.source, 400)
        self.request = 'fixed-selection-request'
        self.state = {'requestId': self.request, 'cjk': 'Han Source', 'latin': 'Latin Source', 'digit': 'Digit Source',
                      'cjkAxes': 'wght=400', 'latinAxes': 'wght=600,wdth=95', 'digitAxes': 'wght=500'}
        self.generation = dict(self.state, compositeHash=mixed.digest(self.source))
        self.save_state()

    def tearDown(self):
        self.context.cleanup()

    def save_state(self):
        write_conf(self.module / 'config/mix-stage-next.conf', self.state)
        write_conf(self.module / '.luoshu-mix-stage/.luoshu-mix-generation.conf', self.generation)

    def freeze(self):
        destination = mixed.freeze(self.module, self.request, 'fixed', self.source)
        return destination / 'fonts/LuoShuMix-Regular.ttf', destination / 'source.json'

    def reports(self):
        root = self.module / 'cache/axes-current'
        (root / 'fonts').mkdir(parents=True)
        write_conf(self.module / 'config/axes_task.conf', dict(self.state, root=root))
        reports = {}
        for role, internal in zip(('cjk', 'latin', 'digit'), ('LuoShuMixCJK', 'LuoShuMixLatin', 'LuoShuMixDigit')):
            component = root / 'fonts' / f'{internal}-Regular.ttf'
            shutil.copyfile(self.source, component)
            self.generation[role + 'Hash'] = mixed.digest(component)
            report_path = Path(str(component) + '.json')
            report = {'status': 'ok', 'role': role, 'output': str(component),
                      'size': component.stat().st_size, 'variable': True,
                      'location': mixed.selected_axes(self.state[role + 'Axes']), 'ignoredAxes': []}
            report_path.write_text(json.dumps(report))
            reports[role] = report_path
        self.save_state()
        return reports

    def edit_report(self, path, callback):
        data = json.loads(path.read_text())
        callback(data)
        path.write_text(json.dumps(data))

    def test_explicit_fixed_policy_and_profile_identity(self):
        font, report = self.freeze()
        generic = profile.build([font])
        annotated = profile.build([font], mixed_selection=report)
        self.assertNotEqual(generic['profileId'], annotated['profileId'])
        self.assertNotIn('mixedSelection', generic['files'][0]['faces'][0])
        metadata = annotated['files'][0]['faces'][0]['mixedSelection']
        self.assertEqual(metadata['policy'], 'fixed-composite-selection-v1')
        self.assertEqual(metadata['requestId'], self.request)
        self.assertEqual(metadata['fontSha256'], mixed.digest(font))
        self.assertEqual(metadata['fontPath'], str(font.resolve()))
        self.assertEqual(metadata['roles']['latin']['selectedAxes'], {'wght': 600, 'wdth': 95})
        self.assertEqual(metadata['roles']['latin']['axisProvenance'], 'generation-hash-only')
        self.assertEqual(metadata['roles']['latin']['effectiveAxes'], {})
        self.assertEqual(annotated['files'][0]['faces'][0]['style']['weight'], 400)
        self.assertFalse(annotated['files'][0]['faces'][0]['variation']['variable'])
        profile.validate(annotated)

    def test_matching_reports_prove_actual_axes_and_components(self):
        self.reports()
        font, report = self.freeze()
        annotated = profile.build([font], mixed_selection=report)
        for role, entry in annotated['files'][0]['faces'][0]['mixedSelection']['roles'].items():
            self.assertEqual(entry['axisProvenance'], 'verified-instance-report')
            self.assertEqual(entry['effectiveAxes'], mixed.selected_axes(self.state[role + 'Axes']))
            self.assertEqual(entry['componentSha256'], self.generation[role + 'Hash'])

    def test_static_component_weight_is_not_invented_axis_position(self):
        self.state['latinAxes'] = 'wght=400'
        reports = self.reports()
        from fontTools.ttLib import TTFont
        for role, report in reports.items():
            component = Path(str(report)[:-5])
            with TTFont(component) as font:
                font['OS/2'].usWeightClass = 600
                font.save(component)
            self.generation[role + 'Hash'] = mixed.digest(component)
            report.unlink()
        self.save_state()
        font, report = self.freeze()
        annotated = profile.build([font], mixed_selection=report)
        entry = annotated['files'][0]['faces'][0]['mixedSelection']['roles']['latin']
        self.assertEqual(entry['selectedAxes'], {'wght': 400})
        self.assertEqual(entry['effectiveAxes'], {})
        self.assertEqual(entry['componentWeightClass'], 600)
        self.assertEqual(entry['axisProvenance'], 'static-component')

    def test_clamped_axes_rejected(self):
        reports = self.reports()
        self.edit_report(reports['latin'], lambda report: report['location'].__setitem__('wght', 550))
        with self.assertRaisesRegex(ValueError, 'range does not cover'):
            self.freeze()

    def test_ignored_axes_rejected(self):
        reports = self.reports()
        self.edit_report(reports['latin'], lambda report: report.__setitem__('ignoredAxes', ['wdth']))
        with self.assertRaisesRegex(ValueError, 'unsupported selected'):
            self.freeze()

    def test_component_tamper_rejected(self):
        reports = self.reports()
        component = Path(str(reports['cjk'])[:-5])
        component.write_bytes(component.read_bytes() + b'tampered')
        with self.assertRaisesRegex(ValueError, 'generation hash mismatch'):
            self.freeze()

    def test_generation_and_request_rejected(self):
        self.generation['compositeHash'] = 'a' * 64
        self.save_state()
        with self.assertRaisesRegex(ValueError, 'generation hash mismatch'):
            self.freeze()
        self.generation['compositeHash'] = mixed.digest(self.source)
        self.generation['requestId'] = 'stale'
        self.save_state()
        with self.assertRaisesRegex(ValueError, 'generation identity'):
            self.freeze()

    def test_frozen_font_tamper_and_equal_content_wrong_path_rejected(self):
        font, report = self.freeze()
        other = self.root / 'copied.ttf'
        other.write_bytes(font.read_bytes())
        with self.assertRaisesRegex(profile.ProfileError, '匹配的冻结字体'):
            profile.build([other], mixed_selection=report)
        font.write_bytes(font.read_bytes() + b'tampered')
        with self.assertRaisesRegex(profile.ProfileError, '内容已变化'):
            profile.build([font], mixed_selection=report)

    def test_profile_metadata_mutation_invalidates_identity(self):
        font, report = self.freeze()
        annotated = profile.build([font], mixed_selection=report)
        for mutation in ('request', 'axes', 'hash', 'mode', 'missing-role'):
            candidate = copy.deepcopy(annotated)
            metadata = candidate['files'][0]['faces'][0]['mixedSelection']
            if mutation == 'request':
                metadata['requestId'] = 'another-request'
            elif mutation == 'axes':
                metadata['roles']['cjk']['selectedAxes']['wght'] = 500
            elif mutation == 'hash':
                metadata['fontSha256'] = 'a' * 64
            elif mutation == 'mode':
                metadata['roles']['cjk']['mode'] = 'auto'
            else:
                del metadata['roles']['cjk']
            with self.assertRaises(profile.ProfileError, msg=mutation):
                profile.validate(candidate)

    def test_selection_only_attaches_to_matching_face(self):
        font, report = self.freeze()
        other = self.root / 'other.ttf'
        make_master(other, 700)
        annotated = profile.build([font, other], mixed_selection=report)
        self.assertIn('mixedSelection', annotated['files'][0]['faces'][0])
        self.assertNotIn('mixedSelection', annotated['files'][1]['faces'][0])

    def test_variable_font_cannot_claim_fixed_policy(self):
        from fontTools.fontBuilder import FontBuilder
        from fontTools.ttLib import TTFont
        with TTFont(self.source) as font:
            builder = FontBuilder(font=font)
            builder.setupFvar([('wght', 100, 400, 900, 'Weight')], [])
            builder.setupGvar({name: [] for name in font.getGlyphOrder()})
            font.save(self.source)
        self.generation['compositeHash'] = mixed.digest(self.source)
        self.save_state()
        font, report = self.freeze()
        with self.assertRaisesRegex(profile.ProfileError, '可变字体'):
            profile.build([font], mixed_selection=report)

    def test_report_path_escape_and_auto_report_rejected(self):
        font, report = self.freeze()
        saved = report.read_text()
        data = json.loads(saved)
        data['mixedSelection']['fontPath'] = '../../generated/composite.ttf'
        report.write_text(json.dumps(data))
        with self.assertRaisesRegex(profile.ProfileError, '路径无效'):
            profile.build([font], mixed_selection=report)
        data = json.loads(saved)
        data['mode'] = 'auto'
        report.write_text(json.dumps(data))
        with self.assertRaisesRegex(profile.ProfileError, '格式无效'):
            profile.build([font], mixed_selection=report)

    def test_symlinked_font_directory_cannot_escape_frozen_source(self):
        font, report = self.freeze()
        external = self.root / 'outside-fonts'
        font.parent.rename(external)
        font.parent.symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(profile.ProfileError, '越出冻结目录'):
            profile.build([font], mixed_selection=report)

    def test_cli_and_shell_explicit_environment_only(self):
        font, report = self.freeze()
        output = self.root / 'profile.json'
        proc = subprocess.run([sys.executable, str(ROOT / 'common/font_source_profile.py'), '--font', str(font), '--output', str(output), '--mixed-selection', str(report)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn('mixedSelection', json.loads(output.read_text())['files'][0]['faces'][0])
        (self.module / 'common').symlink_to(ROOT / 'common', target_is_directory=True)
        env = dict(os.environ, MODDIR=str(self.module), LUOSHU_PUBLIC_DIR=str(font.parent.parent), LUOSHU_PYTHON=sys.executable)
        env.pop('LUOSHU_MIX_SELECTION_FILE', None)
        shell = ['sh', str(ROOT / 'common/font_source_profile.sh')]
        for explicit in (False, True):
            if explicit:
                env['LUOSHU_MIX_SELECTION_FILE'] = str(report)
            proc = subprocess.run([*shell, 'family', 'LuoShuMix'], env=env, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            cached = subprocess.check_output([*shell, 'path', 'LuoShuMix'], env=env, text=True).strip()
            face = json.loads(Path(cached).read_text())['files'][0]['faces'][0]
            self.assertEqual('mixedSelection' in face, explicit)


if __name__ == '__main__':
    unittest.main(verbosity=2)
