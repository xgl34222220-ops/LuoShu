"""Authorized disposable userdebug VM only: apply, reboot, restore, verify.

Never usable without the explicit CI authorization marker. No hidden API or
SELinux policy changes. Failure still attempts restoration and records evidence.
"""
import argparse, copy, hashlib, json, os, signal, subprocess, time
from pathlib import Path
import xml.etree.ElementTree as ET

PACKAGE='io.github.xgl34222220.luoshu.fontcontract'
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--inventory-only',action='store_true');p.add_argument('--production-payload',action='store_true');a=p.parse_args()
if os.environ.get('LUOSHU_DISPOSABLE_SYSTEM_TEST_APPROVED')!='true':
 raise SystemExit('disposable system mutation not authorized for this run')
a.output.mkdir(parents=True,exist_ok=True)
report={'scope':'disposable API36 userdebug CI emulator','rootManagerTested':False,'hardwareRomCoverage':False,'restored':False}
phase='preflight';started=time.monotonic();backups={};touched=False;new_fonts={};expected_roles={};asset='/system/fonts/LuoShuContractExperiment.ttf'
def save():
 report.update(stage=phase,elapsedSeconds=round(time.monotonic()-started,3),systemFilesTouched=touched)
 (a.output/'system-summary.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'stage':phase,'elapsedSeconds':report['elapsedSeconds'],'systemFilesTouched':touched}),flush=True)
def adb(*args,timeout=120,check=True):
 begin=time.monotonic();r=subprocess.run(['adb',*args],capture_output=True,timeout=timeout)
 with (a.output/'system-commands.jsonl').open('a') as f:f.write(json.dumps({'args':args,'returncode':r.returncode,'seconds':round(time.monotonic()-begin,3),'output':(r.stdout+r.stderr).decode(errors='replace')[-4000:]})+'\n')
 if check and r.returncode:raise RuntimeError('adb '+str(args)+': '+(r.stdout+r.stderr).decode(errors='replace'))
 return r.stdout

def read_system_file(remote):
 # exec-out can report exit 0 while cat prints a permission error on Android.
 # Check readability through shell-v2 first, before comparing any file bytes.
 adb('shell','test','-r',remote)
 return adb('exec-out','cat',remote)

def boot():
 adb('wait-for-device',timeout=120);until=time.monotonic()+240
 while time.monotonic()<until:
  if adb('shell','getprop','sys.boot_completed',check=False).strip()==b'1':return
  time.sleep(2)
 raise RuntimeError('emulator boot deadline exceeded')
def reboot():
 adb('reboot');time.sleep(2);boot()
def root():
 adb('root');adb('wait-for-device');assert adb('shell','id','-u').strip()==b'0','adbd root unavailable'
def probe(name, extra_args=None):
 extras=list(extra_args or [])
 if name=='system-applied':
  for role,contract in expected_roles.items():
   axes=','.join(str(x['tag'])+'='+str(x.get('stylevalue',x.get('value'))) for x in contract['axes'])
   extras+=['-e','expected'+role+'Path',contract['path'],'-e','expected'+role+'Face',str(contract['face'])]
   if axes:extras+=['-e','expected'+role+'Axes',axes]
 log=adb('shell','am','instrument','-w','-e','phase',name,*extras,PACKAGE+'/.Runner',timeout=180)
 (a.output/(name+'.txt')).write_bytes(log)
 raw=adb('exec-out','run-as',PACKAGE,'cat','files/report-'+name+'.json')
 (a.output/(name+'.json')).write_bytes(raw);r=json.loads(raw)
 if r.get('status')!=('passed-stock-axis-gate' if name=='stock-axis' else 'passed-system-gate'):raise RuntimeError(r)
 if name=='system-applied':
  for role,sample in [('Latin','A'),('Digit','1'),('Cjk','中')]:
   if role in expected_roles and r['actualDefaultFonts'][sample][0].get('sha256')!=expected_roles[role]['sha256']:
    raise RuntimeError('actual mapped font buffer differs from compiled artifact: '+role)
 return r

def rewrite(raw,ps):
 tree=ET.fromstring(raw);original_primary=[copy.deepcopy(f) for f in list(tree) if f.tag=='family' and f.get('name')=='sans-serif'];parents={child:parent for parent in tree.iter() for child in parent};count=0
 for font in tree.iter('font'):
  current=parents.get(font);family=None
  while current is not None:
   if current.tag in ('family','family-list') and current.get('name'):
    family=current.get('name');break
   current=parents.get(current)
  if family!='sans-serif' or font.get('style','normal')!='normal':continue
  font.text=Path(asset).name;font.set('index','0')
  for attr in ('postScriptName','postscriptName','name','supportedAxes'):font.attrib.pop(attr,None)
  font.set('postScriptName',ps)
  for child in list(font):
   if child.tag=='axis':font.remove(child)
  count+=1
 # The new primary asset intentionally lacks protected script coverage. Keep
 # the original primary immediately in fallback order for those missing glyphs.
 # Its bytes and axes remain unchanged; only the clone's family name is removed.
 if count:
  for source in reversed(original_primary):
   source.attrib.pop('name',None);tree.insert(1,source)
 return ET.tostring(tree,encoding='utf-8',xml_declaration=True),count

try:
 assert adb('shell','getprop','ro.kernel.qemu').strip()==b'1','not emulator'
 assert adb('shell','getprop','ro.build.type').strip()==b'userdebug','not userdebug'
 assert adb('shell','getprop','ro.build.version.sdk').strip()==b'36','unexpected API'
 report['baseline']=probe('system-baseline');phase='snapshot';save()
 root()  # Authorized disposable VM; snapshot system-only configuration too.
 # Refuse collision using the actual command exit status.
 exists=subprocess.run(['adb','shell','test','-e',asset]).returncode==0
 if exists:raise RuntimeError('experiment asset already exists')
 for remote in ['/system/etc/fonts.xml','/system/etc/font_fallback.xml']:
  r=subprocess.run(['adb','shell','test','-f',remote])
  if r.returncode:continue
  raw=read_system_file(remote);backups[remote]=raw
  (a.output/('original-'+Path(remote).name)).write_bytes(raw)
 if not backups:raise RuntimeError('no system font config found')
 for name,cmd in [('font-manager',['shell','dumpsys','font']),('font-files',['shell','find','-H','/system/etc','/product/etc','/vendor/etc','/system_ext/etc','/apex','-maxdepth','4','-iname','*font*'])]:
  (a.output/(name+'.txt')).write_bytes(adb(*cmd,timeout=30,check=False))
 for remote in ['/product/etc/fonts_customization.xml','/product/etc/font_fallback.xml','/system_ext/etc/font_fallback.xml']:
  r=subprocess.run(['adb','shell','test','-f',remote])
  if r.returncode==0:(a.output/('observed-'+remote.strip('/').replace('/','_'))).write_bytes(read_system_file(remote))
 if a.inventory_only:
  report['inventoryOnly']=True;report['takeover']='not-tested';phase='inventory-complete';save();raise SystemExit(0)
 report['originalConfigHashes']={k:hashlib.sha256(v).hexdigest() for k,v in backups.items()}
 assets=Path(__file__).parent/'app/src/main/assets'
 production=None
 if a.production_payload:
  phase='production-compile';save()
  work=Path(__file__).parent/'.work-production';(work/'stock').mkdir(parents=True,exist_ok=True)
  import sys
  sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'xml-first'))
  from build_production_case import build,required_stock_paths,stock_axis_cases
  captured={}
  captured_xml={remote:a.output/('original-'+Path(remote).name) for remote in backups}
  for logical in required_stock_paths(captured_xml,report['baseline']):
   if Path(logical).name not in {'Roboto-Regular.ttf','Roboto-Italic.ttf','NotoSansCJK-Regular.ttc','NotoSerifCJK-Regular.ttc'}:
    raise RuntimeError('unrecognized disposable SDK family member: '+logical)
   local=work/'stock'/Path(logical).name;adb('pull',logical,str(local));captured[logical]=local
  metadata,axis_cases=stock_axis_cases(captured_xml,captured)
  (a.output/'stock-axis-metadata.json').write_text(json.dumps({'fonts':metadata,'cases':axis_cases},indent=2))
  if axis_cases:
   import base64
   report['stockAxisProof']=probe('stock-axis',['-e','axisCases',base64.b64encode(json.dumps(axis_cases).encode()).decode()]);save()
  config='/data/fonts/config/config.xml';exists=subprocess.run(['adb','shell','test','-f',config]).returncode==0
  generation={'path':config,'exists':exists,'sha256':hashlib.sha256(read_system_file(config)).hexdigest() if exists else ''}
  def compile_deadline(_signal,_frame):raise TimeoutError('production compilation exceeded 600-second experimental budget')
  previous_alarm=signal.signal(signal.SIGALRM,compile_deadline);signal.alarm(600)
  try:
   payload,manifest,expected_roles,case_report=build(work/'generated',
     {remote:a.output/('original-'+Path(remote).name) for remote in backups},captured,
     report['baseline'],assets/'composite.ttf',generation,diagnostics=a.output,prove_cff2=True)
  finally:
   signal.alarm(0);signal.signal(signal.SIGALRM,previous_alarm)
  (a.output/'production-pipeline.json').write_text(json.dumps(case_report,indent=2))
  generated={f['logicalPath']:payload/f['payloadPath'] for f in manifest['files'] if f['kind']=='xml'}
  new_fonts={f['logicalPath']:payload/f['payloadPath'] for f in manifest['files'] if f['kind']!='xml'}
  if set(generated)-set(backups):raise RuntimeError('production XML escaped snapshotted configs')
  for logical in new_fonts:
   if not logical.startswith('/system/fonts/LuoShu') or subprocess.run(['adb','shell','test','-e',logical]).returncode==0:
    raise RuntimeError('production font escaped unique experimental assets')
  production=case_report
 phase='authorized-remount';save();root()
 old_boot=adb('shell','cat','/proc/sys/kernel/random/boot_id').strip()
 # -R may return nonzero because adbd disconnects during the requested reboot.
 # Do not treat its text as readiness: prove the boot identity changed, then
 # require a fresh remount command to succeed before touching any font file.
 remount_output=adb('remount','-R',timeout=120,check=False)
 until=time.monotonic()+240
 while time.monotonic()<until:
  current_boot=adb('shell','cat','/proc/sys/kernel/random/boot_id',timeout=10,check=False).strip()
  if current_boot and current_boot!=old_boot:break
  time.sleep(2)
 else:raise RuntimeError('remount preparation did not produce a new boot')
 boot();root();adb('remount')
 if production is None:
  fixture=json.loads((assets/'fixture.json').read_text());generated={};counts={}
  for remote,raw in backups.items():
   output,count=rewrite(raw,fixture['postScriptName']);counts[remote]=count
   if count:
    file=a.output/('patched-'+Path(remote).name);file.write_bytes(output);generated[remote]=file
  new_fonts={asset:assets/'composite.ttf'}
  report['changedRouteCounts']=counts
 else:report['productionPipeline']=production
 if not generated:raise RuntimeError('no explicit upright sans-serif config routes')
 phase='apply';save();touched=True
 for logical,local in new_fonts.items():
  adb('push',str(local),logical);adb('shell','chmod','0644',logical);adb('shell','restorecon',logical)
 for remote,file in generated.items():adb('push',str(file),remote);adb('shell','restorecon',remote)
 adb('shell','sync');phase='applied-reboot';save();reboot()
 root()
 report['appliedConfigHashes']={remote:hashlib.sha256(read_system_file(remote)).hexdigest() for remote in generated}
 for remote,file in generated.items():
  if report['appliedConfigHashes'][remote]!=hashlib.sha256(file.read_bytes()).hexdigest():raise RuntimeError('applied XML did not survive reboot: '+remote)
 for logical,local in new_fonts.items():
  if read_system_file(logical)!=local.read_bytes():raise RuntimeError('new font bytes did not survive reboot: '+logical)
 (a.output/'applied-font-manager.txt').write_bytes(adb('shell','dumpsys','font'))
 report['applied']=probe('system-applied');report['takeover']='passed'
