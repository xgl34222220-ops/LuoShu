"""Conservative glyph semantics: retain supported paths and reject ambiguity."""
from __future__ import annotations
from copy import deepcopy
import math
from fontTools.ttLib.tables.ttProgram import Program
from fontTools.varLib.builder import buildVarIdxMap

class SemanticError(ValueError):
    pass

def strip_glyph_hints(glyph):
    # Foreign programs cannot use the OEM fpgm/prep/cvt environment.
    glyph.program = Program()
    glyph.program.fromBytecode(b'')

def isolate_stock_dependencies(font, imported, selected_codepoints, *, preserve_uvs=True):
    """Append original clones for nonselected cmap/composite dependencies.

    Existing glyph IDs stay stable; clones retain OEM hints and variation maps.
    """
    imported = set(imported); aliases = set()
    for table in font['cmap'].tables:
        if table.isUnicode() and hasattr(table, 'cmap'):
            aliases.update(name for cp, name in table.cmap.items()
                           if cp not in selected_codepoints and name in imported)
        if preserve_uvs and getattr(table, 'format', None) == 14:
            aliases.update(name for entries in table.uvsDict.values()
                           for _cp, name in entries if name in imported)
    cmap_aliases = set(aliases)
    if cmap_aliases:
        def references(obj, wanted, seen):
            if isinstance(obj, str): return obj in wanted
            if obj is None or isinstance(obj, (int,float,bytes,bool)): return False
            if id(obj) in seen: return False
            seen.add(id(obj))
            if isinstance(obj, dict): return any(references(k,wanted,seen) or references(v,wanted,seen) for k,v in obj.items())
            if isinstance(obj, (list,tuple)): return any(references(v,wanted,seen) for v in obj)
            return references(getattr(obj,'__dict__',{}), wanted, seen)
        for tag in ('GSUB','GPOS','GDEF','kern','MATH','morx','mort','kerx'):
            if tag in font and references(font[tag], cmap_aliases, set()):
                raise SemanticError('shared cmap/UVS alias has layout dependencies requiring explicit isolation: ' + tag + ':' + repr(sorted(cmap_aliases)))
    if 'glyf' not in font:
        if aliases:
            raise SemanticError('stock-shell CFF shared cmap/UVS aliases need explicit isolation')
        # CFF1 seac can also reference a replaced component. Its StandardEncoding
        # references cannot be redirected to append-only arbitrary glyph clones.
        # Reject only that affected dependency; ordinary CFF paths stay supported.
        from fontTools.pens.recordingPen import RecordingPen
        glyphs = font.getGlyphSet()
        for name in font.getGlyphOrder():
            if name in imported: continue
            pen = RecordingPen(); glyphs[name].draw(pen)
            if any(op == 'addComponent' and args[0] in imported for op,args in pen.value):
                raise SemanticError('nonselected CFF seac glyph depends on an imported component: ' + name)
        return {'clonedGlyphs': 0}
    glyf = font['glyf']; original_order = list(font.getGlyphOrder())
    for name in original_order:
        if name not in imported and glyf.glyphs[name].isComposite():
            aliases.update(c.glyphName for c in glyf[name].components if c.glyphName in imported)
    pending = list(aliases)
    while pending:
        name = pending.pop()
        if glyf.glyphs[name].isComposite():
            for c in glyf[name].components:
                if c.glyphName in imported and c.glyphName not in aliases:
                    aliases.add(c.glyphName); pending.append(c.glyphName)
    if not aliases: return {'clonedGlyphs': 0}
    if len(original_order) + len(aliases) > 65535:
        raise SemanticError('stock-shell dependency isolation exceeds glyph ID limit')
    names = set(original_order); clones = {}
    for old in sorted(aliases):
        stem = old + '.luoshuOriginal'; new = stem; count = 0
        while new in names: count += 1; new = stem + str(count)
        names.add(new); clones[old] = new
    # Materialize implicit indices before appending glyph IDs.
    for tag, fields in (('HVAR', ('AdvWidthMap', 'LsbMap', 'RsbMap')),
                        ('VVAR', ('AdvHeightMap', 'TsbMap', 'BsbMap', 'VOrgMap'))):
        if tag not in font: continue
        table = font[tag].table
        if getattr(table, fields[0], None) is None:
            setattr(table, fields[0], buildVarIdxMap(range(len(original_order)), original_order))
        for field in fields:
            mapping = getattr(table, field, None)
            if mapping is not None:
                for old, new in clones.items():
                    if old not in mapping.mapping:
                        raise SemanticError('incomplete OEM metric variation mapping: ' + tag + ':' + old)
                    mapping.mapping[new] = mapping.mapping[old]
    # Decompile glyph-count-sensitive tables against the original glyph order.
    variation_table = font['gvar'] if 'gvar' in font else None
    for tag in ('hmtx','vmtx','VORG'):
        if tag in font: font[tag]
    for old, new in clones.items():
        glyf[new] = deepcopy(glyf[old])
        for tag in ('hmtx', 'vmtx'):
            if tag in font: font[tag].metrics[new] = font[tag].metrics[old]
        if 'gvar' in font: font['gvar'].variations[new] = deepcopy(font['gvar'].variations.get(old, []))
        if 'VORG' in font and old in font['VORG'].VOriginRecords:
            font['VORG'].VOriginRecords[new] = font['VORG'].VOriginRecords[old]
    font.setGlyphOrder(original_order + list(clones.values()))
    for name in original_order + list(clones.values()):
        if name not in imported and glyf.glyphs[name].isComposite():
            for c in glyf[name].components: c.glyphName = clones.get(c.glyphName, c.glyphName)
    for table in font['cmap'].tables:
        if table.isUnicode() and hasattr(table, 'cmap'):
            for cp, name in list(table.cmap.items()):
                if cp not in selected_codepoints and name in clones: table.cmap[cp] = clones[name]
        if preserve_uvs and getattr(table, 'format', None) == 14:
            table.uvsDict = {selector: [(cp, clones.get(name, name)) for cp, name in entries]
                             for selector, entries in table.uvsDict.items()}
    return {'clonedGlyphs': len(clones), 'method': 'append-only-original-dependency-clones'}

