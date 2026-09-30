"""Authorized disposable userdebug VM only: apply, reboot, restore, verify.

Never usable without the explicit CI authorization marker. No hidden API or
SELinux policy changes. Failure still attempts restoration and records evidence.
"""
import argparse, hashlib, json, os, subprocess, time
from pathlib import Path
import xml.etree.ElementTree as ET

PACKAGE='io.github.xgl34222220.luoshu.fontcontract'
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--inventory-only',action='store_true');a=p.parse_args()
if os.environ.get('LUOSHU_DISPOSABLE_SYSTEM_TEST_APPROVED')!='true':
 raise SystemExit('disposable system mutation not authorized for this run')
a.output.mkdir(parents=True,exist_ok=True)
report={'scope':'disposable API36 userdebug CI emulator','rootManagerTested':False,'hardwareRomCoverage':False,'restored':False}
phase='preflight';started=time.monotonic();backups={};touched=False;asset='/system/fonts/LuoShuContractExperiment.ttf'
def save():
 report.update(stage=phase,elapsedSeconds=round(time.monotonic()-started,3))
 (a.output/'system-summary.json').write_text(json.dumps(report,indent=2)+'\n')
def adb(*args,timeout=120,check=True):
 begin=time.monotonic();r=subprocess.run(['adb',*args],capture_output=True,timeout=timeout)
 with (a.output/'system-commands.jsonl').open('a') as f:f.write(json.dumps({'args':args,'returncode':r.returncode,'seconds':round(time.monotonic()-begin,3),'output':(r.stdout+r.stderr).decode(errors='replace')[-4000:]})+'\n')
 if check and r.returncode:raise RuntimeError('adb '+str(args)+': '+(r.stdout+r.stderr).decode(errors='replace'))
 return r.stdout

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
def probe(name):
 log=adb('shell','am','instrument','-w','-e','phase',name,PACKAGE+'/.Runner',timeout=180)
 (a.output/(name+'.txt')).write_bytes(log)
 raw=adb('exec-out','run-as',PACKAGE,'cat','files/report-'+name+'.json')
 (a.output/(name+'.json')).write_bytes(raw);r=json.loads(raw)
 if r.get('status')!='passed-system-gate':raise RuntimeError(r)
 return r

def rewrite(raw,ps):
 tree=ET.fromstring(raw);parents={child:parent for parent in tree.iter() for child in parent};count=0
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
  raw=adb('exec-out','cat',remote);backups[remote]=raw
  (a.output/('original-'+Path(remote).name)).write_bytes(raw)
 if not backups:raise RuntimeError('no system font config found')
 for name,cmd in [('font-manager',['shell','dumpsys','font']),('font-files',['shell','find','-H','/system/etc','/product/etc','/vendor/etc','/system_ext/etc','/apex','-maxdepth','4','-iname','*font*'])]:
  (a.output/(name+'.txt')).write_bytes(adb(*cmd,timeout=30,check=False))
 for remote in ['/product/etc/fonts_customization.xml','/product/etc/font_fallback.xml','/system_ext/etc/font_fallback.xml']:
  r=subprocess.run(['adb','shell','test','-f',remote])
  if r.returncode==0:(a.output/('observed-'+remote.strip('/').replace('/','_'))).write_bytes(adb('exec-out','cat',remote))
 if a.inventory_only:
  report['inventoryOnly']=True;report['takeover']='not-tested';phase='inventory-complete';save();raise SystemExit(0)
 report['originalConfigHashes']={k:hashlib.sha256(v).hexdigest() for k,v in backups.items()}
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
 assets=Path(__file__).parent/'app/src/main/assets';fixture=json.loads((assets/'fixture.json').read_text())
 generated={};counts={}
 for remote,raw in backups.items():
  output,count=rewrite(raw,fixture['postScriptName']);counts[remote]=count
  if count:
   file=a.output/('patched-'+Path(remote).name);file.write_bytes(output);generated[remote]=file
 if not generated:raise RuntimeError('no explicit upright sans-serif config routes')
 report['changedRouteCounts']=counts;phase='apply';save();touched=True
 adb('push',str(assets/'composite.ttf'),asset);adb('shell','chmod','0644',asset);adb('shell','restorecon',asset)
 for remote,file in generated.items():adb('push',str(file),remote);adb('shell','restorecon',remote)
 adb('shell','sync');phase='applied-reboot';save();reboot()
 report['applied']=probe('system-applied');report['takeover']='passed'
except Exception as error:
 report['failure']=type(error).__name__+': '+str(error);report['takeover']=report.get('takeover','failed')
finally:
 if touched:
  try:
   phase='restoring';save();root();adb('remount')
   for remote,raw in backups.items():
    file=a.output/('original-'+Path(remote).name);adb('push',str(file),remote);adb('shell','restorecon',remote)
   adb('shell','rm',asset);adb('shell','sync');reboot()
   for remote,raw in backups.items():
    if adb('exec-out','cat',remote)!=raw:raise RuntimeError('restored XML bytes differ: '+remote)
   report['restoredProbe']=probe('system-restored');report['restored']=True
  except Exception as error:report['restorationFailure']=type(error).__name__+': '+str(error)
 phase='finished';report['vmDisposal']='emulator action teardown and ephemeral runner deletion';save()
 for name,cmd in [('logcat',['logcat','-d','-t','400']),('mounts',['shell','cat','/proc/mounts'])]:
  try:(a.output/('system-'+name+'.txt')).write_bytes(adb(*cmd,timeout=15,check=False))
  except Exception:pass
print(json.dumps(report))
if report.get('takeover')!='passed' or not report['restored']:raise SystemExit(1)
