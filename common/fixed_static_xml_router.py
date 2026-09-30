#!/usr/bin/env python3
"""Explicit fixed-static XML representation; legacy router stays text-only.

This stage only plans/renders sealed XML. It does not mount, deploy or infer a
font geometry. Compiled static bindings and retained originals are mandatory.
"""
import copy
import hashlib
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import minimal_xml_router as legacy
import universal_font_plan

SCHEMA = 'fixed-static-xml-route-plan-v1'
REVISION = 1
REPRESENTATION = 'fixed-static-xml-v1'
ERROR = legacy.RouterError
SHA = re.compile(r'^[a-f0-9]{64}$')
PS = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$')


def _artifact(original):
    result = copy.deepcopy(original)
    result.update(representation=REPRESENTATION,
                  originalStockFaceIndex=original['requiredFaceIndex'],
                  originalStockAxes=copy.deepcopy(original['requiredAxes']),
                  originalStockPostScriptName=original['requiredPostScriptName'],
                  requiredFaceIndex=0, requiredAxes=[], requiredPostScriptName='',
                  container='sfnt', preserveXmlAttributes=False, preserveAxisChildren=False)
    identity = legacy._canonical_hash(result)
    result['artifactId'] = 'ufc:' + identity[:32]
    result['suggestedFileName'] = 'LuoShu-Fixed-' + identity[:32] + '.ttf'
    return result


def _eligible(operation):
    node = operation['node']; target = operation['routeTarget']
    attrs = node.get('familyAttributes') or {}
    implicit_axes = set(str((node.get('fontAttributes') or {}).get('supportedAxes') or '').replace(' ', '').split(','))
    return (universal_font_plan.is_fixed_composite_selection(target.get("source") or {})
            and node.get('style') == 'normal'
            and not implicit_axes.intersection({'ital','slnt'})
            and not attrs.get('variant')
            and str(operation.get('role')) in {'ui-sans', 'latin', 'digit', 'cjk'}
            and not str(operation.get('targetPath')).startswith('/data/'))


def _root_for_document(source_xml):
    path = Path(source_xml)
    if source_xml not in {'/system/etc/fonts.xml', '/system/etc/font_fallback.xml'}:
        raise ERROR('fixed XML document has unsupported font directory: ' + source_xml)
    return '/' + path.parts[1] + '/fonts'


def _id(plan):
    docs = copy.deepcopy(plan['documents'])
    for doc in docs.values():doc.pop('sourcePath', None)
    return 'sha256:' + legacy._canonical_hash({'schema':SCHEMA,'revision':REVISION,
        'legacyRouteId':plan['legacyRoutePlan']['routeId'],'documents':docs,
        'retainedOriginals':plan['retainedOriginals'],'summary':plan['summary'],
        'dynamicFontGeneration':plan['dynamicFontGeneration']})


def _bindings(font_plan, source_xml, records):
    by_ordinal = {}
    for path,target in font_plan['targets'].items():
        for ref in target.get('xmlRefs') or []:
            if ref.get('sourceXml') != source_xml:continue
            node,_ = legacy._find_unique_node(legacy._ref_locator(ref), records)
            if node is None:continue
            resolved = universal_font_plan.route_target(target,node)
            ordinal = node['ordinal']
            if ordinal in by_ordinal and by_ordinal[ordinal].get('path') != path:
                raise ERROR('ambiguous original fallback target')
            by_ordinal[ordinal] = resolved
    return by_ordinal


def _dynamic_generation():
    path=Path('/data/fonts/config/config.xml')
    if path.is_symlink() or (path.exists() and not path.is_file()):raise ERROR('dynamic font config is not a regular file')
    result={'path':str(path),'exists':path.is_file(),'sha256':''}
    if result['exists']:
        raw=path.read_bytes()
        try: root=ET.fromstring(raw)
        except ET.ParseError as error:raise ERROR('dynamic font config cannot be proved inactive') from error
        if root.tag not in {'fontConfig','familyset','fonts-modification'}:raise ERROR('unsupported dynamic font config')
        if any(legacy._local(n.tag) in {'font','updatedFontDir'} for n in root.iter()):
            raise ERROR('fixed-static original fallback requires an inactive font-update layer')
        result['sha256']=hashlib.sha256(raw).hexdigest()
    return result


