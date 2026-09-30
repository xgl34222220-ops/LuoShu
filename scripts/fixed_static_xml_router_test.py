#!/usr/bin/env python3
import copy,sys,tempfile,unittest
from pathlib import Path
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'common'),str(ROOT/'scripts')]
import fixed_static_xml_router as fixed
import minimal_xml_router as legacy
import universal_font_plan as planner
from minimal_xml_router_test import target_slot,role
from universal_route_selection_test import fixed_face,node,route_plan,PATH,XML

def fixture(directory):
 nodes=[node(400, wght=400),node(700,wght=700),node(400,'italic',wght=400)]
 slot=target_slot(PATH,family='sans-serif',source_xml=XML,declared=Path(PATH).name,axes=True)
 slot['xmlRefs']=[dict(slot['xmlRefs'][0],**copy.deepcopy(n)) for n in nodes]
 slot['stockIdentity']={'logicalPath':PATH,'faceIndex':0,'sha256':'a'*64,'provenance':{'verified':True}}
 topology={'schema':planner.TOPOLOGY_SCHEMA,'state':'ready','topologyRevision':3,'buildKey':'fixed-xml-test','slots':{PATH:slot}}
 roles={'schema':planner.ROLES_SCHEMA,'state':'ready','roleRevision':3,'buildKey':'fixed-xml-test','slots':{PATH:role('latin','conditional')}}
 profile={'schema':planner.SOURCE_SCHEMA,'state':'ready','profileRevision':1,'profileId':'sha256:test','summary':{},'files':[{'sourcePath':'/synthetic/fixed.ttf','container':'TTF','faces':[fixed_face()]}]}
 fontplan=planner.build_plan(topology,roles,profile);base=route_plan(fontplan,nodes,directory)
 return fontplan,base

def bindings(plan):
 amap={};bound={}
 for doc in plan['documents'].values():
  for op in doc['operations']:
   key=op['artifact']['artifactId'];name='LuoShu-Fixed-'+'b'*32+'.ttf';amap[key]=name
   bound[key]={'fileName':name,'postScriptName':'LuoShu-Fixed-'+ 'b'*32,'faceIndex':0,'axes':[],'renderContractId':'sha256:'+'b'*64}
 return amap,bound

