"""Prepare, never activate, a real production payload inside disposable Android.

No fixture topology, mocked provenance, property override, mount hook, system
write or legacy fallback is used. Inputs are the three generated test fonts.
"""
import argparse,hashlib,json,os,platform,resource,subprocess,sys,time,traceback
from pathlib import Path
from types import SimpleNamespace

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as stream:
  for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()

def build_composite(module):
 import composite_font,font_source_profile
 from fontTools.ttLib import TTFont
 source=module/'source';fonts=source/'fonts';fonts.mkdir(parents=True)
 roles={}
 for role in ('cjk','latin','digit'):
  path=module/'inputs'/(role+'.ttf')
  with TTFont(path) as font:
   if 'fvar' in font or font['OS/2'].usWeightClass!=400:raise RuntimeError('fixture component is not static400')
  roles[role]={'mode':'fixed','selectedAxes':{'wght':400},'effectiveAxes':{},'axisProvenance':'static-component','componentWeightClass':400,'componentSha256':sha(path)}
 output=fonts/'composite.ttf'
 composite_font.build(SimpleNamespace(cjk=str(module/'inputs/cjk.ttf'),latin=str(module/'inputs/latin.ttf'),digit=str(module/'inputs/digit.ttf'),output=str(output),weight=400,cjk_face=0,latin_face=0,digit_face=0,progress=None))
 with TTFont(output) as font:
  for character,count in [('A',3),('1',5),('中',6)]:
   if len(font['glyf'][font.getBestCmap()[ord(character)]].getCoordinates(font['glyf'])[0])!=count:raise RuntimeError('composite role geometry differs: '+character)
 selection={'policy':'fixed-composite-selection-v1','requestId':'android-native-prepare','fontPath':'fonts/composite.ttf','fontSha256':sha(output),'roles':roles}
 report=source/'source.json';report.write_text(json.dumps({'schema':'universal-mixed-source-v1','mode':'fixed','requestId':selection['requestId'],'mixedSelection':selection}))
 return font_source_profile.build([output],mixed_selection=report)

def verify_prepared_roles(artifacts):
 from fontTools.ttLib import TTFont
 checks={}
 for role,character,points,allowed in [('cjk','中',6,{'cjk'}),('latin','A',3,{'latin','ui-sans'}),('digit','1',5,{'clock','numeric','latin','ui-sans'})]:
  for artifact in artifacts['artifacts']:
   if artifact.get('status')!='ready' or artifact.get('role') not in allowed:continue
   with TTFont(artifact['output'],fontNumber=int(artifact['contract'].get('requiredFaceIndex') or 0)) as font:
    name=(font.getBestCmap() or {}).get(ord(character))
    if not name or 'glyf' not in font:continue
    actual=len(font['glyf'][name].getCoordinates(font['glyf'])[0])
    if actual!=points:raise RuntimeError('prepared '+role+' donor outline identity changed')
    checks[role]={'targetPath':artifact['targetPath'],'character':character,'pointCount':actual};break
  if role not in checks:raise RuntimeError('prepared payload did not exercise requested '+role+' role')
 return checks


