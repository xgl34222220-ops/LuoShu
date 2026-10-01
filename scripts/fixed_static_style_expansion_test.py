"""Opt-in revision-two style expansion, synthetic OEM/source provenance."""
import copy
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'scripts')]
from fontTools.ttLib import TTFont
import universal_font_compiler_test as fixture
import universal_fixed_mixed_shell_test as shell_fixture
import fixed_static_xml_router as router
import fixed_static_xml_compiler as static
import universal_font_compiler as compiler
import universal_font_deployment as deployment


class ExpansionTest(unittest.TestCase):
    def setUp(self):
        self.f=shell_fixture.FixedMixedShellTest();self.f.setUp();self.addCleanup(self.f.tearDown)
        self.root=self.f.root;self.xml=self.root/'fonts.xml'

    def plan(self,tags='wght,ital',extra=''):
        self.xml.write_text('<familyset><family name="sans-serif"><font supportedAxes="'+tags+'">SyntheticUiVF.ttf'
                            '<axis tag="wdth" stylevalue="100"/></font>'+extra+'</family></familyset>')
        slot=fixture.slot_from_stock(self.f.logical,self.f.stock,family='sans-serif',source_xml='/system/etc/fonts.xml',declared='SyntheticUiVF.ttf')
        if extra:slot['xmlRefs'].append(dict(slot['xmlRefs'][0],weight=700))
        profile=fixture.font_source_profile.build([self.f.source])
        for file in profile['files']:
            for face in file['faces']:face['mixedSelection']=copy.deepcopy(self.f.target['source']['mixedSelection'])
        with patch.object(fixture.font_source_profile,'build',return_value=profile):
            fp,base=fixture.build_plans(self.f.source,slot,'latin',self.xml)
        return fp,router.build_route_plan(fp,base,expand_styles=True)

    def test_production_compile_deployment_and_explicit_italic_original(self):
        plan,route=self.plan();self.assertEqual(route['routeRevision'],2)
        self.assertEqual(route['summary']['representationDeferralCount'],0)
        self.assertEqual(route['summary']['fixedStaticOperationCount'],11)
        self.assertEqual(route['summary']['preservedOriginalStyleCount'],11)
        self.assertEqual(route['summary']['styleWeightDomain'],'discrete-declared-weights')
        manifest=compiler.compile_all(plan,route,{self.f.logical:self.f.stock},self.root/'compiled',False)
        self.assertEqual(manifest['summary']['readyCount'],11)
        self.assertTrue(manifest['summary']['deploymentReady'])
        mapping=self.root/'map.json';mapping.write_text(json.dumps({self.f.logical:str(self.f.stock)}))
        with patch.dict(os.environ,{'LUOSHU_STOCK_FONT_MAP':str(mapping)}):
            payload=self.root/'payload';sealed=deployment.build_deployment(plan,route,manifest,payload)
            deployment.validate_deployment(sealed,plan,route,manifest,payload)
        tree=ET.parse(payload/'system/etc/fonts.xml').getroot()
        self.assertEqual(len(tree),2)
        nodes=list(tree[0]);normal=[n for n in nodes if n.get('style')=='normal'];italic=[n for n in nodes if n.get('style')=='italic']
        self.assertEqual([int(n.get('weight')) for n in normal],list(router.STYLE_WEIGHTS))
        self.assertEqual(len(italic),11)
        for node in normal:
            self.assertNotIn('supportedAxes',node.attrib);self.assertEqual(list(node),[])
            with TTFont(payload/'system/fonts'/node.text) as font:
                self.assertNotIn('fvar',font);self.assertEqual(font['OS/2'].usWeightClass,400)
        for node in italic:
            self.assertTrue(node.text.startswith('LuoShu-Original-'))
            self.assertEqual((payload/'system/fonts'/node.text).read_bytes(),self.f.stock.read_bytes())
            self.assertEqual({a.get('tag'):float(a.get('stylevalue')) for a in node},
                             {'wdth':100,'wght':int(node.get('weight')),'ital':1})
        self.assertEqual(tree[1][0].get('supportedAxes'),'wght,ital')

    def test_weight_only_expands_without_inventing_true_italic(self):
        plan,route=self.plan('wght')
        self.assertFalse(route['documents']['/system/etc/fonts.xml']['styleExpansions'][0]['preserveItalic'])
        self.assertEqual(len(compiler._collect_units(plan,route)),11)

    def test_same_group_peer_rejected_before_expansion(self):
        with self.assertRaisesRegex(router.ERROR,'ambiguous'):
            self.plan(extra='<font weight="700">SyntheticUiVF.ttf</font>')

    def test_requested_italic_needs_real_original_axis(self):
        plan,route=self.plan();unit=compiler._collect_units(plan,route)[0]
        with TTFont(self.f.stock) as font:
            font['fvar'].axes=[a for a in font['fvar'].axes if a.axisTag!='ital']
            with self.assertRaisesRegex(compiler.CompilerError,'exact italic'):
                static._verify_style_expansion(unit['artifact'],font)

    def test_tampered_weight_mapping_rejected(self):
        plan,route=self.plan();route['documents']['/system/etc/fonts.xml']['operations'][0]['expandedWeight']=700
        route['routeId']=router._id(route)
        with self.assertRaisesRegex(router.ERROR,'sealed source plan'):router.validate_route_plan(route,plan)


if __name__=='__main__':unittest.main()
