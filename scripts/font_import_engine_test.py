#!/usr/bin/env python3
"""Real SFNT import regressions: signature routing, archive collisions and preserved faces."""
from __future__ import annotations

import io
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'common'))
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, TTCollection, newTable
from font_import_engine import import_file, Importer, MAX_BYTES
from font_metadata import inspect
from font_role_check import check


def make_font(path, family='Import Family', weight=400, points=(0x41, 0x31, 0x4E2D), is_italic=False, variable=False):
    order = ['.notdef'] + [f'uni{cp:04X}' for cp in points]
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(order)
    glyphs = {}
    for index, glyph in enumerate(order):
        pen = TTGlyphPen(None)
        if index:
            pen.moveTo((10 + index, 0)); pen.lineTo((300 + index, 0)); pen.lineTo((150, 500 + index)); pen.closePath()
        glyphs[glyph] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({glyph: (600, 0) for glyph in order})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupCharacterMap(dict(zip(points, order[1:])))
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200, usWeightClass=weight,
                     fsSelection=1 if is_italic else 0x40 if weight == 400 else 0)
    builder.setupNameTable({'familyName': family, 'styleName': 'Italic' if is_italic else 'Regular', 'uniqueFontIdentifier': family + str(weight), 'fullName': family, 'psName': family.replace(' ', '')})
    builder.setupPost(italicAngle=-12 if is_italic else 0)
    if is_italic:
        builder.font['head'].macStyle |= 2
    if variable:
        builder.setupFvar([('wght', 100, 400, 900, 'Weight')], [{'location': {'wght': 700}, 'stylename': 'Bold'}])
        builder.font['gvar'] = newTable('gvar')
        builder.font['gvar'].variations = {name: [] for name in order}
    builder.save(path)


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.output = self.root / 'fonts'

    def tearDown(self):
        self.temp.cleanup()

    def font(self, name='input.ttf', **kwargs):
        target = self.root / name
        make_font(target, **kwargs)
        return target

    def test_signature_not_suffix_and_small_valid_sfnt(self):
        source = self.font('no-extension')
        self.assertLess(source.stat().st_size, 4096)
        result = import_file(source, self.output, source.name)['data']
        target = Path(result['faces'][0]['path'])
        self.assertEqual(target.suffix, '.ttf')
        self.assertEqual(source.read_bytes(), target.read_bytes())
        self.assertTrue(result['supportsCjk'])
        self.assertTrue(import_file(source, self.output, 'different.weird')['data']['duplicate'])

    def test_woff_decompresses_to_sfnt_preserving_outlines(self):
        source = self.font()
        with TTFont(source, recalcTimestamp=False) as font:
            font.flavor = 'woff'
            font.save(self.root / 'web.bin')
        result = import_file(self.root / 'web.bin', self.output, 'web.bin')['data']
        target = Path(result['faces'][0]['path'])
        self.assertEqual(target.read_bytes()[:4], b'\0\1\0\0')
        with TTFont(source) as original, TTFont(target) as converted:
            self.assertEqual(original.getBestCmap(), converted.getBestCmap())
            for table in ('glyf', 'hmtx', 'fvar'):
                if table in original:
                    self.assertEqual(original.getTableData(table), converted.getTableData(table))

    def test_otf_cff_and_woff_normalize_with_original_charstrings(self):
        from fontTools.pens.t2CharStringPen import T2CharStringPen
        builder = FontBuilder(1000, isTTF=False)
        order = ['.notdef', 'A', 'one']
        builder.setupGlyphOrder(order)
        builder.setupCharacterMap({0x41: 'A', 0x31: 'one'})
        builder.setupHorizontalMetrics({name: (600, 0) for name in order})
        builder.setupHorizontalHeader(ascent=800, descent=-200)
        builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
        builder.setupNameTable({'familyName': 'CFF Import', 'styleName': 'Regular', 'fullName': 'CFF Import', 'psName': 'CFFImport'})
        builder.setupPost()
        strings = {}
        for name in order:
            pen = T2CharStringPen(600, None)
            if name != '.notdef':
                pen.moveTo((20, 0)); pen.lineTo((300, 0)); pen.lineTo((150, 600)); pen.closePath()
            strings[name] = pen.getCharString()
        builder.setupCFF('CFFImport', {'FullName': 'CFF Import', 'FamilyName': 'CFF Import', 'Weight': 'Regular'}, strings, {})
        source = self.root / 'outline.otf'
        builder.save(source)
        imported = import_file(source, self.output, source.name)['data']
        self.assertEqual(imported['format'], 'OTF')
        with TTFont(source, recalcTimestamp=False) as font:
            original_cff = font.getTableData('CFF ')
            font.flavor = 'woff'; font.save(self.root / 'outline.web')
        normalized = import_file(self.root / 'outline.web', self.root / 'webfonts', 'outline.web')['data']['faces'][0]
        self.assertEqual(normalized['format'], 'OTF')
        with TTFont(normalized['path']) as font:
            self.assertEqual(font.getTableData('CFF '), original_cff)
            self.assertEqual(set(font.getBestCmap()), {0x41, 0x31})

    def test_archive_same_basename_preserves_all_real_weights_and_families(self):
        thin = self.font('thin.ttf', weight=100)
        bold = self.font('bold.ttf', weight=900, is_italic=True)
        other = self.font('other.ttf', family='Other Family', points=(0x31,))
        archive = self.root / 'module.zip'
        with zipfile.ZipFile(archive, 'w') as handle:
            handle.writestr('module.prop', 'name=多字重\nversion=1.0\n')
            handle.write(thin, 'system/fonts/same.ttf')
            handle.write(bold, 'product/fonts/same.ttf')
            handle.write(other, 'assets/font-with-no-suffix')
            handle.writestr('customize.sh', 'touch /tmp/should-not-run')
        result = import_file(archive, self.output, archive.name)['data']
        self.assertEqual(result['imported'], 3)
        self.assertEqual(result['familyCount'], 2)
        self.assertEqual(sorted(row['weight'] for row in result['faces']), [100, 400, 900])
        self.assertTrue(next(row for row in result['faces'] if row['weight'] == 900)['italic'])
        self.assertFalse((self.output / 'customize.sh').exists())
        self.assertEqual(len(list(self.output.glob('*.ttf'))), 3)

    def test_otc_magic_extracts_all_faces_and_variable_axes(self):
        source_a = self.font('variable.ttf', variable=True)
        source_b = self.font('bold.ttf', weight=700)
        collection = TTCollection()
        collection.fonts = [TTFont(source_a), TTFont(source_b)]
        archive = self.root / 'collection.otc'
        try:
            collection.save(archive)
        finally:
            collection.close()
        result = import_file(archive, self.output, archive.name)['data']
        self.assertEqual(result['faceCount'], 2)
        variable = next(face for face in result['faces'] if face['variable'])
        self.assertEqual(variable['axes'][0]['tag'], 'wght')
        self.assertEqual(variable['axes'][0]['max'], 900)
        with TTFont(variable['path']) as font:
            self.assertEqual(font['fvar'].instances[0].coordinates['wght'], 700)
            self.assertIn('gvar', font)

    def test_zip_extracts_collection_and_nested_renamed_web_font(self):
        source = self.font()
        collection = TTCollection()
        collection.fonts = [TTFont(source), TTFont(self.font('bold.ttf', weight=700))]
        face_file = self.root / 'collection.otc'
        try:
            collection.save(face_file)
        finally:
            collection.close()
        other = self.font('web.ttf', family='Web Font')
        with TTFont(other) as font:
            font.flavor = 'woff'; font.save(self.root / 'web.woff')
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, 'w') as archive:
            archive.write(self.root / 'web.woff', 'no-extension')
        outer = self.root / 'outer.zip'
        with zipfile.ZipFile(outer, 'w') as archive:
            archive.write(face_file, 'system/fonts/collection.otc')
            archive.writestr('nested.data', inner.getvalue())
        result = import_file(outer, self.output, outer.name)['data']
        self.assertEqual(result['faceCount'], 3)
        self.assertEqual({row['sourceFormat'] for row in result['faces']}, {'TTC', 'WOFF'})

    def test_partial_role_font_is_usable_and_not_claimed_for_other_roles(self):
        digit = self.font(points=(0xFF11,))
        self.assertTrue(check(digit, 'digit')['valid'])
        self.assertFalse(check(digit, 'latin')['valid'])
        self.assertFalse(check(digit, 'cjk')['valid'])
        roles = inspect(digit)['data']['faces'][0]['coverage']['roles']
        self.assertEqual(roles, {'cjk': False, 'latin': False, 'digit': True})
        result = import_file(digit, self.output, 'clock.ttf')['data']
        self.assertEqual(result['faces'][0]['roleCounts']['digit'], 1)

    def test_traversal_symlink_and_invalid_font_are_reported_without_execution(self):
        source = self.font()
        archive = self.root / 'mixed.zip'
        with zipfile.ZipFile(archive, 'w') as handle:
            handle.write(source, 'good.ttf')
            handle.write(source, '../../escape.ttf')
            symlink = zipfile.ZipInfo('link.ttf')
            symlink.external_attr = (0o120777 << 16)
            handle.writestr(symlink, '/etc/passwd')
            handle.writestr('unsupported.pfb', b'%!PS-AdobeFont-1.0 not convertible')
            handle.writestr('broken.ttf', b'not a font')
        result = import_file(archive, self.output, archive.name)['data']
        self.assertEqual(result['imported'], 1)
        self.assertEqual(len(result['issues']), 4)
        self.assertFalse((self.root / 'escape.ttf').exists())

    def test_sfnt_only_bitmap_is_explicitly_rejected_without_outputs(self):
        source = self.font()
        with TTFont(source) as font:
            del font['glyf']; del font['loca']; font.save(self.root / 'bitmap.ttf')
        with self.assertRaisesRegex(ValueError, '位图'):
            import_file(self.root / 'bitmap.ttf', self.output, 'bitmap.ttf')
        self.assertFalse(self.output.exists())

    def test_publish_failure_rolls_back_new_fonts_and_retains_library(self):
        first = self.font('first.ttf', weight=100)
        second = self.font('second.ttf', weight=900)
        archive = self.root / 'weights.zip'
        with zipfile.ZipFile(archive, 'w') as handle:
            handle.write(first, first.name); handle.write(second, second.name)
        self.output.mkdir()
        existing = self.output / 'Existing.ttf'
        existing.write_bytes(b'keep prior user font')
        real_replace = os.replace
        calls = []
        def fail_second(source, target):
            calls.append(target)
            if len(calls) == 2:
                raise OSError('disk full')
            return real_replace(source, target)
        with patch('font_import_engine.os.replace', side_effect=fail_second):
            with self.assertRaisesRegex(OSError, 'disk full'):
                import_file(archive, self.output, archive.name)
        self.assertEqual(existing.read_bytes(), b'keep prior user font')
        self.assertEqual(list(self.output.iterdir()), [existing])

    def test_real_small_font_donor_gates_canonical_and_legacy(self):
        # Exercise both production shell validators with a host wrapper in the
        # same module layout; no mount or live-device action is performed.
        import re
        module = self.root / 'module'
        binary = module / 'common/python/bin/luoshu-python'
        binary.parent.mkdir(parents=True)
        binary.write_text('#!/bin/sh\nunset PYTHONHOME\nexport PYTHONPATH=' + str(ROOT / 'common/python/lib/python3.14/site-packages') + ':' + str(ROOT / 'common') + '\nexec ' + sys.executable + ' "$@"\n')
        binary.chmod(0o755)
        (module / 'common/font_coverage.py').symlink_to(ROOT / 'common/font_coverage.py')
        safe_text = (ROOT / 'common/legacy_v14_4/font_switch_safe.sh').read_text()
        safe_body = re.search(r'^validate_global\(\) \{.*?^\}', safe_text, re.M | re.S).group()
        for point, accepted in ((0x31, True), (0x4E2D, True), (0x41, True), (0xE001, False)):
            source = self.font(f'sparse-{point}.ttf', points=(point,))
            for checker in ('common/font_check.sh', 'common/legacy_v14_4/font_check.sh'):
                process = subprocess.run(['sh', '-c', '. "$1"; font_validate "$2" text', 'sh', str(ROOT / checker), str(source)], capture_output=True, text=True)
                self.assertEqual(process.returncode, 0, process.stderr)
            env = dict(os.environ, MODDIR=str(module), MODULE_DIR=str(module), LEGACY_DIR=str(ROOT / 'common/legacy_v14_4'))
            for script in (
                '. "$1"; . "$2"; font_validate_global "$3"',
                '. "$1"; safe_validation_restore() { return 1; }; safe_validation_store() { :; }; ' + safe_body + '\nvalidate_global "$3"',
            ):
                result = subprocess.run(['sh', '-c', script, 'sh', str(ROOT / 'common/font_check.sh'), str(ROOT / 'common/font_runtime_policy.sh'), str(source)], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, accepted, (point, result.stdout, result.stderr))

    def test_invalid_web_decompression_size_does_not_publish(self):
        source = self.root / 'bomb.woff2'
        source.write_bytes(b'wOF2' + b'\0' * 12 + struct.pack('>I', MAX_BYTES + 1) + b'\0' * 40)
        with self.assertRaisesRegex(ValueError, '256 MB'):
            import_file(source, self.output, source.name)
        self.assertFalse(self.output.exists())

    def test_native_bridge_dispatches_renamed_font_from_private_cache(self):
        bridge = ROOT / 'common/native_import.sh'
        cache = Path('/data/user/0/io.github.xgl34222220.luoshu.debug/cache/native_import')
        cache.mkdir(parents=True, exist_ok=True)
        source = cache / f'luoshu-import-test-{os.getpid()}.bin'
        make_font(source)
        try:
            env = dict(os.environ, MODDIR=str(ROOT), LUOSHU_IMPORT_PYTHON=sys.executable, LUOSHU_PUBLIC_DIR=str(self.root / 'public'))
            process = subprocess.run(['sh', str(bridge), str(source), 'font.no-suffix'], env=env, capture_output=True, text=True, check=True)
            import json
            result = json.loads(process.stdout)
            self.assertEqual(result['status'], 'ok', process.stderr)
            self.assertEqual(result['data']['imported'], 1)
        finally:
            source.unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