def main():
 parser=argparse.ArgumentParser();parser.add_argument('--module',type=Path,required=True);args=parser.parse_args()
 module=args.module.resolve();out=module/'results';out.mkdir(exist_ok=True)
 sys.path.insert(0,str(module/'common'))
 started=time.monotonic();report={'state':'running','androidPythonExecuted':False,'architecture':platform.machine(),'shippedArm64RuntimeExecuted':False,'systemFontMutation':False,'mountHookExecuted':False,'phases':[]}
 def write(name,data):(out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2))
 def progress(phase,state,seconds=None):
  report['stage']=phase;report['elapsedSeconds']=round(time.monotonic()-started,3)
  event={'phase':phase,'state':state,'elapsedSeconds':report['elapsedSeconds']}
  if seconds is not None:event['seconds']=round(seconds,3)
  report['phases'].append(event);write('native-prepare-summary.json',report);print(json.dumps(event),flush=True)
 def timed(name,call):
  progress(name,'running');begin=time.monotonic();value=call();progress(name,'passed',time.monotonic()-begin);return value
 def command(name,args,timeout):
  with (out/(name+'.log')).open('w') as log:
   r=subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
  if r.returncode:raise RuntimeError(name+' failed: '+(out/(name+'.log')).read_text(errors='replace')[-2500:])
 def prop(name):return subprocess.check_output(['getprop',name],text=True,timeout=5).strip()
 try:
  if str(module)!='/data/local/tmp/luoshu-native-prepare':raise RuntimeError('unexpected owned module path')
  if prop('ro.kernel.qemu')!='1' or prop('ro.build.version.sdk')!='36' or os.getuid()!=0 or prop('ro.product.cpu.abi')!='x86_64':raise RuntimeError('disposable API36 x86 root precondition failed')
  if subprocess.check_output(['getenforce'],text=True).strip()!='Enforcing':raise RuntimeError('SELinux must remain Enforcing')
  if not hasattr(sys,'getandroidapilevel'):raise RuntimeError('interpreter is not the Android Python build')
  report.update(androidPythonExecuted=True,pythonBuildApiLevel=sys.getandroidapilevel(),pythonVersion=sys.version,fingerprint=prop('ro.build.fingerprint'))
  config=module/'config';config.mkdir(exist_ok=True)
  os.environ.update(MODDIR=str(module),MODULE_DIR=str(module),CONFIG_DIR=str(config),LUOSHU_SELF_MOUNT_STATE_ROOT=str(module/'state/self'),LUOSHU_UNIVERSAL_MIX_STRICT='1',LUOSHU_MIX_REQUEST_ID='android-native-prepare',LUOSHU_SWITCH_PROGRESS_FILE=str(out/'compiler-progress.json'))
  profile=timed('compose-and-profile',lambda:build_composite(module));write('source-profile.json',profile)
  timed('stock-scan',lambda:command('stock-scan',[sys.executable,str(module/'common/stock_inventory_scan.py'),'--force','--overlay-module',str(module),'--output',str(config/'device_font_inventory.json')],240))
  timed('topology-and-roles',lambda:command('topology',['sh',str(module/'common/font_topology_snapshot.sh'),'refresh'],120))
  import font_topology_snapshot,font_role_shadow,universal_font_plan,minimal_xml_router,fixed_static_xml_router,universal_font_compiler,universal_font_deployment,universal_font_cutover_gate
  inventory=json.loads((config/'device_font_inventory.json').read_text());topology=json.loads((config/'device_font_topology.json').read_text());roles=json.loads((config/'device_font_roles.json').read_text())
  font_topology_snapshot.validate_inventory_current(inventory);font_role_shadow.validate_role_map(roles,report['fingerprint'])
  for name,data in [('inventory.json',inventory),('topology.json',topology),('roles.json',roles)]:write(name,data)
  report.update(inventorySlotCount=len(inventory['slots']),topologySlotCount=len(topology['slots']),xmlMemberCount=len(inventory.get('xmlMemberSnapshots',{})),specializedSnapshots=inventory.get('specializedSnapshots',{}))
  plan=timed('plan',lambda:universal_font_plan.build_plan(topology,roles,profile,fixed_xml_scopes=True));write('font-plan.json',plan);report['planSummary']=plan['summary']
  def route():
   base=minimal_xml_router.build_route_plan(plan,{},None,True)
   return fixed_static_xml_router.build_route_plan(plan,base,expand_styles=True,matching_weights=True)
  route=timed('route',route);write('route-plan.json',route);report['routeSummary']=route['summary']
  if not route['summary'].get('fixedMatchingOperationCount'):raise RuntimeError('SDK fixture did not exercise fixed-outline weight matching')
  artifacts=timed('compile',lambda:universal_font_compiler.compile_all(plan,route,{},module/'compiled',False));write('artifact-manifest.json',artifacts)
  report['artifactSummary']=artifacts['summary'];report['blocked']=[{'targetPath':a.get('targetPath'),'role':a.get('role'),'reason':a.get('reason')} for a in artifacts['artifacts'] if a.get('status')!='ready']
  if not artifacts['summary']['deploymentReady']:raise RuntimeError('native artifacts are blocked; no deployment or legacy fallback')
  report['preparedDonorRoles']=verify_prepared_roles(artifacts)
  payload=module/'prepared-payload';deployment=timed('deployment',lambda:universal_font_deployment.build_deployment(plan,route,artifacts,payload));write('deployment.json',deployment)
  universal_font_deployment.validate_deployment(deployment,plan,route,artifacts,payload)
  universal_font_deployment.validate_device_generation(deployment,payload)
  universal_font_deployment.validate_dynamic_generation(deployment)
  gate=timed('cutover-gate',lambda:universal_font_cutover_gate.evaluate(plan,route,artifacts,deployment,payload));write('gate.json',gate)
  if gate.get('eligible') is not True:raise RuntimeError('native cutover gate rejected: '+str(gate.get('reasons')))
  # The kernel-backed identities captured by the real scanner must still match.
  digests={}
  for member in inventory.get('xmlMemberSnapshots',{}).values():
   for record in member.values():
    identity=record.get('stockIdentity') or {};proof=identity.get('provenance') or {}
    if proof.get('verified') is not True:continue
    path=proof.get('resolvedPath')
    if not path:raise RuntimeError('verified original lacks resolved path')
    if path not in digests:digests[path]=sha(path)
    if digests[path]!=identity.get('sha256'):raise RuntimeError('original changed during native preparation')
  report.update(state='passed',verifiedOriginalFilesUnchanged=len(digests),deploymentId=deployment['deploymentId'],payloadDigest=deployment['payloadDigest'],gate=gate,sourceBytes=(module/'source/fonts/composite.ttf').stat().st_size)
 except Exception as error:
  report.update(state='failed',error=type(error).__name__+': '+str(error),trace=traceback.format_exc(limit=14))
 finally:
  report.update(elapsedSeconds=round(time.monotonic()-started,3),maxSelfRSSKiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,maxChildRSSKiB=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
  write('native-prepare-summary.json',report);print(json.dumps(report,ensure_ascii=False),flush=True)
 return 0 if report['state']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
