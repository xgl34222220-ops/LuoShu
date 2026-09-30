import copy, hashlib, unittest, xml.etree.ElementTree as ET
from planner import plan, digest, compile_groups

XML=b'''<familyset><family name="sans-serif"><font weight="400" style="normal" index="2" supportedAxes="wght">OEM.ttc<axis tag="wght" stylevalue="400"/></font><font weight="800" style="normal" postScriptName="OEM">OEM.ttf<axis tag="wght" stylevalue="520"/></font><font weight="400" style="italic">Italic.ttf</font></family><family lang="und-Zsye"><font>Emoji.ttf</font></family><family lang="und-Ital"><font>OldItalic.ttf</font></family><alias name="sans" to="sans-serif" weight="400"/></familyset>'''
# The renderer remains responsible for actual font geometry.
SHA=hashlib.sha256(XML).hexdigest()
CONTRACT={'selection':'fixed-static','sourceSha256':'a'*64,'geometryVerified':True,
          'roleGeometry':{'cjk':{'scale':1,'shiftY':10},'latin':{'scale':1,'shiftY':5},'digit':{'scale':1,'shiftY':0}},
          'sourceAxes':{'latin':{'wght':400}},'upem':1000,'lineMetrics':[900,-220]}
def selection(i):
 node=list(ET.fromstring(XML).iter('font'))[i]
 return {'ordinal':i,'nodeDigest':digest(ET.tostring(node,encoding='unicode')),
         'role':'ui-sans','renderContract':copy.deepcopy(CONTRACT)}
class Tests(unittest.TestCase):
 def test_groups_before_render_preserves_protected(self):
  p=plan(XML,SHA,[selection(0),selection(1)]);calls=[]
  compile_groups(p,lambda g:calls.append(g['id']) or b'synthetic-render-result')
  self.assertEqual(len(calls),1);self.assertEqual(len(p['routes']),2)
  nodes=list(ET.fromstring(p['xml']).iter('font'))
  self.assertEqual([n.get('weight') for n in nodes[:2]],['400','800'])
  self.assertTrue(all(n.get('index')=='0' and not list(n) and 'supportedAxes' not in n.attrib for n in nodes[:2]))
  self.assertEqual(nodes[2].get('style'),'italic')
  tree=ET.fromstring(p['xml'])
  self.assertEqual(tree.find("family[@lang='und-Zsye']/font").text,'Emoji.ttf')
  self.assertEqual(tree.find("family[@lang='und-Ital']/font").text,'OldItalic.ttf')
  self.assertEqual(ET.fromstring(p['xml']).find('alias').attrib,{'name':'sans','to':'sans-serif','weight':'400'})
 def test_original_primary_is_retained_once_before_locale_fallbacks(self):
  p=plan(XML,SHA,[selection(0),selection(1)])
  families=ET.fromstring(p['xml']).findall('family')
  self.assertIsNone(families[1].get('name'))
  original=ET.fromstring(XML).find('family');original.attrib.pop('name')
  self.assertEqual(ET.tostring(families[1]),ET.tostring(original))
  self.assertEqual(len(p['retainedFallbacks']),1)
  self.assertTrue(p['retainedFallbacks'][0]['requiresImmutableStockAssets'])
  self.assertFalse(p['deviceDeployable'])
 def test_no_selection_does_not_insert_fallback_or_change_xml_semantics(self):
  p=plan(XML,SHA,[])
  self.assertEqual(ET.tostring(ET.fromstring(p['xml'])),ET.tostring(ET.fromstring(XML)))
  self.assertEqual([],p['retainedFallbacks'])
 def test_specialized_primary_family_rejected(self):
  xml=XML.replace(b'name="sans-serif"',b'name="sans-serif" variant="compact"')
  with self.assertRaises(ValueError):plan(xml,hashlib.sha256(xml).hexdigest(),[selection(0)])
 def test_distinct_geometry_never_coalesces(self):
  b=selection(1);b['renderContract']['roleGeometry']['cjk']['shiftY']=11
  self.assertEqual(len(plan(XML,SHA,[selection(0),b])['groups']),2)
 def test_source_change_never_coalesces(self):
  b=selection(1);b['renderContract']['sourceSha256']='b'*64
  self.assertEqual(len(plan(XML,SHA,[selection(0),b])['groups']),2)
 def test_stale_snapshot(self):
  with self.assertRaises(ValueError):plan(XML+b' ',SHA,[selection(0)])
 def test_stale_node(self):
  s=selection(0);s['nodeDigest']='bad'
  with self.assertRaises(ValueError):plan(XML,SHA,[s])
 def test_italic_or_unknown_not_silently_replaced(self):
  with self.assertRaises(ValueError):plan(XML,SHA,[selection(2)])
  s=selection(0);s['role']='special-fallback'
  with self.assertRaises(ValueError):plan(XML,SHA,[s])
 def test_protected_script_cannot_be_mislabeled_by_caller(self):
  with self.assertRaises(ValueError):plan(XML,SHA,[selection(4)])
 def test_unverified_geometry_rejected(self):
  s=selection(0);s['renderContract']['geometryVerified']=False
  with self.assertRaises(ValueError):plan(XML,SHA,[s])
 def test_duplicate_route_rejected(self):
  with self.assertRaises(ValueError):plan(XML,SHA,[selection(0),selection(0)])
if __name__=='__main__':unittest.main()