def build_route_plan(font_plan, base):
    legacy.validate_route_plan(base,font_plan)
    constraints=font_plan.get('constraints') or {}
    if constraints.get('dataFontFileCount') or constraints.get('dataFontConfigReferenceCount') or constraints.get('dynamicDiscoveryComplete') is False:
        raise ERROR('fixed-static original fallback has unresolved or active dynamic font overrides')
    plan=copy.deepcopy(base)
    plan.update(schema=SCHEMA,routeRevision=REVISION,legacyRoutePlan=copy.deepcopy(base),retainedOriginals={},dynamicFontGeneration=_dynamic_generation())
    static_count=0;clone_count=0
    for source_xml,document in plan['documents'].items():
        selected=[op for op in document['operations'] if _eligible(op)]
        document['fallbackCopies']=[];document['retainedReferences']=[]
        document['representationDeferrals']=[]
        for op in document['operations']:
            if universal_font_plan.is_fixed_composite_selection(op.get('routeTarget',{}).get('source') or {}) and not _eligible(op):
                axes=str((op['node'].get('fontAttributes') or {}).get('supportedAxes') or '')
                reason='implicit-variable-style' if any(tag in axes.split(',') for tag in ('ital','slnt')) else 'unsupported-role-style-or-variant'
                document['representationDeferrals'].append({'ordinal':op['node']['ordinal'],'targetPath':op['targetPath'],'reason':reason})
        if not selected:continue
        if source_xml not in {'/system/etc/fonts.xml','/system/etc/font_fallback.xml'}:
            document['representationDeferrals'].extend({'ordinal':op['node']['ordinal'],'targetPath':op['targetPath'],'reason':'unverified-document-adapter'} for op in selected)
            continue
        document['assetRoot']=_root_for_document(source_xml)
        path=Path(document['sourcePath'])
        if 'sha256:'+legacy._file_sha256(path)!=document['sourceDigest']:raise ERROR('fixed XML snapshot changed')
        tree=legacy._parse_xml(path);root=tree.getroot();fonts=legacy._font_elements(tree)
        if legacy._local(root.tag)!='familyset':
            document['representationDeferrals'].extend({'ordinal':op['node']['ordinal'],'targetPath':op['targetPath'],'reason':'unsupported-customization-structure'} for op in selected)
            continue
        parents={child:parent for parent in root.iter() for child in parent}
        records=legacy._document_nodes(source_xml,tree);targets=_bindings(font_plan,source_xml,records)
        families=[]
        for operation in selected:
            ordinal=operation['node']['ordinal'];family=parents[fonts[ordinal]]
            parent=parents.get(family)
            if parent is not root and family.attrib.get('name'):
                raise ERROR('named child inside family-list requires a separate adapter')
            if parent is not root and (legacy._local(parent.tag)!='family-list' or parents.get(parent) is not root):
                raise ERROR('unsupported nested fixed-static family container')
            if family not in families:families.append(family)
            operation['artifact']=_artifact(operation['artifact'])
            operation['operation']='replace-fixed-static-reference'
            operation['mutation']={'representation':REPRESENTATION,'preserveDeclaredWeight':True,
                'preserveDeclaredStyle':True,'setFaceIndex':0,'clearAxisChildren':True,
                'clearSupportedAxes':True,'postScriptNameFromCompiledBinding':True}
            operation['assetRoot']=document['assetRoot'];static_count+=1
        changed_ordinals={op['node']['ordinal'] for op in document['operations']}
        for family in families:
            ordinals=[i for i,f in enumerate(fonts) if parents[f] is family]
            family_name=records[ordinals[0]].get('family') or ''
            original_refs=[]
            for ordinal in ordinals:
                target=targets.get(ordinal)
                if not target:raise ERROR('original fallback has no sealed target: '+source_xml+'#'+str(ordinal))
                identity=(target.get('targetContract') or {}).get('stockIdentity') or {}
                if not SHA.fullmatch(str(identity.get('sha256',''))) or (identity.get('provenance') or {}).get('verified') is not True:
                    raise ERROR('original fallback identity was not captured from verified stock')
                suffix=Path(target['path']).suffix.lower()
                if suffix not in legacy.FONT_EXTENSIONS:raise ERROR('unsupported retained original container')
                original_id='stock:'+legacy._canonical_hash({'target':target,'index':records[ordinal]['index'],'assetRoot':document['assetRoot']})
                asset_name='LuoShu-Original-'+identity['sha256']+suffix
                record={'originalId':original_id,'targetPath':target['path'],'target':target,
                    'faceIndex':records[ordinal]['index'],'sha256':identity['sha256'],
                    'fileName':asset_name,'assetRoot':document['assetRoot']}
                plan['retainedOriginals'][original_id]=record
                ref={'ordinal':ordinal,'originalId':original_id,'nodeFingerprint':records[ordinal]['fingerprint']}
                original_refs.append(ref)
                if ordinal not in changed_ordinals:document['retainedReferences'].append(ref)
            document['fallbackCopies'].append({'anchorOrdinal':ordinals[0],
                'insideFamilyList':parents[family] is not root,'familyName':family_name,'effectiveFamilyAttributes':copy.deepcopy(records[ordinals[0]]['familyAttributes']),'references':original_refs})
            clone_count+=1
    plan['summary'].update(fixedStaticOperationCount=static_count,retainedOriginalCount=len(plan['retainedOriginals']),fallbackFamilyCount=clone_count,representationDeferralCount=sum(len(d['representationDeferrals']) for d in plan['documents'].values()))
    if not static_count:raise ERROR('no eligible explicitly fixed upright XML route')
    plan['routeId']=_id(plan)
    return plan


