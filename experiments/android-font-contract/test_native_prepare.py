import json,os,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'common'))
import native_prepare_pipeline as native
import run_native_prepare as host

class NativePrepareTest(unittest.TestCase):
 def test_real_composite_and_explicit_profile_metadata(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'inputs').mkdir();assets=Path(__file__).parent/'app/src/main/assets'
   for role in ('cjk','latin','digit'):shutil.copy2(assets/(role+'.ttf'),root/'inputs'/(role+'.ttf'))
   profile=native.build_composite(root);import font_source_profile
   font_source_profile.validate(profile)
   selection=profile['files'][0]['faces'][0]['mixedSelection']
   self.assertEqual(set(selection['roles']),{'cjk','latin','digit'})
   self.assertEqual(selection['fontSha256'],native.sha(root/'source/fonts/composite.ttf'))
   self.assertTrue(all(x['axisProvenance']=='static-component' and x['effectiveAxes']=={} for x in selection['roles'].values()))
 def test_host_or_unowned_root_is_rejected_before_scanning(self):
  with tempfile.TemporaryDirectory() as temp,patch.object(sys,'argv',['native','--module',temp]),patch.object(native.subprocess,'run') as command:
   self.assertEqual(native.main(),1);command.assert_not_called()
   report=json.loads((Path(temp)/'results/native-prepare-summary.json').read_text())
   self.assertFalse(report['androidPythonExecuted']);self.assertFalse(report['mountHookExecuted'])
 def test_scope_proof_requires_one_owned_empty_cleanup(self):
  proof={'task':host.TASK,'leftoverPids':[],'result':0}
  self.assertEqual(host.cleanup_proof(('[TASK-CLEANUP] '+json.dumps(proof)).encode()),proof)
  for value in [b'',b'[TASK-CLEANUP] {"task":"other","leftoverPids":[]}',b'[TASK-CLEANUP] {"task":"ci-native-full-prepare","leftoverPids":[22]}']:
   with self.assertRaises(RuntimeError):host.cleanup_proof(value)
 def test_native_shell_branch_is_one_process_and_no_app_fallthrough(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);fake=root/'python3';log=root/'calls'
   fake.write_text('#!/bin/sh\nprintf "%s\\n" "$1" >> "'+str(log)+'"\nexit 7\n');fake.chmod(0o755)
   env=dict(os.environ,PATH=str(root)+':'+os.environ['PATH'],LUOSHU_NATIVE_PREPARE_TEST_APPROVED='true',LUOSHU_DISPOSABLE_SYSTEM_TEST_APPROVED='true')
   result=subprocess.run(['sh',str(Path(__file__).with_name('run_selected_experiment.sh'))],env=env,capture_output=True,text=True)
   self.assertEqual(result.returncode,7)
   self.assertEqual(log.read_text().splitlines(),['experiments/android-font-contract/run_native_prepare.py'])
 def test_explicit_root_refusal_is_not_retried(self):
  calls=[]
  def adb(*args,**kwargs):
   calls.append(args);return subprocess.CompletedProcess(args,1,b'adbd cannot run as root' if args==('root',) else b'2000',b'')
  with self.assertRaises(PermissionError):host.ensure_root(adb)
  self.assertEqual(calls.count(('root',)),1)

if __name__=='__main__':unittest.main()
