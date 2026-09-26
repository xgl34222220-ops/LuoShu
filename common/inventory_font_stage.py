#!/usr/bin/env python3
"""Build an isolated font payload solely from measured device inventory.

No brand, model, family filename, or fixed list decides which system paths exist.
The scanner owns targets; actual source faces own weight/style/script capability.
"""
from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import struct
import sys
import tempfile
from typing import Any

from fontTools.ttLib import TTCollection, TTFont
from fontTools.unicodedata import category, script
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.ttLib.tables.DefaultTable import DefaultTable

from font_metrics_normalize import _device_build_key
from font_slot_coverage import (preferred_unicode_codepoints, is_han,
                                is_cjk_routing_codepoint, valid_coverage)
from inventory_font_metrics import compact_routed_source, write_metrics, link_copy, contract_for_face

REVISION = 1
EXTENSIONS = {'.ttf', '.otf', '.ttc', '.otc', '.font'}
ROLES = {100: 'thin', 200: 'extralight', 300: 'light', 400: 'regular',
         500: 'medium', 600: 'semibold', 700: 'bold', 800: 'extrabold', 900: 'black'}


class StageError(RuntimeError):
    pass


def identity(path: Path) -> tuple:
    value = path.stat()
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns,
            value.st_ctime_ns)


def file_digest(path: Path, cache: dict | None = None) -> str:
    key = identity(path)
    if cache is not None and key in cache:
        return cache[key]
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    if identity(path) != key:
        raise StageError('校验期间字体文件发生变化')
    digest = result.hexdigest()
    if cache is not None:
        cache[key] = digest
    return digest


def anchors_digest(store: Path, cache: dict) -> str:
    entries = {path.name: file_digest(path, cache) for path in sorted(store.glob('*.font'))
               if path.is_file() and not path.is_symlink()}
    manifest = store / '.luoshu-mix-source-weights.json'
    if manifest.is_file():
        entries[manifest.name] = file_digest(manifest, cache)
    return hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()


def logical_path(value: str) -> str:
    if (not isinstance(value, str) or not value.startswith('/') or value.startswith('//')
            or any(c in value for c in '\r\n\t\x00')
            or any(part in ('', '.', '..') for part in value[1:].split('/'))):
        raise StageError('清单包含不安全的字体路径')
    parts = PurePosixPath(value).parts
    if (len(parts) < 3 or parts[1].startswith('.')
            or parts[1] in {'data', 'storage', 'sdcard', 'proc', 'sys', 'dev', 'mnt'}):
        raise StageError(f'清单目标不是系统字体路径：{value}')
    return value


def load_inventory(module: Path) -> dict:
    try:
        data = json.loads((module / 'config/device_font_inventory.json').read_text())
    except (OSError, ValueError) as exc:
        raise StageError('原厂字体清单不可用，请重新扫描') from exc
    if (not isinstance(data, dict) or data.get('schema') != 'device-font-inventory-v1'
            or data.get('state') != 'ready' or data.get('inventoryRevision') != 1
            or data.get('scannerRevision') != 9 or data.get('metricsRevision') != 4
            or not isinstance(data.get('slots'), dict) or not data['slots']):
        raise StageError('原厂字体清单无效，请重新扫描')
    build_key = _device_build_key()
    if build_key and data.get('buildKey') != build_key:
        raise StageError('原厂字体清单属于其他系统版本，请重新扫描')
    for path, slot in data['slots'].items():
        logical_path(path)
        if not isinstance(slot, dict):
            raise StageError('原厂槽位数据无效')
    return data



def family_names(font: TTFont) -> frozenset[str]:
    table = font['name']
    values = set()
    for name_id in (16, 1):
        for record in table.names:
            if record.nameID == name_id:
                try:
                    value = ' '.join(record.toUnicode().casefold().split())
                except (ValueError, UnicodeError):
                    continue
                if value:
                    values.add(value)
        if values:
            break
    return frozenset(values)