class FixedRouterTest(unittest.TestCase):
 def test_explicit_contract_and_immutable_original_fallback(self):
  with tempfile.TemporaryDirectory() as td:
   fp,base=fixture(Path(td));plan=fixed.build_route_plan(fp,base);fixed.validate_route_plan(plan,fp)
   self.assertEqual(plan['summary']['fixedStaticOperationCount'],2)
   with self.assertRaises(legacy.RouterError):legacy.validate_route_plan(plan,fp)
   amap,bound=bindings(plan);fixed.render_all(plan,amap,Path(td)/'out',bound)
   families=list(ET.parse(Path(td)/'out/system/etc/fonts.xml').getroot());self.assertEqual(len(families),2)
   self.assertEqual(families[0].get('name'),'sans-serif');self.assertIsNone(families[1].get('name'))
   nodes=list(families[0]);self.assertEqual([n.get('weight') for n in nodes],['400','700','400'])
   self.assertEqual([n.get('style') for n in nodes],['normal','normal','italic'])
   self.assertFalse(list(nodes[0]));self.assertTrue(list(nodes[2]));self.assertTrue(nodes[2].text.startswith('LuoShu-Original-'))
   for n in families[1]:self.assertTrue(n.text.startswith('LuoShu-Original-'));self.assertTrue(list(n))
 def test_inherited_family_locale_remains_on_retained_clone(self):
  with tempfile.TemporaryDirectory() as td:
   fp,base=fixture(Path(td));path=Path(base['documents'][XML]['sourcePath'])
   tree=ET.parse(path);root=tree.getroot();family=root[0];root.remove(family);family.attrib.pop('name')
   wrapper=ET.SubElement(root,'family-list',{'name':'sans-serif','lang':'el'});wrapper.append(family);tree.write(path)
   base=legacy.build_route_plan(fp,{XML:path},None,False);plan=fixed.build_route_plan(fp,base);amap,bound=bindings(plan)
   fixed.render_all(plan,amap,Path(td)/'out',bound)
   rendered=ET.parse(Path(td)/'out/system/etc/fonts.xml').getroot()
   self.assertEqual(rendered[0].get('lang'),'el');self.assertEqual(len(rendered[0]),2);self.assertIsNone(rendered[0][1].get('name'))
 def test_multi_family_wrapper_keeps_original_before_later_fallback(self):
  with tempfile.TemporaryDirectory() as td:
   fp,base=fixture(Path(td));path=Path(base['documents'][XML]['sourcePath']);tree=ET.parse(path);root=tree.getroot()
   family=root[0];root.remove(family);family.attrib.pop('name');wrapper=ET.SubElement(root,'family-list',{'name':'sans-serif','lang':'el'});wrapper.append(family)
   later=ET.SubElement(wrapper,'family',{'lang':'el'});ET.SubElement(later,'font').text='Greek.ttf';tree.write(path)
   base=legacy.build_route_plan(fp,{XML:path},None,False);plan=fixed.build_route_plan(fp,base);amap,bound=bindings(plan)
   fixed.render_all(plan,amap,Path(td)/'out',bound);rendered=ET.parse(Path(td)/'out/system/etc/fonts.xml').getroot()[0]
   self.assertEqual(len(rendered),3);self.assertTrue(rendered[1][0].text.startswith('LuoShu-Original-'));self.assertEqual(rendered[2][0].text,'Greek.ttf')
 def test_customization_structure_cannot_emit_familyset_clone(self):
  with tempfile.TemporaryDirectory() as td:
   fp,base=fixture(Path(td));path=Path(base['documents'][XML]['sourcePath']);tree=ET.parse(path);tree.getroot().tag='fonts-modification';tree.getroot()[0].set('customizationType','new-named-family');tree.write(path)
   base=legacy.build_route_plan(fp,{XML:path},None,False)
   with self.assertRaisesRegex(legacy.RouterError,'no eligible'):fixed.build_route_plan(fp,base)
 def test_font_directory_is_not_guessed_from_xml_partition(self):
  with self.assertRaises(legacy.RouterError):fixed._root_for_document('/vendor/etc/fonts.xml')
 def test_implicit_variable_italic_is_explicitly_deferred(self):
  with tempfile.TemporaryDirectory() as td:
   fp,base=fixture(Path(td));path=Path(base['documents'][XML]['sourcePath']);tree=ET.parse(path);tree.getroot()[0][0].set('supportedAxes','wght,ital');tree.write(path)
   base=legacy.build_route_plan(fp,{XML:path},None,False);plan=fixed.build_route_plan(fp,base)
   self.assertEqual(plan['summary']['fixedStaticOperationCount'],1)
   self.assertEqual(plan['documents'][XML]['representationDeferrals'][0]['reason'],'implicit-variable-style')
 def test_snapshot_change_refused(self):
  with tempfile.TemporaryDirectory() as td:
   fp,base=fixture(Path(td));plan=fixed.build_route_plan(fp,base);amap,bound=bindings(plan)
   Path(base['documents'][XML]['sourcePath']).write_text('<familyset/>')
   with self.assertRaises(legacy.RouterError):fixed.render_all(plan,amap,Path(td)/'out',bound)
 def test_unsealed_original_refused(self):
  with tempfile.TemporaryDirectory() as td:
   fp,base=fixture(Path(td));fp['targets'][PATH]['targetContract']['stockIdentity']['provenance']['verified']=False
   # Plan tampering is itself rejected; no invented verified fallback is accepted.
   with self.assertRaises(Exception):fixed.build_route_plan(fp,base)
 def test_compiled_binding_required(self):
  with tempfile.TemporaryDirectory() as td:
   fp,base=fixture(Path(td));plan=fixed.build_route_plan(fp,base);amap,_=bindings(plan)
   with self.assertRaises(legacy.RouterError):fixed.render_all(plan,amap,Path(td)/'out',{})
 def test_binding_face_axes_and_name_mismatch_refused(self):
  for key,value in [('faceIndex',2),('axes',[{'tag':'wght','stylevalue':'400'}]),('fileName','wrong.ttf')]:
   with tempfile.TemporaryDirectory() as td:
    fp,base=fixture(Path(td));plan=fixed.build_route_plan(fp,base);amap,bound=bindings(plan)
    next(iter(bound.values()))[key]=value
    with self.assertRaises(legacy.RouterError):fixed.render_all(plan,amap,Path(td)/'out',bound)
 def test_rehashed_unplanned_mutation_refused(self):
  with tempfile.TemporaryDirectory() as td:
   fp,base=fixture(Path(td));plan=fixed.build_route_plan(fp,base)
   plan['documents'][XML]['operations'][0]['mutation']['preserveDeclaredWeight']=False
   plan['routeId']=fixed._id(plan)
   with self.assertRaises(legacy.RouterError):fixed.validate_route_plan(plan,fp)
if __name__=='__main__':unittest.main()
