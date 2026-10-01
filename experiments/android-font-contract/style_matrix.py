"""Bounded native style cases and exact contracts from a sealed payload."""
import copy


def cases():
    result=[]
    for family,weights,samples in [('sans-serif',(100,300,400,450,520,700,900),('A','1','中')),
                                  ('sans-serif-condensed',(400,700),('A',)),('roboto',(400,700),('A',))]:
        for weight in weights:
            for italic in (False,True):
                for sample in samples:result.append(dict(family=family,weight=weight,italic=italic,sample=sample))
    result.extend(dict(family='sans-serif',weight=400,italic=italic,sample=sample)
                  for italic in (False,True) for sample in ('Ω','😀'))
    return result


def expected_cases(route,artifacts,manifest,baseline):
    if route.get('routeRevision')!=2:raise ValueError('matrix requires explicit style representation')
    keys=('family','weight','italic','sample')
    expected_keys={tuple(c[k] for k in keys) for c in cases()}
    actual_keys=[tuple(c[k] for k in keys) for c in baseline['cases']]
    if len(actual_keys)!=len(expected_keys) or set(actual_keys)!=expected_keys:raise ValueError('incomplete or duplicate matrix baseline')
    operations=route['documents']['/system/etc/font_fallback.xml']['operations']
    expansions={e['ordinal']:e for e in route['documents']['/system/etc/font_fallback.xml']['styleExpansions']}
    compiled={a['artifactId']:a for a in artifacts['artifacts']}
    result=[]
    for observed in baseline['cases']:
        case={k:copy.deepcopy(observed[k]) for k in ('family','weight','italic','sample')}
        fonts=observed['actualFonts']
        if len(fonts)!=1:raise ValueError('matrix baseline has split glyph source')
        old=fonts[0]
        matches=[op for op in operations if op['targetPath']==old['file'] and op['node']['index']==old['face']
                 and op.get('expandedWeight',op['node']['weight'])==case['weight']
                 and (case['sample']=='中' or op['node']['family']==case['family'])]
        preserved=case['sample'] in ('Ω','😀') or (case['italic'] and case['sample'] in ('A','1'))
        if preserved:
            records=[f for f in manifest['files'] if f['kind']=='xml-original' and f['sha256']==old['sha256']]
            if case['sample']!='😀' and len(records)!=1:raise ValueError('matrix preserved source is not uniquely sealed')
            path=records[0]['logicalPath'] if records else old['file']
            if case['sample'] in ('A','1'):
                if len(matches)!=1 or not expansions[matches[0]['node']['ordinal']]['preserveItalic']:
                    raise ValueError('matrix italic route has no explicit original contract')
            expected=dict(path=path,sha256=old['sha256'],face=old['face'],fontWeight=old['weight'],fontSlant=old['slant'],raster=observed['raster'])
            if case['sample'] in ('A','1'):
                # Explicit XML declarations replace the variable-family style
                # descriptor; only the actual glyph raster must match baseline.
                expected.update(fontWeight=case['weight'],fontSlant=1)
            case['coverage']='preserved-original-style-or-script'
        else:
            if len(matches)!=1:raise ValueError('matrix normal route is not unique')
            op=matches[0];artifact=compiled[op['artifact']['artifactId']]
            binding=artifact.get('staticXmlContract')
            if not binding:raise ValueError('matrix silently used legacy adapter')
            file=next(f for f in manifest['files'] if artifact['artifactId'] in f.get('artifactIds',[]))
            expected=dict(path=file['logicalPath'],sha256=file['sha256'],face=0,axes={},fontWeight=case['weight'],fontSlant=0)
            case['coverage']='selected-static-with-platform-synthetic-italic' if case['italic'] else 'selected-static-explicit-weight'
        case['expected']=expected;result.append(case)
    if len(result)!=len(cases()):raise ValueError('incomplete matrix baseline')
    return result
