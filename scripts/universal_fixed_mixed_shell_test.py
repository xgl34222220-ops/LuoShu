#!/usr/bin/env python3
"""Compiler-only fixed-role stock-shell checks with synthetic variable fonts."""
from copy import deepcopy
from pathlib import Path
import hashlib
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'common'), str(ROOT / 'scripts')]
from fontTools.fontBuilder import FontBuilder
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.ttLib.tables._f_v_a_r import Axis
from fontTools.ttLib.tables import otTables as ot
from fontTools.varLib.instancer import instantiateVariableFont
import legacy_composite_layout_test as layout
import universal_font_compiler as compiler
import universal_font_compiler_test as fixture


class FixedMixedShellTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='fixed-mixed-shell-')
        self.root = Path(self.tmp.name)
        self.source, self.stock = self.root / 'source.ttf', self.root / 'stock.ttf'
        original = layout.CHARS
        try:
            layout.CHARS = ''.join(map(chr, range(32, 127))) + '中永国ΩÀ'
            layout.fixture(self.source)
            layout.fixture(self.stock)
        finally:
            layout.CHARS = original
        with TTFont(self.stock) as font:
            order = list(font.getGlyphOrder())
            builder = FontBuilder(font=font)
            builder.setupVerticalMetrics({name: (1000, 100) for name in order})
            builder.setupVerticalHeader(ascent=1000, descent=-300)
            # Non-cmap ligature output is deliberately stock-only. Keeping GSUB
            # is a compatibility choice, not evidence every Latin shaping glyph changed.
            name = 'f_i'
            font['glyf'][name] = deepcopy(font['glyf'][font.getBestCmap()[ord('f')]])
            font.setGlyphOrder([*order, name])
            font['hmtx'].metrics[name] = (700, 50)
            font['vmtx'].metrics[name] = (1000, 100)
            addOpenTypeFeaturesFromString(font, 'feature liga { sub u0066 u0069 by f_i; } liga;')
            font.save(self.stock)
        layout.add_metric_variations(self.stock, explicit=True)
        with TTFont(self.stock) as font:
            font.ensureDecompiled()
            for index, (tag, low, default, high) in enumerate((('wdth', 75, 100, 125), ('slnt', -10, 0, 0), ('ital', 0, 0, 1))):
                axis = Axis()
                axis.axisTag, axis.minValue, axis.defaultValue, axis.maxValue = tag, low, default, high
                axis.flags, axis.axisNameID = 0, 257 + index
                font['fvar'].axes.append(axis)
            for tag in ('HVAR', 'VVAR'):
                regions = font[tag].table.VarStore.VarRegionList
                for region in regions.Region:
                    for _ in range(3):
                        support = ot.VarRegionAxis()
                        support.StartCoord = support.PeakCoord = support.EndCoord = 0
                        region.VarRegionAxis.append(support)
                regions.RegionAxisCount = 4
            for char in ('A', '1', '中'):
                name = font.getBestCmap()[ord(char)]
                coordinates = font['glyf'][name].getCoordinates(font['glyf'])[0]
                deltas = [(80 if x > 100 else 0, 0) for x, _ in coordinates] + [(0, 0)] * 4
                font['gvar'].variations[name] = [TupleVariation({tag: support}, deltas)
                    for tag, support in [('wght', (0, 1, 1)), ('wdth', (0, 1, 1)),
                                         ('slnt', (-1, -1, 0)), ('ital', (0, 1, 1))]]
            font.save(self.stock)
        self.logical = '/system/fonts/SyntheticUiVF.ttf'
        slot = fixture.slot_from_stock(self.logical, self.stock, family='sans-serif', source_xml=None,
                                       declared='SyntheticUiVF.ttf')
        self.plan, self.route = fixture.build_plans(self.source, slot, 'latin', None)
        self.target = self.plan['targets'][self.logical]
        self.target['source']['mixedSelection'] = {
            'policy': 'fixed-composite-selection-v1', 'requestId': 'synthetic-request',
            'fontSha256': hashlib.sha256(self.source.read_bytes()).hexdigest(),
            'roles': {role: {'mode': 'fixed', 'selectedAxes': {'wght': 400}}
                      for role in ('cjk', 'latin', 'digit')},
        }

    def tearDown(self):
        self.tmp.cleanup()

    def compile(self, target=None, weight=400):
        target = deepcopy(target or self.target)
        artifact = compiler._physical_artifact(target, self.plan)
        artifact['requiredWeight'] = weight
        unit = {'artifact': artifact, 'target': target, 'deploymentKinds': ['physical-slot'], 'routeNodes': []}
        out = self.root / 'out'
        out.mkdir(exist_ok=True)
        return compiler._compile_unit(unit, {self.logical: self.stock}, out, False)

    @staticmethod
    def coordinates(font, char):
        return tuple(font['glyf'][font.getBestCmap()[ord(char)]].getCoordinates(font['glyf'])[0])

    def test_selected_roles_are_constant_but_untouched_font_variations_survive(self):
        before = hashlib.sha256(self.stock.read_bytes()).hexdigest()
        result = self.compile()
        self.assertEqual(result['status'], 'ready', result)
        self.assertEqual(result['mode'], 'stock-shell')
        self.assertIsNotNone(result['report']['fixedSelection'])
        with TTFont(result['output']) as output, TTFont(self.stock) as stock:
            self.assertEqual(output.getTableData('GSUB'), stock.getTableData('GSUB'))
            self.assertEqual(output['glyf']['f_i'].compile(output['glyf']), stock['glyf']['f_i'].compile(stock['glyf']))
            # Stock shaping substitutions remain stock unless separately handled.
            snapshots = []
            locations = [{'wght': weight, 'wdth': 100, 'slnt': 0, 'ital': 0} for weight in (100, 250, 400, 650, 900)]
            locations += [dict(wght=400, wdth=75, slnt=0, ital=0), dict(wght=900, wdth=125, slnt=-10, ital=1),
                          dict(wght=550, wdth=112.5, slnt=-5, ital=.5)]
            for location in locations:
                instance = instantiateVariableFont(output, location, inplace=False)
                original = instantiateVariableFont(stock, location, inplace=False)
                try:
                    sample = []
                    for char in ('A', '1'):
                        name = instance.getBestCmap()[ord(char)]
                        sample.append((self.coordinates(instance, char), instance['hmtx'].metrics[name], instance['vmtx'].metrics[name]))
                    snapshots.append(sample)
                    name = instance.getBestCmap()[ord('中')]
                    self.assertEqual(self.coordinates(instance, '中'), self.coordinates(original, '中'))
                    self.assertEqual(instance['hmtx'].metrics[name], original['hmtx'].metrics[name])
                    self.assertEqual(instance['vmtx'].metrics[name], original['vmtx'].metrics[name])
                finally:
                    instance.close()
                    original.close()
            self.assertTrue(all(sample == snapshots[0] for sample in snapshots))
            for tag, field in (('HVAR', 'AdvWidthMap'), ('VVAR', 'AdvHeightMap')):
                self.assertEqual(layout.metric_delta(output, tag, field, 'A', 1.0), 0)
                self.assertEqual(layout.metric_delta(output, tag, field, '中', 1.0), 300)
        self.assertEqual(hashlib.sha256(self.stock.read_bytes()).hexdigest(), before)

    def test_mvar_extreme_line_clipping_is_rejected_without_removing_mvar(self):
        for tag, delta in [('hasc', -800), ('hdsc', 300), ('hcla', -500), ('hcld', -250)]:
            with self.subTest(tag=tag), TTFont(self.stock) as font:
                mvar = newTable('MVAR')
                mvar.table = ot.MVAR()
                mvar.table.VarStore = deepcopy(font['HVAR'].table.VarStore)
                mvar.table.VarStore.VarData[0].Item[0] = [delta]
                record = ot.MetricsValueRecord()
                record.ValueTag, record.VarIdx = tag, 0
                mvar.table.ValueRecord = [record]
                font['MVAR'] = mvar
                with self.assertRaisesRegex(compiler.CompilerError, 'line budget'):
                    compiler._fixed_shell_line_budget(font, {'importedYMin': -100, 'importedYMax': 700})
                self.assertIn('MVAR', font)
                self.assertEqual(font['MVAR'].table.VarStore.VarData[0].Item[0], [delta])

    def test_unsupported_varc_is_rejected(self):
        with TTFont(self.stock) as font:
            font['VARC'] = newTable('VARC')
            with self.assertRaisesRegex(compiler.CompilerError, 'VARC'):
                compiler._fixed_shell_line_budget(font, {'importedYMin': 0, 'importedYMax': 700})

    def test_generic_static_source_still_cannot_masquerade_as_variable(self):
        target = deepcopy(self.target)
        target['source'].pop('mixedSelection')
        result = self.compile(target)
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('variable', result['reason'])

    def test_policy_hash_tamper_is_rejected(self):
        target = deepcopy(self.target)
        target['source']['mixedSelection']['fontSha256'] = '0' * 64
        self.assertEqual(self.compile(target)['status'], 'blocked')

    def test_fixed_weight_intent_does_not_bypass_true_italic_mismatch(self):
        target = deepcopy(self.target)
        target['risks'] = ['italic-style-mismatch']
        target['targetContract']['italic'] = True
        result = self.compile(target)
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('italic-style-mismatch', result['reason'])

    def test_fixed_selection_can_fill_static_weight_contract_without_relabeling_source(self):
        result = self.compile(weight=700)
        self.assertEqual(result['status'], 'ready', result)
        with TTFont(self.source) as source:
            self.assertEqual(source['OS/2'].usWeightClass, 400)
        self.assertIsNotNone(result['report']['fixedSelection'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
