#!/usr/bin/env python3
"""Portable real-shell selection contracts; fixtures are not rendering fonts."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

CASES = [
    ('static-nearest', [('Demo-Regular.ttf', ''), ('Demo-Bold.ttf', '')], 'Demo', '650', 'Demo-Bold.ttf'),
    ('exact-static', [('Demo-Regular.ttf', ''), ('Demo-Bold.ttf', '')], 'Demo', '400', 'Demo-Regular.ttf'),
    ('invalid-weight-default', [('Demo-Regular.ttf', ''), ('Demo-Bold.ttf', '')], 'Demo', 'bad', 'Demo-Regular.ttf'),
    ('static-tie-order', [('Demo-Regular.ttf', ''), ('Demo-Bold.ttf', '')], 'Demo', '550', 'Demo-Bold.ttf'),
    ('cross-format-tie-order', [('Demo-Regular.ttf', ''), ('Demo-Bold.otf', '')], 'Demo', '550', 'Demo-Regular.ttf'),
    ('later-variable-wins-over-exact-static', [('Demo-Regular.ttf', ''), ('Demo-Bold.otf', 'fvar')], 'Demo', '400', 'Demo-Bold.otf'),
    ('first-variable-order', [('Demo-Light.ttf', 'fvar'), ('Demo-Bold.otf', 'fvar')], 'Demo', '900', 'Demo-Light.ttf'),
    ('uppercase-extension', [('Demo-Regular.TTF', '')], 'Demo', '400', 'Demo-Regular.TTF'),
    ('chinese-space-family', [('书 体-Regular.ttf', '')], '书 体', '400', '书 体-Regular.ttf'),
    ('literal-backslash-family', [('Demo\\name-Regular.ttf', '')], 'Demo\\name', '400', 'Demo\\name-Regular.ttf'),
    ('leading-echo-option-family', [('-n-Regular.ttf', '')], '-n', '400', '-n-Regular.ttf'),
    ('single-pass-suffixes', [('Demo-Italic-Black.ttf', '')], 'Demo', '400', 'Demo-Italic-Black.ttf'),
    ('trailing-name-separators', [('Demo-_  .ttf', '')], 'Demo', '400', 'Demo-_  .ttf'),
    ('matching-directory-rejected', [('Demo-Regular.ttf', '<directory>'), ('Demo-Bold.otf', '')], 'Demo', '400', 'Demo-Bold.otf'),
    ('different-family-rejected', [('Other-Regular.ttf', '')], 'Demo', '400', None),
    ('empty-library', [], 'Demo', '400', None),
    ('large-independent-library', [(f'Independent{i:04d}.ttf', '') for i in range(999)] + [('Selected-Regular.ttf', '')], 'Selected', '400', 'Selected-Regular.ttf'),
]


def run(module, shell):
    android = Path('/system/bin/sh').exists()
    report = {'schema': 'luoshu-preview-source-contract-v1', 'environment': 'ANDROID' if android else 'HOST_ONLY',
              'module': str(module), 'shell': shell, 'result': 'PASS', 'cases': []}
    with tempfile.TemporaryDirectory(prefix='luoshu-preview-contract-', dir='/data/local/tmp' if android else None) as temp:
        base = Path(temp)
        for index, (name, files, family, weight, expected) in enumerate(CASES):
            public = base / str(index); fonts = public / 'fonts'; fonts.mkdir(parents=True)
            for filename, marker in files:
                path = fonts / filename
                if marker == '<directory>': path.mkdir()
                else: path.write_text('original selection-only fixture ' + marker)
            env = dict(os.environ, MODDIR=str(module), LUOSHU_PUBLIC_DIR=str(public))
            result = subprocess.run([shell, str(module / 'common/app_bridge.sh'), 'preview_source', family, weight],
                                    env=env, capture_output=True, text=True, timeout=20)
            actual = json.loads(result.stdout)
            if expected is None:
                # The existing bridge ends with exit 0; structured status is
                # authoritative for missing-source errors, as before this batch.
                assert actual['status'] == 'error' and 'data' not in actual, (name, result.stdout)
            else:
                assert result.returncode == 0 and actual['status'] == 'ok', (name, result.stderr, result.stdout)
                assert actual['data']['family'] == family and actual['data']['file'] == expected, (name, actual)
            report['cases'].append({'name': name, 'result': 'PASS'})
        # The in-process entry and existing stdout entry must use the same parser.
        script = '. "$1"; for name in "Demo-Italic-Black.ttf" "Demo-Black-Italic.ttf" "书 体-Regular.ttf"; do old=$(detect_font_family "$name"); detect_font_family_value "$name"; [ "$old" = "$LUOSHU_DETECTED_FONT_FAMILY" ] || exit 1; done'
        result = subprocess.run([shell, '-c', script, 'contract', str(module / 'common/util_functions_core.sh')],
                                capture_output=True, text=True, timeout=20)
        assert result.returncode == 0 and result.stdout == '', (result.stdout, result.stderr)
        report['cases'].append({'name': 'quiet-and-stdout-parser-agree', 'result': 'PASS'})
    report['case_count'] = len(report['cases'])
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--module', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--shell', default='/system/bin/sh' if Path('/system/bin/sh').exists() else 'sh')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = run(args.module.resolve(), args.shell)
    value = json.dumps(report, ensure_ascii=False, separators=(',', ':')) + '\n'
    if args.output: args.output.write_text(value)
    print(value, end='')
