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
  if 'unshare' in args:return b'bind_ownership_namespace_test: PASS'
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
 def test_exact_staging_root_mount_never_removed(self):
  def adb(*args,**kwargs):
   if args==('shell','cat','/proc/self/mountinfo'):return ('1 0 0:1 / '+runner.REMOTE+' ro - tmpfs tmpfs ro\n').encode()
   return self.adb(*args,**kwargs)
  with self.assertRaisesRegex(RuntimeError,'injected mount failure'):self.run_probe(adb)
  self.assertFalse(any(x[:3]==('shell','rm','-rf') for x in self.calls))

class FrameworkGlobalTest(unittest.TestCase):
 setUp=GlobalProbeTest.setUp
 adb=GlobalProbeTest.adb
 def cycle(self):
  parent=self
  class Cycle:
   stopped=False
   def stop(self):self.stopped=True;parent.calls.append(('framework-stop',))
   def start(self):self.stopped=False;parent.calls.append(('framework-start',));return {'newSystemServer':['2','200']}
  return Cycle()
 def good_adb(self,*args,**kwargs):
  if args[:2]==('exec-out','run-as'):
   self.calls.append(args);return b'{"status":"passed-direct-mounted-read","files":[]}'
  if args==('exec-out','cat',runner.REMOTE+'/namespace-result.json'):
   return b'{"state":"passed","deploymentId":"test","payloadDigest":"test"}'
  return self.adb(*args,**kwargs)
 def framework_probe(self,callback):
  self.apply_fails=False
  return runner.run(self.good_adb,lambda:None,lambda:self.calls.append(('reboot',)),lambda p:b'',self.out,{'files':[],'deploymentId':'test','payloadDigest':'test'},{},{},self.out,direct={'files':[],'cases':[]},framework=self.cycle(),default_probe=callback)
 def test_default_consumers_surround_real_rollback_protocol(self):
  result=self.framework_probe(lambda phase:self.calls.append(('default',phase)) or {'status':'passed-style-matrix'})
  order=[x for x in self.calls if x[0].startswith('framework') or x[0]=='default' or x[-1:] in [('apply',),('rollback',)]]
  self.assertEqual([x if x[0]!='shell' else (x[-1],) for x in order],[('framework-stop',),('apply',),('framework-start',),('default','mounted'),('framework-stop',),('rollback',),('framework-start',),('default','restored')])
  self.assertTrue(result['defaultTypefaceTakeoverTested']);self.assertTrue(result['rebootOriginalsUnchanged'])
 def test_failed_default_consumer_reboots_before_removing_stage(self):
  def fail(phase):raise RuntimeError('default consumer failed')
  with self.assertRaisesRegex(RuntimeError,'default consumer failed'):self.framework_probe(fail)
  reboot=self.calls.index(('reboot',));removal=next(i for i,x in enumerate(self.calls) if x[:3]==('shell','rm','-rf'))
  self.assertLess(reboot,removal)
  report=json.loads((self.out/'module-namespace-summary.json').read_text())
  self.assertTrue(report['recoveryRebootAfterFrameworkFailure']);self.assertEqual(report['state'],'failed')

class StagedHookTest(unittest.TestCase):
 setUp=GlobalProbeTest.setUp
 adb=GlobalProbeTest.adb
 cycle=FrameworkGlobalTest.cycle
 good_adb=FrameworkGlobalTest.good_adb
 def test_staged_payload_has_no_precreated_active_runtime(self):
  self.apply_fails=False;captured={}
  def adb(*args,**kwargs):
   if args[:1]==('push',) and args[-1]==runner.REMOTE+'/config':
    directory=Path(args[1]);captured.update({p.name:p.read_text() for p in directory.iterdir()})
   if args[-1:]==('apply',):
    self.calls.append(args);return b'STAGED_HOOKS next-to-live and deferred post-mount verified'
   return self.good_adb(*args,**kwargs)
  result=runner.run(adb,lambda:None,lambda:self.calls.append(('reboot',)),lambda p:b'',self.out,{'files':[],'deploymentId':'test','payloadDigest':'test'},{},{},self.out,direct={'files':[],'cases':[]},framework=self.cycle(),default_probe=lambda phase:{'status':'passed-style-matrix'},staged_hooks=True)
  self.assertIn('universal-font-next.conf',captured);self.assertNotIn('universal-font-runtime.conf',captured)
  self.assertEqual(captured['active_font.conf'],'default\n')
  self.assertTrue(any(x[0]=='push' and x[-1]==runner.REMOTE+'/.luoshu-payload-next' for x in self.calls))
  self.assertTrue(result['manualTopLevelHooksTested']);self.assertFalse(result['actualBootActivationTested']);self.assertFalse(result['rootManagerTested'])
 def test_missing_hook_proof_cannot_succeed(self):
  self.apply_fails=False
  with self.assertRaisesRegex(RuntimeError,'hook proof missing'):
   runner.run(self.good_adb,lambda:None,lambda:self.calls.append(('reboot',)),lambda p:b'',self.out,{'files':[],'deploymentId':'test','payloadDigest':'test'},{},{},self.out,direct={'files':[],'cases':[]},framework=self.cycle(),default_probe=lambda phase:{},staged_hooks=True)
  self.assertIn(('reboot',),self.calls)