except Exception as error:
 report['failure']=type(error).__name__+': '+str(error);report['takeover']=report.get('takeover','failed')
finally:
 if touched:
  try:
   phase='restoring';save();root();adb('remount')
   for remote,raw in backups.items():
    file=a.output/('original-'+Path(remote).name);adb('push',str(file),remote);adb('shell','restorecon',remote)
   for logical in new_fonts:adb('shell','rm','-f',logical)
   adb('shell','sync');reboot()
   root()  # adbd drops root across reboot; protected XML must be read as root.
   for remote,raw in backups.items():
    if read_system_file(remote)!=raw:raise RuntimeError('restored XML bytes differ: '+remote)
   report['restoredProbe']=probe('system-restored');report['restored']=True
  except Exception as error:report['restorationFailure']=type(error).__name__+': '+str(error)
 phase='finished';report['vmDisposal']='emulator action teardown and ephemeral runner deletion';save()
 for name,cmd in [('logcat',['logcat','-d','-t','400']),('mounts',['shell','cat','/proc/mounts'])]:
  try:(a.output/('system-'+name+'.txt')).write_bytes(adb(*cmd,timeout=15,check=False))
  except Exception:pass
print(json.dumps(report))
if report.get('takeover')!='passed' or not report['restored']:raise SystemExit(1)