def validate_route_plan(plan,font_plan=None):
    if plan.get('schema')!=SCHEMA or plan.get('routeRevision')!=REVISION or plan.get('state')!='planned' or plan.get('mutatesSystem') is not False:
        raise ERROR('invalid fixed-static XML representation')
    base=plan.get('legacyRoutePlan')
    if not isinstance(base,dict):raise ERROR('missing original legacy route proof')
    legacy.validate_route_plan(base,font_plan)
    if plan.get('routeId')!=_id(plan):raise ERROR('fixed-static route identity changed')
    if font_plan is not None:
        expected=build_route_plan(font_plan,base)
        if expected!=plan:raise ERROR('fixed-static route differs from sealed source plan')
    for document in plan['documents'].values():
        for op in document['operations']:
            if op.get('operation')=='replace-fixed-static-reference':
                if op['artifact'].get('representation')!=REPRESENTATION or op['node'].get('style')!='normal':raise ERROR('invalid fixed-static operation')
                if op['artifact'].get('requiredFaceIndex')!=0 or op['artifact'].get('requiredAxes')!=[]:raise ERROR('static output cannot inherit source collection/axes')


def _compiled_binding(operation,artifact_map,bindings):
    identity=operation['artifact']['artifactId'];binding=bindings.get(identity)
    if not isinstance(binding,dict) or binding.get('faceIndex')!=0 or binding.get('axes')!=[]:
        raise ERROR('missing verified static XML binding: '+identity)
    name=binding.get('fileName');ps=binding.get('postScriptName')
    if not isinstance(name,str) or not legacy.SAFE_FILE_RE.fullmatch(name) or not name.endswith('.ttf') or artifact_map.get(identity)!=name:
        raise ERROR('static XML filename differs from compiled binding')
    if not isinstance(ps,str) or not PS.fullmatch(ps):raise ERROR('invalid static XML PostScript identity')
    if not str(binding.get('renderContractId','')).startswith('sha256:'):raise ERROR('missing measured render contract')
    return binding


