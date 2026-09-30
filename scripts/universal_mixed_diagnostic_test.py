#!/usr/bin/env python3
"""Existing failed artifacts can be diagnosed without rebuilding fonts."""
import ast
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as raw:
    cfg = Path(raw)
    key = hashlib.sha256(b'LuoShuMix').hexdigest()[:24]
    file = cfg / 'universal-font-artifact-manifests' / (key + '.json')
    file.parent.mkdir()
    file.write_text(json.dumps({'artifacts': [
        {'status': 'ready', 'reason': 'not a blocker'},
        {'status': 'blocked', 'targetPath': '/system/fonts/SysSans-En-Medium.ttf',
         'role': 'latin', 'reason': 'static-weight-fallback'},
        {'status': 'blocked', 'targetPath': '/product/fonts/Clock.ttf',
         'role': 'clock', 'reason': 'source missing /sdcard/LuoShu/fonts/private-name.ttf'},
    ]}))
    kotlin = (ROOT / 'android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/logs/DiagnosticExportUi.kt').read_text()
    code = kotlin.split("<<'PYDIAG'", 1)[1].split('        PYDIAG', 1)[0]
    code = '\n'.join(line[8:] if line.startswith('        ') else line for line in code.splitlines())
    ast.parse(code)
    old_argv = sys.argv
    try:
        sys.argv = ['diagnostic', str(cfg)]
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            exec(compile(code, 'inline-diagnostic', 'exec'), {})
        result = stream.getvalue()
        assert 'static-weight-fallback' in result and 'private-name' not in result
        assert '"blockedCount": 2' in result and 'not a blocker' not in result
        shell = (ROOT / 'common/universal_font_deployment.sh').read_text()
        code = shell.split("<<'PYBLOCK'", 1)[1].split('\nPYBLOCK', 1)[0]
        sys.argv = ['blocked', str(file)]
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            exec(compile(code, 'inline-blocked-summary', 'exec'), {})
        assert '[UNIVERSAL-BLOCKED] count=2' in stream.getvalue()
        assert 'static-weight-fallback' in stream.getvalue() and 'private-name' not in stream.getvalue()
    finally:
        sys.argv = old_argv
with tempfile.TemporaryDirectory() as raw:
    module = Path(raw)
    (module / 'config').mkdir()
    progress = module / 'config/progress.conf'
    progress.write_text('requestId=current\npercent=87\nmessage=compiling slot 14/35\nupdated=123\n')
    (module / 'config/universal-compile-trace.jsonl').write_text(
        '{"requestId":"current","event":"phase","phase":"outline-replacement"}\n'
        '{"requestId":"other","event":"phase","phase":"wrong-phase"}\n')
    shell = (ROOT / 'common/universal_font_cutover.sh').read_text().split('case "${1:-switch}" in', 1)[0]
    env = dict(os.environ, MODDIR=str(module), CONFIG_DIR=str(module / 'config'),
               LUOSHU_SWITCH_PROGRESS_FILE=str(progress), LUOSHU_MIX_REQUEST_ID='current')
    subprocess.run(['sh', '-c', shell + '\nUC_COMPOSITE_REQUEST=true\n_uc_capture_prepare_failure\n_uc_progress 25 fallback\n'], env=env, check=True)
    saved = module / 'config/universal-mixed-last-prepare.conf'
    assert 'compiling slot 14/35' in saved.read_text()
    assert 'fallback' in progress.read_text()
    assert 'compiling slot 14/35' in (module / 'logs/fontswitch.log').read_text()
    assert 'outline-replacement' in (module / 'logs/fontswitch.log').read_text()
    assert 'wrong-phase' not in (module / 'logs/fontswitch.log').read_text()
    # Never attach a newer task's phase to a cancelled/older request.
    progress.write_text('requestId=newer\nmessage=newer task\n')
    subprocess.run(['sh', '-c', shell + '\nUC_COMPOSITE_REQUEST=true\n_uc_capture_prepare_failure\n'], env=env, check=True)
    assert 'compiling slot 14/35' in saved.read_text()
    assert 'newer task' not in (module / 'logs/fontswitch.log').read_text()
print('universal_mixed_diagnostic_test: PASS (manifest redaction and request-bound last phase survive fallback)')
