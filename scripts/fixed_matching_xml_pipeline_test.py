"""Separate matching representation: production compile, payload and runtime."""
import copy,json,os,sys,unittest
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'common'),str(ROOT/'scripts')]
from fontTools.ttLib import TTFont,newTable
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.varLib.featureVars import addFeatureVariations
import fixed_static_style_expansion_test as f
import fixed_static_xml_router as router
import fixed_static_xml_compiler as static
import fixed_outline_weight_match as matching
import universal_font_compiler as compiler
import universal_font_deployment as deploy
import universal_font_runtime_verify as runtime


class MatchingPipelineTest(unittest.TestCase):
    def setUp(self):
        self.case=f.ExpansionTest();self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.root=self.case.root;self.plan,expanded=self.case.plan()
        self.route=router.build_route_plan(self.plan,expanded['legacyRoutePlan'],matching_weights=True)
        self.mapping={self.case.f.logical:self.case.f.stock}

    def build(self):
        return compiler.compile_all(self.plan,self.route,self.mapping,self.root/'compiled',False)

    def test_distinct_mode_constant_response_and_dynamic_italic_xml(self):
        manifest=self.build();self.assertTrue(manifest['summary']['deploymentReady'])
        self.assertEqual(len(manifest['artifacts']),1);artifact=manifest['artifacts'][0]
        self.assertEqual(artifact['mode'],matching.MATCHING)
        self.assertEqual(self.route['routeRevision'],3)
        self.assertEqual(self.route['summary']['fixedMatchingOperationCount'],1)
        self.assertEqual(self.route['summary']['fixedStaticOperationCount'],0)
        self.assertFalse(self.route['summary']['normalSourceVariationPreserved'])
        binding=artifact['staticXmlContract']
        with TTFont(artifact['output']) as font:
            proof=matching.validate(font,binding['weightMatching']);self.assertEqual(proof['shapeResponse'],'constant')
        mapping=self.root/'stock-map.json';mapping.write_text(json.dumps({k:str(v) for k,v in self.mapping.items()}))
        with patch.dict(os.environ,{'LUOSHU_STOCK_FONT_MAP':str(mapping)}):
            payload=self.root/'payload';deployment=deploy.build_deployment(self.plan,self.route,manifest,payload)
            deploy.validate_deployment(deployment,self.plan,self.route,manifest,payload)
        self.assertEqual(len([x for x in deployment['files'] if x['kind']=='xml-matching-font']),1)
        tree=ET.parse(payload/'system/etc/fonts.xml').getroot();self.assertEqual(len(tree[0]),2)
        normal,italic=tree[0];self.assertEqual(normal.get('supportedAxes'),'wght')
        self.assertEqual(italic.get('supportedAxes'),'wght');self.assertEqual(italic.get('style'),'italic')
        self.assertEqual({a.get('tag'):a.get('stylevalue') for a in italic},{'wdth':'100','ital':'1'})
        self.assertEqual((payload/'system/fonts'/italic.text).read_bytes(),self.case.f.stock.read_bytes())
        snapshot=json.loads((payload/'.luoshu-runtime/deployment/fixed-static-route-plan.json').read_text())
        state={'state':'active','deploymentId':deployment['deploymentId'],'payloadDigest':deployment['payloadDigest']}
        result=runtime.verify(self.plan,manifest,deployment,runtime_conf=state,
            mount_state={**state,'state':'mounted'},font_dump='\n'.join('style = FontStyle { weight=400, slant=0}, path = '+x['logicalPath'] for x in deployment['files']),
            mountinfo={},active_font='mix',visible_root=payload,boot_id='synthetic-boot',fixed_route=snapshot)
        self.assertEqual(result['grade'],'WARN',result)
        self.assertIn('fixed-static-consumer-proof-pending',result['warnings'])

    def test_nonconstant_variation_cannot_pass_structural_proof(self):
        artifact=self.build()['artifacts'][0]
        with TTFont(artifact['output']) as font:
            name=font.getBestCmap()[65];n=len(font['glyf'][name].getCoordinates(font['glyf'])[0])+4
            font['gvar'].variations[name]=[TupleVariation({'wght':(0,1,1)},[(1,0)]*n)]
            with self.assertRaisesRegex(ValueError,'not constant'):matching.validate(font,artifact['staticXmlContract']['weightMatching'])

    def test_axis_dependent_shaping_cannot_be_activated(self):
        artifact=self.build()['artifacts'][0]
        with TTFont(artifact['output']) as font:
            cmap=font.getBestCmap();addFeatureVariations(font,[([{'wght':(0,1)}],{cmap[65]:cmap[49]})])
            with self.assertRaisesRegex(ValueError,'variable shaping'):matching.validate(font,artifact['staticXmlContract']['weightMatching'])

    def test_variable_metrics_and_extra_axes_are_rejected(self):
        artifact=self.build()['artifacts'][0]
        with TTFont(artifact['output']) as font:
            font['MVAR']=newTable('MVAR')
            with self.assertRaisesRegex(ValueError,'metric/outline'):matching.validate(font,artifact['staticXmlContract']['weightMatching'])

    def test_generic_source_or_physical_target_cannot_use_matching_contract(self):
        unit=compiler._collect_units(self.plan,self.route)[0]
        for kind in ('generic','physical'):
            invalid=copy.deepcopy(unit)
            if kind=='generic':invalid['target']['source'].pop('mixedSelection')
            else:invalid['deploymentKinds']=['physical-slot']
            result=compiler._compile_unit(invalid,self.mapping,self.root/kind,False)
            self.assertEqual(result['status'],'blocked')

    def test_reference_coordinate_cannot_be_changed(self):
        unit=compiler._collect_units(self.plan,self.route)[0];unit['artifact']['requiredWeight']=520
        with self.assertRaisesRegex(compiler.CompilerError,'reference coordinate'):static.preflight_unit(unit,self.mapping,False)


if __name__=='__main__':unittest.main()
