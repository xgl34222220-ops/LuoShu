#!/usr/bin/env python3
"""Exercise the actual fixed mixed shell entry with sealed synthetic XML stock."""
import copy,hashlib,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'common'),str(ROOT/'scripts')]
import universal_mixed_pipeline_test as fixture
import universal_mixed_font as mixed
import minimal_xml_router as legacy
import font_topology_snapshot as topology
import font_role_shadow as roles
import universal_font_deployment as deployment
import xml.etree.ElementTree as ET

class FixedEntryTest(unittest.TestCase):
 def test_real_entry_selects_fixed_xml_and_stages_same_request(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);module=root/'module';source=module/'cache/generated/composite.ttf';source.parent.mkdir(parents=True)
   fixture.make_font(source,marked=True);stock=root/'stock.ttf';fixture.make_font(stock,variable=True)
   logical='/system/fonts/Ui-Regular.ttf';stocks={logical:stock}
   fixture.plans(source,stocks,{logical:'ui-sans'},module)
   config=module/'config';snapshot=config/'font-config-source/system/fonts.xml';snapshot.parent.mkdir(parents=True)
   snapshot.write_text('<familyset><family name="sans-serif"><font weight="400" style="normal" supportedAxes="wght">Ui-Regular.ttf</font></family></familyset>')
   refs=legacy._document_nodes('/system/etc/fonts.xml',ET.parse(snapshot))
   for ref in refs:ref['resolvedPath']=logical
   inv=json.loads((config/'device_font_inventory.json').read_text())
   inv['slots'][logical]['xmlRefs']=copy.deepcopy(refs);inv['xmlGraph']['refs']=refs
   inv['xmlMemberSnapshots']={logical:{'0':{'state':'ready','faceIndex':0,'stockIdentity':inv['slots'][logical]['stockIdentity']}}}
   (config/'device_font_inventory.json').write_text(json.dumps(inv))
   tp=topology.build_topology(inv,None,'',None,None,'');rm,_=roles.build(tp)
   (config/'device_font_topology.json').write_text(json.dumps(tp));(config/'device_font_roles.json').write_text(json.dumps(rm))
   (module/'common').symlink_to(ROOT/'common',target_is_directory=True);(module/'module.prop').write_text('id=LuoShu\n');(module/'logs').mkdir()
   (config/'active_font.conf').write_text('default\n')
   state={'requestId':'real-fixed-entry','state':'prepared','previousFont':'default',**{r:r for r in ('cjk','latin','digit')},**{r+'Axes':'wght=400' for r in ('cjk','latin','digit')}}
   fixture.write_conf(config/'mix-stage-next.conf',state)
   fixture.write_conf(module/'.luoshu-mix-stage/.luoshu-mix-generation.conf',dict(state,compositeHash=mixed.digest(source)))
   mapping=root/'stock-map.json';mapping.write_text(json.dumps({k:str(v) for k,v in stocks.items()}))
   bin=root/'bin';bin.mkdir();prop=bin/'getprop';prop.write_text('#!/bin/sh\necho mixed-pipeline-test\n');prop.chmod(0o755)
   env={**os.environ,'MODDIR':str(module),'LUOSHU_REAL_MODDIR':str(module),'LUOSHU_MIX_REQUEST_ID':state['requestId'],'LUOSHU_PYTHON':sys.executable,'LUOSHU_STOCK_FONT_MAP':str(mapping),'PATH':str(bin)+os.pathsep+os.environ['PATH']}
   result=subprocess.run(['sh',str(module/'common/universal_mixed_font.sh'),'fixed',str(source)],env=env,capture_output=True,text=True,timeout=90)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr+(module/'logs/fontswitch.log').read_text())
   response=json.loads(result.stdout.strip().splitlines()[-1]);self.assertFalse(response['fallback']);self.assertEqual(response['pipeline'],'universal')
   payload=module/'.luoshu-payload-next';manifest=json.loads((payload/'.luoshu-runtime/deployment/deployment.json').read_text());deployment.validate_payload_integrity(manifest,payload)
   route=json.loads((payload/'.luoshu-runtime/deployment/fixed-static-route-plan.json').read_text())
   self.assertEqual(route['routeRevision'],5);self.assertGreater(route['summary']['fixedMatchingOperationCount'],0)
   plan=json.loads((payload/'.luoshu-runtime/deployment/font-plan.json').read_text())
   self.assertEqual(plan['constraints']['xmlScopePolicy'],'fixed-chinese-reference-v1')
   next_state=mixed.conf(config/'universal-font-next.conf');self.assertEqual(next_state['requestId'],state['requestId']);self.assertEqual(next_state['deploymentId'],manifest['deploymentId'])
   self.assertFalse((config/'font-payload-next.conf').exists());self.assertFalse((config/'font_runtime_legacy_v14_4.conf').exists())
   emitted=next(f for f in manifest['files'] if f['kind']=='xml')
   self.assertIn('LuoShuFixed-',(payload/emitted['payloadPath']).read_text())
   self.assertIn('Ui-Regular.ttf',snapshot.read_text())
if __name__=='__main__':unittest.main()