def validate_source_structure(font: TTFont, file_size: int) -> None:
    """Validate SFNT structure without decoding or recompiling glyph outlines."""
    for entry in font.reader.tables.values():
        if entry.offset < 0 or entry.length < 0 or entry.offset + entry.length > file_size:
            raise StageError('源字体包含越界的数据表')
    for tag in ('head', 'hhea', 'hmtx', 'maxp', 'OS/2', 'cmap', 'name'):
        if tag not in font:
            raise StageError(f'源字体缺少 {tag} 表')
    count = int(font['maxp'].numGlyphs)
    hmetrics = int(font['hhea'].numberOfHMetrics)
    if not 1 <= count <= 65535 or not 1 <= hmetrics <= count:
        raise StageError('源字体字形或水平度量数量无效')
    if font.reader.tables['hmtx'].length < hmetrics * 4 + (count - hmetrics) * 2:
        raise StageError('源字体水平度量被截断')
    if 'glyf' in font:
        if 'loca' not in font:
            raise StageError('源字体缺少 TrueType 字形定位表')
        offsets = font['loca'].locations
        if (len(offsets) != count + 1 or any(a > b for a, b in zip(offsets, offsets[1:]))
                or offsets[-1] > font.reader.tables['glyf'].length):
            raise StageError('源字体 TrueType 字形定位无效')
    elif 'CFF ' in font or 'CFF2' in font:
        table = font['CFF ' if 'CFF ' in font else 'CFF2'].cff
        if not table.topDictIndex or len(table.topDictIndex[0].CharStrings.charStrings) != count:
            raise StageError('源字体 CFF 字形数量无效')
    else:
        raise StageError('源字体不包含可渲染的字形轮廓')


@dataclass
class SourceFace:
    path: Path
    index: int
    key: tuple
    family: frozenset[str]
    weight: int
    axes: dict[str, tuple[float, float, float]]
    points: frozenset[int]
    scripts: frozenset[str]
    italic: bool
    mono: bool
    color: bool
    role_weights: dict | None = None


def inspect_faces(path: Path, allowed_families: frozenset[str] | None = None) -> list[SourceFace]:
    key = identity(path)
    with path.open('rb') as stream:
        collection = stream.read(4) == b'ttcf'
        if collection:
            stream.seek(8)
            count = struct.unpack('>I', stream.read(4))[0]
            if not 1 <= count <= 256:
                raise StageError('字体集合面数无效')
        else:
            count = 1
    result = []
    for index in range(count):
        number = index if collection else -1
        kwargs = {'fontNumber': number} if collection else {}
        with TTFont(path, lazy=True, recalcBBoxes=False, recalcTimestamp=False, **kwargs) as font:
            names = family_names(font)
            if allowed_families is not None and not names.intersection(allowed_families):
                continue
            validate_source_structure(font, key[2])
            points = frozenset(preferred_unicode_codepoints(font))
            scripts = frozenset(script(chr(cp)) for cp in points
                                if category(chr(cp)).startswith('L')) - {'Zyyy', 'Zinh'}
            post = font.reader['post'] if 'post' in font else b''
            mono = len(post) >= 16 and bool(struct.unpack_from('>I', post, 12)[0])
            os2, head = font['OS/2'], font['head']
            axes = {}
            if 'fvar' in font:
                for axis in font['fvar'].axes:
                    values = tuple(float(v) for v in (axis.minValue, axis.defaultValue, axis.maxValue))
                    if not all(float('-inf') < v < float('inf') for v in values) or not values[0] <= values[1] <= values[2]:
                        raise StageError('源字体可变轴范围无效')
                    axes[axis.axisTag] = values
            result.append(SourceFace(path, number, (*key, number), names,
                int(os2.usWeightClass), axes, points, scripts,
                bool(int(os2.fsSelection) & 1 or int(head.macStyle) & 2), mono,
                any(tag in font for tag in ('COLR', 'CBDT', 'sbix', 'SVG '))))
    return result


