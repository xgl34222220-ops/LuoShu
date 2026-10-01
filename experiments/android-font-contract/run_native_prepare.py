"""Run the full production prepare path on disposable Android x86, without apply."""
import argparse,json,os,subprocess,time,traceback
from pathlib import Path
REMOTE='/data/local/tmp/luoshu-native-prepare'
TASK='ci-native-full-prepare'
SYSTEM_FILES=['/system/etc/fonts.xml','/system/etc/font_fallback.xml','/system/fonts/Roboto-Regular.ttf','/system/fonts/NotoSansCJK-Regular.ttc']

def cleanup_proof(stdout):
 proofs=[]
 for line in stdout.decode(errors='replace').splitlines():
  if '[TASK-CLEANUP] ' in line:proofs.append(json.loads(line.split('[TASK-CLEANUP] ',1)[1]))
 if len(proofs)!=1 or proofs[0].get('task')!=TASK or proofs[0].get('leftoverPids'):
  raise RuntimeError('owned native process cleanup was not proved')
 return proofs[0]

def ensure_root(adb):
 for attempt in range(2):
  adb('wait-for-device',timeout=15)
  if adb('shell','id','-u',timeout=5,check=False).stdout.strip()==b'0':return
  result=adb('root',timeout=10,check=False)
  if b'cannot run as root' in result.stdout+result.stderr:raise PermissionError('adbd refused root')
  adb('wait-for-device',timeout=15)
  if adb('shell','id','-u',timeout=5,check=False).stdout.strip()==b'0':return
 raise RuntimeError('disposable root verification failed')

def main():
 p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--fixtures',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 if os.environ.get('LUOSHU_DISPOSABLE_SYSTEM_TEST_APPROVED')!='true' or os.environ.get('LUOSHU_NATIVE_PREPARE_TEST_APPROVED')!='true':raise SystemExit('native prepare experiment was not approved')
 report={'state':'running','scope':'disposable API36 Android x86 full prepare only','shippedArm64RuntimeExecuted':False,'systemFontMutation':False,'mountHookExecuted':False};owned=False;scope_done=False;before=None;results_pulled=False
 def adb(*args,timeout=60,check=True):
  start=time.monotonic();r=subprocess.run(['adb',*args],capture_output=True,timeout=timeout)
  with (a.output/'commands.jsonl').open('a') as f:f.write(json.dumps({'args':args,'returncode':r.returncode,'seconds':round(time.monotonic()-start,3),'output':(r.stdout+r.stderr).decode(errors='replace')[-3000:]})+'\n')
  if check and r.returncode:raise RuntimeError('adb '+str(args)+': '+(r.stdout+r.stderr).decode(errors='replace')[-3000:])
  return r
 def originals():return adb('shell','sha256sum',*SYSTEM_FILES,timeout=60).stdout
 def reboot():
  old=adb('shell','cat','/proc/sys/kernel/random/boot_id').stdout.strip();adb('reboot',check=False);adb('wait-for-device',timeout=180)
  until=time.monotonic()+180
  while time.monotonic()<until:
   boot=adb('shell','cat','/proc/sys/kernel/random/boot_id',timeout=10,check=False).stdout.strip()
   if boot and boot!=old and adb('shell','getprop','sys.boot_completed',timeout=10,check=False).stdout.strip()==b'1':ensure_root(adb);return
   time.sleep(2)
  raise RuntimeError('recovery reboot did not complete')
 try:
  for prop,value in [('ro.kernel.qemu','1'),('ro.build.version.sdk','36'),('ro.product.cpu.abi','x86_64')]:
   if adb('shell','getprop',prop).stdout.decode().strip()!=value:raise RuntimeError('unexpected disposable environment')
  ensure_root(adb)
  if adb('shell','getenforce').stdout.strip()!=b'Enforcing':raise RuntimeError('SELinux must remain Enforcing')
  before=originals();(a.output/'original-sha256-before.txt').write_bytes(before)
  adb('shell','test','!','-e',REMOTE)
  origin=json.loads((a.runtime/'runtime-origin.json').read_text())
  if origin.get('architecture')!='x86_64':raise RuntimeError('CI runtime architecture mismatch')
  owned=True;adb('push',str(a.runtime),REMOTE,timeout=180);adb('shell','mkdir',REMOTE+'/inputs')
  for role in ('cjk','latin','digit'):adb('push',str(a.fixtures/(role+'.ttf')),REMOTE+'/inputs/'+role+'.ttf')
  adb('push',str(Path(__file__).with_name('native_prepare_pipeline.py')),REMOTE+'/pipeline.py')
  py=REMOTE+'/common/python';env=['env','MODDIR='+REMOTE,'MODULE_DIR='+REMOTE,'PYTHONUTF8=1','PYTHONHOME='+py,'PYTHONPATH='+REMOTE+'/common:'+py+'/lib/python3.14/site-packages','LD_LIBRARY_PATH='+py+'/lib:'+py+'/lib/python3.14/lib-dynload']
  print(json.dumps({'stage':'android-full-prepare','budgetSeconds':900,'architecture':'x86_64'}),flush=True)
  r=adb('shell',*env,py+'/bin/luoshu-python',REMOTE+'/common/task_scope.py','--task',TASK,'--timeout','900','--',py+'/bin/luoshu-python',REMOTE+'/pipeline.py','--module',REMOTE,timeout=940,check=False)
  output=r.stdout+r.stderr;(a.output/'native-stdout.txt').write_bytes(output)
  proof=cleanup_proof(output);scope_done=True;report['cleanupScope']=proof
  adb('pull',REMOTE+'/results',str(a.output/'results'),timeout=120);results_pulled=True
  summary=json.loads((a.output/'results/native-prepare-summary.json').read_text());report['native']=summary
  if r.returncode or proof.get('result')!=0 or proof.get('deadlineExceeded') or summary.get('state')!='passed':raise RuntimeError('native prepare failed: '+str(summary.get('error',r.returncode)))
  after=originals();(a.output/'original-sha256-after.txt').write_bytes(after)
  if after!=before:raise RuntimeError('original SDK font/config bytes changed')
  if adb('shell','getenforce').stdout.strip()!=b'Enforcing':raise RuntimeError('SELinux state changed')
  report.update(state='passed',originalsUnchanged=True,runtimeOrigin=origin)
 except Exception as e:report.update(state='failed',error=str(e),trace=traceback.format_exc(limit=12))
 finally:
  if owned:
   try:
    if not scope_done:reboot();report['recoveryRebootBeforeCleanup']=True
    ensure_root(adb)
    if not results_pulled:adb('pull',REMOTE+'/results',str(a.output/'results'),timeout=120,check=False)
    mounts=adb('shell','cat','/proc/self/mountinfo').stdout.decode()
    if any(line.split()[4].startswith(REMOTE+'/') for line in mounts.splitlines()):raise RuntimeError('owned stock view is still mounted; refuse recursive deletion')
    if before is not None and originals()!=before:raise RuntimeError('originals changed before cleanup')
    adb('shell','rm','-rf',REMOTE);adb('shell','test','!','-e',REMOTE)
    report['temporaryModuleRemoved']=True
   except Exception as e:report.update(state='failed',cleanupError=str(e))
  (a.output/'summary.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
 return 0 if report.get('state')=='passed' and report.get('temporaryModuleRemoved') is True else 1

if __name__=='__main__':raise SystemExit(main())
