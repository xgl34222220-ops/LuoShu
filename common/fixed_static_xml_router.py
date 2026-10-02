#!/usr/bin/env python3
"""Explicit fixed-static XML representation; legacy router stays text-only.

This stage only plans/renders sealed XML. It does not mount, deploy or infer a
font geometry. Compiled static bindings and retained originals are mandatory.
"""
import copy
import hashlib
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import minimal_xml_router as legacy
import universal_font_plan
import fixed_outline_weight_match as fixed_match

SCHEMA = 'fixed-static-xml-route-plan-v1'
REVISION = 1
STYLE_REVISION = 2
MATCHING_REVISION = 4
DIRECT_PATH_REVISION = 5
DIRECT_PATH_SCHEMA = "fixed-xml-direct-path-coverage-v1"
STYLE_WEIGHTS = tuple(sorted(set(range(100, 1000, 100)) | {450, 520}))
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


def _eligible(operation, expand_styles=False):
    node = operation['node']; target = operation['routeTarget']
    attrs = node.get('familyAttributes') or {}
    implicit_axes = set(str((node.get('fontAttributes') or {}).get('supportedAxes') or '').replace(' ', '').split(','))
    return (universal_font_plan.is_fixed_composite_selection(target.get("source") or {})
            and node.get('style') == 'normal'
            and (implicit_axes in ({''},{'wght'}) or
                 (expand_styles and implicit_axes == {'wght','ital'}))
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
    semantic={'schema':SCHEMA,'revision':plan['routeRevision'],
        'legacyRouteId':plan['legacyRoutePlan']['routeId'],'documents':docs,
        'retainedOriginals':plan['retainedOriginals'],'summary':plan['summary'],
        'dynamicFontGeneration':plan['dynamicFontGeneration']}
    if plan.get('styleExpansion'):semantic['styleExpansion']=plan['styleExpansion']
    if 'directPathCoverage' in plan:
        semantic['directPathCoverage']=plan['directPathCoverage']
        semantic['directPathTargets']=plan.get('directPathTargets')
    return 'sha256:' + legacy._canonical_hash(semantic)


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


def _direct_path_record(target):
    """Conservative standalone text shell; never alias an XML-generated face.

    This contract covers the original file at face zero, not every Android
    consumer. Collections, style siblings, scoped scripts and ROM aliases need
    separate adapters; their XML coverage can still proceed independently.
    """
    path = str(target.get('path') or '')
    stock = target.get('targetContract') or {}
    identity = stock.get('stockIdentity') or {}
    source = target.get('source') or {}
    refs = target.get('xmlRefs') or []
    reason = ''
    if not path.startswith(('/system/fonts/', '/product/fonts/', '/vendor/fonts/', '/system_ext/fonts/', '/odm/fonts/')):
        reason = 'unsupported-direct-path-root'
    elif target.get('xmlScopedTarget') or target.get('xmlScopePolicy'):
        reason = 'protected-scoped-container'
    elif target.get('action') not in legacy.ROUTABLE_ACTIONS or target.get('status') == 'blocked':
        reason = 'target-not-independently-routable'
    elif target.get('role') not in {'ui-sans', 'latin', 'cjk'}:
        reason = 'specialized-direct-path-contract-required'
    elif not universal_font_plan.is_fixed_composite_selection(source):
        reason = 'fixed-selection-required'
    elif stock.get('format') != 'TTF' or Path(path).suffix.lower() != '.ttf' or stock.get('faceIndex') != 0:
        reason = 'standalone-glyf-face-zero-required'
    elif (identity.get('logicalPath') != path or identity.get('faceIndex') != 0
          or not SHA.fullmatch(str(identity.get('sha256') or ''))
          or (identity.get('provenance') or {}).get('verified') is not True):
        reason = 'sealed-original-identity-required'
    elif ((identity.get('provenance') or {}).get('aliasChain') != []
          or (identity.get('provenance') or {}).get('resolvedLogicalPath') not in (None, '', path)):
        reason = 'original-path-alias-needs-terminal-contract'
    elif (not refs or stock.get('italic') or source.get('italic')
          or any(ref.get('index', 0) != 0 or ref.get('style', 'normal') != 'normal'
                 or (ref.get('familyAttributes') or {}).get('variant') for ref in refs)):
        reason = 'mixed-face-style-or-variant-container'
    axes = {}
    if not reason:
        for axis in (stock.get('metrics') or {}).get('variationAxes') or []:
            tag = str(axis.get('tag') or '')
            try:
                lo, default, hi = (float(axis[key]) for key in ('minimum', 'default', 'maximum'))
            except (TypeError, ValueError, KeyError):
                reason = 'invalid-original-axis-domain'; break
            if (tag not in {'wght', 'wdth', 'opsz'} or tag in axes
                    or not all(math.isfinite(v) for v in (lo, default, hi)) or not lo <= default <= hi):
                reason = 'unsupported-original-axis-domain'; break
            axes[tag] = {'min': lo, 'default': default, 'max': hi}
        if bool(axes) != bool(stock.get('variable')):
            reason = reason or 'incomplete-original-axis-domain'
        for ref in refs:
            for axis in ref.get('axes') or []:
                tag = str(axis.get('tag') or '')
                try: value = float(axis.get('stylevalue'))
                except (TypeError, ValueError): value = math.nan
                if tag not in axes or not math.isfinite(value) or not axes[tag]['min'] <= value <= axes[tag]['max']:
                    reason = reason or 'unsupported-original-axis-coordinate'
    if reason:
        return {'state': 'unsupported', 'reason': reason}
    return {'state': 'planned', 'contract': {
        'policy': 'fixed-selected-stock-shell-direct-v1', 'targetPath': path,
        'stockSha256': identity['sha256'], 'faceIndex': 0, 'container': 'TTF',
        'axisRanges': axes, 'role': target['role'], 'sourceSha256': source['fileUid'],
        'sourceIntentSha256': legacy._canonical_hash(source['mixedSelection']),
        'targetContractSha256': legacy._canonical_hash(stock),
        'outlinePolicy': 'fixed-selected-source-with-original-unselected-glyphs',
        'consumerCoverage': 'not-proven',
    }}


def _add_direct_path_coverage(plan, font_plan):
    paths = sorted({op['targetPath'] for doc in plan['documents'].values()
                    for op in doc.get('operations', [])
                    if op.get('artifact', {}).get('representation') in fixed_match.REPRESENTATIONS})
    records = {path: _direct_path_record(font_plan['targets'][path]) for path in paths}
    plan['directPathCoverage'] = {'schema': DIRECT_PATH_SCHEMA, 'targets': records}
    plan['directPathTargets'] = [path for path, record in records.items() if record['state'] == 'planned']
    plan['summary'].update(directPathPlannedCount=len(plan['directPathTargets']),
                           directPathUnsupportedCount=len(paths)-len(plan['directPathTargets']),
                           directPathConsumersVerified=False)


def build_route_plan(font_plan, base, *, expand_styles=False, matching_weights=False, direct_paths=None):
    if direct_paths is None: direct_paths = matching_weights
    if direct_paths and not matching_weights: raise ERROR("direct paths require fixed matching routes")
    if matching_weights:expand_styles=True
    weights=(400,) if matching_weights else STYLE_WEIGHTS
    legacy.validate_route_plan(base,font_plan)
    constraints=font_plan.get('constraints') or {}
    if constraints.get('dataFontFileCount') or constraints.get('dataFontConfigReferenceCount') or constraints.get('dynamicDiscoveryComplete') is False:
        raise ERROR('fixed-static original fallback has unresolved or active dynamic font overrides')
    plan=copy.deepcopy(base)
    plan.update(schema=SCHEMA,routeRevision=REVISION,legacyRoutePlan=copy.deepcopy(base),retainedOriginals={},dynamicFontGeneration=_dynamic_generation())
    if expand_styles:
        plan.update(routeRevision=MATCHING_REVISION if matching_weights else STYLE_REVISION,
                    styleExpansion={'policy':'fixed-normal-original-italic-v1','weights':list(weights)})
        if matching_weights:
            plan['styleExpansion'].update(matchingAxis='constant-outline-selection',namedFallbackPolicy='local-original-chain-v1')
    static_count=0;clone_count=0
    for source_xml,document in plan['documents'].items():
        selected=[op for op in document['operations'] if _eligible(op,expand_styles)]
        document['fallbackCopies']=[];document['retainedReferences']=[]
        document['representationDeferrals']=[]
        for op in document['operations']:
            if universal_font_plan.is_fixed_composite_selection(op.get('routeTarget',{}).get('source') or {}) and not _eligible(op,expand_styles):
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
        if expand_styles:
            expanded=[];document['styleExpansions']=[]
            for operation in document['operations']:
                node=operation['node'];tags=set(str((node.get('fontAttributes') or {}).get('supportedAxes') or '').replace(' ','').split(','))
                if operation.get('operation')!='replace-fixed-static-reference' or tags not in ({'wght'},{'wght','ital'}):
                    expanded.append(operation);continue
                ordinal=node['ordinal'];family=parents[fonts[ordinal]];group=fonts[ordinal].get('fallbackFor')
                if any(f is not fonts[ordinal] and legacy._local(f.tag)=='font' and f.get('fallbackFor')==group for f in family):
                    raise ERROR('implicit style expansion has ambiguous same-group peers')
                originals=[r for f in document['fallbackCopies'] for r in f['references'] if r['ordinal']==ordinal]
                if len(originals)!=1:raise ERROR('implicit style expansion lacks one sealed original')
                document['styleExpansions'].append({'ordinal':ordinal,'weights':list(weights),
                    'preserveItalic':'ital' in tags,'originalId':originals[0]['originalId'],
                    'nodeFingerprint':operation['nodeFingerprint']})
                if matching_weights:document['styleExpansions'][-1]['matchingAxis']=True
                for weight in weights:
                    op=copy.deepcopy(operation);artifact=op['artifact']
                    axes=[copy.deepcopy(a) for a in artifact['originalStockAxes'] if a['tag'] not in tags]
                    for tag,value in [('wght',weight)]+([('ital',0)] if 'ital' in tags else []):
                        axes.append({'tag':tag,'stylevalue':str(value),'attributes':{'tag':tag,'stylevalue':str(value)}})
                    artifact.update(requiredWeight=weight,originalStockAxes=axes,
                                    styleExpansion={'policy':'fixed-normal-original-italic-v1','declaredWeight':weight,'implicitAxes':sorted(tags)})
                    if matching_weights:
                        artifact.update(representation=fixed_match.MATCHING,
                                        weightMatching={'policy':'fixed-normal-original-italic-v1','referenceWeight':400})
                    artifact.pop('artifactId',None);artifact.pop('suggestedFileName',None)
                    key=legacy._canonical_hash(artifact);artifact['artifactId']='ufc:'+key[:32];artifact['suggestedFileName']='LuoShu-Fixed-'+key[:32]+'.ttf'
                    op['expandedWeight']=weight;expanded.append(op)
                static_count+=len(weights)-1
            document['operations']=expanded
    plan['summary'].update(fixedStaticOperationCount=static_count,retainedOriginalCount=len(plan['retainedOriginals']),fallbackFamilyCount=clone_count,representationDeferralCount=sum(len(d['representationDeferrals']) for d in plan['documents'].values()))
    if expand_styles:
        plan['summary'].update(styleWeightDomain='constant-normal-continuous-selection' if matching_weights else 'discrete-declared-weights',declaredStyleWeights=list(weights),
            preservedOriginalStyleCount=sum(len(e['weights']) for d in plan['documents'].values()
                                           for e in d.get('styleExpansions',[]) if e['preserveItalic']))
    if matching_weights:
        matching_count=sum(op['artifact'].get('representation')==fixed_match.MATCHING for d in plan['documents'].values() for op in d['operations'])
        plan['summary'].update(fixedXmlOperationCount=static_count,fixedMatchingOperationCount=matching_count,
                               fixedStaticOperationCount=static_count-matching_count,
                               normalSourceVariationPreserved=False)
    if not static_count:raise ERROR('no eligible explicitly fixed upright XML route')
    if direct_paths:
        plan['routeRevision'] = DIRECT_PATH_REVISION
        _add_direct_path_coverage(plan, font_plan)
    plan['routeId']=_id(plan)
    return plan


def validate_route_plan(plan,font_plan=None):
    if plan.get('schema')!=SCHEMA or plan.get('routeRevision') not in {REVISION,STYLE_REVISION,MATCHING_REVISION,DIRECT_PATH_REVISION} or plan.get('state')!='planned' or plan.get('mutatesSystem') is not False:
        raise ERROR('invalid fixed-static XML representation')
    matching=plan.get('routeRevision') in {MATCHING_REVISION,DIRECT_PATH_REVISION}
    expansion=plan.get('routeRevision') in {STYLE_REVISION,MATCHING_REVISION,DIRECT_PATH_REVISION}
    expected_policy={'policy':'fixed-normal-original-italic-v1','weights':[400] if matching else list(STYLE_WEIGHTS)}
    if matching:expected_policy.update(matchingAxis='constant-outline-selection',namedFallbackPolicy='local-original-chain-v1')
    if expansion and plan.get('styleExpansion')!=expected_policy:
        raise ERROR('invalid fixed-static style expansion policy')
    if not expansion and plan.get('styleExpansion'):raise ERROR('unexpected style expansion on old representation')
    base=plan.get('legacyRoutePlan')
    if not isinstance(base,dict):raise ERROR('missing original legacy route proof')
    legacy.validate_route_plan(base,font_plan)
    if plan.get('routeId')!=_id(plan):raise ERROR('fixed-static route identity changed')
    if font_plan is not None:
        expected=build_route_plan(font_plan,base,expand_styles=expansion,matching_weights=matching,
                                  direct_paths=plan.get('routeRevision')==DIRECT_PATH_REVISION)
        if expected!=plan:raise ERROR('fixed-static route differs from sealed source plan')
    coverage = plan.get('directPathCoverage')
    if plan.get('routeRevision') == DIRECT_PATH_REVISION:
        if not isinstance(coverage, dict) or coverage.get('schema') != DIRECT_PATH_SCHEMA or not isinstance(coverage.get('targets'), dict):
            raise ERROR('missing direct-path coverage contract')
        if any(record.get('state') not in {'planned', 'unsupported'} for record in coverage['targets'].values()):
            raise ERROR('invalid direct-path coverage state')
        expected_paths = sorted(path for path, record in coverage['targets'].items() if record['state'] == 'planned')
        if plan.get('directPathTargets') != expected_paths:
            raise ERROR('direct-path target membership changed')
    elif coverage is not None or plan.get('directPathTargets') is not None:
        raise ERROR('unexpected direct-path contract on legacy route')
    for document in plan['documents'].values():
        for op in document['operations']:
            if op.get('operation')=='replace-fixed-static-reference':
                if op['artifact'].get('representation') not in fixed_match.REPRESENTATIONS or op['node'].get('style')!='normal':raise ERROR('invalid fixed-static operation')
                if op['artifact'].get('representation')==fixed_match.MATCHING and not matching:raise ERROR('matching artifact in wrong route revision')
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
    matching=operation['artifact'].get('representation')==fixed_match.MATCHING
    if matching and binding.get('weightMatching')!=fixed_match.policy(binding.get('fontWeight')):
        raise ERROR('missing constant-outline matching contract')
    if not matching and binding.get('weightMatching'):raise ERROR('unexpected matching axis on static route')
    return binding


def render_document(plan,source_xml,artifact_map,output,bindings):
    validate_route_plan(plan)
    doc=plan['documents'][source_xml];path=Path(doc['sourcePath'])
    if 'sha256:'+legacy._file_sha256(path)!=doc['sourceDigest']:raise ERROR('fixed XML snapshot changed')
    tree=legacy._parse_xml(path);root=tree.getroot();fonts=legacy._font_elements(tree)
    parents={child:parent for parent in root.iter() for child in parent}
    records=legacy._document_nodes(source_xml,tree)
    clones=[];named_clones=[]
    matching=plan.get('routeRevision') in {MATCHING_REVISION,DIRECT_PATH_REVISION}
    for fallback in doc.get('fallbackCopies',[]):
        family=parents[fonts[fallback['anchorOrdinal']]];clone=copy.deepcopy(family)
        if not fallback['insideFamilyList']:
            clone.attrib.clear();clone.attrib.update(fallback['effectiveFamilyAttributes'])
        clone.attrib.pop('name',None)
        clone_fonts=[f for f in list(clone) if legacy._local(f.tag)=='font']
        if len(clone_fonts)!=len(fallback['references']):raise ERROR('fallback family changed')
        local_named=matching and not fallback['insideFamilyList'] and bool(fallback['familyName'])
        if local_named and any(font.get('fallbackFor') is not None for font in clone_fonts):
            raise ERROR('named local fallback has an ambiguous explicit fallbackFor')
        for font,ref in zip(clone_fonts,fallback['references']):
            original=plan['retainedOriginals'][ref['originalId']]
            font.text=original['fileName']
            if not local_named and not fallback['insideFamilyList'] and fallback['familyName'] and fallback['familyName']!='sans-serif':
                if font.get('fallbackFor') not in (None,fallback['familyName']):raise ERROR('ambiguous named fallbackFor contract')
                font.set('fallbackFor',fallback['familyName'])
        if local_named:
            named_clones.append((parents[family],family,copy.deepcopy(clone),fallback['familyName']))
            # The original default family remains the global fallback for other
            # names. Each changed named primary gets its own original first.
            if fallback['familyName']!='sans-serif':continue
        clones.append((parents[family],family,clone))
    expanded_fonts={}
    for operation in doc['operations']:
        ordinal=operation['node']['ordinal']
        if records[ordinal]['fingerprint']!=operation['nodeFingerprint']:raise ERROR('fixed XML node changed')
        font=copy.deepcopy(fonts[ordinal]) if 'expandedWeight' in operation else fonts[ordinal]
        identity=operation['artifact']['artifactId']
        if operation.get('operation')=='replace-fixed-static-reference':
            binding=_compiled_binding(operation,artifact_map,bindings);font.text=binding['fileName'];font.set('index','0')
            for key in ('postScriptName','postscriptName','name','supportedAxes'):font.attrib.pop(key,None)
            font.set('postScriptName',binding['postScriptName'])
            for child in list(font):
                if legacy._local(child.tag)=='axis':font.remove(child)
            if 'expandedWeight' in operation:
                font.set('weight',str(operation['expandedWeight']));font.set('style','normal')
                if operation['artifact'].get('representation')==fixed_match.MATCHING:font.set('supportedAxes','wght')
                expanded_fonts.setdefault(ordinal,[]).append(font)
        else:
            name=artifact_map.get(identity)
            if not name or not legacy.SAFE_FILE_RE.fullmatch(name):raise ERROR('missing legacy compiled font')
            font.text=name
    for expansion in doc.get('styleExpansions',[]):
        ordinal=expansion['ordinal'];original=fonts[ordinal];parent=parents[original]
        children=expanded_fonts.pop(ordinal,[])
        if len(children)!=len(expansion['weights']):raise ERROR('incomplete normal style expansion')
        if expansion['preserveItalic']:
            for weight in expansion['weights']:
                font=copy.deepcopy(original);font.attrib.pop('supportedAxes',None)
                font.set('weight',str(weight));font.set('style','italic')
                if expansion.get('matchingAxis'):font.set('supportedAxes','wght')
                font.text=plan['retainedOriginals'][expansion['originalId']]['fileName']
                for child in list(font):
                    if legacy._local(child.tag)=='axis' and child.get('tag') in {'wght','ital'}:font.remove(child)
                if not expansion.get('matchingAxis'):ET.SubElement(font,'axis',tag='wght',stylevalue=str(weight))
                ET.SubElement(font,'axis',tag='ital',stylevalue='1')
                children.append(font)
        position=list(parent).index(original);parent.remove(original)
        for offset,font in enumerate(children):parent.insert(position+offset,font)
    if expanded_fonts:raise ERROR('unbound style expansion')
    for ref in doc.get('retainedReferences',[]):
        if records[ref['ordinal']]['fingerprint']!=ref['nodeFingerprint']:raise ERROR('retained XML node changed')
        fonts[ref['ordinal']].text=plan['retainedOriginals'][ref['originalId']]['fileName']
    anchors={}
    for parent,family,clone,name in named_clones:
        position=list(parent).index(family)
        tag=family.tag[:-len('family')]+'family-list'
        wrapper=ET.Element(tag,{'name':name})
        family.attrib.pop('name',None)
        parent.remove(family);wrapper.append(family);wrapper.append(clone);parent.insert(position,wrapper)
        anchors[family]=wrapper
    for parent,anchor,clone in reversed(clones):parent.insert(list(parent).index(anchors.get(anchor,anchor))+1,clone)
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
    parser.add_argument('--expand-styles',action='store_true')
    parser.add_argument('--matching-weights',action='store_true')
    parser.add_argument('--allow-physical-only',action='store_true')
    args=parser.parse_args()
    try:
        font_plan=legacy._load(args.font_plan)
        if args.validate:
            plan=legacy._load(args.validate)
            if args.allow_physical_only and plan.get('schema')==legacy.SCHEMA and not plan.get('documents'):
                legacy.validate_route_plan(plan,font_plan)
            else:validate_route_plan(plan,font_plan)
        else:
            if not args.base_route or not args.output:raise ERROR('missing fixed-static route paths')
            base=legacy._load(args.base_route)
            if args.allow_physical_only and not base.get('documents'):
                legacy.validate_route_plan(base,font_plan)
                plan=base  # No XML is consumed; keep the existing physical contract.
            else:
                plan=build_route_plan(font_plan,base,expand_styles=args.expand_styles,matching_weights=args.matching_weights)
            legacy._atomic_json(args.output,plan)
        print(json.dumps({'status':'ok','schema':plan['schema'],'routeId':plan['routeId'],**plan['summary']},separators=(',',':')))
        return 0
    except Exception as error:
        print(json.dumps({'status':'error','message':str(error)},ensure_ascii=False,separators=(',',':')))
        return 1

if __name__=='__main__':raise SystemExit(main())
