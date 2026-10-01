"""Stage a real production payload in the approved disposable Android VM."""
import base64,copy,hashlib,json,shutil,tempfile,math
import xml.etree.ElementTree as ET
from pathlib import Path

REMOTE='/data/local/tmp/luoshu-module-namespace'

def original_direct_axes(case, observed, metadata, xml_bytes):
 """Construct an explicit Font.Builder location from the frozen XML contract.
 Font.getAxes reports declared XML axes, not implicit supportedAxes selection.
 """
 matches=[m for m in metadata if m['path']==observed['file'] and m['face']==observed['face'] and m['sha256']==observed['sha256']]
 if len(matches)!=1:raise RuntimeError('direct original face lacks unique sealed axis metadata')
 nodes=[]
 for family in ET.fromstring(xml_bytes).findall('family'):
  if family.get('name')!=case['family']:continue
  for node in family.findall('font'):
   if (node.text or '').strip()==Path(observed['file']).name and int(node.get('index','0'))==observed['face']:nodes.append(node)
 if len(nodes)!=1:raise RuntimeError('direct original font lacks unique frozen family node')
 node=nodes[0];supported={x.strip() for x in node.get('supportedAxes','').split(',') if x.strip()}
 if supported-{'wght','ital'}:raise RuntimeError('unsupported direct original implicit axes')
 axes={a.get('tag'):float(a.get('stylevalue')) for a in node.findall('axis')}
 if len(axes)!=len(node.findall('axis')):raise RuntimeError('duplicate direct original XML axes')
 for tag,value in axes.items():
  if not math.isfinite(value) or observed.get('axes',{}).get(tag)!=value:raise RuntimeError('direct original declared axes differ from observed XML axes')
 selected={'wght':case['weight'],'ital':1 if case['italic'] else 0}
 for tag in supported:
  domain=matches[0]['axes'].get(tag)
  if domain is None:raise RuntimeError('declared implicit axis is absent from sealed face')
  axes[tag]=max(domain['min'],min(domain['max'],selected[tag]))
 return axes

def direct_contract(manifest, cases, baseline,metadata=None,xml_bytes=None):
 files=[{'path':f['logicalPath'],'sha256':f['sha256']} for f in manifest['files'] if f['kind']!='xml']
 known={f['path'] for f in files};selected=[]
 base={(x['family'],x['weight'],x['italic'],x['sample']):x for x in baseline['cases']}
 for case in cases:
  if case['sample'] not in ('A','1','中') and not (case['sample']=='Ω' and case['weight']==400 and not case['italic']):continue
  if case['expected']['path'] not in known:continue
  item=copy.deepcopy(case)
  if 'axes' not in item['expected']:
   observed=base[(case['family'],case['weight'],case['italic'],case['sample'])]['actualFonts'][0]
   if metadata is None or xml_bytes is None:raise RuntimeError('direct original glyph needs frozen XML and axis metadata')
   item['expected']['axes']=original_direct_axes(case,observed,metadata,xml_bytes)
   # Match the already-instanced outline's descriptor to avoid synthetic bold
   # being added again by CustomFallbackBuilder at the requested weight.
   item['expected']['referenceWeight']=case['weight']
  selected.append(item)
 emoji=base[('sans-serif',400,False,'😀')];font=emoji['actualFonts'][0]
 if font['file']!='/system/fonts/NotoColorEmoji.ttf':raise RuntimeError('unexpected protected emoji path')
 files.append({'path':font['file'],'sha256':font['sha256']})
 selected.append({'family':'sans-serif','weight':400,'italic':False,'sample':'😀','expected':{
  'path':font['file'],'sha256':font['sha256'],'face':font['face'],'fontWeight':font['weight'],'fontSlant':font['slant'],'axes':font['axes'],'raster':emoji['raster']}})
 if not {'A','1','中'}.issubset({x['sample'] for x in selected}):raise RuntimeError('direct contract lacks selected role coverage')
 return {'files':files,'cases':selected}