class DirectContractTest(unittest.TestCase):
 def test_roles_and_preserved_axes_are_explicit(self):
  selected=[];baseline=[];files=[];metadata=[];nodes=[]
  for sample in ('A','1','中','Ω','😀'):
   path='/system/fonts/NotoColorEmoji.ttf' if sample=='😀' else '/system/fonts/LuoShu-'+sample+'.ttf'
   case={'family':'sans-serif','weight':400,'italic':False,'sample':sample}
   font={'file':path,'sha256':'hash','face':0,'weight':400,'slant':0,'axes':{'wdth':75}}
   baseline.append({**case,'actualFonts':[font],'raster':'pixels'})
   if sample!='😀':
    metadata.append({'path':path,'face':0,'sha256':'hash','axes':{'wght':{'min':100,'max':900},'ital':{'min':0,'max':1}}})
    nodes.append('<font supportedAxes="wght,ital">'+Path(path).name+'<axis tag="wdth" stylevalue="75"/></font>')
    files.append({'logicalPath':path,'kind':'font','sha256':'hash'})
    selected.append({**case,'expected':{'path':path,'sha256':'hash','face':0,'fontWeight':400,'fontSlant':0}})
  result=runner.direct_contract({'files':files},selected,{'cases':baseline},metadata,('<familyset><family name="sans-serif">'+''.join(nodes)+'</family></familyset>').encode())
  self.assertEqual({x['sample'] for x in result['cases']},{'A','1','中','Ω','😀'})
  self.assertTrue(all(x['expected']['axes']=={'wdth':75,'wght':400,'ital':0} for x in result['cases'] if x['sample']!='😀'))
  self.assertNotIn('axes',selected[0]['expected'])
  self.assertEqual(len(result['files']),5)
 def test_missing_role_is_not_a_valid_direct_probe(self):
  emoji={'family':'sans-serif','weight':400,'italic':False,'sample':'😀','actualFonts':[{'file':'/system/fonts/NotoColorEmoji.ttf','sha256':'h','face':0,'weight':400,'slant':0,'axes':{}}],'raster':'r'}
  with self.assertRaisesRegex(RuntimeError,'lacks selected role'):runner.direct_contract({'files':[]},[],{'cases':[emoji]})

class OriginalDirectAxesTest(unittest.TestCase):
 def setUp(self):
  self.case={'family':'sans-serif','weight':1,'italic':True}
  self.font={'file':'/system/fonts/Original.ttf','face':0,'sha256':'sealed','axes':{'wdth':75}}
  self.meta=[{'path':self.font['file'],'face':0,'sha256':'sealed','axes':{'wght':{'min':100,'max':900},'ital':{'min':0,'max':1}}}]
  self.xml=b'<familyset><family name="sans-serif"><font supportedAxes="wght,ital">Original.ttf<axis tag="wdth" stylevalue="75"/></font></family></familyset>'
 def test_implicit_weight_and_real_italic_are_explicit_and_clamped(self):
  self.assertEqual(runner.original_direct_axes(self.case,self.font,self.meta,self.xml),{'wdth':75,'wght':100,'ital':1})
  self.case.update(weight=1000,italic=False)
  self.assertEqual(runner.original_direct_axes(self.case,self.font,self.meta,self.xml),{'wdth':75,'wght':900,'ital':0})
 def test_wrong_original_hash_is_rejected(self):
  self.meta[0]['sha256']='different'
  with self.assertRaisesRegex(RuntimeError,'sealed axis'):runner.original_direct_axes(self.case,self.font,self.meta,self.xml)
 def test_wrong_declared_width_is_rejected(self):
  self.font['axes']['wdth']=100
  with self.assertRaisesRegex(RuntimeError,'declared axes'):runner.original_direct_axes(self.case,self.font,self.meta,self.xml)

if __name__=='__main__':unittest.main()