def conservative_variable_ink_bounds(font):
    """Bound all glyf ink using signed gvar intervals after IUP expansion.

    Every tuple scalar is in [0,1]. Bounds are conservative, including mutually
    exclusive tuples. Static component transforms propagate interval boxes.
    Point-matched composites and VARC require a different proof and are rejected.
    """
    if 'VARC' in font or 'glyf' not in font:
        raise SemanticError('variable ink bounds require glyf without VARC')
    from fontTools.varLib.iup import iup_delta
    glyf = font['glyf']; gvar = font.get('gvar'); cache = {}; active = set()
    axis_tags = {str(axis.axisTag) for axis in font['fvar'].axes} if 'fvar' in font else set()
    def bounds(name):
        if name in cache: return cache[name]
        if name in active: raise SemanticError('cyclic composite glyph dependency')
        active.add(name); glyph = glyf[name]
        coords, controls = glyf._getCoordinatesAndControls(name, font['hmtx'].metrics,
                                                           font['vmtx'].metrics if 'vmtx' in font else None)
        size = len(coords) - 4
        lows = [[float(x), float(y)] for x, y in coords[:size]]; highs = [list(v) for v in lows]
        for variation in (gvar.variations.get(name, []) if gvar else []):
            for tag, support in variation.axes.items():
                if (tag not in axis_tags or len(support) != 3 or
                    any(not math.isfinite(float(v)) or abs(v) > 1 for v in support) or
                    not support[0] <= support[1] <= support[2]):
                    raise SemanticError('invalid gvar support interval')
            delta = variation.coordinates
            if None in delta:
                ends = controls[1] if controls[0] >= 1 else list(range(len(controls[1])))
                delta = iup_delta(delta, coords, ends)
            if len(delta) != len(coords): raise SemanticError('gvar coordinate count mismatch')
            for i, point in enumerate(delta[:size]):
                for axis in (0, 1):
                    value = float(point[axis])
                    if not math.isfinite(value): raise SemanticError('nonfinite gvar delta')
                    lows[i][axis] += min(0, value); highs[i][axis] += max(0, value)
        if glyph.isComposite():
            boxes = []
            for i, component in enumerate(glyph.components):
                if not hasattr(component, 'x') or not hasattr(component, 'y'):
                    raise SemanticError('variable ink bounds do not support point-matched composites')
                child = bounds(component.glyphName)
                if child is None: continue
                _name, (a,b,c,d,_x,_y) = component.getComponentInfo()
                corners = [(a*x+c*y, b*x+d*y) for x in (child[0], child[2]) for y in (child[1], child[3])]
                offsets = [(x,y) for x in (lows[i][0], highs[i][0]) for y in (lows[i][1], highs[i][1])]
                # Include both offset interpretations conservatively.
                offsets += [(a*x+c*y,b*x+d*y) for x,y in list(offsets)]
                boxes.append((min(x for x,y in corners)+min(x for x,y in offsets)-1,
                              min(y for x,y in corners)+min(y for x,y in offsets)-1,
                              max(x for x,y in corners)+max(x for x,y in offsets)+1,
                              max(y for x,y in corners)+max(y for x,y in offsets)+1))
            result = (min(b[0] for b in boxes), min(b[1] for b in boxes),
                      max(b[2] for b in boxes), max(b[3] for b in boxes)) if boxes else None
        elif size:
            result = (min(p[0] for p in lows), min(p[1] for p in lows),
                      max(p[0] for p in highs), max(p[1] for p in highs))
        else: result = None
        active.remove(name); cache[name] = result; return result
    os2 = font['OS/2']; top = min(font['hhea'].ascent, os2.sTypoAscender, os2.usWinAscent)
    bottom = max(font['hhea'].descent, os2.sTypoDescender, -os2.usWinDescent); low = high = 0
    for name in font.getGlyphOrder():
        box = bounds(name)
        if box is None: continue
        low = min(low, box[1]); high = max(high, box[3])
        if box[1] < bottom or box[3] > top:
            raise SemanticError('variable glyph exceeds conservative line budget: ' + name)
    return {'status': 'ready', 'method': 'all-glyph-signed-gvar-intervals', 'glyphCount': len(cache),
            'inkYMin': low, 'inkYMax': high, 'lineYMin': bottom, 'lineYMax': top,
            'scope': 'glyf ink clipping; not a proof of all shaping or rasterization behavior'}