class SourcePool:
    def __init__(self, module: Path, stage: Path, mode: str, source: Path | None, temporary: Path):
        self.temporary = temporary
        self.materialized: dict[tuple, Path] = {}
        self.materialized_axes: dict[Path, list[str]] = {}
        self.faces: list[SourceFace] = []
        self.mode = mode
        self.store = stage / 'system/fonts/.luoshu-font-store'
        if mode == 'direct':
            if source is None:
                raise StageError('直接换字体缺少源文件')
            source = source.resolve(strict=True)
            self.faces = inspect_faces(source)
            families = frozenset(name for face in self.faces for name in face.family)
            seen = {identity(source)}
            for candidate in sorted(source.parent.iterdir()):
                if not candidate.is_file() or candidate.suffix.lower() not in EXTENSIONS:
                    continue
                key = identity(candidate)
                if key in seen:
                    continue
                seen.add(key)
                try:
                    self.faces.extend(inspect_faces(candidate, families))
                except MemoryError:
                    raise
                except Exception:
                    # An unrelated/corrupt library file must not block selected valid source.
                    continue
        elif mode == 'mix':
            composite = self.store / 'mix-composite.font'
            if composite.is_file():
                # Original donors may have unselected axes/scripts. Only the
                # final composite and explicit composed weight anchors qualify.
                paths = [composite, *sorted(self.store.glob('wght-*.font'))]
            else:
                paths = [self.store / f'{role}.font' for role in ROLES.values()]
                paths += sorted(self.store.glob('wght-*.font'))
                paths += sorted(self.store.glob('source-*.font'))
                paths += [self.store / 'variable.font']
            seen = set()
            for path in paths:
                if not path.is_file() or identity(path) in seen:
                    continue
                seen.add(identity(path))
                self.faces.extend(inspect_faces(path))
            manifest = self.store / '.luoshu-mix-source-weights.json'
            if manifest.is_file() and mode == 'mix':
                metadata = json.loads(manifest.read_text())
                if metadata.get('schema') != 'luoshu-mix-source-weights-v1':
                    raise StageError('组合字体字重记录无效')
                for face in self.faces:
                    face.role_weights = metadata.get('sources', {}).get(face.path.name)
                    if face.role_weights:
                        expected = face.role_weights.get('digest')
                        digest = hashlib.sha256()
                        with face.path.open('rb') as stream:
                            for block in iter(lambda: stream.read(1024 * 1024), b''):
                                digest.update(block)
                        if expected != digest.hexdigest():
                            raise StageError('组合字体字重记录与源文件不一致')
        else:
            raise StageError('未知换字体模式')
        if not self.faces:
            raise StageError('没有可用的字体源')

    def pick(self, target: dict) -> tuple[SourceFace | None, int, str]:
        metrics = target.get('metrics') or {}
        traits = metrics.get('fontTraits') or {}
        coverage = metrics.get('coverage')
        if not valid_coverage(coverage):
            raise StageError('原厂槽位缺少可靠字符覆盖信息，请重新扫描')
        if target.get('preservedReason'):
            return None, 0, str(target['preservedReason'])
        if traits.get('color') or traits.get('symbol'):
            return None, 0, 'protected-color-font'
        try:
            weight = int(target.get('weight', metrics.get('weightClass', 400)))
        except (ValueError, TypeError) as exc:
            raise StageError('原厂字重无效') from exc
        if not 1 <= weight <= 1000:
            raise StageError('原厂字重超出范围')
        required = set(target.get('requiresScripts') or (traits.get('letterScripts') or {}).keys()) - {'Zyyy', 'Zinh'}
        if not required:
            if coverage['hasHan']:
                required.add('Hani')
            if coverage['hasLatin']:
                required.add('Latn')
        italic = bool(traits.get('italic') or target.get('style') in {'italic', 'oblique'})
        digits = target.get('replacementRole') == 'digits'
        def supports_style(face):
            if face.italic == italic:
                return True
            if 'ital' in face.axes:
                return face.axes['ital'][0] <= int(italic) <= face.axes['ital'][2]
            if 'slnt' in face.axes:
                low, _default, high = face.axes['slnt']
                return (low < 0 or high > 0) if italic else low <= 0 <= high
            return False
        candidates = [face for face in self.faces if not face.color
                      and supports_style(face) and (not traits.get('monospaced') or face.mono)]
        if not candidates:
            return None, weight, 'source-style-missing'
        candidates = [face for face in candidates if required.issubset(face.scripts)
                      and (not coverage['hasLatin'] or all(cp in face.points for cp in range(65, 91))
                           and all(cp in face.points for cp in range(97, 123)))
                      and (not digits or all(cp in face.points for cp in range(48, 58)))]
        if not candidates:
            return None, weight, 'source-script-coverage-missing'
        def supported(face):
            if face.role_weights:
                role = 'cjk' if coverage['hasHan'] else 'digit' if digits else 'latin'
                actual = face.role_weights.get(role + 'Weight', face.weight)
                return actual == weight or face.role_weights.get(role + 'Mode') == 'fixed'
            return (face.axes.get('wght', (face.weight, face.weight, face.weight))[0]
                    <= weight <= face.axes.get('wght', (face.weight, face.weight, face.weight))[2])
        eligible = [face for face in candidates if supported(face)]
        if not eligible:
            return None, weight, 'source-weight-missing'
        # Exact static faces preserve designer interpolation. Otherwise a real
        # reachable axis instance is mandatory; never relabel Regular as Bold.
        best = min(eligible, key=lambda face: (
                                             bool(face.role_weights and face.role_weights.get('targetWeight') != weight),
                                             self.faces.index(face), bool(face.axes), face.weight != weight))
        return best, weight, ''

    def materialize(self, face: SourceFace, weight: int, variable: bool = False,
                    italic: bool | None = None) -> Path:
        key = (face.key, weight, variable, italic)
        if key in self.materialized:
            return self.materialized[key]
        if identity(face.path) != face.key[:-1]:
            raise StageError('生成期间源字体发生变化，请重新应用')
        output = self.temporary / f'anchor-{len(self.materialized)}.font'
        kwargs = {'fontNumber': face.index} if face.index >= 0 else {}
        with TTFont(face.path, lazy=True, recalcTimestamp=False, recalcBBoxes=False, **kwargs) as original:
            style_axes = {}
            if italic is not None and face.italic != italic:
                if 'ital' in face.axes:
                    style_axes['ital'] = int(italic)
                elif 'slnt' in face.axes:
                    low, default, high = face.axes['slnt']
                    style_axes['slnt'] = (default if default else (max(low, -12) if low < 0 else min(high, 12))) if italic else 0
            if face.axes and (not variable or style_axes):
                location = ({} if variable else
                            {tag: weight if tag == 'wght' else values[1] for tag, values in face.axes.items()})
                location.update(style_axes)
                font = instantiateVariableFont(original, location, inplace=False, optimize=True)
                try:
                    if 'fvar' in font and not variable:
                        raise StageError('实例字体仍有未固定的可变轴')
                    if not variable:
                        font['OS/2'].usWeightClass = weight
                    if style_axes:
                        font['OS/2'].fsSelection = (int(font['OS/2'].fsSelection) & ~1) | int(bool(italic))
                        font['head'].macStyle = (int(font['head'].macStyle) & ~2) | (2 if italic else 0)
                    font.save(output, reorderTables=None)
                finally:
                    font.close()
            elif face.index >= 0:
                # Save a selected TTC face once; untouched raw tables stay raw.
                original.save(output, reorderTables=None)
            else:
                # User-owned library files can be overwritten in place. Pin a
                # private snapshot so later edits cannot mutate staged anchors.
                shutil.copyfile(face.path, output)
        if identity(face.path) != face.key[:-1]:
            raise StageError('生成期间源字体发生变化，请重新应用')
        with TTFont(output, lazy=True, recalcTimestamp=False) as font:
            if (('fvar' in font and not variable) or
                    (not variable and not face.role_weights and int(font['OS/2'].usWeightClass) != weight)):
                raise StageError('生成的字重与请求不一致')
            for tag in ('head', 'hhea', 'OS/2', 'maxp'):
                font[tag]
            if len(font.reader['cmap']) < 4:
                raise StageError('生成的字符映射表无效')
            self.materialized_axes[output] = sorted(axis.axisTag for axis in font['fvar'].axes) if 'fvar' in font else []
        self.materialized[key] = output
        return output


