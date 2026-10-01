"""Stage a real production payload in the approved disposable Android VM."""
import hashlib,json,shutil,tempfile
from pathlib import Path

REMOTE='/data/local/tmp/luoshu-module-namespace'

def run(adb,root,reboot,read_system_file,payload,manifest,captured,backups,output):
 output=Path(output);module_report={'scope':'disposable API36 private mount namespace','globalAppConsumerTested':False,'rootManagerTested':False,'moduleBootTested':False,'state':'running'}
 created=False
 original={k:hashlib.sha256(v).hexdigest() for k,v in backups.items()}
 original.update({k:hashlib.sha256(Path(v).read_bytes()).hexdigest() for k,v in captured.items()})
 new=[f['logicalPath'] for f in manifest['files'] if f['kind']!='xml']
 def unchanged():
  for logical,sha in original.items():
   if hashlib.sha256(read_system_file(logical)).hexdigest()!=sha:raise RuntimeError('outside namespace original changed: '+logical)
  for logical in new:adb('shell','test','!','-e',logical)
 try:
  root();adb('shell','test','!','-e',REMOTE);adb('shell','mkdir',REMOTE);created=True
  runtime=Path(__file__).parent/'.runtime-x86'
  adb('push',str(runtime/'common'),REMOTE+'/common',timeout=180)
  adb('push',str(payload),REMOTE+'/.luoshu-payload',timeout=180)
  with tempfile.TemporaryDirectory() as td:
   local=Path(td);(local/'config').mkdir()
   (local/'config/active_font.conf').write_text('mix\n')
   (local/'config/universal-font-runtime.conf').write_text('state=active\npipeline=universal-font-deployment-v1\nfont=mix\ndeploymentId='+manifest['deploymentId']+'\npayloadDigest='+manifest['payloadDigest']+'\n')
   (local/'namespace-contract.json').write_text(json.dumps({'originalHashes':original,'newAssetPaths':new}))
   # This observer delegates every call to the real Android mount executable;
   # it cannot convert failure into success or synthesize a mount result.
   (local/'observe-mount.sh').write_text('''#!/system/bin/sh
err="$MODDIR/mount-error.$$"
/system/bin/mount "$@" 2> "$err"
rc=$?
cat "$err" >&2
"$PYTHONHOME/bin/luoshu-python" -c 'import json,sys,pathlib; f=open(sys.argv[1],"a");f.write(json.dumps({"rc":int(sys.argv[2]),"stderr":pathlib.Path(sys.argv[3]).read_text(errors="replace")[-4000:],"args":sys.argv[4:]})+"\\n")' "$MODDIR/mount-calls.jsonl" "$rc" "$err" "$@"
rm -f "$err"
exit "$rc"
''')
   for path in local.iterdir():adb('push',str(path),REMOTE+'/'+path.name)
  for name in ('module_namespace_probe.sh','module_namespace_verify.py'):
   adb('push',str(Path(__file__).with_name(name)),REMOTE+'/'+name)
  adb('shell','chmod','0755',REMOTE+'/observe-mount.sh',REMOTE+'/module_namespace_probe.sh')
  parent=adb('shell','readlink','/proc/self/ns/mnt').decode().strip()
  module_report['parentNamespace']=parent
  raw=adb('shell','env','LUOSHU_PARENT_MOUNT_NAMESPACE='+parent,'timeout','-k','5','180','unshare','-m','/system/bin/sh',REMOTE+'/module_namespace_probe.sh',REMOTE,timeout=200)
  (output/'module-namespace-stdout.txt').write_bytes(raw)
  data=adb('exec-out','cat',REMOTE+'/namespace-result.json',check=False)
  (output/'module-namespace-result.json').write_bytes(data)
  parsed=json.loads(data)
  module_report['transaction']=parsed
  if parsed.get('state')!='passed':raise RuntimeError('namespace transaction did not pass every phase')
  if parsed.get('deploymentId')!=manifest['deploymentId'] or parsed.get('payloadDigest')!=manifest['payloadDigest']:
   raise RuntimeError('namespace result belongs to a different sealed deployment')
  unchanged();module_report['outsideNamespaceUnchanged']=True
  reboot();root();unchanged();module_report['rebootOriginalsUnchanged']=True
  module_report['state']='passed'
 except Exception as error:
  module_report['state']='failed'
  module_report['failure']=type(error).__name__+': '+str(error)
  raise
 finally:
  if created:
   # The bounded child namespace has no background workers. After it exits,
   # no test mounts may be reachable from this parent before removing staging.
   try:
    root();unchanged();module_report['outsideNamespaceUnchanged']=True
    if not module_report.get('rebootOriginalsUnchanged'):
     reboot();root();unchanged();module_report['rebootOriginalsUnchanged']=True
    adb('shell','test','!','-f',REMOTE+'/temporarily-hidden-font') if module_report['state']=='passed' else None
    for name in ('namespace-result.json','mount-calls.jsonl'):
     (output/('module-'+name)).write_bytes(adb('exec-out','cat',REMOTE+'/'+name,check=False))
    adb('shell','rm','-rf',REMOTE);adb('shell','test','!','-e',REMOTE)
    module_report['temporaryStageRemoved']=True
   except Exception as error:
    module_report['state']='failed';module_report['cleanupFailure']=str(error)
  (output/'module-namespace-summary.json').write_text(json.dumps(module_report,indent=2))
 if module_report.get('cleanupFailure'):raise RuntimeError(module_report['cleanupFailure'])
 return module_report
