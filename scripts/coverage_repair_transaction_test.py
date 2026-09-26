#!/usr/bin/env python3
"""Physical repair never regenerates the selection or sacrifices existing slots."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


def tree(path):
    return {p.relative_to(path).as_posix(): p.read_bytes() for p in path.rglob('*') if p.is_file()}


class RepairTransactionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='luoshu repair ')
        self.addCleanup(self.temp.cleanup)
        self.module = Path(self.temp.name) / 'module'
        self.config = self.module / 'config'
        self.live = self.module / '.luoshu-payload'
        self.next = self.module / '.luoshu-payload-next'
        for path in ('common/legacy_v14_4', 'config', 'logs', '.luoshu-payload/system/fonts/.luoshu-font-store', 'bin'):
            (self.module / path).mkdir(parents=True)
        for name in ('font_switch_safe.sh', 'payload_clone.sh'):
            shutil.copyfile(ROOT / 'common/legacy_v14_4' / name, self.module / 'common/legacy_v14_4' / name)
        for name in ('font_switch_lock.sh', 'background_task.sh', 'font_switch_task.sh'):
            shutil.copyfile(ROOT / 'common' / name, self.module / 'common' / name)
        (self.module / 'module.prop').write_text('id=LuoShu\n')
        (self.config / 'active_font.conf').write_text('Demo\n')
        (self.config / 'font_runtime_legacy_v14_4.conf').write_text('enabled=true\n')
        (self.config / 'font-payload-activated.conf').write_text(
            'font=Demo\nprovenanceSchema=font-provenance-v1\nproofKind=direct\ndirectProof=source-proof\n')
        (self.config / 'device_font_inventory.json').write_text('{}')
        slots = [f'/system/fonts/Slot{i}.ttf' for i in range(15)]
        for i, slot in enumerate(slots):
            (self.live / slot.lstrip('/')).write_text(f'applied-font-{i}')
        (self.live / 'system/fonts/.luoshu-font-store/regular.font').write_text('pinned-original-source')
        (self.live / '.luoshu-metrics-covered.lst').write_text(''.join(s + '\n' for s in slots))
        (self.live / '.luoshu-metrics-report.json').write_text('{"summary":{"mode":"direct"}}')
        (self.live / '.luoshu-inventory-output-manifest.json').write_text('{"schema":"inventory-font-output-v1"}')
        self.plan = self.config / 'coverage plan.txt'
        self.plan.write_text('/system/fonts/Slot14.ttf\n')
        self.helper = self.module / 'common/inventory_font_stage.sh'
        self.helper.write_text('''#!/bin/sh
[ "$1" != --ensure-inventory ] || exit 0
[ "$#" = 3 ] || exit 8
[ "$LUOSHU_COVERAGE_REMEDIATE" = 1 ] && [ -s "$LUOSHU_COVERAGE_PLAN" ] || exit 9
printf '%s|%s|%s\n' "$2" "$3" "$#" > "$LUOSHU_REAL_MODDIR/repair-args"
[ "${TEST_ENGINE_BLOCK:-0}" != 1 ] || sleep 30
printf changed-report > "$1/.luoshu-metrics-report.json"
[ "${TEST_ENGINE_FAIL:-0}" != 1 ] || exit 7
if [ "${TEST_PRUNE:-0}" = 1 ]; then
    rm "$1/system/fonts/Slot0.ttf"
    sed '/Slot0.ttf/d' "$1/.luoshu-metrics-covered.lst" > "$1/.list-new"
    mv "$1/.list-new" "$1/.luoshu-metrics-covered.lst"
fi
while IFS= read -r slot; do
    printf repaired > "$1$slot.new"
    mv "$1$slot.new" "$1$slot"
done < "$LUOSHU_COVERAGE_PLAN"
''')
        self.env = {**os.environ, 'MODDIR': str(self.module), 'LUOSHU_REAL_MODDIR': str(self.module),
                    'LUOSHU_COVERAGE_REMEDIATE': '1', 'LUOSHU_COVERAGE_PLAN': str(self.plan),
                    'LUOSHU_PUBLIC_DIR': str(self.module / 'missing-library')}

    def run_repair(self, active='Demo', **env):
        return subprocess.run(['sh', str(self.module / 'common/legacy_v14_4/font_switch_safe.sh'),
                               'action', 'switch', active], env={**self.env, **env},
                              text=True, capture_output=True, timeout=8)

    def seed_next(self):
        self.next.mkdir()
        (self.next / 'queued').write_text('previous-queued-payload')
        (self.config / 'font-payload-next.conf').write_text('state=prepared\nfont=Other\nrequestId=queued\n')
        (self.config / 'text_reboot_required.conf').write_text('old-reboot-marker\n')

    def test_success_retains_fifteen_slots_source_and_direct_provenance(self):
        self.seed_next()
        before = tree(self.live)
        result = self.run_repair()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(tree(self.live), before, 'hardlink cloning must not let report writes alter LIVE')
        self.assertEqual(len(list((self.next / 'system/fonts').glob('Slot*.ttf'))), 15)
        self.assertEqual((self.next / 'system/fonts/Slot0.ttf').read_bytes(), before['system/fonts/Slot0.ttf'])
        self.assertEqual((self.next / 'system/fonts/Slot14.ttf').read_text(), 'repaired')
        self.assertEqual((self.next / 'system/fonts/.luoshu-font-store/regular.font').read_text(), 'pinned-original-source')
        state = (self.config / 'font-payload-next.conf').read_text()
        self.assertIn('directProof=source-proof\n', state)
        self.assertIn('previousFont=Demo\n', state)
        self.assertEqual((self.config / 'active_font.conf').read_text(), 'Demo\n')
        self.assertEqual((self.module / 'repair-args').read_text(), 'direct|Demo|3\n')

    def test_mix_preserves_recipe_without_composing_or_library_sources(self):
        (self.config / 'active_font.conf').write_text('mix\n')
        recipe = 'requestId=original-request\ncjk=CJK\nlatin=Latin\ndigit=Digits\ncompositeHash=original-composite\n'
        (self.config / 'font-payload-activated.conf').write_text('font=mix\n' + recipe)
        (self.live / '.luoshu-mix-generation.conf').write_text(recipe)
        result = self.run_repair('mix')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        state = (self.config / 'font-payload-next.conf').read_text()
        for line in recipe.splitlines():
            self.assertIn(line + '\n', state)
        self.assertEqual((self.next / '.luoshu-mix-generation.conf').read_text(), recipe)
        self.assertEqual((self.module / 'repair-args').read_text(), 'mix|mix|3\n')

    def test_success_only_clears_legacy_repair_intent(self):
        pending = self.config / 'font-payload-rebuild-pending.conf'
        notified = self.config / 'font-payload-reapply-notified.conf'
        for reason in ('font-builder-changed', 'another-update-request', '', 'coverage-remediate'):
            with self.subTest(reason=reason):
                content = f'reason={reason}\nsource=earlier-update\n'
                pending.write_text(content)
                notified.write_text('earlier-update-notification\n')
                result = self.run_repair()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                if reason == 'coverage-remediate':
                    self.assertFalse(pending.exists())
                    self.assertFalse(notified.exists())
                else:
                    self.assertEqual(pending.read_text(), content)
                    self.assertEqual(notified.read_text(), 'earlier-update-notification\n')

    def test_failed_repair_preserves_legacy_and_update_intent(self):
        pending = self.config / 'font-payload-rebuild-pending.conf'
        for reason in ('font-builder-changed', 'coverage-remediate'):
            with self.subTest(reason=reason):
                content = f'reason={reason}\n'
                pending.write_text(content)
                result = self.run_repair(TEST_ENGINE_FAIL='1')
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(pending.read_text(), content)

    def test_failed_engine_or_coverage_reduction_preserves_live_next_and_selection(self):
        self.seed_next()
        before_live, before_next = tree(self.live), tree(self.next)
        before_state = (self.config / 'font-payload-next.conf').read_bytes()
        for override in ({'TEST_ENGINE_FAIL': '1'}, {'TEST_PRUNE': '1'}):
            with self.subTest(override=override):
                result = self.run_repair(**override)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(tree(self.live), before_live)
                self.assertEqual(tree(self.next), before_next)
                self.assertEqual((self.config / 'font-payload-next.conf').read_bytes(), before_state)
                self.assertEqual((self.config / 'active_font.conf').read_text(), 'Demo\n')
                self.assertFalse(list(self.module.glob('.luoshu-payload-stage.*')))

    def test_commit_failure_restores_previous_next_and_all_state(self):
        self.seed_next()
        before_next = tree(self.next)
        before_state = (self.config / 'font-payload-next.conf').read_bytes()
        real_mv = shutil.which('mv')
        wrapper = self.module / 'bin/mv'
        wrapper.write_text(f'''#!/bin/sh
case "$1" in */.luoshu-payload-stage.*) exit 71 ;; esac
exec "{real_mv}" "$@"
''')
        wrapper.chmod(0o755)
        result = self.run_repair(PATH=str(wrapper.parent) + os.pathsep + os.environ['PATH'])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(tree(self.next), before_next)
        self.assertEqual((self.config / 'font-payload-next.conf').read_bytes(), before_state)
        self.assertEqual((self.config / 'text_reboot_required.conf').read_text(), 'old-reboot-marker\n')
        self.assertFalse(list(self.module.glob('.luoshu-repair-commit.*')))

    def test_state_commit_failure_rolls_back_an_already_moved_stage(self):
        self.seed_next()
        before_next = tree(self.next)
        before_state = (self.config / 'font-payload-next.conf').read_bytes()
        real_mv = shutil.which('mv')
        wrapper = self.module / 'bin/mv'
        wrapper.write_text(f'''#!/bin/sh
for arg in "$@"; do case "$arg" in */.luoshu-repair-commit.*/new-state) exit 72 ;; esac; done
exec "{real_mv}" "$@"
''')
        wrapper.chmod(0o755)
        result = self.run_repair(PATH=str(wrapper.parent) + os.pathsep + os.environ['PATH'])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(tree(self.next), before_next)
        self.assertEqual((self.config / 'font-payload-next.conf').read_bytes(), before_state)
        self.assertEqual((self.config / 'text_reboot_required.conf').read_text(), 'old-reboot-marker\n')

    def test_cancelled_repair_keeps_live_and_prior_next(self):
        self.seed_next()
        before_live, before_next = tree(self.live), tree(self.next)
        result = subprocess.run(['timeout', '1', 'sh',
            str(self.module / 'common/legacy_v14_4/font_switch_safe.sh'), 'action', 'switch', 'Demo'],
            env={**self.env, 'TEST_ENGINE_BLOCK': '1'}, capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(tree(self.live), before_live)
        self.assertEqual(tree(self.next), before_next)
        self.assertFalse((self.module / '.font_switch.lock').exists())
        self.assertFalse(list(self.module.glob('.luoshu-payload-stage.*')))

    def test_missing_plan_or_activation_mismatch_never_enters_engine(self):
        self.seed_next()
        result = self.run_repair(LUOSHU_COVERAGE_PLAN='')
        self.assertNotEqual(result.returncode, 0)
        (self.config / 'font-payload-activated.conf').write_text('font=Earlier\n')
        result = self.run_repair()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.module / 'repair-args').exists())
        self.assertTrue((self.next / 'queued').is_file())

    def test_detached_task_keeps_repair_env_and_marker_for_old_apk_polling(self):
        manager = self.module / 'common/font_manager.sh'
        manager.write_text('''#!/bin/sh
printf '%s|%s|%s\n' "$LUOSHU_COVERAGE_REMEDIATE" "$LUOSHU_COVERAGE_PLAN" "$LUOSHU_FORCE_REBUILD" > "$MODDIR/worker-env"
echo '{"status":"ok","data":{"rebootRequired":true}}'
''')
        script = self.module / 'common/font_switch_task.sh'
        result = subprocess.run(['sh', str(script), 'start', 'mix'], env=self.env,
                                text=True, capture_output=True, timeout=5)
        task = json.loads(result.stdout)['data']['task']
        deadline = time.monotonic() + 6
        state = ''
        while time.monotonic() < deadline:
            state = (self.config / 'switch_task.conf').read_text()
            if 'state=success\n' in state:
                break
            time.sleep(.05)
        self.assertIn('state=success\n', state)
        self.assertIn('coverageRemediate=true\n', state)
        self.assertIn(f'coveragePlan={self.plan}\n', state)
        self.assertEqual((self.module / 'worker-env').read_text(), f'1|{self.plan}|1\n')
        clean_env = {key: value for key, value in self.env.items() if not key.startswith('LUOSHU_COVERAGE_')}
        status = subprocess.run(['sh', str(script), 'status', task], env=clean_env,
                                text=True, capture_output=True, timeout=5)
        self.assertEqual(json.loads(status.stdout)['data']['state'], 'success')
        self.assertIn('coverageRemediate=true\n', (self.config / 'switch_task.conf').read_text())
        # A later poll has no repair environment. Reconciliation must retain the
        # marker even while converting a dead running worker into failed state.
        task_file = self.config / 'switch_task.conf'
        task_file.write_text(task_file.read_text().replace('state=success\n', 'state=running\n'))
        reconciled = subprocess.run(['sh', str(script), 'reconcile'], env=clean_env,
                                    text=True, capture_output=True, timeout=5)
        self.assertEqual(reconciled.returncode, 0, reconciled.stderr)
        self.assertIn('state=failed\n', task_file.read_text())
        self.assertIn('coverageRemediate=true\n', task_file.read_text())
        self.assertIn(f'coveragePlan={self.plan}\n', task_file.read_text())


if __name__ == '__main__':
    unittest.main(verbosity=2)
