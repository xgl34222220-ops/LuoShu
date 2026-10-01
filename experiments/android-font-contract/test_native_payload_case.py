import copy,json,os,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import native_payload_case as case

class NativePayloadTest(unittest.TestCase):
 def fixture(self, root):
  results=root/'results';results.mkdir();payload=root/'payload';payload.mkdir()
  summary={'state':'passed','androidPythonExecuted':True,'fingerprint':'sdk','deploymentId':'d','payloadDigest':'p',
   'preparedDonorRoles':{r:{'character':c,'pointCount':n} for r,c,n in [('cjk','中',6),('latin','A',3),('digit','1',5)]}}
  docs={'plan':{},'route':{},'artifacts':{'summary':{'deploymentReady':True}}}
  manifest={'deploymentId':'d','payloadDigest':'p','verificationContracts':{}}
  for key, sealed, filename in [('plan','fontPlan','font-plan.json'),('route','fixedStaticRoute','route-plan.json'),('artifacts','artifactManifest','artifact-manifest.json')]:
   (results/filename).write_text(json.dumps(docs[key]));(payload/filename).write_text(json.dumps(dict(docs[key],sealed=True)))
   manifest['verificationContracts'][sealed]={'payloadPath':filename}
  (results/'deployment.json').write_text(json.dumps(manifest));(results/'native-prepare-summary.json').write_text(json.dumps(summary))
  return results,summary
 def test_validated_sealed_contracts_drive_consumer_not_loose_results(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);self.fixture(root)
   with patch.object(case.deployment,'validate_deployment') as validate:
    payload,docs,_=case.read_prepared(root,'sdk');validate.assert_called_once()
   self.assertTrue(all(docs[k]['sealed'] for k in ('plan','route','artifacts')))
 def test_firmware_native_proof_donors_and_summary_identity_fail_closed(self):
  for changes in [{'fingerprint':'old'},{'androidPythonExecuted':False},{'state':'failed'},{'preparedDonorRoles':{}},{'payloadDigest':'wrong'}]:
   with self.subTest(changes=changes),tempfile.TemporaryDirectory() as td:
    root=Path(td);results,summary=self.fixture(root);summary.update(changes)
    (results/'native-prepare-summary.json').write_text(json.dumps(summary))
    with patch.object(case.deployment,'validate_deployment') as validate,self.assertRaises(ValueError):case.read_prepared(root,'sdk')
    validate.assert_not_called()
 def test_payload_integrity_rejection_is_not_swallowed(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);self.fixture(root)
   with patch.object(case.deployment,'validate_deployment',side_effect=ValueError('tampered')),self.assertRaisesRegex(ValueError,'tampered'):case.read_prepared(root,'sdk')
 def test_default_route_ambiguity_is_not_first_match_wins(self):
  op={'targetPath':'stock','node':{'index':0,'weight':400,'style':'normal','family':'sans-serif'},'artifact':{'artifactId':'a'}}
  route={'documents':{'/system/etc/font_fallback.xml':{'operations':[op]}}}
  art={'artifacts':[{'artifactId':'a','staticXmlContract':True,'contract':{}}]}
  manifest={'files':[{'artifactId':'a','logicalPath':'new','sha256':'sha'}]}
  baseline={'actualDefaultFonts':{s:[{'file':'stock','ttcIndex':0}] for s in ('A','1','中')}}
  self.assertEqual(case.expected_defaults(route,art,manifest,baseline)['Cjk']['path'],'new')
  other=copy.deepcopy(op);other['artifact']['artifactId']='b';route['documents']['/system/etc/font_fallback.xml']['operations'].append(other)
  art['artifacts'].append({'artifactId':'b','staticXmlContract':True,'contract':{}});manifest['files'].append({'artifactId':'b','logicalPath':'other','sha256':'other'})
  with self.assertRaisesRegex(ValueError,'ambiguous'):case.expected_defaults(route,art,manifest,baseline)
 def test_failed_native_prepare_never_installs_or_mounts(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);log=root/'calls';fake=root/'python3'
   fake.write_text('#!/bin/sh\necho "$*" >> "'+str(log)+'"\nexit 7\n');fake.chmod(0o755)
   env=dict(os.environ,PATH=str(root)+':'+os.environ['PATH'],LUOSHU_NATIVE_PREPARE_TEST_APPROVED='true',LUOSHU_NATIVE_CONSUMER_TEST_APPROVED='true')
   result=subprocess.run(['sh',str(Path(__file__).with_name('run_selected_experiment.sh'))],env=env,capture_output=True)
   self.assertEqual(result.returncode,7);self.assertEqual(len(log.read_text().splitlines()),1)
   self.assertIn('--export-prepared',log.read_text())
 def test_native_consumer_branch_uses_export_then_install_then_same_payload(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);log=root/'calls'
   for name in ('python3','adb'):
    fake=root/name;fake.write_text('#!/bin/sh\necho "'+name+' $*" >> "'+str(log)+'"\n');fake.chmod(0o755)
   env=dict(os.environ,PATH=str(root)+':'+os.environ['PATH'],LUOSHU_NATIVE_PREPARE_TEST_APPROVED='true',LUOSHU_NATIVE_CONSUMER_TEST_APPROVED='true')
   result=subprocess.run(['sh',str(Path(__file__).with_name('run_selected_experiment.sh'))],env=env,capture_output=True)
   self.assertEqual(result.returncode,0,result.stderr)
   calls=log.read_text().splitlines();self.assertEqual(len(calls),3)
   self.assertIn('run_native_prepare.py',calls[0]);self.assertIn('--export-prepared',calls[0])
   self.assertTrue(calls[1].startswith('adb install -r -t'))
   self.assertIn('run_system_emulator.py',calls[2]);self.assertIn('--native-prepared-root',calls[2])
if __name__=='__main__':unittest.main()
