"""Host orchestration guards; no claim of Android SELinux validation."""
import json,tempfile,unittest
from pathlib import Path
import run_module_namespace as runner

class GlobalProbeTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.out=Path(self.tmp.name);self.calls=[];self.apply_fails=True
 def adb(self,*args,**kwargs):
  self.calls.append(args)
  if args[:2]==('shell','readlink'):return b'mnt:[1]\n'
  if args==('shell','getenforce'):return b'Enforcing\n'
  if args[-1:] == ('apply',) and self.apply_fails:raise RuntimeError('injected mount failure')
  if args[:2]==('exec-out','run-as'):return b'{"status":"failed","error":"injected App refusal"}'
  if args[:2]==('exec-out','cat'):return b'{}'
  return b''
 def run_probe(self,adb):
  return runner.run(adb,lambda:None,lambda:self.calls.append(('reboot',)),lambda p:b'',self.out,{'files':[],'deploymentId':'test','payloadDigest':'test'},{},{},self.out,direct={'files':[],'cases':[]})
 def test_namespace_mismatch_precedes_staging(self):
  def adb(*args,**kwargs):
   if args==('shell','readlink','/proc/1/ns/mnt'):return b'mnt:[2]'
   return self.adb(*args,**kwargs)
  with self.assertRaisesRegex(RuntimeError,'namespace mismatch'):self.run_probe(adb)
  self.assertFalse(any('mkdir' in x or 'push' in x for x in self.calls))
 def test_non_enforcing_precedes_staging(self):
  def adb(*args,**kwargs):
   if args==('shell','getenforce'):return b'Permissive'
   return self.adb(*args,**kwargs)
  with self.assertRaisesRegex(RuntimeError,'enforcing'):self.run_probe(adb)
  self.assertFalse(any('mkdir' in x or 'push' in x for x in self.calls))
 def test_app_failure_runs_rollback_before_cleanup(self):
  self.apply_fails=False
  with self.assertRaisesRegex(RuntimeError,'injected App refusal'):self.run_probe(self.adb)
  rollback=next(i for i,x in enumerate(self.calls) if x[-1:]==('rollback',))
  removal=next(i for i,x in enumerate(self.calls) if x[:3]==('shell','rm','-rf'))
  self.assertLess(rollback,removal)
  self.assertTrue(json.loads((self.out/'module-namespace-summary.json').read_text())['temporaryStageRemoved'])
 def test_failed_rollback_never_removes_live_staging(self):
  self.apply_fails=False
  def adb(*args,**kwargs):
   if args[-1:]==('rollback',):raise RuntimeError('unmount blocked')
   return self.adb(*args,**kwargs)
  with self.assertRaisesRegex(RuntimeError,'injected App refusal'):self.run_probe(adb)
  self.assertFalse(any(x[:3]==('shell','rm','-rf') for x in self.calls))
  self.assertIn('unmount blocked',json.loads((self.out/'module-namespace-summary.json').read_text())['cleanupFailure'])
 def test_incomplete_apply_reboots_before_removal(self):
  with self.assertRaisesRegex(RuntimeError,'injected mount failure'):self.run_probe(self.adb)
  reboot=self.calls.index(('reboot',));removal=next(i for i,x in enumerate(self.calls) if x[:3]==('shell','rm','-rf'))
  self.assertLess(reboot,removal)
  self.assertFalse(any(x[-1:]==('rollback',) for x in self.calls))
  self.assertTrue(json.loads((self.out/'module-namespace-summary.json').read_text())['recoveryRebootAfterIncompleteApply'])
 def test_remaining_staging_mount_never_removed(self):
  def adb(*args,**kwargs):
   if args==('shell','cat','/proc/self/mountinfo'):return ('1 0 0:1 / '+runner.REMOTE+'/state/layer ro - tmpfs tmpfs ro\n').encode()
   return self.adb(*args,**kwargs)
  with self.assertRaisesRegex(RuntimeError,'injected mount failure'):self.run_probe(adb)
  self.assertFalse(any(x[:3]==('shell','rm','-rf') for x in self.calls))

class DirectContractTest(unittest.TestCase):
 def test_roles_and_preserved_axes_are_explicit(self):
  selected=[];baseline=[];files=[]
  for sample in ('A','1','中','Ω','😀'):
   path='/system/fonts/NotoColorEmoji.ttf' if sample=='😀' else '/system/fonts/LuoShu-'+sample+'.ttf'
   case={'family':'sans-serif','weight':400,'italic':False,'sample':sample}
   font={'file':path,'sha256':'hash','face':0,'weight':400,'slant':0,'axes':{'wdth':75}}
   baseline.append({**case,'actualFonts':[font],'raster':'pixels'})
   if sample!='😀':
    files.append({'logicalPath':path,'kind':'font','sha256':'hash'})
    selected.append({**case,'expected':{'path':path,'sha256':'hash','face':0,'fontWeight':400,'fontSlant':0}})
  result=runner.direct_contract({'files':files},selected,{'cases':baseline})
  self.assertEqual({x['sample'] for x in result['cases']},{'A','1','中','Ω','😀'})
  self.assertTrue(all(x['expected']['axes']=={'wdth':75} for x in result['cases']))
  self.assertNotIn('axes',selected[0]['expected'])
  self.assertEqual(len(result['files']),5)
 def test_missing_role_is_not_a_valid_direct_probe(self):
  emoji={'family':'sans-serif','weight':400,'italic':False,'sample':'😀','actualFonts':[{'file':'/system/fonts/NotoColorEmoji.ttf','sha256':'h','face':0,'weight':400,'slant':0,'axes':{}}],'raster':'r'}
  with self.assertRaisesRegex(RuntimeError,'lacks selected role'):runner.direct_contract({'files':[]},[],{'cases':[emoji]})

if __name__=='__main__':unittest.main()
