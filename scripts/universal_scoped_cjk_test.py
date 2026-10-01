#!/usr/bin/env python3
"""A shared protected TTC permits only its explicitly Chinese XML references."""
import copy,hashlib,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'common'),str(ROOT/'scripts')]
import universal_font_compiler_test as fixture
import font_role_shadow as roles
import universal_font_plan as planner
import minimal_xml_router as legacy
import fixed_static_xml_router as fixed
import universal_font_compiler as compiler
import universal_font_deployment as deployment
import universal_font_cutover_gate as gate
from fontTools.ttLib import TTFont

class ScopedCjkTest(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.source=self.root/'source.ttf';a=self.root/'ja.ttf';b=self.root/'zh.ttf';self.stock=self.root/'SharedCJK.ttc';self.logical='/system/fonts/SharedCJK.ttc'
  from font_coverage import CJK_COMMON as CJK_PROBES
  points=tuple(sorted(set(fixture.ASCII_POINTS)|set(CJK_PROBES)|set(range(0x4e00,0x4e00+6000))|{ord('あ'),ord('가'),ord('ㄅ'),ord('Ω')}))
  with patch.object(fixture,'ASCII_POINTS',points):
   fixture.make_font(self.source,family='Fixed Mixed')
   fixture.make_font(a,family='Original JP')
   fixture.make_font(b,family='Original ZH',ascent=950,y_max=740)
  fixture.make_collection(self.stock,a,b)
  self.xml=self.root/'fonts.xml';self.xml.write_text('<familyset><family lang="zh-Hans"><font index="1">SharedCJK.ttc</font></family><family lang="ja"><font index="0">SharedCJK.ttc</font></family><family lang="ko"><font index="0">SharedCJK.ttc</font></family><family lang="zh-Hant,zh-Bopo"><font index="1">SharedCJK.ttc</font></family><family lang="zh-Hans"><font index="1" fallbackFor="serif">SharedCJK.ttc</font></family></familyset>')
  self.slot=fixture.slot_from_stock(self.logical,self.stock,family='',source_xml=None,declared='SharedCJK.ttc')
  self.slot['xmlRefs']=legacy._document_nodes('/system/etc/fonts.xml',ET.parse(self.xml))
  for ref in self.slot['xmlRefs']:ref['resolvedPath']=self.logical
  self.top={'schema':planner.TOPOLOGY_SCHEMA,'state':'ready','topologyRevision':3,'buildKey':'phase6-test','slots':{self.logical:self.slot},'summary':{},'families':{},'xmlAliases':[],'unresolvedXmlRefs':[]}
  self.roles,_=roles.build(self.top)
  self.profile=fixture.font_source_profile.build([self.source])
  policy={'policy':'fixed-composite-selection-v1','requestId':'scoped-test','fontSha256':hashlib.sha256(self.source.read_bytes()).hexdigest(),'roles':{r:{'mode':'fixed','selectedAxes':{'wght':400}} for r in ('cjk','latin','digit')}}
  for file in self.profile['files']:
   for face in file['faces']:face['mixedSelection']=copy.deepcopy(policy)
 def build(self):
  plan=planner.build_plan(self.top,self.roles,self.profile,fixed_xml_scopes=True)
  base=legacy.build_route_plan(plan,{'/system/etc/fonts.xml':self.xml},None,False)
  return plan,base,fixed.build_route_plan(plan,base)
 def test_only_chinese_reference_compiles_and_original_container_is_preserved(self):
  original=self.stock.read_bytes();plan,base,route=self.build();target=plan['targets'][self.logical]
  default=planner.build_plan(self.top,self.roles,self.profile)
  self.assertNotIn('xmlScopedTarget',default['targets'][self.logical])
  unsafe=compiler.compile_all(plan,base,{self.logical:self.stock},self.root/'minimal-out',False)
  self.assertFalse(unsafe['summary']['deploymentReady'])
  self.assertIn('requires fixed static XML',unsafe['artifacts'][0]['reason'])
  self.assertEqual(target['role'],'special-fallback');self.assertEqual(target['action'],'preserve')
  self.assertEqual(len(target['xmlScopedTarget']['xmlRefs']),1)
  self.assertEqual(base['physicalOnlyTargets'],[])
  operations=route['documents']['/system/etc/fonts.xml']['operations']
  self.assertEqual([x['node']['ordinal'] for x in operations],[0]);self.assertEqual(operations[0]['role'],'cjk')
  artifacts=compiler.compile_all(plan,route,{self.logical:self.stock},self.root/'compiled',False)
  self.assertTrue(artifacts['summary']['deploymentReady'],artifacts)
  self.assertEqual(artifacts['artifacts'][0]['role'],'cjk')
  with TTFont(artifacts['artifacts'][0]['output']) as font:
   self.assertIn(ord('中'),font.getBestCmap())
   for cp in map(ord,'A1あ가ㄅΩ'):self.assertNotIn(cp,font.getBestCmap())
  mapping=self.root/'stock-map.json';mapping.write_text(json.dumps({self.logical:str(self.stock)}))
  with patch.dict(os.environ,{'LUOSHU_STOCK_FONT_MAP':str(mapping)}):
   payload=self.root/'payload';manifest=deployment.build_deployment(plan,route,artifacts,payload)
  decision=gate.evaluate(plan,route,artifacts,manifest,payload);self.assertTrue(decision['eligible'],decision)
  self.assertEqual(decision['summary']['xmlScopedTargetCount'],1)
  self.assertFalse(any(x['logicalPath']==self.logical for x in manifest['files']))
  emitted=next(x for x in manifest['files'] if x['kind']=='xml')
  tree=ET.parse(payload/emitted['payloadPath']);nodes=list(tree.getroot().iter('font'))
  unchanged=[n for n in nodes if (n.text or '').strip()=='SharedCJK.ttc']
  self.assertEqual(len(unchanged),4)
  self.assertEqual(self.stock.read_bytes(),original)
 def test_nonfixed_source_and_protected_serif_cannot_opt_in(self):
  fixed_profile=copy.deepcopy(self.profile)
  for file in self.profile['files']:
   for face in file['faces']:face.pop('mixedSelection')
  plan=planner.build_plan(self.top,self.roles,self.profile,fixed_xml_scopes=True)
  self.assertNotIn('xmlScopedTarget',plan['targets'][self.logical])
  self.profile=fixed_profile
  self.roles['slots'][self.logical]['role']='serif'
  plan=planner.build_plan(self.top,self.roles,self.profile,fixed_xml_scopes=True)
  self.assertNotIn('xmlScopedTarget',plan['targets'][self.logical])
 def test_scoped_reference_cannot_be_silently_omitted_or_promoted_to_physical(self):
  plan,base,route=self.build()
  bad=copy.deepcopy(base)
  bad['documents']['/system/etc/fonts.xml']['operations']=[]
  with self.assertRaisesRegex(legacy.RouterError,'unaccounted reference'):legacy.validate_route_plan(bad,plan)
  bad=copy.deepcopy(base);bad['physicalOnlyTargets']=[self.logical]
  with self.assertRaisesRegex(legacy.RouterError,'protected physical container'):legacy.validate_route_plan(bad,plan)

 def test_forged_top_level_named_family_cannot_borrow_unnamed_scope(self):
  plan,base,route=self.build();target=plan['targets'][self.logical]
  node=copy.deepcopy(target['xmlRefs'][0]);node['family']='serif'
  self.assertEqual(planner.route_target(target,node)['action'],'preserve')
  bad=copy.deepcopy(base);op=bad['documents']['/system/etc/fonts.xml']['operations'][0]
  op['node']['family']='serif'
  op['nodeFingerprint']=legacy._node_fingerprint(op['node'])
  with self.assertRaisesRegex(legacy.RouterError,'scoped replacement permission'):
   legacy.validate_route_plan(bad,plan)

 def test_scope_cannot_borrow_japanese_ref_or_named_variant(self):
  plan,base,route=self.build();target=plan['targets'][self.logical]
  ref=target['xmlRefs'][1];resolved=planner.route_target(target,ref)
  self.assertEqual(resolved['action'],'preserve');self.assertIsNone(resolved.get('source'))
  bad=copy.deepcopy(plan);bad['targets'][self.logical]['xmlScopedTarget']['xmlRefs'].append(ref)
  with self.assertRaisesRegex(planner.UniversalPlanError,'escaped frozen evidence'):planner.validate_plan(bad)
  for attrs in ({'lang':'zh-Hans','variant':'elegant'},{'lang':'zh-Hans','name':'serif'},{'lang':'ar'},{'lang':'zh-Hant,zh-Bopo'}):
   node=copy.deepcopy(target['xmlRefs'][0]);node['familyAttributes']=attrs
   self.assertFalse(planner._scoped_chinese_reference(node))

if __name__=='__main__':unittest.main(verbosity=2)
