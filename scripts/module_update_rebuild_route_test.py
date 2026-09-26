#!/usr/bin/env python3
"""Migration waits for the public mix route, including axes-only auto tasks."""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RebuildRouteTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='luoshu-update-route-')
        self.addCleanup(self.temp.cleanup)
        self.module = Path(self.temp.name)
        for name in ('common/legacy_v14_4', 'config', 'logs'):
            (self.module / name).mkdir(parents=True)
        shutil.copyfile(ROOT / 'common/font_mix.sh', self.module / 'common/font_mix.sh')
        (self.module / 'config/active_font.conf').write_text('mix\n')
        (self.module / 'config/font_mix.conf').write_text('cjk=CJK\nlatin=Latin\ndigit=Digits\n')
        (self.module / 'config/font-payload-rebuild-pending.conf').write_text('pending\n')
        (self.module / 'common/legacy_v14_4/mix_router.sh').write_text('''#!/bin/sh
case "$1" in
start)
    [ "$2" = CJK ] && [ "$3" = Latin ] && [ "$4" = Digits ] || exit 6
    printf 'task=current\nstate=success\n' > "$MODDIR/config/${TEST_TASK_FILE:-axes_task.conf}"
    if [ "${TEST_COMMIT:-1}" = 1 ]; then
        mkdir -p "$MODDIR/.luoshu-payload-next/system/fonts"
        printf generated > "$MODDIR/.luoshu-payload-next/system/fonts/Custom.ttf"
        printf 'state=prepared\nfont=mix\nrequestId=current\n' > "$MODDIR/config/font-payload-next.conf"
    fi
    echo '{"status":"ok","data":{"task":"current"}}'
    ;;
status)
    [ "$2" = current ] || exit 7
    if [ "${TEST_ROUTE_FAIL:-0}" = 1 ]; then
        printf 'state=success\n' > "$MODDIR/config/mix_task.conf"
        echo '{"status":"ok","data":{"task":"current","state":"failed"}}'
    else
        echo '{"status":"ok","data":{"task":"current","state":"success"}}'
    fi
    ;;
esac
''')

    def rebuild(self, **env):
        return subprocess.run(['sh', '-c', '. "$1"; luoshu_v4_update_rebuild_selected "$2"',
            'sh', str(ROOT / 'common/module_update_hotfix_v4.sh'), str(self.module)],
            env={**os.environ, **env}, capture_output=True, text=True, timeout=5)

    def test_auto_axes_success_without_mix_task_finishes_rebuild(self):
        result = self.rebuild()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.module / 'config/mix_task.conf').exists())
        self.assertFalse((self.module / 'config/font-payload-rebuild-pending.conf').exists())
        self.assertEqual((self.module / 'config/active_font.conf').read_text(), 'mix\n')

    def test_fixed_nested_task_route_also_finishes_rebuild(self):
        result = self.rebuild(TEST_TASK_FILE='mix_task.conf')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.module / 'config/font-payload-rebuild-pending.conf').exists())

    def test_stale_mix_success_does_not_override_router_failure(self):
        result = self.rebuild(TEST_ROUTE_FAIL='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((self.module / 'config/font-payload-rebuild-pending.conf').exists())

    def test_success_without_prepared_payload_keeps_pending(self):
        result = self.rebuild(TEST_COMMIT='0')
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((self.module / 'config/font-payload-rebuild-pending.conf').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