def render_document(plan,source_xml,artifact_map,output,bindings):
    validate_route_plan(plan)
    doc=plan['documents'][source_xml];path=Path(doc['sourcePath'])
    if 'sha256:'+legacy._file_sha256(path)!=doc['sourceDigest']:raise ERROR('fixed XML snapshot changed')
    tree=legacy._parse_xml(path);root=tree.getroot();fonts=legacy._font_elements(tree)
    parents={child:parent for parent in root.iter() for child in parent}
    records=legacy._document_nodes(source_xml,tree)
    clones=[]
    for fallback in doc.get('fallbackCopies',[]):
        family=parents[fonts[fallback['anchorOrdinal']]];clone=copy.deepcopy(family)
        if not fallback['insideFamilyList']:
            clone.attrib.clear();clone.attrib.update(fallback['effectiveFamilyAttributes'])
        clone.attrib.pop('name',None)
        clone_fonts=[f for f in list(clone) if legacy._local(f.tag)=='font']
        if len(clone_fonts)!=len(fallback['references']):raise ERROR('fallback family changed')
        for font,ref in zip(clone_fonts,fallback['references']):
            original=plan['retainedOriginals'][ref['originalId']]
            font.text=original['fileName']
            if not fallback['insideFamilyList'] and fallback['familyName'] and fallback['familyName']!='sans-serif':
                if font.get('fallbackFor') not in (None,fallback['familyName']):raise ERROR('ambiguous named fallbackFor contract')
                font.set('fallbackFor',fallback['familyName'])
        clones.append((parents[family],family,clone))
    for operation in doc['operations']:
        ordinal=operation['node']['ordinal']
        if records[ordinal]['fingerprint']!=operation['nodeFingerprint']:raise ERROR('fixed XML node changed')
        font=fonts[ordinal];identity=operation['artifact']['artifactId']
        if operation.get('operation')=='replace-fixed-static-reference':
            binding=_compiled_binding(operation,artifact_map,bindings);font.text=binding['fileName'];font.set('index','0')
            for key in ('postScriptName','postscriptName','name','supportedAxes'):font.attrib.pop(key,None)
            font.set('postScriptName',binding['postScriptName'])
            for child in list(font):
                if legacy._local(child.tag)=='axis':font.remove(child)
        else:
            name=artifact_map.get(identity)
            if not name or not legacy.SAFE_FILE_RE.fullmatch(name):raise ERROR('missing legacy compiled font')
            font.text=name
    for ref in doc.get('retainedReferences',[]):
        if records[ref['ordinal']]['fingerprint']!=ref['nodeFingerprint']:raise ERROR('retained XML node changed')
        fonts[ref['ordinal']].text=plan['retainedOriginals'][ref['originalId']]['fileName']
    for parent,anchor,clone in reversed(clones):parent.insert(list(parent).index(anchor)+1,clone)
    legacy._atomic_tree(Path(output),tree)
    return {'sourceXml':source_xml,'output':str(output),'changedFonts':len(doc['operations']),
            'sourceDigest':doc['sourceDigest'],'representation':REPRESENTATION}


def render_all(plan,artifact_map,output_root,compiled_bindings):
    validate_route_plan(plan)
    if plan['summary'].get('routingComplete') is not True:raise ERROR('incomplete fixed-static route plan')
    rendered=[]
    for source_xml,doc in sorted(plan['documents'].items()):
        if not doc.get('operations'):continue
        output=Path(output_root)/source_xml.lstrip('/')
        rendered.append(render_document(plan,source_xml,artifact_map,output,compiled_bindings))
    return {'documents':rendered,'renderedDocuments':len(rendered),'changedFonts':sum(d['changedFonts'] for d in rendered)}


def main():
    import argparse,json
    parser=argparse.ArgumentParser()
    parser.add_argument('--font-plan',required=True,type=Path)
    parser.add_argument('--base-route',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--validate',type=Path)
    args=parser.parse_args()
    try:
        font_plan=legacy._load(args.font_plan)
        if args.validate:
            plan=legacy._load(args.validate);validate_route_plan(plan,font_plan)
        else:
            if not args.base_route or not args.output:raise ERROR('missing fixed-static route paths')
            plan=build_route_plan(font_plan,legacy._load(args.base_route));legacy._atomic_json(args.output,plan)
        print(json.dumps({'status':'ok','schema':SCHEMA,'routeId':plan['routeId'],**plan['summary']},separators=(',',':')))
        return 0
    except Exception as error:
        print(json.dumps({'status':'error','message':str(error)},ensure_ascii=False,separators=(',',':')))
        return 1

if __name__=='__main__':raise SystemExit(main())
