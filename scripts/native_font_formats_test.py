#!/usr/bin/env python3
"""Real host SFNT/web/collection import bridge, without executing package scripts."""
from pathlib import Path
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'common'), str(ROOT / 'scripts')]
from fontTools.ttLib import TTCollection, TTFont
from fontTools.ttLib.woff2 import haveBrotli
import universal_font_compiler_test as fonts


def run() -> None:
    with tempfile.TemporaryDirectory(prefix='native-formats-') as folder:
        root = Path(folder)
        module = root / 'module'
        common = module / 'common'
        common.mkdir(parents=True)
        for path in (ROOT / 'common').iterdir():
            if path.is_file():
                (common / path.name).symlink_to(path)
        pyroot = common / 'python'
        (pyroot / 'bin').mkdir(parents=True)
        runner = pyroot / 'bin/luoshu-python'
        runner.write_text('#!/bin/sh\nunset PYTHONHOME\nexec ' + shlex.quote(sys.executable) + ' "$@"\n')
        runner.chmod(0o755)
        site = pyroot / 'lib/python3.14/site-packages'
        site.parent.mkdir(parents=True)
        import fontTools
        site.mkdir()
        (site / 'fontTools').symlink_to(Path(fontTools.__file__).parent, target_is_directory=True)
        prefix = (ROOT / 'common/native_import.sh').read_text().split('\nsource_path="${1:-}"')[0]
        functions = root / 'functions.sh'
        functions.write_text(prefix)
        assert 'ttf|otf|ttc|otc) import_font_file' in (ROOT / 'common/native_import.sh').read_text()
        assert '-name \'*.ttc\'' in (ROOT / 'common/native_import.sh').read_text()
        kotlin = (ROOT / 'android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeFontFormats.kt').read_text()
        for extension in ('ttf', 'otf', 'ttc', 'otc', 'woff', 'woff2', 'zip'):
            assert f'"{extension}"' in kotlin

        ttf, otf = root / 'a.ttf', root / 'b.otf'
        old_points = fonts.ASCII_POINTS
        try:
            fonts.ASCII_POINTS = tuple(range(32, 512))
            fonts.make_font(ttf, family='Native TTF')
            fonts.make_font(otf, family='Native CFF', cff=True)
        finally:
            fonts.ASCII_POINTS = old_points
        collection = root / 'collection.otc'
        with TTFont(ttf) as a, TTFont(otf) as b:
            bundle = TTCollection(); bundle.fonts = [a, b]; bundle.save(collection)
        inputs = [('ttf', ttf), ('otf', otf), ('otc', collection)]
        for flavor in ('woff', 'woff2'):
            if flavor == 'woff2' and not haveBrotli:
                if os.environ.get('LUOSHU_REQUIRE_BROTLI_TEST') == '1':
                    raise AssertionError('real WOFF2 test requires Brotli')
                print('SKIP real WOFF2 host codec: Brotli unavailable (no Android ABI claim)')
                continue
            path = root / ('web.' + flavor)
            with TTFont(ttf) as font:
                font.flavor = flavor; font.save(path)
            inputs.append((flavor, path))
        for extension, source in inputs:
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            public = root / ('public-' + extension)
            function = 'import_web_font_file' if extension.startswith('woff') else 'import_font_file'
            env = dict(os.environ, MODDIR=str(module), MODULE_DIR=str(module),
                       LUOSHU_PUBLIC_DIR=str(public), LUOSHU_IMPORT_PYTHON=sys.executable,
                       PYTHONPATH=str(Path(fontTools.__file__).parent.parent))
            script = '. "$1"; schedule_font_prewarm() { :; }; ' + function + ' "$2" "$3"'
            result = subprocess.run(['sh', '-c', script, 'sh', str(functions), str(source), source.name],
                                    env=env, text=True, capture_output=True, timeout=30)
            assert result.returncode == 0, result.stderr
            response = json.loads(result.stdout.strip().splitlines()[-1])
            assert response['status'] == 'ok', (extension, response)
            outputs = list((public / 'fonts').glob('*.ttf')) + list((public / 'fonts').glob('*.otf'))
            assert len(outputs) == (2 if extension == 'otc' else 1), (extension, outputs)
            for path in outputs:
                with TTFont(path) as font:
                    assert font.flavor is None and ord('A') in font.getBestCmap()
                    assert 'glyf' in font or 'CFF ' in font
            assert hashlib.sha256(source.read_bytes()).hexdigest() == before
        invalid = root / 'bad.woff2'; invalid.write_bytes(b'not a font')
        env = dict(os.environ, MODDIR=str(module), LUOSHU_PUBLIC_DIR=str(root / 'invalid'))
        result = subprocess.run(['sh','-c','. "$1"; import_web_font_file "$2" bad.woff2', 'sh',str(functions),str(invalid)],env=env,text=True,capture_output=True,timeout=30)
        assert json.loads(result.stdout.strip().splitlines()[-1])['status'] == 'error'
        assert not list((root / 'invalid').glob('fonts/*'))
    print('native_font_formats_test: PASS (host real conversion/extraction; Android ABI and UI remain separate)')

if __name__ == '__main__': run()
