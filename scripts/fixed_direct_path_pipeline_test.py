#!/usr/bin/env python3
"""Dual XML/direct-file deployment with generated fonts; no device coverage claim."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import os
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'common'), str(ROOT / 'scripts')]
from fontTools.ttLib import TTFont
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.varLib.instancer import instantiateVariableFont
import fixed_static_xml_compiler_test as fixture
import universal_font_compiler_test as fonts
import fixed_static_xml_router as router
import universal_font_compiler as compiler
import universal_font_deployment as deploy
import universal_font_runtime_verify as runtime


class DirectPathTest(unittest.TestCase):
    def setUp(self):
        self.case = fixture.FixedStaticCompilerTest()
        self.case.setUp()
        self.addCleanup(self.case.tearDown)
        self.root = self.case.root
        # Distinct source topology makes direct-path outline replacement observable.
        with TTFont(self.case.source) as font:
            name = font.getBestCmap()[ord('A')]
            pen = TTGlyphPen(None)
            pen.moveTo((40, -120)); pen.lineTo((570, -120)); pen.lineTo((300, 720)); pen.closePath()
            font['glyf'][name] = pen.glyph()
            font.save(self.case.source)

    def plan(self, variable=False):
        if variable:
            fonts.make_font(self.case.stock, family='OEM Direct', variable=True)
        plan, fixed = self.case.routed_plan()
        route = router.build_route_plan(plan, fixed['legacyRoutePlan'], matching_weights=True)
        return plan, route

    def pipeline(self, variable=False):
        plan, route = self.plan(variable)
        manifest = compiler.compile_all(plan, route, {self.case.logical: self.case.stock}, self.root / 'compiled', False)
        self.assertTrue(manifest['summary']['deploymentReady'], manifest)
        mapping = self.root / 'stock-map.json'
        mapping.write_text(json.dumps({self.case.logical: str(self.case.stock)}))
        payload = self.root / 'payload'
        with patch.dict(os.environ, {'LUOSHU_STOCK_FONT_MAP': str(mapping)}):
            deployment = deploy.build_deployment(plan, route, manifest, payload)
            deploy.validate_deployment(deployment, plan, route, manifest, payload)
        return plan, route, manifest, deployment, payload

    def verify(self, plan, route, manifest, deployment, payload):
        state = {'state': 'active', 'deploymentId': deployment['deploymentId'], 'payloadDigest': deployment['payloadDigest']}
        return runtime.verify(plan, manifest, deployment, runtime_conf=state,
            mount_state={**state, 'state': 'mounted'},
            font_dump='\n'.join('style = FontStyle { weight=400, slant=0}, path = ' + f['logicalPath'] for f in deployment['files']),
            mountinfo={}, active_font='mix', visible_root=payload, boot_id='synthetic-boot', fixed_route=route)

    def test_xml_backed_static_font_has_separate_original_path_shell_and_retained_fallback(self):
        before = self.case.stock.read_bytes()
        plan, route, manifest, deployment, payload = self.pipeline()
        self.assertEqual(route['directPathTargets'], [self.case.logical])
        direct_id = manifest['physicalTargetMap'][self.case.logical]
        direct = next(a for a in manifest['artifacts'] if a['artifactId'] == direct_id)
        self.assertEqual(direct['deploymentKinds'], ['physical-slot'])
        self.assertEqual(direct['mode'], 'stock-shell')
        self.assertEqual(direct['contract']['directPathContract']['sourceIntentSha256'],
                         compiler._canonical_hash(plan['targets'][self.case.logical]['source']['mixedSelection']))
        self.assertNotIn(direct_id, manifest['staticXmlBindings'])
        physical = payload / self.case.logical.lstrip('/')
        self.assertNotEqual(physical.read_bytes(), before)
        with TTFont(physical) as font:
            self.assertEqual(len(font['glyf'][font.getBestCmap()[65]].getCoordinates(font['glyf'])[0]), 3)
        xml = ET.parse(payload / 'system/etc/fonts.xml')
        self.assertTrue(next(xml.iter('font')).text.startswith('LuoShuFixed-'))
        originals = [f for f in deployment['files'] if f['kind'] == 'xml-original']
        self.assertEqual((payload / originals[0]['payloadPath']).read_bytes(), before)
        result = self.verify(plan, route, manifest, deployment, payload)
        self.assertEqual(result['grade'], 'WARN', result)
        physical.unlink()
        result = self.verify(plan, route, manifest, deployment, payload)
        self.assertEqual(result['grade'], 'FAIL', result)
        self.assertTrue(any(self.case.logical in f for f in result['failures']))

    def test_runtime_requires_direct_artifact_even_if_xml_assets_are_present(self):
        plan, route, manifest, deployment, payload = self.pipeline()
        incomplete = deepcopy(manifest)
        direct_id = incomplete['physicalTargetMap'][self.case.logical]
        incomplete['artifacts'] = [a for a in incomplete['artifacts'] if a['artifactId'] != direct_id]
        incomplete['manifestId'] = compiler._manifest_id(plan['planId'], route['routeId'], incomplete['artifacts'], [])
        changed = deepcopy(deployment)
        changed['artifactManifestId'] = incomplete['manifestId']
        # Isolate membership checking after already-tested deployment hash gates.
        with patch.object(deploy, 'validate_payload_integrity'), \
                self.assertRaisesRegex(runtime.VerificationError, 'direct-path artifact membership'):
            self.verify(plan, route, incomplete, changed, payload)

    def test_variable_original_preserves_axis_domain_and_fixed_selected_glyphs(self):
        plan, route, manifest, deployment, payload = self.pipeline(variable=True)
        physical = payload / self.case.logical.lstrip('/')
        direct = next(a for a in manifest['artifacts'] if a['artifactId'] == manifest['physicalTargetMap'][self.case.logical])
        self.assertEqual(direct['report']['directPathCompatibility']['status'], 'ready')
        samples = []
        with TTFont(physical) as font, TTFont(self.case.stock) as stock:
            self.assertEqual(font.getTableData('fvar'), stock.getTableData('fvar'))
            for weight in (100, 400, 900):
                instance = instantiateVariableFont(font, {'wght': weight}, inplace=False)
                name = instance.getBestCmap()[65]
                samples.append(list(instance['glyf'][name].getCoordinates(instance['glyf'])[0]))
                instance.close()
        self.assertTrue(all(v == samples[0] for v in samples))
        self.assertEqual(self.verify(plan, route, manifest, deployment, payload)['grade'], 'WARN')

    def test_unsafe_containers_roles_styles_aliases_and_axes_are_explicitly_uncovered(self):
        plan, route = self.plan()
        target = plan['targets'][self.case.logical]
        cases = []
        for field, value in [('format', 'TTC'), ('faceIndex', 1), ('italic', True)]:
            t = deepcopy(target); t['targetContract'][field] = value; cases.append(t)
        t = deepcopy(target); t['xmlRefs'][0]['style'] = 'italic'; cases.append(t)
        t = deepcopy(target); t['xmlRefs'][0]['index'] = 1; cases.append(t)
        t = deepcopy(target); t['xmlScopedTarget'] = {'role': 'cjk'}; cases.append(t)
        t = deepcopy(target); t['role'] = 'symbol'; cases.append(t)
        t = deepcopy(target); t['path'] = '/data/fonts/files/Test.ttf'; cases.append(t)
        t = deepcopy(target); t['targetContract']['stockIdentity']['provenance']['aliasChain'] = [{'path': '/system/fonts/alias.ttf'}]; cases.append(t)
        t = deepcopy(target); t['targetContract']['variable'] = True
        t['targetContract']['metrics']['variationAxes'] = [{'tag': 'ital', 'minimum': 0, 'default': 0, 'maximum': 1}]; cases.append(t)
        for t in cases:
            record = router._direct_path_record(t)
            self.assertEqual(record['state'], 'unsupported', t)
            self.assertTrue(record['reason'])
        unsafe = deepcopy(plan)
        unsafe['targets'][self.case.logical]['xmlScopedTarget'] = {'role': 'cjk'}
        router._add_direct_path_coverage(route, unsafe)
        self.assertEqual(route['directPathTargets'], [])
        self.assertEqual(route['summary']['directPathUnsupportedCount'], 1)

    def test_rehashed_unplanned_direct_path_is_rejected(self):
        plan, route = self.plan()
        route['directPathCoverage']['targets'][self.case.logical]['contract']['faceIndex'] = 1
        route['routeId'] = router._id(route)
        with self.assertRaisesRegex(router.ERROR, 'sealed source plan'):
            router.validate_route_plan(route, plan)

    def test_old_matching_revision_remains_valid_without_new_direct_claims(self):
        plan, route = self.plan()
        old = router.build_route_plan(plan, route['legacyRoutePlan'], matching_weights=True, direct_paths=False)
        self.assertEqual(old['routeRevision'], 4)
        self.assertNotIn('directPathTargets', old)
        router.validate_route_plan(old, plan)
        self.assertFalse(any('physical-slot' in u['deploymentKinds'] for u in compiler._collect_units(plan, old)))

    def test_direct_selector_mutation_is_rejected(self):
        plan, route = self.plan(variable=True)
        contract = route['directPathCoverage']['targets'][self.case.logical]['contract']
        with TTFont(self.case.stock) as font:
            font['fvar'].axes[0].maxValue = 950
            changed = self.root / 'changed.ttf'; font.save(changed)
        with self.assertRaisesRegex(compiler.CompilerError, 'axis domain'):
            compiler._direct_path_snapshot(changed, contract)


if __name__ == '__main__':
    unittest.main()
