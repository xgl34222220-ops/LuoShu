#!/usr/bin/env python3
"""Build an index-preserving CJK collection inside a finite mix task.

Each stock face remains the base: cmap/UVS, glyph IDs, layout tables, names,
style and line metrics stay at their original indexes. Supported donor outlines
replace existing encoded slots. Specialized faces and uncovered glyphs stay stock.
No system XML, live font, user source or mounting implementation is modified.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen, RecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.reverseContourPen import ReverseContourPen
from fontTools.pens.transformPen import TransformPen
from fontTools.misc.psCharStrings import T2CharString
from fontTools.ttLib import TTCollection, TTFont
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.varLib.builder import buildVarData, buildVarIdxMap

from composite_collection_contract import collection_faces
from composite_font import LATIN_CODEPOINTS, DIGIT_CODEPOINTS, _pick_face, _progress
import font_inventory as stock_inventory

SCHEMA = 'composite-collection-build-v1'
PROTECTED = ('cmap', 'GSUB', 'GPOS', 'GDEF', 'name', 'hhea', 'OS/2', 'vhea', 'vmtx', 'VORG',
             'fvar', 'avar', 'STAT', 'MVAR', 'BASE', 'cvar', 'VVAR')
REQUIRED_CHARACTERS = '中ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
CJK_RANGES = ((0x2E80, 0x31EF), (0x3400, 0x9FFF), (0xF900, 0xFAFF),
              (0xFF00, 0xFFEF), (0x20000, 0x323AF))


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def identity(path):
    value = Path(path).stat()
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def role(cp):
    if cp in DIGIT_CODEPOINTS:
        return 'digit'
    if cp in LATIN_CODEPOINTS:
        return 'latin'
    return 'cjk' if any(lo <= cp <= hi for lo, hi in CJK_RANGES) else None


def protected(font):
    recalc = font.recalcBBoxes
    font.recalcBBoxes = False
    try:
        return _protected(font)
    finally:
        font.recalcBBoxes = recalc


def _protected(font):
    # Canonical compiled bytes survive a FontTools round trip. Keeping the
    # original glyph order makes the retained layout/UVS indexes meaningful.
    # getTableData returns original bytes for lazy tables, compiled bytes for
    # loaded ones. Load every protected table before hashing either snapshot.
    for tag in PROTECTED:
        if tag in font:
            font[tag]
    tables = {}
    for tag in PROTECTED:
        if tag not in font:
            continue
        if tag == 'vmtx' and 'glyf' in font:
            # TrueType vertical origins are yMax + top side bearing. A new
            # outline needs a different bearing to keep that same origin.
            glyf = font['glyf']
            tables[tag] = canonical({name: [advance, getattr(glyf[name], 'yMax', 0) + bearing]
                                     for name, (advance, bearing) in font['vmtx'].metrics.items()})
            continue
        data = font.getTableData(tag)
        # Metric serialization may change its run-length compression count.
        # Every other header field still binds the original line metrics.
        if tag in ('hhea', 'vhea'):
            data = data[:-2]
        tables[tag] = hashlib.sha256(data).hexdigest()
    return {'tables': tables, 'glyphOrder': canonical(font.getGlyphOrder()),
            'frame': [font['head'].unitsPerEm, font['head'].xMin, font['head'].yMin,
                      font['head'].xMax, font['head'].yMax]}


def specialized(font, allow=()):
    # allow: label words a caller deliberately replaces (e.g. 'serif' for a
    # stock serif CJK collection). Mono/italic faces always stay stock.
    names = font['name'] if 'name' in font else None
    label = ' '.join(filter(None, (names.getDebugName(i) for i in (1, 2, 16, 17)))) if names else ''
    words = tuple(word for word in ('mono', 'serif', 'emoji', 'symbol', 'icon') if word not in allow)
    return (bool(font['post'].isFixedPitch) if 'post' in font else False) or any(
        word in label.lower() for word in words) or bool(
        font['head'].macStyle & 2 or ('OS/2' in font and font['OS/2'].fsSelection & 1))


def draw_record(glyphs, name):
    pen = DecomposingRecordingPen(glyphs)
    glyphs[name].draw(pen)
    return pen


def guard_retained_components(font, mapping):
    if 'glyf' in font:
        glyf = font['glyf']
        for name in font.getGlyphOrder():
            if name in mapping:
                continue  # Its complete outline will be replaced.
            raw = getattr(glyf.glyphs[name], 'data', None)
            if raw is not None and (len(raw) < 2 or int.from_bytes(raw[:2], 'big', signed=True) >= 0):
                continue
            glyph = glyf[name]
            if glyph.isComposite() and any(component.glyphName in mapping for component in glyph.components):
                raise ValueError('原厂保留组合字形依赖被替换槽，当前不能保持其完整形状与边界')
    elif 'CFF ' in font and not hasattr(font['CFF '].cff.topDictIndex[0], 'ROS'):
        # Non-CID CFF can have seac components addressed by standard names.
        glyphs = font.getGlyphSet()
        for name in font.getGlyphOrder():
            if name in mapping:
                continue
            pen = RecordingPen()
            glyphs[name].draw(pen)
            if any(operation == 'addComponent' and arguments[0] in mapping
                   for operation, arguments in pen.value):
                raise ValueError('原厂保留 CFF 组合字形依赖被替换槽，当前不能保持其完整形状与边界')


def freeze_horizontal_variations(font, mapping):
    """Detach only replaced slots from stock width/side-bearing variation data.

    Keep the existing store and each retained glyph's exact indices. In
    particular, an implicit advance mapping must be expanded before changing
    selected slots; editing a shared delta row would corrupt uncovered glyphs.
    """
    if 'HVAR' not in font:
        return
    table = font['HVAR'].table
    store = table.VarStore
    if len(store.VarData) >= 65535:
        raise ValueError('水平变化存储没有可用索引')
    zero = len(store.VarData) << 16
    store.VarData.append(buildVarData([], [[]], optimize=False))
    store.VarDataCount = len(store.VarData)
    order = font.getGlyphOrder()
    for field in ('AdvWidthMap', 'LsbMap', 'RsbMap'):
        old = getattr(table, field, None)
        if old is None and field != 'AdvWidthMap':
            continue
        indices = [zero if name in mapping else (old.mapping[name] if old else index)
                   for index, name in enumerate(order)]
        setattr(table, field, buildVarIdxMap(indices, order))


def retained_vertical_deltas(font, name):
    if 'gvar' not in font or 'vmtx' not in font:
        return []
    if 'VVAR' in font and getattr(font['VVAR'].table, 'TsbMap', None) is not None:
        raise ValueError('可变 TrueType 垂直侧距映射需要独立重编译，不能沿用旧轮廓数据')
    coordinates, controls = font['glyf']._getCoordinatesAndControls(
        name, font['hmtx'].metrics, font['vmtx'].metrics)
    from copy import deepcopy
    values = []
    for original in font['gvar'].variations.get(name, []):
        variation = deepcopy(original)
        variation.calcInferredDeltas(coordinates, controls.endPts)
        top, bottom = variation.coordinates[-2:]
        if any(top) or any(bottom):
            values.append((variation.axes, top, bottom))
    return values


# Format/control/space code points (soft hyphen U+00AD, ZWJ, NBSP...) often
# share a stock glyph with a visible character while the donor gives them a
# distinct (often blank) outline. They never decide a shared slot.
IGNORABLE_CATEGORIES = ('Cc', 'Cf', 'Zs', 'Zl', 'Zp')
OUTLINE_TAGS = ('glyf', 'loca', 'CFF ', 'CFF2', 'hmtx', 'vmtx', 'maxp', 'gvar', 'HVAR')
DROPPED_TAGS = ('DSIG', 'LTSH', 'hdmx', 'VDMX')


def cff_charstring(recording, width, cff2, scale, reverse, private, subrs):
    """Draw one donor outline as a Type 2 charstring.

    Quadratic TrueType segments are elevated to cubics exactly (the plain
    pen's own conversion) instead of being re-fitted with Qu2Cu: the shape is
    identical to the donor, contours without on-curve points need no special
    case, and the pure-Python curve fitting that dominated the on-device build
    time (FontTools ships without its compiled extensions there) disappears.
    The charstrings get somewhat longer; the collection stays index-preserving.
    """
    pen = T2CharStringPen(width, None, CFF2=cff2)
    output = ReverseContourPen(pen) if reverse else pen
    if scale != 1:
        output = TransformPen(output, (scale, 0, 0, scale, 0, 0))
    recording.replay(output)
    return pen.getCharString(private=private, globalSubrs=subrs)


# Converted CFF outline bodies (control box, Type 2 bytes without width) keyed
# by (donor sha256, glyph, scale, donor is TrueType). Sans and Serif CJK
# collections compiled one after another in one stage process take the same
# per-weight donors, so the second collection skips drawing and converting.
OUTLINE_CACHE = {}


def width_prefix(value):
    """Type 2 encoding of a leading width operand (same as in a program)."""
    char = T2CharString(program=[value, 'endchar'])
    char.compile()
    return char.bytecode[:-1]


def control_box(recording):
    """Bounds of every recorded point, on- and off-curve (None when empty)."""
    xs, ys = [], []
    for _operator, arguments in recording.value:
        for point in arguments:
            if point is not None:
                xs.append(point[0])
                ys.append(point[1])
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def frame_problem(bounds, scale, frame, header, width, bearing, source_name):
    """Why a donor outline cannot keep the stock face frame (None when it fits).

    Keep the stock line frame: a donor outside it fails before publication;
    arbitrary per-glyph shrinking would change the requested typeface."""
    if bounds is not None:
        x0, y0, x1, y1 = (coordinate * scale for coordinate in bounds)
        if x0 < frame.xMin - 1 or y0 < frame.yMin - 1 or x1 > frame.xMax + 1 or y1 > frame.yMax + 1:
            return f'来源字形 {source_name} 超出本机原厂字体面边界'
    outline_width = 0 if bounds is None else (bounds[2] - bounds[0]) * scale
    if (width > header.advanceWidthMax or bearing < header.minLeftSideBearing or
            width - bearing - outline_width < header.minRightSideBearing - 1 or
            bearing + outline_width > header.xMaxExtent + 1):
        return f'来源字形 {source_name} 水平度量超出本机原厂字体面边界'
    return None


def ignorable(cp):
    import unicodedata
    return unicodedata.category(chr(cp)) in IGNORABLE_CATEGORIES


def plan_face(font, donor, allow=()):
    """Encoded candidates of one face: {stock glyph ID: {code point: donor glyph}}.

    Keyed by glyph ID, not name: faces sharing one outline table can derive
    different names (post format 3 names come from each face's own cmap).
    Slots that must stay stock (encoded by an uncovered or other-role
    character) are returned in ``blocked``."""
    if specialized(font, allow):
        return None
    gid = {name: index for index, name in enumerate(font.getGlyphOrder())}
    cmap, source = font.getBestCmap() or {}, donor.getBestCmap() or {}
    candidates, uncovered = {}, 0
    for cp, target_name in sorted(cmap.items()):
        if not role(cp):
            continue
        source_name = source.get(cp)
        if not source_name:
            uncovered += 1
            continue
        candidates.setdefault(gid[target_name], {})[cp] = source_name
    blocked = {gid[name] for table in font['cmap'].tables
               if table.isUnicode() and table.format != 14
               for cp, name in table.cmap.items() if not role(cp) or cp not in source}
    return {'candidates': candidates, 'blocked': blocked, 'uncovered': uncovered}


def resolve_mapping(plans, donor, recordings):
    """Merge face plans that share one outline table into one slot mapping.

    A stock slot whose characters map to donor outlines that differ (inside
    one face or across faces sharing the slot) keeps its stock outline instead
    of failing the whole collection; ignorable characters never decide it."""
    glyphs = donor.getGlyphSet()
    candidates, blocked = {}, set()
    for plan in plans:
        blocked |= plan['blocked']
        for target, values in plan['candidates'].items():
            candidates.setdefault(target, {}).update(values)
    mapping, conflicts = {}, set()
    for target, values in candidates.items():
        if target in blocked:
            continue
        def classes(items):
            found = []
            for cp, name in items:
                if name not in recordings:
                    recordings[name] = draw_record(glyphs, name)
                key = (recordings[name].value, donor['hmtx'][name])
                if not any(key == other for other, _ in found):
                    found.append((key, (cp, name)))
            return found
        if len(set(values.values())) == 1:
            mapping[target] = next(iter(values.values()))
            continue
        found = classes(sorted(values.items()))
        if len(found) > 1:
            visible = [(cp, name) for cp, name in sorted(values.items()) if not ignorable(cp)]
            found = classes(visible) if visible else found
        if len(found) != 1:
            conflicts.add(target)
            continue
        mapping[target] = found[0][1][1]
    return {'mapping': mapping, 'conflicts': conflicts, 'rejected': set()}


def slot_summary(plan, group):
    """Why this face's encoded slots that stayed stock did so."""
    mapping, conflicts, rejected = group['mapping'], group['conflicts'], group['rejected']
    kept = {gid: values for gid, values in plan['candidates'].items() if gid not in mapping}
    conflict = sorted(min(values) for gid, values in kept.items() if gid in conflicts)
    frame = sorted(min(values) for gid, values in kept.items() if gid in rejected)
    return {'retainedSharedSlots': len(kept) - len(conflict) - len(frame),
            'retainedConflictSlots': len(conflict),
            'conflictCodepoints': [f'U+{cp:04X}' for cp in conflict[:16]],
            'retainedOutOfFrameSlots': len(frame),
            'outOfFrameCodepoints': [f'U+{cp:04X}' for cp in frame[:16]]}


def replace_face(font, donor, recordings, allow=(), group=None, donor_key=None):
    """Replace one face. ``group`` (from resolve_mapping) lets faces that
    share one stock outline table receive the same replacement set; slots
    that stay stock for frame reasons are added to its ``rejected`` set.
    ``donor_key`` (the donor's sha256) lets CFF faces of other collections
    built in this process reuse already converted outlines."""
    if specialized(font, allow):
        return {'mode': 'retained-specialized', 'replaced': {}, 'uncovered': 0}
    kind = 'glyf' if 'glyf' in font else 'CFF ' if 'CFF ' in font else 'CFF2' if 'CFF2' in font else None
    if kind is None:
        raise ValueError('本机 CJK 集合包含不支持的轮廓')
    plan = plan_face(font, donor, allow)
    uncovered = plan['uncovered']
    order = font.getGlyphOrder()
    if group is None:
        group = resolve_mapping([plan], donor, recordings)
    mapping = {order[glyph]: name for glyph, name in group['mapping'].items()}
    source_glyphs = donor.getGlyphSet()
    cmap = font.getBestCmap() or {}
    counts = {category: sum(role(cp) == category and name in mapping for cp, name in cmap.items())
              for category in ('cjk', 'latin', 'digit')}
    if not counts['cjk']:
        return {'mode': 'retained-no-cjk-match', 'replaced': counts, 'uncovered': uncovered}
    if '.notdef' in mapping:
        raise ValueError('原厂编码映射指向缺字槽，不能覆盖 .notdef')
    guard_retained_components(font, mapping)
    scale = font['head'].unitsPerEm / donor['head'].unitsPerEm
    frame = font['head']
    converted = {}
    # A few donor outlines (e.g. ideographic tone marks U+302A-302F) may sit
    # outside the stock face frame. Such a slot keeps its stock outline; only
    # a required character or a broad mismatch rejects the whole collection.
    required = {cmap[cp] for cp in map(ord, REQUIRED_CHARACTERS) if cp in cmap}
    rejected = []
    applied = {}
    for target_name, source_name in mapping.items():
        # Only conflict checks keep recordings; a converted outline is cached
        # below, so do not hold every drawn donor outline in memory as well.
        recording = recordings.get(source_name)
        shared_key = (donor_key, source_name, scale, 'glyf' in donor) if donor_key and kind == 'CFF ' else None
        shared = OUTLINE_CACHE.get(shared_key) if shared_key else None
        if recording is None and shared is None:
            recording = draw_record(source_glyphs, source_name)
        width, bearing = donor['hmtx'][source_name]
        width, bearing = round(width * scale), round(bearing * scale)
        if not 0 <= width <= 65535 or not -32768 <= bearing <= 32767:
            rejected.append((target_name, '来源水平度量超出 SFNT 范围'))
            continue
        # The control box (all recorded points) contains the exact outline
        # bounds, so passing with it proves the exact check passes too. Only a
        # box that fails pays for the exact curve-extrema computation.
        box = shared[0] if shared is not None else control_box(recording)
        problem = frame_problem(box, scale, frame, font['hhea'], width, bearing, source_name)
        if problem:
            if recording is None:
                recording = draw_record(source_glyphs, source_name)
            exact = BoundsPen(None)
            recording.replay(exact)
            problem = frame_problem(exact.bounds, scale, frame, font['hhea'], width, bearing, source_name)
        if problem:
            rejected.append((target_name, problem))
            continue
        if kind == 'glyf':
            key = (source_name,)
            if key not in converted:
                if recording is None:
                    recording = draw_record(source_glyphs, source_name)
                pen = TTGlyphPen(None)
                output = Cu2QuPen(pen, max_err=max(0.5, frame.unitsPerEm / 2000),
                                  reverse_direction='glyf' not in donor)
                recording.replay(TransformPen(output, (scale, 0, 0, scale, 0, 0)))
                converted[key] = pen.glyph()
            glyph = converted[key]
            vertical = retained_vertical_deltas(font, target_name)
            old_origin = None
            if 'vmtx' in font:
                old_advance, old_bearing = font['vmtx'][target_name]
                old_origin = getattr(font['glyf'][target_name], 'yMax', 0) + old_bearing
            font['glyf'][target_name] = glyph
            glyph.recalcBounds(font['glyf'])
            if not hasattr(glyph, 'xMin'):
                glyph.xMin = glyph.yMin = glyph.xMax = glyph.yMax = 0
            # recalcBBoxes=False keeps the stock frame but also disables maxp
            # recomputation. Retain stock interpreter limits while reserving
            # enough point/contour capacity for the newly imported outlines.
            maxp = font['maxp']
            maxp.maxPoints = max(maxp.maxPoints, len(glyph.getCoordinates(font['glyf'])[0]))
            maxp.maxContours = max(maxp.maxContours, glyph.numberOfContours)
            if 'fvar' in font and bearing != glyph.xMin:
                raise ValueError('可变 TrueType 的来源侧距必须等于轮廓 xMin')
            if old_origin is not None:
                new_bearing = old_origin - glyph.yMax
                if not -32768 <= new_bearing <= 32767:
                    raise ValueError('原厂垂直原点无法保持在 SFNT 度量范围内')
                header = font['vhea']
                height = glyph.yMax - glyph.yMin
                if (new_bearing < header.minTopSideBearing or
                        old_advance - new_bearing - height < header.minBottomSideBearing or
                        new_bearing + height > header.yMaxExtent):
                    raise ValueError('来源字形垂直度量超出本机原厂字体面边界')
                font['vmtx'][target_name] = (old_advance, new_bearing)
            if 'gvar' in font:
                points = len(glyph.getCoordinates(font['glyf'])[0])
                font['gvar'].variations[target_name] = [
                    TupleVariation(axes, [(0, 0)] * (points + 2) + [top, bottom])
                    for axes, top, bottom in vertical]
        else:
            if kind == 'CFF2' and 'vmtx' in font and 'VORG' not in font:
                raise ValueError('CFF2 集合缺少独立垂直原点，不能沿用旧轮廓的垂直侧距')
            cff = font[kind].cff
            top = cff.topDictIndex[0]
            _, selector = top.CharStrings.getItemAndSelector(target_name)
            private = top.FDArray[selector or 0].Private if hasattr(top, 'FDArray') else top.Private
            key = (source_name, selector, width)
            if key not in converted:
                encoded_width = None if kind == 'CFF2' or width == private.defaultWidthX else width - private.nominalWidthX
                if kind == 'CFF ':
                    # Private dicts only encode the width; the outline body is
                    # independent of them, so it is shared by every face (and
                    # collection) that takes this donor glyph at this scale.
                    if shared is None:
                        char = cff_charstring(recording, None, False, scale, 'glyf' in donor,
                                              private, cff.GlobalSubrs)
                        char.compile()
                        shared = (box, char.bytecode)
                        if shared_key:
                            OUTLINE_CACHE[shared_key] = shared
                    prefix = b'' if encoded_width is None else width_prefix(encoded_width)
                    char = T2CharString(bytecode=prefix + shared[1], private=private,
                                        globalSubrs=cff.GlobalSubrs)
                else:
                    char = cff_charstring(recording, encoded_width, True, scale,
                                          'glyf' in donor, private, cff.GlobalSubrs)
                if selector is not None:
                    char.fdSelectIndex = selector
                converted[key] = char
            top.CharStrings[target_name] = converted[key]
        font['hmtx'][target_name] = (width, bearing)
        applied[target_name] = source_name
    if rejected and (required.intersection(name for name, _ in rejected) or
                     len(rejected) > max(1, len(mapping) // 100)):
        raise ValueError(rejected[0][1])
    if rejected:
        guard_retained_components(font, applied)
    mapping = applied
    group['rejected'] = {font.getGlyphID(name) for name, _ in rejected}
    group['mapping'] = {font.getGlyphID(name): source for name, source in mapping.items()}
    counts = {category: sum(role(cp) == category and name in mapping for cp, name in cmap.items())
              for category in ('cjk', 'latin', 'digit')}
    freeze_horizontal_variations(font, mapping)
    for tag in DROPPED_TAGS:
        if tag in font:
            del font[tag]
    return {'mode': 'compiled', 'replaced': counts, 'uncovered': uncovered,
            **slot_summary(plan, group), 'retainedUnencodedGlyphs': True,
            'outline': kind, 'retainedVariationAxes': 'fvar' in font,
            'replacementVariation': 'fixed-source-at-selected-weight'}


def raw_contract(font):
    """Byte identity of the stock layout/metric tables a face keeps verbatim."""
    tables = getattr(font.reader, 'tables', {})
    return {'rawTables': {tag: hashlib.sha256(font.reader[tag]).hexdigest()
                          for tag in PROTECTED if tag in tables},
            'frame': [font['head'].unitsPerEm, font['head'].xMin, font['head'].yMin,
                      font['head'].xMax, font['head'].yMax]}


def contract_of(font, like):
    return raw_contract(font) if 'rawTables' in like else protected(font)


def changed_tables(stock, index, compiled_path):
    """Outline tables whose compiled bytes differ from the stock face."""
    changed = []
    with TTFont(stock, fontNumber=index, lazy=True) as original, \
            TTFont(compiled_path, lazy=True) as compiled:
        for tag in OUTLINE_TAGS:
            if tag not in original.reader.tables:
                continue
            if tag not in compiled.reader.tables:
                raise ValueError('共享轮廓表在编译后缺失')
            if compiled.reader[tag] != original.reader[tag]:
                changed.append(tag)
    return changed


def reuse_face(font, reuse, face_path, group, plan):
    """Write a face whose outline tables are byte-shared with an already
    compiled face: its own cmap/layout/name/metrics headers stay stock, the
    shared outline tables take the compiled bytes. No second compilation."""
    from fontTools.ttLib.tables.DefaultTable import DefaultTable
    from fontTools.ttLib import TTFont as _TTFont
    changed, compiled_path = reuse
    mapping = group['mapping']
    # Count from the plan: loading cmap here would recompile it on save.
    counts = dict(cjk=0, latin=0, digit=0)
    for name, values in plan['candidates'].items():
        if name in mapping:
            for cp in values:
                counts[role(cp)] += 1
    if not counts['cjk']:
        return {'mode': 'retained-no-cjk-match', 'replaced': counts, 'uncovered': plan['uncovered']}
    with _TTFont(compiled_path, lazy=True, recalcBBoxes=False, recalcTimestamp=False) as compiled:
        for tag in changed:
            table = DefaultTable(tag)
            table.data = compiled.reader[tag]
            font[tag] = table
    for tag in DROPPED_TAGS:
        if tag in font:
            del font[tag]
    font.save(face_path, reorderTables=False)
    return {'mode': 'compiled', 'replaced': counts, 'uncovered': plan['uncovered'],
            **slot_summary(plan, group), 'retainedUnencodedGlyphs': True, 'sharedOutlineTables': True,
            'outline': 'glyf' if 'glyf' in font.reader.tables else 'CFF ' if 'CFF ' in font.reader.tables else 'CFF2',
            'retainedVariationAxes': 'fvar' in font,
            'replacementVariation': 'fixed-source-at-selected-weight'}


def face_weight(stock, index):
    with TTFont(stock, fontNumber=index, lazy=True, recalcTimestamp=False) as font:
        weight = font['OS/2'].usWeightClass if 'OS/2' in font else 400
    return weight if 1 <= weight <= 1000 else 400


def build(source, stock, output, workspace, request, target, progress=None,
          source_for_weight=None, allow=()):
    """source_for_weight(weight) -> donor path picks a donor per stock face
    (by its OS/2 weight); without it every face uses ``source``."""
    stock, output = Path(stock), Path(output)
    count = collection_faces(stock)
    weights = [face_weight(stock, index) for index in range(count)]
    sources = ([Path(source_for_weight(weight)) for weight in weights] if source_for_weight
               else [Path(source)] * count)
    unique = list(dict.fromkeys(sources))
    if any(path.resolve() == output.resolve() for path in unique) or stock.resolve() == output.resolve():
        raise ValueError('集合输出不能覆盖来源或原厂文件')
    before = ([identity(path) for path in unique], identity(stock))
    source_hashes, stock_hash = [sha(path) for path in unique], sha(stock)
    faces = {path: _pick_face(path, 'cjk', weights[sources.index(path)], None) for path in unique}
    for stale in [key for key in OUTLINE_CACHE if key[0] not in source_hashes]:
        del OUTLINE_CACHE[stale]  # only donors of this build stay cached
    report = {'schema': SCHEMA, 'requestId': request, 'target': target,
              'sourceSha256': source_hashes[0], 'stockSha256': stock_hash,
              'sourceFace': faces[unique[0]], 'stockFaces': count, 'faces': []}
    with tempfile.TemporaryDirectory(prefix='collection-', dir=workspace) as temporary:
        temporary = Path(temporary)
        face_paths = []
        donors = {}
        try:
            for path in unique:
                kwargs = {'fontNumber': faces[path]} if faces[path] >= 0 else {}
                donor = TTFont(path, lazy=True, recalcTimestamp=False, **kwargs)
                donors[path] = (donor, {})
                cmap = donor.getBestCmap() or {}
                if any(cp not in cmap for cp in map(ord, REQUIRED_CHARACTERS)):
                    raise ValueError('组合来源缺少必需的中文、英文字母或数字')
                if not any(tag in donor for tag in ('glyf', 'CFF ', 'CFF2')):
                    raise ValueError('组合来源不包含可用轮廓')
            # Faces that share one stock outline table (Noto CJK: every region
            # face shares CFF/hmtx/vmtx) and one donor get one merged
            # replacement set, compiled once; the other faces reuse those exact
            # bytes so the collection can still share them.
            plans, groups = {}, {}
            for index in range(count):
                with TTFont(stock, fontNumber=index, lazy=True, recalcBBoxes=False,
                            recalcTimestamp=False) as font:
                    plan = plan_face(font, donors[sources[index]][0], allow)
                    if plan is None:
                        continue
                    plans[index] = plan
                    tables = getattr(font.reader, 'tables', {})
                    # Plans are keyed by glyph ID, so the shared outline/metric
                    # tables alone decide which faces can share one compile.
                    shared = tuple((tag, tables[tag].offset, tables[tag].length)
                                   for tag in OUTLINE_TAGS if tag in tables)
                    groups.setdefault((sources[index], shared), []).append(index)
            merged, leader_of = {}, {}
            for (path, _shared), members in groups.items():
                donor, recordings = donors[path]
                group = resolve_mapping([plans[index] for index in members], donor, recordings)
                for index in members:
                    merged[index] = group
                    leader_of[index] = members[0]
            built = {}
            for index in range(count):
                donor, recordings = donors[sources[index]]
                _progress(progress, 'collection', f'正在编译本机 CJK 集合面 {index + 1}/{count}', 95)
                face_path = temporary / f'face-{index}.font'
                leader = leader_of.get(index)
                reuse = built.get(leader) if leader is not None and leader != index else None
                with TTFont(stock, fontNumber=index, lazy=True, recalcBBoxes=False,
                            recalcTimestamp=False) as font:
                    if index not in plans or reuse is not None:
                        # Specialized and shared-outline faces copy their stock
                        # layout tables byte for byte: prove exactly that instead
                        # of recompiling GSUB/GPOS/vmtx for a semantic hash.
                        original = raw_contract(font)
                        if index not in plans:
                            details = {'mode': 'retained-specialized', 'replaced': {}, 'uncovered': 0}
                        else:
                            details = reuse_face(font, reuse, face_path, merged[index], plans[index])
                    else:
                        original = protected(font)
                        details = replace_face(font, donor, recordings, allow, merged.get(index),
                                               donor_key=source_hashes[unique.index(sources[index])])
                        if protected(font) != original:
                            raise ValueError(f'集合面 {index} 的原厂布局契约已变化')
                        if details['mode'] == 'compiled':
                            font.save(face_path, reorderTables=False)
                            built[index] = (changed_tables(stock, index, face_path), face_path)
                            recordings.clear()  # followers reuse the compiled bytes
                if details['mode'] != 'compiled':
                    # Retained faces need no expensive outline round trip.
                    with TTFont(stock, fontNumber=index, lazy=True, recalcBBoxes=False,
                                recalcTimestamp=False) as untouched:
                        untouched.save(face_path, reorderTables=False)
                with TTFont(face_path, lazy=True, recalcTimestamp=False) as check:
                    if contract_of(check, original) != original:
                        raise ValueError(f'集合面 {index} 序列化后布局契约已变化')
                if source_for_weight:
                    details = dict(details, stockWeight=weights[index], source=sources[index].name)
                report['faces'].append(dict(index=index, contract=original, **details))
                face_paths.append(face_path)
                del font, check
                gc.collect()
        finally:
            for donor, _recordings in donors.values():
                donor.close()
        if not any(face['mode'] == 'compiled' for face in report['faces']):
            raise ValueError('集合没有可替换的常规 CJK 字体面')
        collection = TTCollection()
        collection.fonts = [TTFont(path, lazy=True, recalcBBoxes=False, recalcTimestamp=False)
                            for path in face_paths]
        staged = temporary / 'compiled.ttc'
        try:
            collection.save(staged, shareTables=True)
        finally:
            collection.close()
        if collection_faces(staged) != count:
            raise ValueError('生成后的集合面数量变化')
        for index, face in enumerate(report['faces']):
            with TTFont(staged, fontNumber=index, lazy=True, recalcTimestamp=False) as check:
                if contract_of(check, face['contract']) != face['contract']:
                    raise ValueError(f'集合面 {index} 合集后布局契约已变化')
        if (before != ([identity(path) for path in unique], identity(stock)) or
                [sha(path) for path in unique] != source_hashes or sha(stock) != stock_hash):
            raise ValueError('集合编译期间来源或原厂字体已变化')
        report['outputSha256'] = sha(staged)
        report['result'] = 'PASS'
        output.parent.mkdir(parents=True, exist_ok=True)
        # Rename on the output filesystem; keep the old alias until all checks pass.
        fd, name = tempfile.mkstemp(prefix='.collection-', dir=output.parent)
        try:
            with os.fdopen(fd, 'wb') as stream, staged.open('rb') as data:
                shutil.copyfileobj(data, stream)
                stream.flush(); os.fsync(stream.fileno())
            os.chmod(name, 0o644)
            os.replace(name, output)
        finally:
            Path(name).unlink(missing_ok=True)
    return report


def stock_path(module, target):
    logical = Path(target)
    if (len(logical.parts) != 4 or logical.parts[0] != '/' or logical.parts[2] != 'fonts'
            or logical.suffix.lower() not in ('.ttc', '.otc')):
        raise ValueError('集合目标必须是准确的系统字体路径')
    allowed = dict(stock_inventory.LOGICAL_FONT_ROOTS)
    if logical.parts[1] not in allowed:
        raise ValueError('集合目标分区不受支持')
    override = Path(os.environ.get('LUOSHU_COLLECTION_STOCK_ROOT', '/'))
    if override != Path('/'):
        return override / logical.relative_to('/')
    risk = stock_inventory._overlay_risk(module)
    part = logical.parts[1]
    base = allowed[part]
    root = stock_inventory.FontRoot(part, base, stock_inventory._pick_actual_root(base, None, risk))
    roots = [root]
    # Follow stock cross-partition aliases through verified roots too. Optional
    # roots without a stock view cannot authorize a symlink escape.
    for other, location in allowed.items():
        if other == part or not location.is_dir():
            continue
        try:
            roots.append(stock_inventory.FontRoot(other, location,
                         stock_inventory._pick_actual_root(location, None, risk)))
        except stock_inventory.InventoryError:
            pass
    return stock_inventory._stock_font_path(root, root.actual / logical.name, roots)


def owned_workspace():
    """Scratch space inside the finite supervisor's own task directory.

    The supervisor removes LUOSHU_TASK_SCOPE_TMPDIR when the task ends, so a
    killed build cannot leave a resident or orphaned workspace behind.
    """
    raw = os.environ.get('LUOSHU_TASK_SCOPE_TMPDIR', '')
    scope = Path(raw)
    if not raw or not scope.is_absolute() or scope.is_symlink() or not scope.is_dir():
        raise ValueError('缺少任务专属字体工作区')
    scope = scope.resolve()
    return Path(tempfile.mkdtemp(prefix='collection-build.', dir=scope)), scope


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--target', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--request', required=True)
    args = parser.parse_args()
    workspace = None
    try:
        workspace, scope = owned_workspace()
        parent = args.output.parent.resolve()
        module = args.module.resolve()
        # The legacy engine stages its payload in the task directory; the router
        # stages the next-boot tree in the module's owned tmp directory.
        stage = Path(os.environ.get('LUOSHU_TMP_DIR') or module / '.luoshu-state' / 'tmp') / 'mix-stage'
        if not (parent.is_relative_to(scope) or parent.is_relative_to(stage.resolve())):
            raise ValueError('集合输出必须位于本次组合暂存目录')
        report = build(args.source, stock_path(args.module, args.target), args.output,
                       workspace, args.request, args.target,
                       str(args.module / 'config/composite_progress.json'))
        sidecar = args.output.with_name(args.output.name + '.luoshu-collection.json')
        temporary = sidecar.with_suffix('.tmp')
        temporary.write_text(json.dumps(report, ensure_ascii=True, separators=(',', ':')) + '\n')
        os.replace(temporary, sidecar)
        print(json.dumps({'status': 'ok', 'faces': report['stockFaces']}, separators=(',', ':')))
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print('[MIX] CJK 集合生成失败：' + str(error), flush=True)
        return 1
    finally:
        if workspace is not None:
            shutil.rmtree(workspace, ignore_errors=True)


if __name__ == '__main__':
    raise SystemExit(main())
