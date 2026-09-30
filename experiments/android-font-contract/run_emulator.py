"""CI emulator probe: native font data, configuration access and real reboot.

Never roots the emulator, changes hidden API policy, or mounts system partitions.
"""
from pathlib import Path
import argparse,json,subprocess,time,atexit,sys
PACKAGE='io.github.xgl34222220.luoshu.fontcontract'
p=argparse.ArgumentParser();p.add_argument('--apk',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
stage='initializing'
started=time.monotonic()
def status(value, **extra):
 global stage
 stage=value
 (args.output/'progress.json').write_text(json.dumps({'stage':stage,'elapsedSeconds':round(time.monotonic()-started,3),**extra},indent=2)+'\n')
def adb(*values,timeout=120):
 begin=time.monotonic()
 try:
  r=subprocess.run(['adb',*values],capture_output=True,timeout=timeout)
 except subprocess.TimeoutExpired as error:
  status(stage,status='failed',error='adb-timeout',command=list(values),timeoutSeconds=timeout)
  raise
 with (args.output/'commands.jsonl').open('a') as stream:
  stream.write(json.dumps({'command':list(values),'durationSeconds':round(time.monotonic()-begin,3),'returncode':r.returncode})+'\n')
 if r.returncode:
  (args.output/('failure-'+stage+'.txt')).write_bytes(r.stdout+r.stderr)
  status(stage,status='failed',error='adb-nonzero',command=list(values),returncode=r.returncode)
  raise RuntimeError(r.stderr.decode(errors='replace'))
 return r.stdout
def diagnostics():
 # Bounded collection also runs before a failed test exits; no device mutation.
 for name,command in [('devices',['devices','-l']),('boot',['shell','getprop','sys.boot_completed']),('logcat',['logcat','-d','-t','400'])]:
  try:
   r=subprocess.run(['adb',*command],capture_output=True,timeout=10)
   (args.output/('diagnostic-'+name+'.txt')).write_bytes(r.stdout+r.stderr)
  except Exception as error:
   (args.output/('diagnostic-'+name+'.txt')).write_text(type(error).__name__+': '+str(error))
atexit.register(diagnostics)
status('installing-probe')
adb('wait-for-device');adb('install','-r','-t',str(args.apk))
reports=[]
platform_reports=[]
# Ordinary shell-owned temporary files; never touches /system or app-private data.
remote='/data/local/tmp/luoshu-font-contract'
adb('shell','mkdir','-p',remote)
adb('push',str(args.apk),remote+'/probe.apk')
assets=Path(__file__).parent/'app/src/main/assets'
adb('push',str(assets/'composite.ttf'),remote+'/composite.ttf')
ps_name=json.loads((assets/'fixture.json').read_text())['postScriptName']
for phase in ['before','after']:
 status('native-font-contract-'+phase)
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
 status('platform-xml-'+phase)
 platform=adb('shell','env','CLASSPATH='+remote+'/probe.apk','app_process',remote,
  PACKAGE+'.PlatformXmlProbe',remote+'/composite.ttf',remote+'/probe-fonts.xml',ps_name)
 (args.output/('platform-xml-'+phase+'.json')).write_bytes(platform)
 parsed=json.loads(platform);platform_reports.append(parsed)
 if parsed.get('status')!='passed' or parsed.get('rasterSha256')!=report.get('nativeCombinedHash'):
  raise RuntimeError('platform XML raster differs from independently verified app raster')
framework=all(r.get('status')=='passed' for r in platform_reports)
status('completed-native-probe')
summary={'nativeDataGate':'passed','frameworkXmlGate':'passed' if framework else 'blocked',
 'emulatorReboot':'passed','moduleGlobalMountAndBootGate':'not-tested','noHook':True,
 'appFrameworkApi':'available' if all(r.get('frameworkXmlConsumer',{}).get('status')=='passed' for r in reports) else 'unavailable',
 'frameworkContext':'existing adb shell via app_process',
 'note':'Temporary test XML consumed by platform; system configuration and security policy unchanged',
 'hardwareRomCoverage':'not-tested'}
(args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
if not framework:raise SystemExit('Framework XML API unavailable or validation failed; see reports, do not count this gate passed')
