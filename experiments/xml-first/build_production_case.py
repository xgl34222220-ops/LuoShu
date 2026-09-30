"""CI fixture driving the real production planner/compiler/deployment.

ROM bytes and XML are captured read-only from the disposable emulator. The host
models those exact captures as ROM mounts through the existing test-only seam;
this is not evidence of Android Python execution or root-manager deployment.
No captured SDK fonts or payload bytes are uploaded as experiment artifacts.
"""
from pathlib import Path
import copy,hashlib,json,os,sys,time
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'scripts')]
import font_source_profile
import universal_font_plan as planner
import minimal_xml_router as legacy
import fixed_static_xml_router as router
import universal_font_compiler as compiler
import universal_font_deployment as deployment
import universal_font_compiler_test as fixture


def required_stock_paths(xml_paths, baseline):
    """Capture complete direct family membership, including protected siblings."""
    selected={Path(baseline['actualDefaultFonts'][c][0]['file']).name for c in ['A','中']}
    required=set()
    for actual in xml_paths.values():
        tree=legacy._parse_xml(Path(actual));root=tree.getroot()
        for family in root.iter():
            if legacy._local(family.tag)!='family':continue
            fonts=[f for f in family if legacy._local(f.tag)=='font']
            if not any((f.text or '').strip() in selected for f in fonts):continue
            for font in fonts:
                name=(font.text or '').strip()
                if not legacy.SAFE_FILE_RE.fullmatch(name):raise RuntimeError('unsupported SDK family filename: '+name)
                required.add('/system/fonts/'+name)
    return sorted(required)


def build(work, xml_paths, stock_paths, baseline, source, generation):
    work=Path(work);work.mkdir(parents=True,exist_ok=True);started=time.monotonic()
    build_key=baseline['fingerprint'];slots={};roles={}
    # The rendered baseline identifies the exact default physical face. Other
    # captured XML indices in the same immutable collection remain distinct.
    selected={baseline['actualDefaultFonts'][sample][0]['file']:(role,baseline['actualDefaultFonts'][sample][0]['ttcIndex'])
              for role,sample in [('ui-sans','A'),('cjk','中')]}
    for logical in required_stock_paths(xml_paths,baseline):
        role,face=selected.get(logical,('special-fallback',None));stock=Path(stock_paths[logical])
        if face is None:
            face=next(node['index'] for xml,actual in xml_paths.items()
                for node in legacy._document_nodes(xml,legacy._parse_xml(Path(actual)))
                if node['declared']==Path(logical).name)
        slot=fixture.slot_from_stock(logical,stock,family='',source_xml=None,declared=Path(logical).name,face_index=face)
        refs=[];names=set()
        for xml_logical,actual in xml_paths.items():
            for node in legacy._document_nodes(xml_logical,legacy._parse_xml(Path(actual))):
                if node['declared'] != Path(logical).name:continue
                ref=copy.deepcopy(node);ref['resolvedPath']=logical;refs.append(ref)
                if node['family']:names.add(node['family'])
        if not refs:raise RuntimeError('captured default font has no exact XML references: '+logical)
        slot['xmlRefs']=refs;slot['families']=sorted(names);slots[logical]=slot;roles[logical]=fixture.role_map(role)
    topology={'schema':planner.TOPOLOGY_SCHEMA,'state':'ready','topologyRevision':3,'buildKey':build_key,
              'slots':slots,'summary':{'slotCount':len(slots),'dataFontFileCount':0,'dataFontConfigReferenceCount':0},
              'families':{},'xmlAliases':[],'unresolvedXmlRefs':[],'runtime':{}}
    role_map={'schema':planner.ROLES_SCHEMA,'state':'ready','roleRevision':3,'buildKey':build_key,'slots':roles}
    profile=font_source_profile.build([Path(source)])
    sha=hashlib.sha256(Path(source).read_bytes()).hexdigest()
    policy={'policy':'fixed-composite-selection-v1','requestId':'native-production-fixture','fontSha256':sha,
            'roles':{r:{'mode':'fixed','selectedAxes':{'wght':400}} for r in ['cjk','latin','digit']}}
    for item in profile['files']:
        for face in item['faces']:face['mixedSelection']=copy.deepcopy(policy)
    plan=planner.build_plan(topology,role_map,profile)
    base=legacy.build_route_plan(plan,{k:Path(v) for k,v in xml_paths.items()},None,False)
    mapping=work/'stock-map.json';mapping.write_text(json.dumps({k:str(v) for k,v in stock_paths.items()}))
    # Namespace translation is confined to this experiment. Production calls
    # always read the real current mount/config state and contain no bypass.
    with patch.object(router,'_dynamic_generation',return_value=generation),patch.dict(os.environ,{'LUOSHU_STOCK_FONT_MAP':str(mapping),'LUOSHU_UNIVERSAL_MIX_STRICT':'1'}):
        route=router.build_route_plan(plan,base)
        artifacts=compiler.compile_all(plan,route,{k:Path(v) for k,v in stock_paths.items()},work/'compiled',False)
        (work/'artifacts.json').write_text(json.dumps(artifacts,ensure_ascii=False,indent=2))
        if not artifacts['summary']['deploymentReady']:
            raise RuntimeError('production compile blocked: '+str([(a['targetPath'],a.get('reason')) for a in artifacts['artifacts'] if a['status']!='ready'][:4]))
        payload=work/'payload';manifest=deployment.build_deployment(plan,route,artifacts,payload)
        deployment.validate_deployment(manifest,plan,route,artifacts,payload)
    for name,value in [('plan',plan),('route',route),('deployment',manifest)]:
        (work/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2))
    by_id={a['artifactId']:a for a in artifacts['artifacts']};expected={}
    authoritative='/system/etc/font_fallback.xml' if '/system/etc/font_fallback.xml' in route['documents'] else '/system/etc/fonts.xml'
    operations=route['documents'][authoritative]['operations']
    for role,sample in [('Latin','A'),('Digit','1'),('Cjk','中')]:
        observed=baseline['actualDefaultFonts'][sample][0]
        candidates=[op for op in operations if op['targetPath']==observed['file']
                    and op['node']['index']==observed['ttcIndex'] and op['node']['weight']==400
                    and op['node']['style']=='normal' and (role=='Cjk' or op['node']['family']=='sans-serif')]
        if not candidates:raise RuntimeError('no explicit production default route for '+role)
        op=candidates[0];item=by_id[op['artifact']['artifactId']]
        file=next(f for f in manifest['files'] if item['artifactId'] in f.get('artifactIds',[f.get('artifactId')]))
        contract=item['contract'];binding=item.get('staticXmlContract')
        expected[role]={'path':file['logicalPath'],'face':0 if binding else contract['requiredFaceIndex'],
                        'axes':[] if binding else contract['requiredAxes'],'sha256':file['sha256']}
    report={'productionModulesUsed':True,'androidPythonExecuted':False,
            'originProofContext':'root-captured SDK bytes with test-only host namespace model',
            'seconds':round(time.monotonic()-started,3),'artifactCount':len(artifacts['artifacts']),
            'uniqueCompiledFiles':len(set(artifacts['artifactMap'].values())),
            'staticRouteCount':route['summary']['fixedStaticOperationCount'],
            'deferredRepresentationCount':route['summary']['representationDeferralCount'],
            'payloadBytes':sum(f['bytes'] for f in manifest['files']),
            'expectedDefaultConsumers':expected,'deploymentId':manifest['deploymentId']}
    return payload,manifest,expected,report