def protected_math_glyphs(font):
    """Explicit math constructions keep their original glyph geometry/layout."""
    if 'MATH' not in font: return set()
    names = set(font.getGlyphOrder()); seen = set(); used = set()
    def collect(obj):
        if isinstance(obj,str):
            if obj in names: used.add(obj)
            return
        if obj is None or isinstance(obj,(int,float,bytes,bool)) or id(obj) in seen: return
        seen.add(id(obj))
        if isinstance(obj,dict):
            for k,v in obj.items(): collect(k); collect(v)
        elif isinstance(obj,(list,tuple)):
            for v in obj: collect(v)
        else: collect(getattr(obj,'__dict__',{}))
    collect(font['MATH'])
    return used


def mark_glyph_names(font):
    import unicodedata
    result = {name for cp,name in (font.getBestCmap() or {}).items()
              if unicodedata.category(chr(cp)).startswith('M')}
    if 'GDEF' in font:
        classes = getattr(font['GDEF'].table,'GlyphClassDef',None)
        if classes: result.update(name for name,kind in classes.classDefs.items() if kind == 3)
    return result


def protected_shared_marks(font, selected):
    """Preserve mark shapes used with bases outside the selected glyph subset.

    Selected Latin anchors may move, but a Greek base + shared accent must keep
    both its original glyphs and attachment coordinates, even without ccmp.
    """
    selected = set(selected); marks = mark_glyph_names(font); protected = set(); edges = []; mark_groups = []
    if 'GPOS' in font and font['GPOS'].table.LookupList:
        def positioning(kind, table):
            if kind == 9: return positioning(table.ExtensionLookupType,table.ExtSubTable)
            if kind in (4,5):
                bases = table.BaseCoverage.glyphs if kind == 4 else table.LigatureCoverage.glyphs
                if any(name not in selected for name in bases): protected.update(table.MarkCoverage.glyphs)
            elif kind == 6:
                mark_groups.append((set(table.Mark2Coverage.glyphs), set(table.Mark1Coverage.glyphs)))
        for lookup in font['GPOS'].table.LookupList.Lookup:
            for table in lookup.SubTable: positioning(lookup.LookupType,table)
    if 'GSUB' in font and font['GSUB'].table.LookupList:
        def substitution(kind, table):
            if kind == 7: return substitution(table.ExtensionLookupType,table.ExtSubTable)
            if kind == 1: edges.extend(table.mapping.items())
            elif kind in (2,3):
                mapping = table.mapping if kind == 2 else table.alternates
                edges.extend((a,b) for a,outputs in mapping.items() for b in outputs)
            elif kind == 4:
                for first, ligatures in table.ligatures.items():
                    for ligature in ligatures:
                        inputs = (first,*ligature.Component)
                        if any(name not in selected and name not in marks for name in inputs):
                            protected.update(name for name in inputs if name in marks)
            elif kind == 8: edges.extend(zip(table.Coverage.glyphs,table.Substitute))
        for lookup in font['GSUB'].table.LookupList.Lookup:
            for table in lookup.SubTable: substitution(lookup.LookupType,table)
    while True:
        next_set = protected | {b for a,b in edges if a in protected and b in marks}
        for bases, attached in mark_groups:
            if bases.intersection(protected): next_set.update(attached.intersection(marks))
        if next_set == protected: return protected.intersection(marks)
        protected = next_set