def run(adb,root,reboot,read_system_file,payload,manifest,captured,backups,output,direct=None):
 output=Path(output);module_report={'scope':'disposable API36 private mount namespace','globalAppConsumerTested':False,'rootManagerTested':False,'moduleBootTested':False,'state':'running'}
 created=False;global_attempted=False;global_restored=False;app_started=False;apply_completed=False
 original_key='originalsAfterRollback' if direct is not None else 'outsideNamespaceUnchanged'
 if direct is not None:
  module_report.update(scope='temporary global mounts with ordinary App direct font reads',ordinaryAppDirectReadTested=False,defaultTypefaceTakeoverTested=False)
 original={k:hashlib.sha256(v).hexdigest() for k,v in backups.items()}
 original.update({k:hashlib.sha256(Path(v).read_bytes()).hexdigest() for k,v in captured.items()})
 new=[f['logicalPath'] for f in manifest['files'] if f['kind']!='xml']
 def unchanged():
  for logical,sha in original.items():
   if hashlib.sha256(read_system_file(logical)).hexdigest()!=sha:raise RuntimeError('outside namespace original changed: '+logical)
  for logical in new:adb('shell','test','!','-e',logical)
 try:
  root()
  if direct is not None:
   if adb('shell','readlink','/proc/self/ns/mnt').strip()!=adb('shell','readlink','/proc/1/ns/mnt').strip():raise RuntimeError('global probe refuses namespace mismatch; no nsenter allowed')
   if adb('shell','getenforce').strip()!=b'Enforcing':raise RuntimeError('global probe requires unchanged enforcing SELinux')
  adb('shell','test','!','-e',REMOTE);adb('shell','mkdir',REMOTE);created=True
  runtime=Path(__file__).parent/'.runtime-x86'
  adb('push',str(runtime/'common'),REMOTE+'/common',timeout=180)
  adb('push',str(payload),REMOTE+'/.luoshu-payload',timeout=180)
  with tempfile.TemporaryDirectory() as td:
   local=Path(td);(local/'config').mkdir()
   (local/'config/active_font.conf').write_text('mix\n')
   (local/'config/universal-font-runtime.conf').write_text('state=active\npipeline=universal-font-deployment-v1\nfont=mix\ndeploymentId='+manifest['deploymentId']+'\npayloadDigest='+manifest['payloadDigest']+'\n')
   (local/'namespace-contract.json').write_text(json.dumps({'originalHashes':original,'newAssetPaths':new,'mountScope':module_report['scope']}))
   # This observer delegates every call to the real Android mount executable;
   # it cannot convert failure into success or synthesize a mount result.
   (local/'observe-mount.sh').write_text('''#!/system/bin/sh
err="$MODDIR/mount-error.$$"
/system/bin/mount "$@" 2> "$err"
rc=$?
if [ "$rc" -ne 0 ]; then
  /system/bin/dmesg 2>&1 | tail -n 120 > "$MODDIR/mount-kernel-tail.txt"
  cat /proc/self/mountinfo > "$MODDIR/mount-failure-mountinfo.txt"
fi
cat "$err" >&2
"$PYTHONHOME/bin/luoshu-python" -c 'import json,sys,pathlib; f=open(sys.argv[1],"a");f.write(json.dumps({"rc":int(sys.argv[2]),"stderr":pathlib.Path(sys.argv[3]).read_text(errors="replace")[-4000:],"args":sys.argv[4:]})+"\\n")' "$MODDIR/mount-calls.jsonl" "$rc" "$err" "$@"
rm -f "$err"
exit "$rc"
''')
   for path in local.iterdir():adb('push',str(path),REMOTE+'/'+path.name)
  for name in ('module_namespace_probe.sh','module_namespace_verify.py','module_global_probe.sh','bind_ownership_probe.sh'):
   adb('push',str(Path(__file__).with_name(name)),REMOTE+'/'+name)
  adb('shell','chmod','0755',REMOTE+'/observe-mount.sh',REMOTE+'/module_namespace_probe.sh')
  parent=adb('shell','readlink','/proc/self/ns/mnt').decode().strip()
  module_report['parentNamespace']=parent
  if direct is not None:
   adb('shell','mkdir',REMOTE+'/scripts')
   adb('push',str(Path(__file__).resolve().parents[2]/'scripts/bind_ownership_namespace_test.sh'),REMOTE+'/scripts/bind_ownership_namespace_test.sh')
   try:
    bind_log=adb('shell','env','LUOSHU_PARENT_MOUNT_NAMESPACE='+parent,'timeout','-k','5','60','unshare','-m','sh',REMOTE+'/bind_ownership_probe.sh',REMOTE,timeout=80)
   finally:
    adb('pull',REMOTE+'/bind-ownership-trace.txt',str(output/'android-bind-ownership-trace.txt'),check=False)
   (output/'android-bind-ownership.txt').write_bytes(bind_log)
   if b'bind_ownership_namespace_test: PASS' not in bind_log:raise RuntimeError('Android bind ownership proof did not complete')
   module_report['bindOwnershipPrivateNamespaceTested']=True
  if direct is None:
   raw=adb('shell','env','LUOSHU_PARENT_MOUNT_NAMESPACE='+parent,'timeout','-k','5','180','unshare','-m','/system/bin/sh',REMOTE+'/module_namespace_probe.sh',REMOTE,timeout=200)
  else:
   (output/'original-font-labels.txt').write_bytes(adb('shell','ls','-ldZ','/system/fonts','/system/etc',*backups.keys(),*captured.keys(),check=False))
   global_attempted=True;module_report['globalMountAttempted']=True
   raw=adb('shell','timeout','-k','5','150','sh',REMOTE+'/module_global_probe.sh',REMOTE,'apply',timeout=180)
   apply_completed=True
   paths=[f['path'] for f in direct['files']]
   stat_before=adb('shell','stat','-c','%d:%i',*paths).decode().splitlines()
   (output/'ordinary-app-file-labels.txt').write_bytes(adb('shell','ls','-lZ',*paths,check=False))
   package='io.github.xgl34222220.luoshu.fontcontract'
   encoded=base64.b64encode(json.dumps(direct).encode()).decode()
   app_started=True
   log=adb('shell','am','instrument','-w','-e','phase','direct-mounted','-e','directContract',encoded,package+'/.Runner',timeout=180)
   (output/'ordinary-app-direct-read.txt').write_bytes(log)
   data=adb('exec-out','run-as',package,'cat','files/report-direct-mounted.json')
   (output/'ordinary-app-direct-read.json').write_bytes(data);app=json.loads(data)
   if app.get('status')!='passed-direct-mounted-read':raise RuntimeError('ordinary App direct font read failed: '+str(app.get('error',app.get('status'))))
   observed=[str(f['device'])+':'+str(f['inode']) for f in app['files']]
   stat_after=adb('shell','stat','-c','%d:%i',*paths).decode().splitlines()
   if observed!=stat_before or observed!=stat_after:raise RuntimeError('App did not observe the mounted inode/device identity')
   if adb('shell','getenforce').strip()!=b'Enforcing':raise RuntimeError('SELinux enforcing state changed')
   module_report.update(ordinaryAppDirectReadTested=True,ordinaryApp=app)
   adb('shell','am','force-stop',package);app_started=False
   module_report['testAppStoppedBeforeRollback']=True
   adb('shell','timeout','-k','5','90','sh',REMOTE+'/module_global_probe.sh',REMOTE,'rollback',timeout=120);global_restored=True
  (output/'module-namespace-stdout.txt').write_bytes(raw)
  data=adb('exec-out','cat',REMOTE+'/namespace-result.json',check=False)
  (output/'module-namespace-result.json').write_bytes(data)
  parsed=json.loads(data)
  module_report['transaction']=parsed
  if parsed.get('state')!='passed':raise RuntimeError('namespace transaction did not pass every phase')
  if parsed.get('deploymentId')!=manifest['deploymentId'] or parsed.get('payloadDigest')!=manifest['payloadDigest']:
   raise RuntimeError('namespace result belongs to a different sealed deployment')
  unchanged();module_report[original_key]=True
  reboot();root();unchanged();module_report['rebootOriginalsUnchanged']=True
  module_report['state']='passed'
 except Exception as error:
  module_report['state']='failed'
  module_report['failure']=type(error).__name__+': '+str(error)
  if global_attempted:
   try:(output/'ordinary-app-kernel-tail.txt').write_bytes(adb('shell','dmesg',timeout=15,check=False)[-24000:])
   except Exception as diagnostic_error:module_report['diagnosticFailure']=str(diagnostic_error)
  raise
 finally:
  if created:
   # The bounded child namespace has no background workers. After it exits,
   # no test mounts may be reachable from this parent before removing staging.
   try:
    root()
    if app_started:
     adb('shell','am','force-stop','io.github.xgl34222220.luoshu.fontcontract');app_started=False
     module_report['testAppStoppedBeforeRollback']=True
    if global_attempted and not global_restored and not apply_completed:
     # A lost adb client must not race a possibly still-running global mount.
     # Reboot terminates that transaction and its ephemeral mounts first.
     reboot();root();unchanged();global_restored=True
     module_report.update(recoveryRebootAfterIncompleteApply=True,rebootOriginalsUnchanged=True)
    if global_attempted and not global_restored:
     adb('shell','timeout','-k','5','90','sh',REMOTE+'/module_global_probe.sh',REMOTE,'rollback',timeout=120);global_restored=True
    unchanged();module_report[original_key]=True
    if not module_report.get('rebootOriginalsUnchanged'):
     reboot();root();unchanged();module_report['rebootOriginalsUnchanged']=True
    adb('shell','test','!','-f',REMOTE+'/temporarily-hidden-font') if module_report['state']=='passed' else None
    for name in ('namespace-result.json','namespace-isolation.json','mount-calls.jsonl','mount-kernel-tail.txt','mount-failure-mountinfo.txt','logs/universal-mount.log','config/universal-font-mount.conf'):
     (output/('module-'+name.replace('/','-'))).write_bytes(adb('exec-out','cat',REMOTE+'/'+name,check=False))
    mountinfo=adb('shell','cat','/proc/self/mountinfo').decode()
    if any(line.split()[4].startswith(REMOTE+'/') for line in mountinfo.splitlines()):raise RuntimeError('refuse removal while staging mount remains')
    adb('shell','rm','-rf',REMOTE);adb('shell','test','!','-e',REMOTE)
    module_report['temporaryStageRemoved']=True
   except Exception as error:
    module_report['state']='failed';module_report['cleanupFailure']=str(error)
  (output/'module-namespace-summary.json').write_text(json.dumps(module_report,indent=2))
 if module_report.get('cleanupFailure'):raise RuntimeError(module_report['cleanupFailure'])
 return module_report