def safe_destination(stage: Path, logical: str) -> Path:
    destination = stage / logical_path(logical).lstrip('/')
    for parent in [destination, *destination.parents]:
        if parent == stage:
            break
        if parent.is_symlink():
            raise StageError(f'暂存目标包含符号链接：{logical}')
    return destination


def faces_for_slot(slot: dict) -> list[dict]:
    faces = slot.get('faces')
    if not isinstance(faces, list) or not faces:
        if str(slot.get('format', '')).upper() in {'TTC', 'OTC'}:
            return []
        return [slot]
    if not all(isinstance(face, dict) for face in faces):
        raise StageError('字体集合面记录无效')
    if len(faces) > 1 and [face.get('faceIndex') for face in faces] != list(range(len(faces))):
        raise StageError('字体集合面顺序无效')
    return [{**slot, **face} for face in faces]


def run(module: Path, stage: Path, mode: str, source: Path | None = None,
        family: str = '', plan: Path | None = None) -> dict:
    module, stage = module.resolve(), stage.absolute()
    live = module / '.luoshu-payload'
    if (stage.is_symlink() or stage.resolve() != stage or stage == module
            or stage == live or live in stage.parents
            or any(module / part in (stage, *stage.parents)
                   for part in ('system', 'product', 'system_ext', 'vendor', 'odm'))):
        raise StageError('仅允许在隔离暂存目录生成字体')
    data = load_inventory(module)
    requested = None
    if plan is not None:
        requested = {logical_path(line.strip()) for line in plan.read_text().splitlines() if line.strip()}
        if not requested or requested - data['slots'].keys():
            raise StageError('补齐计划与当前字体清单不一致')
    stage.mkdir(parents=True, exist_ok=True)
    for logical in data['slots']:
        safe_destination(stage, logical)
    store = stage / 'system/fonts/.luoshu-font-store'
    store.mkdir(parents=True, exist_ok=True)
    preserved: dict[str, str] = {}
    for path, value in (data.get('preservedFonts') or {}).items():
        try:
            logical_path(path)
        except StageError:
            continue
        preserved[path] = str(value.get('reason', 'protected-font') if isinstance(value, dict) else value)
    report_slots = []
    old_report = {}
    old_manifest = {}
    digest_cache = {}
    inventory_digest = hashlib.sha256(json.dumps(data['slots'], sort_keys=True,
                                               separators=(',', ':')).encode()).hexdigest()
    if requested is not None:
        try:
            old_report = json.loads((stage / '.luoshu-metrics-report.json').read_text())
        except (OSError, ValueError):
            pass
    try:
        old_manifest = json.loads((stage / '.luoshu-inventory-output-manifest.json').read_text())
    except (OSError, ValueError):
        pass
    reusable = set()
    if (requested is not None and source is None
            and old_manifest.get('schema') == 'inventory-font-output-v1'
            and old_manifest.get('inventory') == inventory_digest
            and old_manifest.get('anchors') == anchors_digest(store, digest_cache)):
        for logical, digest in old_manifest.get('files', {}).items():
            if logical not in data['slots']:
                continue
            path = safe_destination(stage, logical)
            if path.is_file() and file_digest(path, digest_cache) == digest:
                reusable.add(logical)
    with tempfile.TemporaryDirectory(prefix='inventory-stage-', dir=store) as directory:
        temporary = Path(directory)
        if mode == 'direct' and source is None:
            # Incremental coverage repair uses pinned source anchors from the
            # same staged payload. It never guesses a ROM filename as source.
            pool_mode = 'mix'
        else:
            pool_mode = mode
        pool = SourcePool(module, stage, pool_mode, source, temporary)
        if mode != 'mix':
            for face in pool.faces:
                face.role_weights = None
        jobs = {}
        for logical, slot in sorted(data['slots'].items()):
            if logical in preserved:
                continue
            faces = faces_for_slot(slot)
            if not faces:
                preserved[logical] = 'preserved-collection'
                continue
            selected = []
            for face in faces:
                contract = contract_for_face(face)
                src, weight, reason = pool.pick(face)
                if src is None:
                    preserved[logical] = reason if len(faces) == 1 else 'preserved-collection:' + reason
                    break
                weights = {int(ref.get('axes', {}).get('wght', ref.get('weight', weight)))
                           for ref in face.get('xmlReferences', [])}
                axes = face.get('supportedAxes') or []
                preserve_variable = bool(src.axes and ('wght' in axes or 'ital' in axes
                    or face.get('metrics', {}).get('variationAxes') or len(weights) > 1))
                if len(weights) > 1 and (not preserve_variable or 'wght' not in src.axes
                        or min(weights) < src.axes['wght'][0] or max(weights) > src.axes['wght'][2]):
                    preserved[logical] = 'source-variable-range-missing'
                    break
                selected.append((face, src, weight, contract, preserve_variable))
            if logical not in preserved:
                jobs[logical] = selected
        if not jobs:
            raise StageError('所选字体不支持当前任何系统槽位：' + ', '.join(sorted(set(preserved.values()))))

        def route(logical: str, face: dict) -> frozenset[int]:
            coverage = face['metrics']['coverage']
            if coverage['hanCount'] > int(0x3007 in coverage['cjkPunctuation']) or not coverage['hasLatin']:
                return frozenset()
            points = set()
            for target in face.get('fallbackTargets', []):
                for other, src, _weight, _contract, _variable in jobs.get(target, []):
                    cv = other['metrics']['coverage']
                    if cv['hanCount'] > int(0x3007 in cv['cjkPunctuation']):
                        points.update(cp for cp in src.points if is_cjk_routing_codepoint(cp))
            return frozenset(points)

        punctuation = {}
        for logical, selected in jobs.items():
            for face, src, weight, contract, variable in selected:
                routing = route(logical, face)
                if routing:
                    punctuation.setdefault((src.key, weight, variable, routing), set()).update(face['metrics']['coverage']['cjkPunctuation'])
        cache, compact, ink_bounds = {}, {}, {}
        prepared = []
        anchors = {}
        role_anchors = {}
        existing = 0
        rewritten = 0
        for logical, selected in jobs.items():
            destination = safe_destination(stage, logical)
            if requested is not None and logical not in requested and logical in reusable:
                existing += 1
                continue
            rewritten += int(destination.is_file())
            generated_faces = []
            for face, src, weight, contract, variable in selected:
                italic = bool(face['metrics'].get('fontTraits', {}).get('italic')
                              or face.get('style') in {'italic', 'oblique'})
                anchor = pool.materialize(src, weight, variable, italic)
                anchors[(src.key, weight, variable, italic)] = anchor
                if not italic and not src.mono:
                    role_anchors.setdefault(weight, anchor)
                routing = route(logical, face)
                stock_punctuation = frozenset(face['metrics']['coverage']['cjkPunctuation'])
                # Only routed non-Han faces can prove a compact Latin bitmap.
                align_bottom = bool(routing) and not face['metrics'].get('fontTraits', {}).get('monospaced', False)
                key = (src.key, weight, variable, italic, contract, routing, stock_punctuation, align_bottom)
                if key not in cache:
                    metric_source, removed = anchor, 0
                    if routing:
                        compact_key = (src.key, weight, variable, italic, routing)
                        if compact_key not in compact:
                            compact[compact_key] = compact_routed_source(anchor,
                                temporary / f'compact-{len(compact)}.font', routing,
                                frozenset(punctuation[(src.key, weight, variable, routing)]))
                        metric_source, removed = compact[compact_key]
                    output = temporary / f'metrics-{len(cache)}.font'
                    details = write_metrics(metric_source, output, contract, routing,
                        stock_punctuation, align_bitmap_bottom=align_bottom, ink_bounds_cache=ink_bounds)
                    with TTFont(output, lazy=True, recalcTimestamp=False) as verified:
                        for tag in ('head', 'hhea', 'OS/2', 'maxp'):
                            verified[tag]
                        # The source cmap was validated before writing; loading
                        # an unchanged CFF cmap here would decode 65k glyph
                        # names again for every alias contract. Check its SFNT
                        # header without reloading untouched outline tables.
                        cmap_header = verified.reader['cmap'][:4]
                        if len(cmap_header) != 4 or struct.unpack('>HH', cmap_header)[1] == 0:
                            raise StageError('生成的字体没有字符映射表')
                    details['removedCjkMappings'] += removed
                    cache[key] = output, details
                output, details = cache[key]
                generated_faces.append(output)
                report_slots.append({'slot': logical, 'faceIndex': face.get('faceIndex', 0),
                    'weight': weight, 'metricsSource': 'stock', 'hhea': list(contract[1:4]),
                    'variableAxesPreserved': pool.materialized_axes[anchor],
                    'sourceWeight': src.weight,
                    'compositeRoleWeights': src.role_weights or {},
                    'requestedVariableAxes': face.get('supportedAxes', []),
                    'typo': list(contract[4:7]), 'win': list(contract[7:9]),
                    'cjkRoutingSource': 'stock-fallback' if routing else 'source', **details})
            target_collection = (len(selected) > 1 or
                                 str(data['slots'][logical].get('format', '')).upper() in {'TTC', 'OTC'})
            if target_collection:
                output = temporary / f'collection-{len(prepared)}.font'
                collection = TTCollection()
                collection.fonts = [TTFont(path, lazy=True, recalcBBoxes=False,
                                           recalcTimestamp=False) for path in generated_faces]
                try:
                    collection.save(output, shareTables=True)
                finally:
                    collection.close()
                with TTCollection(output, lazy=True) as check:
                    if len(check.fonts) != len(selected):
                        raise StageError('生成的字体集合面数不一致')
            else:
                output = generated_faces[0]
            prepared.append((output, safe_destination(stage, logical)))

        # All generation has succeeded. Mutations affect only this isolated tree.
        for output, destination in prepared:
            link_copy(output, destination)
        for logical in old_manifest.get('files', {}):
            if logical not in jobs:
                safe_destination(stage, logical).unlink(missing_ok=True)
        font_roots = {root / 'fonts' for root in stage.iterdir()
                      if root.is_dir() and not root.is_symlink() and not root.name.startswith('.')}
        for field in ('sourceRoots', 'auxiliaryRoots', 'discoveredFontRoots'):
            for item in data.get(field, []):
                if isinstance(item, dict) and isinstance(item.get('logical'), str):
                    font_roots.add(safe_destination(stage, item['logical']))
        for fonts in font_roots:
            if not fonts.is_dir() or fonts.is_symlink():
                continue
            for path in fonts.rglob('*'):
                if '.luoshu-font-store' in path.parts or not (path.is_file() or path.is_symlink()):
                    continue
                logical = '/' + path.relative_to(stage).as_posix()
                font_file = path.suffix.lower() in EXTENSIONS - {'.font'}
                if not font_file and not path.is_symlink():
                    with path.open('rb') as stream:
                        font_file = stream.read(4) in (b'\x00\x01\x00\x00', b'OTTO', b'ttcf', b'true')
                if logical not in jobs and font_file:
                    path.unlink()
        for logical in preserved:
            safe_destination(stage, logical).unlink(missing_ok=True)
        if mode == 'direct':
            if source is not None:
                for old in store.glob('*.font'):
                    old.unlink()
                (store / '.luoshu-mix-source-weights.json').unlink(missing_ok=True)
            for anchor in anchors.values():
                link_copy(anchor, store / f'source-{file_digest(anchor, digest_cache)}.font')
            for weight, anchor in role_anchors.items():
                link_copy(anchor, store / f'wght-{weight}.font')
                if weight in ROLES:
                    link_copy(anchor, store / f'{ROLES[weight]}.font')
        preserved_text = ''.join(f'{path}\t{reason}\n' for path, reason in sorted(preserved.items()))
        (stage / '.luoshu-coverage-preserved.tsv').write_text(preserved_text, encoding='utf-8')
        (stage / '.luoshu-metrics-covered.lst').write_text(''.join(path + '\n' for path in sorted(jobs)), encoding='utf-8')
        summary = {'mapped': len(jobs), 'generated': len(cache), 'preserved': len(preserved),
                   'inventorySlots': len(data['slots']), 'sourceInstances': len(pool.materialized),
                   'fallbackSlots': 0, 'engineRevision': REVISION}
        summary.update({'mode': mode, 'font': family, 'inventory': len(data['slots']),
                        'requested': len(requested or []), 'matched': len(requested or []),
                        'planned': len(prepared), 'rewritten': rewritten,
                        'added': len(prepared) - rewritten, 'fallback': 0,
                        'existing': existing, 'failed': 0, 'degraded': False,
                        'seen': len(data['slots']), 'status': 'ok'})
        if old_report.get('engine') == 'inventory-font-stage-v1':
            newly_written = {row['slot'] for row in report_slots}
            report_slots += [row for row in old_report.get('slots', [])
                             if isinstance(row, dict) and row.get('slot') in jobs
                             and row['slot'] not in newly_written]
        report = {'schema': 'luoshu-slot-metrics-v1', 'engine': 'inventory-font-stage-v1',
                  'slots': report_slots, 'preservedFonts': preserved, 'summary': summary,
                  'preservedWeightAliases': [path for path, reason in preserved.items() if reason == 'source-weight-missing'],
                  'preservedDynamicAliases': [], 'preservedStockAliases': []}
        (stage / '.luoshu-metrics-report.json').write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
        (stage / '.luoshu-coverage-summary.conf').write_text(''.join(f'{key}={value}\n' for key, value in summary.items()))
        (stage / '.luoshu-coverage-remediation.conf').write_text(''.join(
            f'{key}={str(value).lower() if isinstance(value, bool) else str(value).replace(chr(10), " ").replace(chr(13), " ")}\n'
            for key, value in summary.items()))
        manifest = {'schema': 'inventory-font-output-v1', 'inventory': inventory_digest,
                    'anchors': anchors_digest(store, digest_cache),
                    'files': {logical: file_digest(safe_destination(stage, logical), digest_cache)
                              for logical in jobs}}
        (stage / '.luoshu-inventory-output-manifest.json').write_text(json.dumps(manifest, sort_keys=True))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', required=True, type=Path)
    parser.add_argument('--stage', type=Path)
    parser.add_argument('--mode', choices=('direct', 'mix'))
    parser.add_argument('--source', type=Path)
    parser.add_argument('--family', default='')
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--validate-inventory', action='store_true')
    args = parser.parse_args()
    try:
        if args.validate_inventory:
            data = load_inventory(args.module)
            for slot in data['slots'].values():
                for face in faces_for_slot(slot):
                    contract_for_face(face)
            print(json.dumps({'status': 'ready', 'slots': len(data['slots'])}))
        else:
            if args.stage is None or args.mode is None:
                parser.error('--stage 与 --mode 为必需参数')
            print(json.dumps(run(args.module, args.stage, args.mode, args.source, args.family, args.plan), ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f'通用字体生成失败：{exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