def complete_layout_probe_map(font, initial, signature):
    """Propagate a consistent transform through GSUB and explicit UVS outputs."""
    result = dict(initial); candidates = {name:{probe} for name,probe in initial.items()}; edges = []
    bounds_cache = {}; group_cache = {}; glyph_set = font.getGlyphSet()
    mark_names = mark_glyph_names(font)
    def glyph_bounds(name):
        if name not in bounds_cache:
            from fontTools.pens.boundsPen import BoundsPen
            pen = BoundsPen(glyph_set)
            glyph_set[name].draw(pen); bounds_cache[name] = pen.bounds
        return bounds_cache[name]
    def choose(name, options):
        options = sorted(options)
        if len({signature(probe) for probe in options}) == 1: return options[0]
        import statistics
        target = glyph_bounds(name)
        if target is None: raise SemanticError('GSUB output has ambiguous role transforms: empty glyph')
        scores = []
        canonical = {'latinCap':'HIXE','latinX':'xace','latinDescender':'gpqy','digits':'0123'}
        cmap = font.getBestCmap() or {}
        for probe in options:
            if probe not in group_cache:
                names = [cmap[ord(c)] for c in canonical.get(probe,'') if ord(c) in cmap and initial.get(cmap[ord(c)])==probe]
                if not names: names = sorted(n for n,p in initial.items() if p==probe)[:32]
                boxes = [glyph_bounds(n) for n in names]; boxes = [b for b in boxes if b is not None]
                group_cache[probe] = ((statistics.median(b[1] for b in boxes),statistics.median(b[3] for b in boxes)) if boxes else None)
            ref = group_cache[probe]
            if ref is not None: scores.append((abs(target[1]-ref[0])+abs(target[3]-ref[1]),probe))
        scores.sort()
        if not scores or (len(scores)>1 and abs(scores[1][0]-scores[0][0]) <= font['head'].unitsPerEm*.005):
            raise SemanticError('GSUB output has ambiguous role transforms: ' + name)
        return scores[0][1]

    if 'GSUB' in font and font['GSUB'].table.LookupList:
        def read(kind, table):
            if kind == 7:
                return read(table.ExtensionLookupType, table.ExtSubTable)
            if kind == 1:
                edges.extend(((a,), (b,)) for a,b in table.mapping.items())
            elif kind in (2,3):
                mapping = table.mapping if kind == 2 else table.alternates
                edges.extend(((a,), tuple(bs)) for a,bs in mapping.items())
            elif kind == 4:
                for first, ligatures in table.ligatures.items():
                    edges.extend(((first,*lig.Component),(lig.LigGlyph,)) for lig in ligatures)
            elif kind == 8:
                edges.extend(((a,), (b,)) for a,b in zip(table.Coverage.glyphs, table.Substitute))
            elif kind not in (5,6):
                raise SemanticError('unsupported GSUB transform lookup: ' + str(kind))
            # Contextual lookups contain no new output glyphs themselves. Their
            # referenced substitution lookups are included in this global closure.
        for lookup in font['GSUB'].table.LookupList.Lookup:
            for table in lookup.SubTable: read(lookup.LookupType, table)
    cmap = font.getBestCmap() or {}
    for table in font['cmap'].tables:
        if getattr(table, 'format', None) == 14:
            edges.extend(((cmap[cp],), (name,)) for entries in table.uvsDict.values()
                         for cp,name in entries if name is not None and cp in cmap)
    for _round in range(len(font.getGlyphOrder()) + 1):
        changed = False
        for inputs, outputs in edges:
            # Encoded outputs retain their own Unicode/script geometry contract
            # (e.g. the encoded FAX symbol is not an uppercase Latin ligature).
            outputs = tuple(name for name in outputs if name not in initial)
            if not outputs: continue
            if not any(name in result for name in inputs): continue
            effective_inputs = [name for name in inputs if name in result or
                                glyph_bounds(name) is not None or font['hmtx'].metrics.get(name,(0,0))[0] != 0]
            # A combining mark does not determine the script/geometry of a
            # composed output. Follow its base; mark-only substitutions retain
            # their own mark geometry. This avoids treating Greek+accent as Latin.
            bases = [name for name in effective_inputs if name not in mark_names]
            if bases: effective_inputs = bases
            assigned = [result[name] for name in effective_inputs if name in result]
            if not assigned: continue
            if len(assigned) != len(effective_inputs):
                raise SemanticError('GSUB output mixes transformed and unclassified input glyphs: ' + repr((inputs, outputs)))
            for name in outputs:
                options = candidates.setdefault(name,set())
                previous = set(options); options.update(assigned)
                probe = choose(name,options)
                if result.get(name) != probe or options != previous:
                    result[name] = probe; changed = True
        if not changed: return result
    raise SemanticError('GSUB transform closure did not converge')


