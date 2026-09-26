#!/usr/bin/env python3
"""Real-font regression for fifteen active slots becoming eleven on repair.

The fixture models the capability reduction, not an assertion about one phone's
unavailable logs. Repair must preserve active coverage; a deliberate full font
change is a separate operation and may legitimately have different capability.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
import unittest

from coverage_inventory_integration_test import CoverageFixture, LATIN, ROOT, text_font

GREEK = set(range(0x391, 0x3aa)) - {0x3a2}
CYRILLIC = set(range(0x410, 0x430))
BASE = [f"/system/fonts/Interface-{index:02d}.ttf" for index in range(11)]
EXTRA = [f"/product/nested/fonts/Multiscript-{index}.ttf" for index in range(4)]
ALL = BASE + EXTRA


class FifteenSlotFixture(CoverageFixture):
    def __init__(self):
        super().__init__()
        shutil.rmtree(self.stock)
        for logical in ALL:
            points = LATIN | GREEK | CYRILLIC if logical in EXTRA else LATIN
            text_font(self.stock / logical.lstrip('/'), points=points,
                      weight=700 if logical in EXTRA else 400,
                      family='Unknown stock UI', ascent=980, descent=-240)
        for path in self.config.glob('device_font_*'):
            if path.is_file():
                path.unlink()
        text_font(self.source, points=LATIN | GREEK | CYRILLIC, advance=660)
        self.scan()
        self.write_mix_source(LATIN | GREEK | CYRILLIC)
        self.live_hashes = {}

    def write_mix_source(self, points, include_bold=True):
        store = self.stage / 'system/fonts/.luoshu-font-store'
        store.mkdir(parents=True, exist_ok=True)
        source = store / 'mix-composite.font'
        text_font(source, points=points, advance=660)
        sources = {
            source.name: {'digest': hashlib.sha256(source.read_bytes()).hexdigest(),
                          'cjkWeight': 400, 'latinWeight': 400, 'digitWeight': 400}}
        bold = store / 'wght-700.font'
        if include_bold:
            text_font(bold, points=points, weight=700, advance=920)
            sources[bold.name] = {'digest': hashlib.sha256(bold.read_bytes()).hexdigest(),
                                 'cjkWeight': 700, 'latinWeight': 700, 'digitWeight': 700}
        else:
            bold.unlink(missing_ok=True)
        (store / '.luoshu-mix-source-weights.json').write_text(json.dumps({
            'schema': 'luoshu-mix-source-weights-v1', 'sources': sources}))

    @staticmethod
    def public_bytes(root):
        return {logical: (root / logical.lstrip('/')).read_bytes()
                for logical in ALL if (root / logical.lstrip('/')).is_file()}

    def activate_initial(self):
        result = self.invoke('mix')
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        if len(self.public_bytes(self.stage)) != 15:
            raise AssertionError('initial real composition must cover all fifteen targets')
        shutil.rmtree(self.live)
        self.stage.rename(self.live)
        (self.config / 'active_font.conf').write_text('mix\n')
        (self.config / 'font-payload-activated.conf').write_text('font=mix\nstate=activated\n')
        self.live_hashes = self.public_bytes(self.live)
        return result

    def clone_active(self):
        shutil.copytree(self.live, self.stage)

    def install_real_repair_entrypoints(self):
        for name in ('app_bridge.sh', 'font_switch_task.sh', 'font_switch_lock.sh',
                     'font_provenance.sh', 'background_task.sh'):
            shutil.copyfile(ROOT / 'common' / name, self.module / 'common' / name)
        legacy = self.module / 'common/legacy_v14_4'
        legacy.mkdir(exist_ok=True)
        for name in ('font_switch_safe.sh', 'payload_clone.sh'):
            shutil.copyfile(ROOT / 'common/legacy_v14_4' / name, legacy / name)
        (self.module / 'module.prop').write_text('id=LuoShu\nversion=repair-fixture\n')
        self.env.update(MODDIR=str(self.module), MODULE_DIR=str(self.module),
                        LUOSHU_FONT_MANAGER=str(legacy / 'font_switch_safe.sh'),
                        LUOSHU_SWITCH_HEARTBEAT_INTERVAL='1')

    def app_repair(self):
        return subprocess.run(['sh', str(self.module / 'common/app_bridge.sh'), 'coverage_reapply'],
                              env=self.env, text=True, capture_output=True, timeout=15)


class CoverageRepairRegressionTest(unittest.TestCase):
    def setUp(self):
        self.f = FifteenSlotFixture()
        self.addCleanup(self.f.close)
        self.f.activate_initial()
        self.assertEqual(set(self.f.inventory['slots']), set(ALL))
        self.assertEqual(len(self.f.live_hashes), 15)

    def assert_live_unchanged(self):
        self.assertEqual(self.f.public_bytes(self.f.live), self.f.live_hashes)
        self.assertEqual(len(self.f.public_bytes(self.f.live)), 15)

    def test_cached_sourceless_repair_preserves_all_fifteen_valid_outputs(self):
        self.f.clone_active()
        result = self.f.invoke('mix', plan=[BASE[0]], source=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.f.public_bytes(self.f.stage), self.f.live_hashes)
        summary = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual((summary['mapped'], summary['planned'], summary['existing']), (15, 1, 14))
        self.assert_live_unchanged()

    def test_repair_of_corrupt_requested_output_restores_only_that_output(self):
        self.f.clone_active()
        requested = self.f.path(BASE[0])
        requested.unlink()
        requested.write_bytes(b'interrupted selected slot')
        result = self.f.invoke('mix', plan=[BASE[0]], source=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.f.public_bytes(self.f.stage), self.f.live_hashes)
        self.assert_live_unchanged()

    def test_repair_cannot_reclassify_four_existing_outputs_as_preserved(self):
        self.f.clone_active()
        self.f.write_mix_source(LATIN, include_bold=False)
        before = self.f.public_bytes(self.f.stage)
        result = self.f.invoke('mix', plan=[BASE[0]], source=False)
        self.assertNotEqual(result.returncode, 0,
            'Changed repair source was accepted; this previously reduced fifteen targets to eleven: '
            + result.stdout + result.stderr)
        self.assertEqual(self.f.public_bytes(self.f.stage), before)
        self.assertEqual(len(self.f.public_bytes(self.f.stage)), 15)
        self.assert_live_unchanged()
        self.assertFalse((self.f.module / '.luoshu-payload-next').exists())

    def test_new_stage_repair_cannot_replace_active_fifteen_with_eleven(self):
        self.f.stage.mkdir()
        self.f.write_mix_source(LATIN, include_bold=False)
        result = self.f.invoke('mix', plan=[BASE[0]], source=False)
        self.assertNotEqual(result.returncode, 0,
            'A repair plan without the active output proof must not start a full rebuild: '
            + result.stdout + result.stderr)
        self.assertFalse(self.f.public_bytes(self.f.stage))
        self.assert_live_unchanged()
        self.assertFalse((self.f.module / '.luoshu-payload-next').exists())

    def test_complete_reapply_is_distinct_from_repair_and_can_change_capability(self):
        self.f.stage.mkdir()
        self.f.write_mix_source(LATIN, include_bold=False)
        result = self.f.invoke('mix', source=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(set(self.f.public_bytes(self.f.stage)), set(BASE))
        report = self.f.report()
        self.assertEqual(report['summary']['mapped'], 11)
        for logical in EXTRA:
            self.assertEqual(report['preservedFonts'][logical], 'source-weight-missing')
        self.assert_live_unchanged()

    def test_unrequested_corrupt_output_aborts_repair_without_rebuilding_others(self):
        self.f.clone_active()
        damaged = self.f.path(BASE[1])
        damaged.unlink()
        damaged.write_bytes(b'unrequested damaged slot')
        before = self.f.public_bytes(self.f.stage)
        result = self.f.invoke('mix', plan=[BASE[0]], source=False)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.f.public_bytes(self.f.stage), before)
        self.assert_live_unchanged()

    def test_app_repair_with_no_missing_slot_cannot_recompose_a_complete_mix(self):
        self.f.install_real_repair_entrypoints()
        result = self.f.app_repair()
        self.assertEqual(json.loads(result.stdout)['status'], 'error')
        self.assertFalse((self.f.module / '.luoshu-payload-next').exists())
        self.assertFalse((self.f.config / 'switch_task.conf').exists())
        self.assert_live_unchanged()

    def test_builder_update_requires_full_apply_without_queueing_a_false_repair(self):
        import device_font_slot_trace as trace
        self.f.install_real_repair_entrypoints()
        # The installer retains the old eleven files while the new builder
        # waits for explicit application. Its partition-only migration does
        # not carry the old root output proof into the new payload.
        for logical in EXTRA:
            (self.f.live / logical.lstrip('/')).unlink()
        for name in ('.luoshu-inventory-output-manifest.json', '.luoshu-metrics-report.json',
                     '.luoshu-metrics-covered.lst', '.luoshu-coverage-preserved.tsv'):
            (self.f.live / name).unlink(missing_ok=True)
        before = self.f.public_bytes(self.f.live)
        self.assertEqual(len(before), 11)
        marker = self.f.config / 'font-payload-rebuild-pending.conf'
        marker_text = 'state=awaiting-explicit-apply\nreason=font-builder-changed\nfont=mix\n'
        marker.write_text(marker_text)
        status = trace.build_physical_trace(self.f.inventory, self.f.live, active_font='mix',
                                            verify_payload=True)
        self.assertTrue(status['reapplyRequired'])
        self.assertEqual(status['summary']['remediable'], 0)
        plan = self.f.config / 'test-update-repair.plan'
        trace.atomic_write_plan(status, plan)
        self.assertFalse(plan.read_text().strip())
        result = self.f.app_repair()
        response = json.loads(result.stdout)
        self.assertEqual(response['status'], 'error', result.stdout + result.stderr)
        self.assertIn('重新应用', response['message'])
        self.assertFalse((self.f.config / 'switch_task.conf').exists())
        self.assertFalse((self.f.module / '.luoshu-payload-next').exists())
        self.assertEqual(self.f.public_bytes(self.f.live), before)
        self.assertEqual(marker.read_text(), marker_text)

    def test_real_app_worker_repairs_active_mix_without_reselecting_library_source(self):
        self.f.install_real_repair_entrypoints()
        (self.f.live / BASE[0].lstrip('/')).unlink()
        before = self.f.public_bytes(self.f.live)
        self.assertEqual(len(before), 14)
        # The current library/UI recipe now has insufficient scripts. Repair
        # must use the activated composite's pinned bytes and keep these UI
        # choices untouched, rather than recomposing and shrinking to eleven.
        text_font(self.f.source, points=LATIN)
        recipe = ('cjk=Different Library\nlatin=Different Library\ndigit=Different Library\n'
                  'cjkMode=fixed\nlatinMode=auto\ndigitMode=fixed\n'
                  'cjkAxes=wght=400\nlatinAxes=wght=700\ndigitAxes=wght=400\n')
        (self.f.config / 'axes_mix.conf').write_text(recipe)
        started = self.f.app_repair()
        self.assertEqual(started.returncode, 0, started.stdout + started.stderr)
        self.assertEqual(json.loads(started.stdout)['status'], 'ok')
        task_file = self.f.config / 'switch_task.conf'
        task = {}
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if task_file.is_file():
                task = dict(line.split('=', 1) for line in task_file.read_text().splitlines() if '=' in line)
                if task.get('state') in {'success', 'failed'}:
                    break
            time.sleep(.05)
        logs = (self.f.module / 'logs/fontswitch.log').read_text()
        self.assertEqual(task.get('state'), 'success', str(task) + '\n' + logs)
        self.assertEqual(task.get('font'), 'mix')
        self.assertEqual(task.get('coverageRemediate'), 'true')
        plan = self.f.config / 'font-coverage-remediation-paths.txt'
        self.assertEqual(plan.read_text().splitlines(), [BASE[0]])
        queued = self.f.module / '.luoshu-payload-next'
        self.assertEqual(self.f.public_bytes(queued), self.f.live_hashes)
        self.assertEqual(len(self.f.public_bytes(queued)), 15)
        self.assertEqual(self.f.public_bytes(self.f.live), before)
        self.assertEqual((self.f.config / 'active_font.conf').read_text(), 'mix\n')
        self.assertEqual((self.f.config / 'axes_mix.conf').read_text(), recipe)
        self.assertFalse((self.f.config / 'axes_task.conf').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
