#!/usr/bin/env python3
"""Existing failed artifacts can be diagnosed without rebuilding fonts."""
import ast
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
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
print('universal_mixed_diagnostic_test: PASS (read-only existing manifest, private paths redacted)')