def transform_layout(font, transforms, *, materialize_points=False):
    """Keep supported GPOS/GDEF coordinates consistent with actual glyph transforms.

    Transform anchors in each glyph's coordinate system. Placement/advance
    vectors are scaled, never translated. Ambiguous shared records fail closed.
    """
    identity = (1.0, 1.0, 0.0, 0.0)
    def tx(name): return transforms.get(name, identity)
    if not materialize_points and not any(v != identity for v in transforms.values()): return {'status': 'identity'}
    if any(tx(name) != identity for name in protected_math_glyphs(font)):
        raise SemanticError('transformed MATH construction glyphs require dedicated layout support')
    for tag in ('morx', 'mort', 'kerx'):
        if tag in font and not materialize_points: raise SemanticError('nonidentity source transforms do not support ' + tag)
    if 'BASE' in font and not materialize_points:
        raise SemanticError('nonidentity source transforms require explicit BASE baseline policy')
    visited = {}; changed = 0
    def remember(obj, signature):
        old = visited.get(id(obj))
        if old is not None:
            if old != signature: raise SemanticError('shared layout record has conflicting transforms')
            return False
        visited[id(obj)] = signature; return True
    def anchor(obj, name):
        nonlocal changed
        if obj is None: return
        sx,sy,dx,dy = tx(name)
        signature = ('anchor',sx,sy,dx,dy)
        if not remember(obj, signature): return
        if materialize_points and name in transforms and obj.Format == 2:
            if 'glyf' not in font: raise SemanticError('point anchor requires glyf outlines')
            coordinates = font['glyf'][name].getCoordinates(font['glyf'])[0]
            index = int(obj.AnchorPoint)
            if index < 0 or index >= len(coordinates): raise SemanticError('GPOS anchor point index out of bounds')
            obj.XCoordinate, obj.YCoordinate = map(round, coordinates[index])
            obj.Format = 1; del obj.AnchorPoint; changed += 1
        if (sx,sy,dx,dy) == identity: return
        if obj.Format == 2:
            raise SemanticError('transformed contour-point GPOS anchors need materialization')
        if (getattr(obj,'XDeviceTable',None) and sx != 1) or (getattr(obj,'YDeviceTable',None) and sy != 1):
            raise SemanticError('transformed size-dependent anchor devices are unsupported')
        obj.XCoordinate = round(obj.XCoordinate*sx+dx)
        obj.YCoordinate = round(obj.YCoordinate*sy+dy); changed += 1
    def vector_scale(obj, name):
        sx,sy,_dx,_dy = tx(name)
        if obj is None: return (1.0,1.0)
        if not any(getattr(obj,f,None) for f in ('XPlacement','XAdvance','XPlaDevice','XAdvDevice')): sx = 1.0
        if not any(getattr(obj,f,None) for f in ('YPlacement','YAdvance','YPlaDevice','YAdvDevice')): sy = 1.0
        return sx,sy
    def value(obj, name):
        nonlocal changed
        if obj is None: return
        sx,sy = vector_scale(obj,name)
        # Translation changes glyph origin/anchor coordinates, not relative vectors.
        if not remember(obj, ('value',sx,sy)): return
        for field, scale in (('XPlacement',sx),('XAdvance',sx),('YPlacement',sy),('YAdvance',sy)):
            device_field = {'XPlacement':'XPlaDevice','XAdvance':'XAdvDevice','YPlacement':'YPlaDevice','YAdvance':'YAdvDevice'}[field]
            if scale != 1 and getattr(obj, device_field, None):
                raise SemanticError('transformed size-dependent positioning devices are unsupported')
            if hasattr(obj,field): setattr(obj, field, round(getattr(obj,field)*scale))
        changed += 1
    def compatible(names, record=None):
        # Pair positioning contains relative vectors; only scale factors matter.
        names = list(names)
        values = {vector_scale(record,name) for name in names}
        if len(values) > 1: raise SemanticError('class positioning has nonuniform glyph scales')
        return names[0] if names else ''
    def process(kind, table):
        if kind == 9: return process(table.ExtensionLookupType, table.ExtSubTable)
        coverage = getattr(getattr(table,'Coverage',None),'glyphs',[])
        if kind == 1:
            if table.Format == 1: value(table.Value, compatible(coverage,table.Value))
            else:
                for name,item in zip(coverage, table.Value): value(item,name)
        elif kind == 2:
            if table.Format == 1:
                for name,pairset in zip(coverage, table.PairSet):
                    for record in pairset.PairValueRecord:
                        value(record.Value1,name); value(record.Value2,record.SecondGlyph)
            elif table.Format == 2:
                class1 = table.ClassDef1.classDefs; class2 = table.ClassDef2.classDefs
                for i,row in enumerate(table.Class1Record):
                    for j,record in enumerate(row.Class2Record):
                        first = compatible((n for n in coverage if class1.get(n,0)==i), record.Value1)
                        second = compatible((n for n in font.getGlyphOrder() if class2.get(n,0)==j), record.Value2)
                        value(record.Value1,first); value(record.Value2,second)
            else: raise SemanticError('unsupported pair positioning format')
        elif kind == 3:
            for name,record in zip(coverage,table.EntryExitRecord):
                anchor(record.EntryAnchor,name); anchor(record.ExitAnchor,name)
        elif kind in (4,5,6):
            mark_cov = table.MarkCoverage if kind in (4,5) else table.Mark1Coverage
            mark_array = table.MarkArray if kind in (4,5) else table.Mark1Array
            for name,record in zip(mark_cov.glyphs,mark_array.MarkRecord): anchor(record.MarkAnchor,name)
            if kind == 4:
                for name,record in zip(table.BaseCoverage.glyphs,table.BaseArray.BaseRecord):
                    for item in record.BaseAnchor: anchor(item,name)
            elif kind == 5:
                for name,record in zip(table.LigatureCoverage.glyphs,table.LigatureArray.LigatureAttach):
                    if record:
                        for component in record.ComponentRecord:
                            for item in component.LigatureAnchor: anchor(item,name)
            else:
                for name,record in zip(table.Mark2Coverage.glyphs,table.Mark2Array.Mark2Record):
                    for item in record.Mark2Anchor: anchor(item,name)
        elif kind not in (7,8): raise SemanticError('unsupported GPOS transform lookup: '+str(kind))
    if 'GPOS' in font and font['GPOS'].table.LookupList:
        for lookup in font['GPOS'].table.LookupList.Lookup:
            for table in lookup.SubTable: process(lookup.LookupType,table)
    if 'GDEF' in font:
        table = font['GDEF'].table
        attaches = getattr(table,'AttachList',None)
        if attaches and any(tx(name) != identity for name in attaches.Coverage.glyphs):
            raise SemanticError('transformed GDEF attachment point indices need explicit reindexing')
        carets = getattr(table,'LigCaretList',None)
        if carets:
            for name,record in zip(carets.Coverage.glyphs,carets.LigGlyph):
                sx,sy,dx,dy = tx(name)
                for caret in record.CaretValue:
                    if materialize_points and name in transforms and caret.Format == 2:
                        if 'glyf' not in font: raise SemanticError('point caret requires glyf outlines')
                        coordinates = font['glyf'][name].getCoordinates(font['glyf'])[0]
                        index = int(caret.CaretValuePoint)
                        if index < 0 or index >= len(coordinates): raise SemanticError('GDEF caret point index out of bounds')
                        caret.Coordinate = round(coordinates[index][0]); caret.Format = 1; del caret.CaretValuePoint
                    if caret.Format == 2 and tx(name) != identity:

                        raise SemanticError('transformed GDEF contour-point carets need explicit reindexing')
                    if caret.Format in (1,3):
                        if getattr(caret,'DeviceTable',None) and sx != 1:
                            raise SemanticError('transformed GDEF caret devices are unsupported')
                        caret.Coordinate = round(caret.Coordinate*sx+dx)
    if 'kern' in font:
        for table in font['kern'].kernTables:
            if not hasattr(table,'kernTable'):
                raise SemanticError('unsupported legacy kern transform format')
            vertical = not bool(getattr(table,'coverage',1) & 1)
            for pair, amount in list(table.kernTable.items()):
                index = 1 if vertical else 0
                scales = {tx(name)[index] for name in pair}
                if len(scales) != 1: raise SemanticError('legacy kern pair has conflicting transforms')
                table.kernTable[pair] = round(amount*scales.pop())
    return {'status':'ready','method':'GSUB-closure-and-glyph-local-GPOS','derivedTransformPolicy':'encoded-script-or-nearest-original-geometry','positionRecords':changed,
            'preservedMathGlyphs':len(protected_math_glyphs(font))}
