"""CI emulator probe: native font data, configuration access and real reboot.

Never roots the emulator, changes hidden API policy, or mounts system partitions.
"""
from pathlib import Path
import argparse,json,subprocess,time
PACKAGE='io.github.xgl34222220.luoshu.fontcontract'
p=argparse.ArgumentParser();p.add_argument('--apk',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
def adb(*values,timeout=120):
 r=subprocess.run(['adb',*values],capture_output=True,timeout=timeout)
 if r.returncode:raise RuntimeError(r.stderr.decode(errors='replace'))
 return r.stdout
adb('wait-for-device');adb('install','-r','-t',str(args.apk))
reports=[]
for phase in ['before','after']:
 if phase=='after':
  adb('reboot');adb('wait-for-device',timeout=240)
  until=time.monotonic()+240
  while time.monotonic()<until:
   if adb('shell','getprop','sys.boot_completed').strip()==b'1':break
   time.sleep(2)
  else:raise RuntimeError('reboot did not complete')
 log=adb('shell','am','instrument','-w','-e','phase',phase,PACKAGE+'/.Runner',timeout=180)
 (args.output/('instrument-'+phase+'.txt')).write_bytes(log)
 raw=adb('exec-out','run-as',PACKAGE,'cat','files/report-'+phase+'.json')
 (args.output/('report-'+phase+'.json')).write_bytes(raw);report=json.loads(raw);reports.append(report)
 for i in range(3):(args.output/('role-'+str(i)+'-'+phase+'.png')).write_bytes(adb('exec-out','run-as',PACKAGE,'cat','files/role-'+str(i)+'.png'))
 if report.get('status')!='passed-native-data-gate':raise RuntimeError(report)
framework=all(r.get('frameworkXmlConsumer',{}).get('status')=='passed' for r in reports)
summary={'nativeDataGate':'passed','frameworkXmlGate':'passed' if framework else 'blocked',
 'emulatorReboot':'passed','moduleGlobalMountAndBootGate':'not-tested','noHook':True,
 'note':'App-owned configuration test; no system font config/SELinux/root settings changed',
 'hardwareRomCoverage':'not-tested'}
(args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
if not framework:raise SystemExit('Framework XML API unavailable or validation failed; see reports, do not count this gate passed')
