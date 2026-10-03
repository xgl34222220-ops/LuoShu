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
from fontTools.pens.qu2cuPen import Qu2CuPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTCollection, TTFont
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.varLib.builder import buildVarData, buildVarIdxMap

from composite_collection_contract import collection_faces
from composite_font import LATIN_CODEPOINTS, DIGIT_CODEPOINTS, _pick_face, _progress
import font_inventory as stock_inventory

SCHEMA = 'composite-collection-build-v1'
PROTECTED = ('cmap', 'GSUB', 'GPOS', 'GDEF', 'name', 'hhea', 'OS/2', 'vhea', 'vmtx', 'VORG',
             'fvar', 'avar', 'STAT', 'MVAR', 'BASE', 'cvar', 'VVAR')
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


def specialized(font):
    names = font['name'] if 'name' in font else None
    label = ' '.join(filter(None, (names.getDebugName(i) for i in (1, 2, 16, 17)))) if names else ''
    return (bool(font['post'].isFixedPitch) if 'post' in font else False) or any(
        word in label.lower() for word in ('mono', 'serif', 'emoji', 'symbol', 'icon')) or bool(
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


def replace_face(font, donor, recordings):
    if specialized(font):
        return {'mode': 'retained-specialized', 'replaced': {}, 'uncovered': 0}
    kind = 'glyf' if 'glyf' in font else 'CFF ' if 'CFF ' in font else 'CFF2' if 'CFF2' in font else None
    if kind is None:
        raise ValueError('本机 CJK 集合包含不支持的轮廓')
    cmap, source = font.getBestCmap() or {}, donor.getBestCmap() or {}
    source_glyphs = donor.getGlyphSet()
    mapping, counts, uncovered = {}, dict(cjk=0, latin=0, digit=0), 0
    for cp, target_name in sorted(cmap.items()):
        category = role(cp)
        if not category:
            continue
        source_name = source.get(cp)
        if not source_name:
            uncovered += 1
            continue
        if target_name in mapping and mapping[target_name] != source_name:
            previous = mapping[target_name]
            for name in (previous, source_name):
                if name not in recordings:
                    recordings[name] = draw_record(source_glyphs, name)
            if (recordings[previous].value != recordings[source_name].value or
                    donor['hmtx'][previous] != donor['hmtx'][source_name]):
                raise ValueError(f'原厂共享字形 U+{cp:04X} 对应不同来源轮廓，不能安全覆盖')
        mapping[target_name] = source_name
        counts[category] += 1
    # A covered character can share its glyph ID with an uncovered character
    # (or a character outside these roles). Keep that whole slot stock.
    blocked = {name for table in font['cmap'].tables
               if table.isUnicode() and table.format != 14
               for cp, name in table.cmap.items() if not role(cp) or cp not in source}
    retained_shared = len(blocked.intersection(mapping))
    for name in blocked:
        mapping.pop(name, None)
    counts = {category: sum(role(cp) == category and name in mapping for cp, name in cmap.items())
              for category in counts}
    if not counts['cjk']:
        return {'mode': 'retained-no-cjk-match', 'replaced': counts, 'uncovered': uncovered}
    if '.notdef' in mapping:
        raise ValueError('原厂编码映射指向缺字槽，不能覆盖 .notdef')
    guard_retained_components(font, mapping)
    scale = font['head'].unitsPerEm / donor['head'].unitsPerEm
    frame = font['head']
    converted = {}
    for target_name, source_name in mapping.items():
        if source_name not in recordings:
            recordings[source_name] = draw_record(source_glyphs, source_name)
        recording = recordings[source_name]
        bounds = BoundsPen(None)
        recording.replay(bounds)
        # Keep the stock line frame. A donor outside it fails before publication;
        # arbitrary per-glyph shrinking would change the requested typeface.
        if bounds.bounds is not None:
            x0, y0, x1, y1 = (coordinate * scale for coordinate in bounds.bounds)
            if x0 < frame.xMin - 1 or y0 < frame.yMin - 1 or x1 > frame.xMax + 1 or y1 > frame.yMax + 1:
                raise ValueError(f'来源字形 {source_name} 超出本机原厂字体面边界')
        width, bearing = donor['hmtx'][source_name]
        width, bearing = round(width * scale), round(bearing * scale)
        if not 0 <= width <= 65535 or not -32768 <= bearing <= 32767:
            raise ValueError('来源水平度量超出 SFNT 范围')
        header = font['hhea']
        outline_width = 0 if bounds.bounds is None else (bounds.bounds[2] - bounds.bounds[0]) * scale
        if (width > header.advanceWidthMax or bearing < header.minLeftSideBearing or
                width - bearing - outline_width < header.minRightSideBearing - 1 or
                bearing + outline_width > header.xMaxExtent + 1):
            raise ValueError(f'来源字形 {source_name} 水平度量超出本机原厂字体面边界')
        if kind == 'glyf':
            key = (source_name,)
            if key not in converted:
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
                pen = T2CharStringPen(encoded_width, None, CFF2=kind == 'CFF2')
                output = Qu2CuPen(pen, max_err=max(0.5, frame.unitsPerEm / 2000),
                                  all_cubic=True, reverse_direction='glyf' in donor)
                recording.replay(TransformPen(output, (scale, 0, 0, scale, 0, 0)))
                char = pen.getCharString(private=private, globalSubrs=cff.GlobalSubrs)
                if selector is not None:
                    char.fdSelectIndex = selector
                converted[key] = char
            top.CharStrings[target_name] = converted[key]
        font['hmtx'][target_name] = (width, bearing)
    freeze_horizontal_variations(font, mapping)
    for tag in ('DSIG', 'LTSH', 'hdmx', 'VDMX'):
        if tag in font:
            del font[tag]
    return {'mode': 'compiled', 'replaced': counts, 'uncovered': uncovered,
            'retainedSharedSlots': retained_shared, 'retainedUnencodedGlyphs': True,
            'outline': kind, 'retainedVariationAxes': 'fvar' in font,
            'replacementVariation': 'fixed-source-at-selected-weight'}


def build(source, stock, output, workspace, request, target, progress=None):
    source, stock, output = map(Path, (source, stock, output))
    if source.resolve() == output.resolve() or stock.resolve() == output.resolve():
        raise ValueError('集合输出不能覆盖来源或原厂文件')
    before = (identity(source), identity(stock))
    source_hash, stock_hash = sha(source), sha(stock)
    count = collection_faces(stock)
    face_index = _pick_face(source, 'cjk', 400, None)
    kwargs = {'fontNumber': face_index} if face_index >= 0 else {}
    report = {'schema': SCHEMA, 'requestId': request, 'target': target,
              'sourceSha256': source_hash, 'stockSha256': stock_hash,
              'sourceFace': face_index, 'stockFaces': count, 'faces': []}
    with tempfile.TemporaryDirectory(prefix='collection-', dir=workspace) as temporary:
        temporary = Path(temporary)
        face_paths = []
        with TTFont(source, lazy=True, recalcTimestamp=False, **kwargs) as donor:
            cmap = donor.getBestCmap() or {}
            if any(cp not in cmap for cp in map(ord, '中ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789')):
                raise ValueError('组合来源缺少必需的中文、英文字母或数字')
            if not any(tag in donor for tag in ('glyf', 'CFF ', 'CFF2')):
                raise ValueError('组合来源不包含可用轮廓')
            recordings = {}
            for index in range(count):
                _progress(progress, 'collection', f'正在编译本机 CJK 集合面 {index + 1}/{count}', 95)
                face_path = temporary / f'face-{index}.font'
                with TTFont(stock, fontNumber=index, lazy=True, recalcBBoxes=False,
                            recalcTimestamp=False) as font:
                    original = protected(font)
                    details = replace_face(font, donor, recordings)
                    if protected(font) != original:
                        raise ValueError(f'集合面 {index} 的原厂布局契约已变化')
                    if details['mode'] == 'compiled':
                        font.save(face_path, reorderTables=False)
                    else:
                        # Retained faces need no expensive outline round trip.
                        with TTFont(stock, fontNumber=index, lazy=True, recalcBBoxes=False,
                                    recalcTimestamp=False) as untouched:
                            untouched.save(face_path, reorderTables=False)
                with TTFont(face_path, lazy=True, recalcTimestamp=False) as check:
                    if protected(check) != original:
                        raise ValueError(f'集合面 {index} 序列化后布局契约已变化')
                report['faces'].append(dict(index=index, contract=original, **details))
                face_paths.append(face_path)
                del font, check
                gc.collect()
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
                if protected(check) != face['contract']:
                    raise ValueError(f'集合面 {index} 合集后布局契约已变化')
        if before != (identity(source), identity(stock)) or sha(source) != source_hash or sha(stock) != stock_hash:
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--target', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--request', required=True)
    args = parser.parse_args()
    try:
        from font_switch_input import owned_workspace
        workspace = owned_workspace(args.module)
        parent = args.output.parent.resolve()
        module = args.module.resolve()
        stage = module / '.luoshu-mix-stage'
        engine = module / '.legacy-v14-runtime'
        if not (parent.is_relative_to(stage) or
                (parent.parent == engine and re.fullmatch(r'\.font-payload-stage\.[0-9]+', parent.name))):
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


if __name__ == '__main__':
    raise SystemExit(main())
