#!/usr/bin/env python3
"""Different real face contracts, conversion, rollback and owned-task entry."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'common'))
import composite_collection_build as builder
import composite_collection_contract as contract
from fontTools.fontBuilder import FontBuilder
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTCollection, TTFont, newTable
from fontTools.ttLib.tables._f_v_a_r import Axis


CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789中国永Ω'


def fixture(path, index, cff=False, mono=False):
    points = {ord(c): f'f{index}u{ord(c):04x}' for c in CHARS}
    order = ['.notdef', *sorted(points.values(), reverse=bool(index % 2)), 'retainedAlt']
    font = FontBuilder(1000, isTTF=not cff)
    font.setupGlyphOrder(order); font.setupCharacterMap(points)
    glyphs = {}
    for name in order:
        pen = T2CharStringPen(800, None) if cff else TTGlyphPen(None)
        pen.moveTo((20, 0)); pen.lineTo((600, 0))
        pen.lineTo((400 if index % 2 else 600, 700)); pen.lineTo((20, 700)); pen.closePath()
        glyphs[name] = pen.getCharString() if cff else pen.glyph()
    if cff:
        font.setupCFF(f'StockFace{index}', {'FullName': f'Stock Face {index}'}, glyphs, {})
    else:
        font.setupGlyf(glyphs)
    font.setupHorizontalMetrics({name: (800, 20) for name in order})
    font.setupHorizontalHeader(ascent=900 + index, descent=-300 - index)
    font.setupNameTable({'familyName': ('Mono' if mono else 'Stock') + f' Face {index}',
                         'styleName': 'Regular', 'psName': f'StockFace{index}'})
    font.setupOS2(sTypoAscender=900 + index, sTypoDescender=-300 - index,
                 usWinAscent=900 + index, usWinDescent=300 + index,
                 usWeightClass=400 + index * 100)
    font.setupPost(isFixedPitch=int(mono)); font.setupMaxp()
    addOpenTypeFeaturesFromString(font.font,
        f'feature liga {{ sub {points[ord("A")]} {points[ord("B")]} by retainedAlt; }} liga;\n'
        f'feature kern {{ pos {points[ord("A")]} {points[ord("B")]} -30; }} kern;')
    from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
    variation = CmapSubtable.newSubtable(14)
    variation.platformID = 0; variation.platEncID = 5; variation.language = 0
    variation.cmap = {}; variation.uvsDict = {0xFE00: [(ord('中'), 'retainedAlt')]}
    font.font['cmap'].tables.append(variation)
    font.save(path)


def outline(font, char=None, name=None):
    glyphs = font.getGlyphSet()
    pen = DecomposingRecordingPen(glyphs)
    glyphs[name or font.getBestCmap()[ord(char)]].draw(pen)
    return pen.value


class CollectionBuildTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'donor.ttf'; fixture(self.source, 1)
        self.stock = self.root / 'stock.ttc'; self.output = self.root / 'output.ttc'
        self.workspace = self.root / 'work'; self.workspace.mkdir()

    def collection(self, specifications=(dict(index=0), dict(index=2))):
        collection = TTCollection(); collection.fonts = []
        for number, spec in enumerate(specifications):
            path = self.root / f'stock-{number}.font'; fixture(path, **spec)
            collection.fonts.append(TTFont(path))
        try:
            collection.save(self.stock)
        finally:
            collection.close()

    def run_build(self):
        return builder.build(self.source, self.stock, self.output, self.workspace,
                             'request-collection', '/system/fonts/NotoSansCJK-Regular.ttc')

    def test_different_face_indexes_keep_layout_uvs_coverage_style_and_frame(self):
        self.collection()
        report = self.run_build()
        self.assertEqual([0, 1], [face['index'] for face in report['faces']])
        for index in (0, 1):
            with TTFont(self.stock, fontNumber=index) as original, TTFont(self.output, fontNumber=index) as result:
                self.assertEqual(builder.protected(original), builder.protected(result))
                self.assertEqual(original.getBestCmap(), result.getBestCmap())
                self.assertNotEqual(outline(original, '中'), outline(result, '中'))
                self.assertEqual(outline(original, 'Ω'), outline(result, 'Ω'))
                self.assertEqual(outline(original, name='retainedAlt'), outline(result, name='retainedAlt'))
                self.assertEqual(400 + index * 200, result['OS/2'].usWeightClass)
        self.assertEqual(builder.sha(self.output), report['outputSha256'])

    def test_cff_stock_accepts_true_type_donor_and_preserves_cid_independent_order(self):
        self.collection((dict(index=0, cff=True), dict(index=2, cff=True)))
        report = self.run_build()
        self.assertTrue(all(face['mode'] == 'compiled' for face in report['faces']))
        with TTFont(self.stock, fontNumber=1) as original, TTFont(self.output, fontNumber=1) as result:
            self.assertIn('CFF ', result)
            self.assertEqual(builder.protected(original), builder.protected(result))
            self.assertNotEqual(outline(original, 'A'), outline(result, 'A'))

    def test_true_type_stock_accepts_cff_donor(self):
        fixture(self.source, 1, cff=True); self.collection()
        self.run_build()
        with TTFont(self.output, fontNumber=0) as result:
            self.assertIn('glyf', result)

    def test_collection_donor_selects_its_cjk_face(self):
        first = self.root / 'latin-only.ttf'
        fixture(first, 0)
        collection = TTCollection()
        collection.fonts = [TTFont(first), TTFont(self.source)]
        for table in collection.fonts[0]['cmap'].tables:
            if table.isUnicode() and table.format != 14:
                for letter in '中国永':
                    table.cmap.pop(ord(letter), None)
        source_collection = self.root / 'donor.ttc'
        collection.save(source_collection); collection.close()
        self.source = source_collection
        self.collection()
        self.assertEqual(1, self.run_build()['sourceFace'])

    def test_cff_width_uses_stock_private_nominal_and_default_widths(self):
        self.collection((dict(index=0, cff=True),))
        collection = TTCollection(self.stock)
        top = collection.fonts[0]['CFF '].cff.topDictIndex[0]
        top.Private.nominalWidthX = 107
        top.Private.defaultWidthX = 800
        name_a = collection.fonts[0].getBestCmap()[ord('A')]
        for name in top.CharStrings.keys():
            char = top.CharStrings[name]
            char.decompile()
            char.program[0] = (700 if name == name_a else 800) - 107
        collection.fonts[0]['hmtx'][name_a] = (700, 20)
        collection.save(self.stock); collection.close()
        with TTFont(self.source) as font:
            font['hmtx'][font.getBestCmap()[ord('A')]] = (733, 20)
            font.save(self.source)
        self.run_build()
        with TTFont(self.output, fontNumber=0) as result:
            top = result['CFF '].cff.topDictIndex[0]
            for letter, expected in (('A', 733), ('中', 800)):
                char = top.CharStrings[result.getBestCmap()[ord(letter)]]
                char.draw(DecomposingRecordingPen(None))
                self.assertEqual(expected, char.width)
                self.assertEqual(expected, result['hmtx'][result.getBestCmap()[ord(letter)]][0])

    def test_monospace_face_retains_original_outlines_at_its_index(self):
        self.collection((dict(index=0), dict(index=2, mono=True)))
        report = self.run_build()
        self.assertEqual('retained-specialized', report['faces'][1]['mode'])
        with TTFont(self.stock, fontNumber=1) as original, TTFont(self.output, fontNumber=1) as result:
            self.assertEqual(outline(original, '中'), outline(result, '中'))
            self.assertEqual(builder.protected(original), builder.protected(result))

    def test_missing_donor_character_keeps_existing_stock_glyph(self):
        with TTFont(self.source) as font:
            for table in font['cmap'].tables:
                if table.isUnicode() and table.format != 14:
                    table.cmap.pop(ord('永'), None)
            font.save(self.source)
        self.collection(); report = self.run_build()
        self.assertGreater(report['faces'][0]['uncovered'], 0)
        with TTFont(self.stock, fontNumber=0) as original, TTFont(self.output, fontNumber=0) as result:
            self.assertEqual(outline(original, '永'), outline(result, '永'))

    def test_variable_stock_rejected_without_destroying_old_output(self):
        self.collection()
        collection = TTCollection(self.stock)
        font = collection.fonts[1]; variable = newTable('fvar'); axis = Axis()
        axis.axisTag='wght'; axis.minValue=100; axis.defaultValue=400
        axis.maxValue=900; axis.flags=0; axis.axisNameID=256
        variable.axes=[axis]; variable.instances=[]; font['fvar']=variable
        collection.save(self.stock); collection.close()
        self.output.write_bytes(b'previous generation')
        with self.assertRaisesRegex(ValueError, '可变目标面'):
            self.run_build()
        self.assertEqual(b'previous generation', self.output.read_bytes())
        self.assertEqual([], list(self.workspace.iterdir()))

    def test_ambiguous_stock_encoded_slot_is_rejected(self):
        self.collection()
        with TTFont(self.source) as font:
            glyph=font['glyf'][font.getBestCmap()[ord('B')]]
            glyph.coordinates[2]=(500, 700)
            font.save(self.source)
        collection = TTCollection(self.stock)
        for table in collection.fonts[0]['cmap'].tables:
            if table.isUnicode() and table.format != 14:
                table.cmap[ord('B')]=table.cmap[ord('A')]
        collection.save(self.stock); collection.close()
        with self.assertRaisesRegex(ValueError, '共享字形'):
            self.run_build()

    def test_aliases_with_equivalent_donor_outlines_are_supported(self):
        self.collection()
        collection = TTCollection(self.stock)
        for table in collection.fonts[0]['cmap'].tables:
            if table.isUnicode() and table.format != 14:
                table.cmap[ord('B')]=table.cmap[ord('A')]
        collection.save(self.stock); collection.close()
        self.assertEqual('PASS', self.run_build()['result'])

    def test_shared_uncovered_or_other_role_slot_is_kept_stock(self):
        self.collection()
        collection = TTCollection(self.stock)
        for table in collection.fonts[0]['cmap'].tables:
            if table.isUnicode() and table.format != 14:
                table.cmap[ord('Ω')] = table.cmap[ord('A')]
                table.cmap[0x3400] = table.cmap[ord('中')]
        collection.save(self.stock); collection.close()
        report = self.run_build()
        self.assertEqual(2, report['faces'][0]['retainedSharedSlots'])
        with TTFont(self.stock, fontNumber=0) as original, TTFont(self.output, fontNumber=0) as result:
            for letter in 'AΩ中':
                self.assertEqual(outline(original, letter), outline(result, letter))
            self.assertNotEqual(outline(original, '国'), outline(result, '国'))

    def test_donor_outside_stock_frame_is_rejected_without_touching_output(self):
        self.collection()
        with TTFont(self.source) as font:
            glyph=font['glyf'][font.getBestCmap()[ord('中')]]
            glyph.coordinates[2]=(400, 1800)
            font.save(self.source)
        self.output.write_bytes(b'previous generation')
        with self.assertRaisesRegex(ValueError, '超出'):
            self.run_build()
        self.assertEqual(b'previous generation', self.output.read_bytes())

    def test_source_change_during_build_cannot_publish(self):
        self.collection(); original=builder.replace_face
        def modify(*args):
            result=original(*args)
            with self.source.open('ab') as stream: stream.write(b'changed')
            return result
        self.output.write_bytes(b'previous generation')
        with patch.object(builder, 'replace_face', side_effect=modify), self.assertRaisesRegex(ValueError, '已变化'):
            self.run_build()
        self.assertEqual(b'previous generation', self.output.read_bytes())

    def test_donor_advance_outside_stock_header_is_rejected(self):
        self.collection()
        with TTFont(self.source) as font:
            font['hmtx'][font.getBestCmap()[ord('A')]] = (900, 20)
            font.save(self.source)
        self.output.write_bytes(b'previous generation')
        with self.assertRaisesRegex(ValueError, '水平度量超出'):
            self.run_build()
        self.assertEqual(b'previous generation', self.output.read_bytes())

    def test_active_module_requires_stock_lower_or_mirror(self):
        module=self.root/'module'; (module/'config').mkdir(parents=True)
        (module/'system/fonts').mkdir(parents=True)
        (module/'system/fonts/old.ttf').write_bytes(b'old payload')
        (module/'config/active_font.conf').write_text('mix\n')
        with patch.dict(os.environ, {'LUOSHU_COLLECTION_STOCK_ROOT':'/'}), patch.object(
                builder.stock_inventory, '_pick_actual_root', side_effect=builder.stock_inventory.InventoryError('no lower')) as pick:
            with self.assertRaisesRegex(RuntimeError, 'no lower'):
                builder.stock_path(module, '/system/fonts/NotoSansCJK-Regular.ttc')
            self.assertTrue(pick.call_args.args[2])

    def test_alias_entry_builds_actual_collection_inside_owned_stage(self):
        self.collection()
        module=self.root/'module'; (module/'common').mkdir(parents=True)
        for path in (ROOT/'common').iterdir():
            if path.is_file() or path.name == 'legacy_v14_4':
                (module/'common'/path.name).symlink_to(path)
        scope=module/'cache/tasks/owned'; scope.mkdir(parents=True)
        (scope/'.luoshu-task-owner').write_text('owned')
        target='/system/fonts/NotoSansCJK-Regular.ttc'
        stock_root=self.root/'stock-root'; actual=stock_root/target.lstrip('/')
        actual.parent.mkdir(parents=True); actual.write_bytes(self.stock.read_bytes())
        dest=module/'.legacy-v14-runtime/.font-payload-stage.123'/actual.name
        dest.parent.mkdir(parents=True)
        env=dict(os.environ, MODDIR=str(module), LUOSHU_REAL_MODDIR=str(module),
                 LUOSHU_COLLECTION_STOCK_ROOT=str(stock_root), LUOSHU_MIX_REQUEST_ID='owned-request',
                 LUOSHU_TASK_SCOPE='owned', LUOSHU_TASK_WORK_DIR=str(scope),
                 LUOSHU_TASK_HELPER=str(ROOT/'common/task_scope.py'))
        call=subprocess.run(['sh','-c','. "$1"; _font_alias "$2" "$3"','test',
                             str(ROOT/'common/legacy_v14_4/rom_adapters.sh'),str(self.source),str(dest)],
                            env=env,capture_output=True,text=True)
        self.assertEqual(0,call.returncode,call.stdout+call.stderr)
        self.assertEqual(2,builder.collection_faces(dest))
        report=json.loads(dest.with_name(dest.name+'.luoshu-collection.json').read_text())
        self.assertEqual(target,report['target']); self.assertEqual('owned-request',report['requestId'])
        self.assertEqual([],list(scope.glob('collection-*')))

    def test_finalize_proof_binds_indexes_request_path_and_payload_bytes(self):
        self.collection(); report=self.run_build()
        payload=self.root/'.luoshu-mix-stage'; path=payload/'system/fonts/NotoSansCJK-Regular.ttc'
        path.parent.mkdir(parents=True); path.write_bytes(self.output.read_bytes())
        sidecar=path.with_name(path.name+'.luoshu-collection.json')
        sidecar.write_text(json.dumps(report))
        checked=contract.validate(payload,'request-collection',self.root/'empty-stock')
        self.assertEqual('PASS',checked['result'])
        self.assertTrue(checked['collections'][0]['generatedContractVerified'])
        self.assertEqual('FAIL',contract.validate(payload,'another-request',self.root/'empty-stock')['result'])
        data=bytearray(path.read_bytes()); data[-1]^=1; path.write_bytes(data)
        checked=contract.validate(payload,'request-collection',self.root/'empty-stock')
        self.assertEqual('FAIL',checked['result']); self.assertIn('生成证明',checked['errors'][0]['reason'])


if __name__ == '__main__':
    unittest.main()
