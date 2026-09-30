#!/usr/bin/env python3
"""Production planner/compiler/payload/runtime path with synthetic ROM evidence."""
import copy,json,os,shutil,sys,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'common'),str(ROOT/'scripts')]
import fixed_static_xml_compiler_test as fixture
import universal_font_compiler as compiler
import universal_font_deployment as deploy
import universal_font_runtime_verify as verify
import fixed_static_xml_router as router

class PipelineTest(unittest.TestCase):
 def setUp(self):
  self.case=fixture.FixedStaticCompilerTest('test_honest_static_source_at_different_xml_weight');self.case.setUp();self.addCleanup(self.case.tearDown)
  self.root=self.case.root;self.plan,self.route=self.case.routed_plan()
  self.artifacts=compiler.compile_all(self.plan,self.route,{self.case.logical:self.case.stock},self.root/'compiled',False)
  self.mapping=self.root/'stock-map.json';self.mapping.write_text(json.dumps({self.case.logical:str(self.case.stock)}))
  self.env=patch.dict(os.environ,{'LUOSHU_STOCK_FONT_MAP':str(self.mapping)});self.env.start();self.addCleanup(self.env.stop)
  self.payload=self.root/'payload';self.deployment=deploy.build_deployment(self.plan,self.route,self.artifacts,self.payload)
  self.visible=self.root/'visible';shutil.copytree(self.payload,self.visible)
 def verify(self,dump=None):
  route=json.loads((self.payload/'.luoshu-runtime/deployment/fixed-static-route-plan.json').read_text())
  runtime={'state':'active','deploymentId':self.deployment['deploymentId'],'payloadDigest':self.deployment['payloadDigest']}
  mount={'state':'mounted',**{k:v for k,v in runtime.items() if k!='state'}}
  return verify.verify(self.plan,self.artifacts,self.deployment,runtime_conf=runtime,mount_state=mount,
   font_dump=dump if dump is not None else '\n'.join('style = FontStyle { weight=400, slant=0}, path = '+f['logicalPath'] for f in self.deployment['files']),
   mountinfo={},active_font='mix',visible_root=self.visible,boot_id='synthetic-boot',fixed_route=route)
 def test_shared_compile_payload_and_runtime(self):
  deploy.validate_deployment(self.deployment,self.plan,self.route,self.artifacts,self.payload)
  static=[f for f in self.deployment['files'] if f['kind']=='xml-static-font']
  originals=[f for f in self.deployment['files'] if f['kind']=='xml-original']
  self.assertEqual(len(static),1);self.assertEqual(len(static[0]['artifactIds']),2);self.assertEqual(len(originals),1)
  original_bytes=self.case.stock.read_bytes()
  self.assertEqual((self.payload/originals[0]['payloadPath']).read_bytes(),original_bytes)
  # An unrelated physical adapter may own the old logical name; fallback copies
  # continue referring to their immutable original asset, not this replaced name.
  old=self.visible/self.case.logical.lstrip('/');old.parent.mkdir(parents=True,exist_ok=True);old.write_bytes(b'other physical payload')
  self.case.source.unlink();self.case.stock.unlink()
  result=self.verify();self.assertEqual(result['grade'],'WARN',result);self.assertIn('fixed-static-consumer-proof-pending',result['warnings'])
 def test_shared_collection_faces_are_bound_independently(self):
  import fixed_static_xml_compiler as static
  import universal_font_compiler_test as factory
  from fontTools.ttLib import TTFont
  other=self.root/'other.ttf';factory.make_font(other,family='OtherFace',ascent=950)
  collection=self.root/'collection.ttc';factory.make_collection(collection,self.case.stock,other)
  logical='/system/fonts/Collection.ttc';xml=self.root/'collection.xml'
  xml.write_text('<familyset><family name="sans-serif"><font index="0">Collection.ttc</font><font index="1">Collection.ttc</font></family></familyset>')
  slot=factory.slot_from_stock(logical,collection,family='sans-serif',source_xml='/system/etc/fonts.xml',declared='Collection.ttc')
  slot['xmlRefs'].append(dict(slot['xmlRefs'][0],index=1))
  profile=factory.font_source_profile.build([self.case.source]);policy=self.case.unit()['target']['source']['mixedSelection']
  for file in profile['files']:
   for face in file['faces']:face['mixedSelection']=copy.deepcopy(policy)
  with patch.object(factory.font_source_profile,'build',return_value=profile):fp,base=factory.build_plans(self.case.source,slot,'latin',xml)
  route=router.build_route_plan(fp,base);units=compiler._collect_units(fp,route)
  second=next(u for u in units if u['artifact']['originalStockFaceIndex']==1)
  with self.assertRaisesRegex(compiler.CompilerError,'face mismatch'):
   compiler._validate_stock_contract(second['target'],collection,1)
  manifest=compiler.compile_all(fp,route,{logical:collection},self.root/'collection-out',False)
  self.assertEqual(manifest['summary']['readyCount'],2);self.assertEqual(len(set(manifest['artifactMap'].values())),2)
  self.mapping.write_text(json.dumps({logical:str(collection)}))
  payload=self.root/'collection-payload';deployment=deploy.build_deployment(fp,route,manifest,payload)
  deploy.validate_payload_integrity(deployment,payload)
  self.assertEqual(len([f for f in deployment['files'] if f['kind']=='xml-original']),1)
  self.assertEqual({a['report']['renderContract']['stock']['faceIndex'] for a in manifest['artifacts']},{0,1})
  tampered=copy.deepcopy(second);tampered['target']['xmlRefs']=[]
  with self.assertRaisesRegex(compiler.CompilerError,'frozen XML node'):static.verify_original_face(tampered['target'],collection,1)
 def test_protected_family_member_uses_scanned_face_identity(self):
  import universal_font_compiler_test as f
  import universal_font_plan as planner
  import minimal_xml_router as legacy
  protected=self.root/'Serif.ttf';shutil.copy(self.case.stock,protected)
  protected_path='/system/fonts/Serif.ttf';xml=self.root/'protected-family.xml'
  xml.write_text('<familyset><family name="sans-serif"><font>SyntheticOEM.ttf</font><font fallbackFor="serif">Serif.ttf</font></family></familyset>')
  slots={}
  for logical,path in [(self.case.logical,self.case.stock),(protected_path,protected)]:
   slots[logical]=f.slot_from_stock(logical,path,family='sans-serif',source_xml='/system/etc/fonts.xml',declared=Path(logical).name)
  identity=slots[protected_path].pop('stockIdentity');slots[protected_path]['stockIdentities']={'0':identity}
  slots[protected_path]['xmlRefs'][0]['fontAttributes']={'fallbackFor':'serif'}
  profile=f.font_source_profile.build([self.case.source])
  for file in profile['files']:
   for face in file['faces']:face['mixedSelection']=copy.deepcopy(self.case.unit()['target']['source']['mixedSelection'])
  topology={'schema':planner.TOPOLOGY_SCHEMA,'state':'ready','topologyRevision':3,'buildKey':'phase6-test','slots':slots,'summary':{},'families':{},'xmlAliases':[],'unresolvedXmlRefs':[]}
  roles={'schema':planner.ROLES_SCHEMA,'state':'ready','roleRevision':3,'buildKey':'phase6-test','slots':{self.case.logical:f.role_map('latin'),protected_path:f.role_map('serif','preserve')}}
  plan=planner.build_plan(topology,roles,profile);base=legacy.build_route_plan(plan,{'/system/etc/fonts.xml':xml},None,False)
  route=router.build_route_plan(plan,base)
  self.assertEqual(plan['targets'][protected_path]['action'],'preserve')
  retained=next(v for v in route['retainedOriginals'].values() if v['targetPath']==protected_path)
  self.assertEqual(retained['target']['targetContract']['stockIdentity'],identity)
  self.mapping.write_text(json.dumps({self.case.logical:str(self.case.stock),protected_path:str(protected)}))
  artifacts=compiler.compile_all(plan,route,{self.case.logical:self.case.stock,protected_path:protected},self.root/'protected-compiled',False)
  payload=self.root/'protected-payload';manifest=deploy.build_deployment(plan,route,artifacts,payload)
  original=next(f for f in manifest['files'] if f['kind']=='xml-original' and retained['originalId'] in f['originalIds'])
  self.assertEqual((payload/original['payloadPath']).read_bytes(),protected.read_bytes())
 def test_new_asset_registration_is_required_not_old_family_name(self):
  result=self.verify('sans-serif SyntheticOEM.ttf')
  self.assertEqual(result['grade'],'WARN',result)
  self.assertTrue(any('static-font-manager-path-unconfirmed' in x for x in result['warnings']))
 def test_error_message_is_not_positive_registration(self):
  logical=next(f['logicalPath'] for f in self.deployment['files'] if f['kind']=='xml-static-font')
  result=self.verify('ERROR: failed to load '+logical)
  self.assertNotEqual(result['grade'],'PASS')
  self.assertTrue(all(not f['fontManagerHits'] for f in result['fonts']))
 def test_runtime_recomputes_shared_route_membership(self):
  item=next(f for f in self.deployment['files'] if f['kind']=='xml-static-font');item['artifactIds'].pop()
  with self.assertRaises(Exception):self.verify()
 def test_new_dynamic_update_cannot_redirect_retained_ps(self):
  path=self.visible/'data/fonts/config/config.xml';path.parent.mkdir(parents=True);path.write_text('<fontConfig><updatedFontDir value="new"/></fontConfig>')
  with self.assertRaises(deploy.DeploymentError):self.verify()
 def test_tampered_retained_original_cannot_activate(self):
  item=next(f for f in self.deployment['files'] if f['kind']=='xml-original')
  (self.payload/item['payloadPath']).write_bytes(b'tampered')
  with self.assertRaises(deploy.DeploymentError):deploy.validate_payload_integrity(self.deployment,self.payload)
 def test_tampered_route_snapshot_cannot_activate(self):
  path=self.payload/'.luoshu-runtime/deployment/fixed-static-route-plan.json';path.write_text('{}')
  with self.assertRaises(deploy.DeploymentError):deploy.validate_payload_integrity(self.deployment,self.payload)
 def test_missing_shared_artifact_identity_cannot_hide_route(self):
  changed=copy.deepcopy(self.deployment)
  item=next(f for f in changed['files'] if f['kind']=='xml-static-font');item['artifactIds'].pop()
  with self.assertRaises(deploy.DeploymentError):deploy.validate_payload_integrity(changed,self.payload)
if __name__=='__main__':unittest.main()
