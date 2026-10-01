#!/usr/bin/env python3
"""Request-local source measurement reuse: equivalence and unchanged safety gates."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'common'), str(ROOT / 'scripts')]
import fixed_static_xml_compiler as fixed
import fixed_static_xml_compiler_test as fixture
import universal_font_compiler as compiler
import universal_font_compiler_test as fonts


class MeasurementCacheTest(unittest.TestCase):
    def setUp(self):
        self.case = fixture.FixedStaticCompilerTest('test_honest_static_source_at_different_xml_weight')
        self.case.setUp()
        self.addCleanup(self.case.tearDown)
        self.mapping = {self.case.logical: self.case.stock}

    def prepare(self, unit, cache=None):
        return fixed.prepare_unit(unit, self.mapping, False, cache=cache)

    def test_reuses_source_profile_but_revalidates_and_measures_each_stock_route(self):
        cache = {}
        with patch.object(compiler, '_profile_from_font', wraps=compiler._profile_from_font) as profile, \
                patch.object(compiler, '_verify_stock_identity', wraps=compiler._verify_stock_identity) as identity, \
                patch.object(compiler, '_stock_geometry_font', wraps=compiler._stock_geometry_font) as geometry:
            first = self.prepare(self.case.unit(), cache)
            second = self.prepare(self.case.unit(weight=700), cache)
        self.assertEqual(profile.call_count, 5)  # Two original-stock + two measured-stock + one source.
        self.assertEqual(identity.call_count, 2)
        self.assertEqual(geometry.call_count, 2)
        self.assertEqual(first['binding'], second['binding'])

    def test_eager_reference_lazy_and_cached_outputs_are_identical(self):
        unit = self.case.unit()
        opened = compiler._open_face
        def eager(path, face, *, lazy=False):
            return opened(path, face, lazy=False if Path(path) == self.case.source else lazy)
        with patch.object(compiler, '_open_face', side_effect=eager):
            reference = self.prepare(unit)
        cached = self.prepare(unit, {})
        self.assertEqual(reference['contract'], cached['contract'])
        self.assertEqual(reference['binding'], cached['binding'])
        a = fixed.compile_prepared(reference, self.case.root / 'reference', {})
        b = fixed.compile_prepared(cached, self.case.root / 'cached', {})
        self.assertEqual(Path(a['output']).read_bytes(), Path(b['output']).read_bytes())

    def test_returned_profile_mutation_does_not_poison_other_routes(self):
        unit = self.case.unit()
        cache = {}
        first = self.prepare(unit, cache)
        expected = deepcopy(first['contract'])
        first['contract']['source']['profile']['metrics']['unitsPerEm'] = -1
        first['geometry']['lineContract']['hheaAscent'] = -1
        second = self.prepare(unit, cache)
        self.assertEqual(expected, second['contract'])

    def test_role_intersections_keep_independent_probe_results(self):
        shared = list(map(ord, '中永国文'))
        fixture.add_points(self.case.source, shared)
        fixture.add_points(self.case.stock, shared)
        cache = {}
        for role in ['ui-sans', 'cjk', 'latin', 'cjk', 'ui-sans']:
            # Focused compiler fixture, like the existing four-Han CJK cases;
            # four probes do not claim a full planner-qualified UI repertoire.
            unit = self.case.unit()
            unit['target']['role'] = role
            self.assertEqual(self.prepare(unit)['contract'], self.prepare(unit, cache)['contract'])

    def test_different_stock_axis_locations_are_still_measured_separately(self):
        fonts.make_font(self.case.stock, family='Synthetic OEM', variable=True)
        cache = {}
        locations = []
        with patch.object(compiler, '_stock_geometry_font', wraps=compiler._stock_geometry_font) as geometry:
            for weight in [100, 650, 900]:
                unit = self.case.unit(weight=weight)
                unit['artifact']['originalStockAxes'] = [{'tag': 'wght', 'stylevalue': weight}]
                prepared = self.prepare(unit, cache)
                self.assertEqual(self.prepare(unit)['contract'], prepared['contract'])
                locations.append(prepared['contract']['stock']['location'])
        self.assertEqual(locations, [{'wght': 100}, {'wght': 650}, {'wght': 900}])
        self.assertEqual(geometry.call_count, 6)

    def test_changed_source_bytes_are_rejected_even_with_populated_measurements(self):
        unit, cache = self.case.unit(), {}
        self.prepare(unit, cache)
        self.case.source.write_bytes(self.case.source.read_bytes() + b'changed')
        with self.assertRaisesRegex(compiler.CompilerError, '源字体内容已变化'):
            self.prepare(unit, cache)

    def test_changed_stock_bytes_and_frozen_metrics_remain_rejected(self):
        unit, cache = self.case.unit(), {}
        self.prepare(unit, cache)
        altered = deepcopy(unit)
        altered['target']['targetContract']['metrics']['upem'] += 1
        with self.assertRaisesRegex(compiler.CompilerError, 'UPEM'):
            self.prepare(altered, cache)
        self.case.stock.write_bytes(self.case.stock.read_bytes() + b'changed')
        with self.assertRaisesRegex(compiler.CompilerError, 'digest mismatch'):
            self.prepare(unit, cache)

    def test_changed_request_selection_does_not_reuse_prior_source_profile(self):
        cache = {}
        unit = self.case.unit()
        self.prepare(unit, cache)
        different = deepcopy(unit)
        different['target']['source']['mixedSelection']['requestId'] = 'a-new-request'
        with patch.object(compiler, '_profile_from_font', wraps=compiler._profile_from_font) as profile:
            self.prepare(different, cache)
        self.assertEqual(profile.call_count, 3)

    def test_compile_calls_own_separate_measurement_contexts(self):
        plan, route = self.case.routed_plan()
        contexts = []
        prepare = fixed.prepare_unit
        def tracked(*args, **kwargs):
            contexts.append(kwargs.get('cache'))
            return prepare(*args, **kwargs)
        with patch.object(fixed, 'prepare_unit', side_effect=tracked):
            first = compiler.compile_all(plan, route, self.mapping, self.case.root / 'one', False)
            second = compiler.compile_all(plan, route, self.mapping, self.case.root / 'two', False)
        self.assertEqual(first['artifactMap'], second['artifactMap'])
        self.assertEqual(len(contexts), 4)
        self.assertIs(contexts[0], contexts[1])
        self.assertIs(contexts[2], contexts[3])
        self.assertIsNot(contexts[0], contexts[2])


if __name__ == '__main__':
    unittest.main()
