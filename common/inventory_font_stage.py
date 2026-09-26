#!/usr/bin/env python3
"""Build an isolated font payload solely from measured device inventory.

No brand, model, family filename, or fixed list decides which system paths exist.
The scanner owns targets; actual source faces own weight/style/script capability.
"""
from __future__ import annotations

import argparse
import hashlib
from contextlib import ExitStack, closing
from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import struct
import sys
import tempfile

from fontTools.ttLib import TTCollection, TTFont
from fontTools.unicodedata import category, script
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.ttLib.tables.DefaultTable import DefaultTable

from font_metrics_normalize import _device_build_key
from font_slot_coverage import (preferred_unicode_codepoints, is_han,
                                is_cjk_routing_codepoint, is_cjk_punctuation, valid_coverage)
from inventory_font_metrics import compact_routed_source, write_metrics, link_copy, contract_for_face, restrict_unicode_scope
from inventory_stock_source import StockSourceResolver
from inventory_font_supplement import supplement, UnsupportedSupplementError

REVISION = 1
EXTENSIONS = {'.ttf', '.otf', '.ttc', '.otc', '.font'}
ROLES = {100: 'thin', 200: 'extralight', 300: 'light', 400: 'regular',
         500: 'medium', 600: 'semibold', 700: 'bold', 800: 'extrabold', 900: 'black'}
TARGET_ROLES = ('cjk', 'latin', 'digit')


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


def preservation_digest(path: Path, face_index: int, cache: dict) -> str:
    """Prove glyph/layout identity while allowing the metric edits we restore.

    Different paths with different hhea/head contracts can still contain the
    exact same outlines and shaping tables. Copying those raw tables already
    preserves every unselected script; no subset/merge is needed for them.
    """
    key = (identity(path), face_index)
    if key in cache:
        return cache[key]
    options = {'fontNumber': face_index} if face_index >= 0 else {}
    digest = hashlib.sha256()
    with TTFont(path, lazy=True, recalcTimestamp=False, **options) as font:
        for tag in sorted(font.reader.keys()):
            if tag in {'name', 'DSIG', 'FFTM'}:
                continue
            raw = bytearray(font.reader[tag])
            if tag == 'head':
                for start, end in ((8, 12), (20, 36), (38, 40), (42, 44)):
                    raw[start:end] = b'\0' * (end - start)
            elif tag == 'hhea':
                raw[4:10] = b'\0' * 6
            elif tag == 'OS/2' and len(raw) >= 78:
                selection = struct.unpack_from('>H', raw, 62)[0] & ~128
                struct.pack_into('>H', raw, 62, selection)
                raw[68:78] = b'\0' * 10
            digest.update(tag.encode('ascii')); digest.update(struct.pack('>I', len(raw))); digest.update(raw)
    cache[key] = digest.hexdigest()
    return cache[key]


def has_unicode_variations(path: Path, face_index: int, cache: dict) -> bool:
    key = ('uvs', identity(path), face_index)
    if key not in cache:
        options = {'fontNumber': face_index} if face_index >= 0 else {}
        with TTFont(path, lazy=True, recalcTimestamp=False, **options) as font:
            raw = font.reader['cmap']
            count = struct.unpack_from('>H', raw, 2)[0]
            cache[key] = any(struct.unpack_from('>H', raw, struct.unpack_from('>I', raw, 8 + 8 * index)[0])[0] == 14
                             for index in range(count))
    return cache[key]


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
            or data.get('scannerRevision') != 10 or data.get('metricsRevision') != 5
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


def character_role(point: int) -> str | None:
    if is_han(point) and point != 0x3007:
        return 'cjk'
    if 48 <= point <= 57 or 0xFF10 <= point <= 0xFF19:
        return 'digit'
    if category(chr(point)).startswith('L') and script(chr(point)) == 'Latn':
        return 'latin'
    return None


def slot_roles(target: dict) -> set[str]:
    metrics = target.get('metrics') or {}
    coverage, traits = metrics.get('coverage') or {}, metrics.get('fontTraits') or {}
    roles = set()
    if coverage.get('hanCount', 0) > int(0x3007 in coverage.get('cjkPunctuation', [])):
        roles.add('cjk')
    if coverage.get('hasLatin') or traits.get('letterScripts', {}).get('Latn', 0):
        roles.add('latin')
    if traits.get('digitCount', 0) or target.get('replacementRole') == 'digits':
        roles.add('digit')
    return roles


def replacement_points(source_points, stock_points, roles) -> frozenset[int]:
    roles = set(roles)
    result = set()
    for point in set(source_points).intersection(stock_points):
        role = character_role(point)
        if (role in roles or (roles and 32 <= point <= 126 and role is None)
                or ('cjk' in roles and is_cjk_punctuation(point))):
            result.add(point)
    return frozenset(result)


def replacement_counts(points) -> dict[str, int]:
    counts = dict.fromkeys(TARGET_ROLES, 0)
    for point in points:
        role = character_role(point)
        if role:
            counts[role] += 1
    return counts


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
        self.capabilities = {}
        for face in self.faces:
            points_by_role = {role: set() for role in TARGET_ROLES}
            for point in face.points:
                role = character_role(point)
                if role:
                    points_by_role[role].add(point)
            self.capabilities[face.key] = {role: frozenset(points)
                                           for role, points in points_by_role.items()}

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
        wanted = slot_roles(target)
        if not wanted:
            return None, weight, 'no-requested-text-role'
        italic = bool(traits.get('italic') or target.get('style') in {'italic', 'oblique'})
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
        def capable_roles(face):
            stock_points = target.get('_stockPoints')
            return {role for role in wanted if self.capabilities[face.key][role]
                    and (stock_points is None or not self.capabilities[face.key][role].isdisjoint(stock_points))}
        candidates = [face for face in candidates if capable_roles(face)]
        if not candidates:
            return None, weight, ('source-target-characters-missing' if '_stockPoints' in target
                                  else 'source-script-coverage-missing')
        def supported_roles(face):
            roles = capable_roles(face)
            if face.role_weights:
                return {role for role in roles if
                        face.role_weights.get(role + 'Weight', face.weight) == weight
                        or face.role_weights.get(role + 'Mode') == 'fixed'}
            if (face.axes.get('wght', (face.weight, face.weight, face.weight))[0]
                    <= weight <= face.axes.get('wght', (face.weight, face.weight, face.weight))[2]):
                return roles
            return set()
        eligible = [face for face in candidates if supported_roles(face)]
        if not eligible:
            return None, weight, 'source-weight-missing'
        # Exact static faces preserve designer interpolation. Otherwise a real
        # reachable axis instance is mandatory; never relabel Regular as Bold.
        best = min(eligible, key=lambda face: (-len(supported_roles(face)),
                                             bool(face.role_weights and face.role_weights.get('targetWeight') != weight),
                                             self.faces.index(face), bool(face.axes), face.weight != weight))
        target['_replacementRoles'] = sorted(supported_roles(best))
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
    if ((len(faces) > 1 or str(slot.get('format', '')).upper() in {'TTC', 'OTC'})
            and [face.get('faceIndex') for face in faces] != list(range(len(faces)))):
        raise StageError('字体集合面顺序无效')
    return [{**slot, **face} for face in faces]


def face_table_fingerprint(font: TTFont) -> dict[str, bytes]:
    """Compare SFNT contents across TTC packing without interpreting glyph names.

    All outline, layout, metadata, cmap and variation tables must stay identical.
    Packing a face into a collection only changes head.checkSumAdjustment.
    """
    result = {}
    for tag in font.reader.keys():
        raw = font.reader[tag]
        if tag == 'head':
            raw = raw[:8] + b'\0' * 4 + raw[12:]
        result[tag] = hashlib.sha256(raw).digest()
    return result


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
        if source is not None:
            raise StageError('补齐不能更换字体源，请先重新应用所选字体')
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
    repair_anchor_digest = ''
    if requested is not None:
        if (old_manifest.get('schema') != 'inventory-font-output-v1'
                or old_report.get('engine') != 'inventory-font-stage-v1'
                or not isinstance(old_manifest.get('files'), dict)
                or not isinstance(old_report.get('preservedFonts'), dict)):
            raise StageError('补齐缺少当前字体的完整校验记录，请重新应用字体')
        if old_manifest.get('inventory') != inventory_digest:
            raise StageError('字体清单已变化，补齐已取消，请重新应用字体')
        previous_mode = old_manifest.get('mode', old_report.get('summary', {}).get('mode'))
        if previous_mode != mode:
            raise StageError('补齐模式与当前字体不一致，已取消本次补齐')
        repair_anchor_digest = anchors_digest(store, digest_cache)
        if old_manifest.get('anchors') != repair_anchor_digest:
            raise StageError('当前字体源校验不一致，补齐已取消，请重新应用字体')
        # A repair is an incremental transaction. Reassessing every old slot
        # through a freshly reconstructed SourcePool used to turn four valid
        # outputs into "preserved" and delete them (15 mapped -> 11). Actual
        # verified files are authoritative outside the explicit repair set.
        for logical, digest in old_manifest.get('files', {}).items():
            if logical not in data['slots']:
                raise StageError('当前负载与字体清单不一致，已取消本次补齐')
            path = safe_destination(stage, logical)
            if logical in requested:
                continue
            if not path.is_file() or file_digest(path, digest_cache) != digest:
                raise StageError(f'未请求补齐的字体校验失败，需重新生成补齐计划：{logical}')
            reusable.add(logical)
        preserved = dict(old_report['preservedFonts'])
    with tempfile.TemporaryDirectory(prefix='inventory-stage-', dir=store) as directory, ExitStack() as resources:
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
        stock_sources = resources.enter_context(closing(StockSourceResolver(module, data)))
        preservation_cache, replacement_cache = {}, {}
        for logical, slot in sorted(data['slots'].items()):
            if requested is not None and logical not in requested:
                continue
            if requested is not None:
                preserved.pop(logical, None)
                if logical in (data.get('preservedFonts') or {}):
                    raise StageError(f'补齐目标是受保护的系统字体：{logical}')
            if logical in preserved:
                continue
            faces = faces_for_slot(slot)
            if not faces:
                preserved[logical] = 'preserved-collection'
                continue
            # A definitely unsupported optional file does not need its stock
            # view opened or hashed. Collections only need all original faces
            # when at least one face has a possible source replacement.
            candidates = [(face, *pool.pick(face)) for face in faces]
            if not any(src is not None for _face, src, _weight, _reason in candidates):
                reason = candidates[0][3]
                preserved[logical] = ('preserved-collection:' if len(faces) > 1 else '') + reason
                continue
            selected = []
            for face, src, weight, reason in candidates:
                # Source capability is the actual stock/source character
                # intersection, never a minimum alphabet or Han sample size.
                stock = stock_sources.resolve(logical, face)
                face['_stock'] = stock
                face['_stockPoints'] = stock.codepoints
                if len(faces) > 1 or str(slot.get('format', '')).upper() in {'TTC', 'OTC'}:
                    with stock.path.open('rb') as stream:
                        header = stream.read(12)
                    if (len(header) != 12 or header[:4] != b'ttcf'
                            or struct.unpack_from('>I', header, 8)[0] != len(faces)):
                        raise StageError('原厂字体集合面数与清单不一致，请重新扫描')
                    if selected and stock.digest != selected[0][0]['_stock'].digest:
                        raise StageError('原厂字体集合各面来自不同文件，请重新扫描')
                if src is not None:
                    src, weight, reason = pool.pick(face)
                if src is None:
                    face['_retainedReason'] = reason
                    selected.append((face, None, weight, None, False))
                    continue
                contract = contract_for_face(face)
                replacement_key = (src.key, stock.codepoints, tuple(face['_replacementRoles']))
                if replacement_key not in replacement_cache:
                    points = replacement_points(src.points, stock.codepoints, face['_replacementRoles'])
                    replacement_cache[replacement_key] = points, replacement_counts(points)
                points, counts = replacement_cache[replacement_key]
                if not sum(counts.values()):
                    face['_retainedReason'] = 'source-target-characters-missing'
                    selected.append((face, None, weight, contract, False))
                    continue
                face['_replacePoints'] = points
                face['_replaceCounts'] = counts
                same_face = (file_digest(src.path, digest_cache) == stock.digest
                             and max(src.index, 0) == max(stock.face_index, 0))
                preserve_variants = has_unicode_variations(stock.path, stock.face_index, preservation_cache)
                if not same_face and (stock.codepoints - points or preserve_variants):
                    same_face = (preservation_digest(src.path, src.index, preservation_cache)
                                 == preservation_digest(stock.path, stock.face_index, preservation_cache))
                # A full raw donor is valid only when every original character
                # is covered and no unselected script/symbol is overwritten.
                # Identical original faces are already proof of preservation.
                needs_supplement = not same_face and bool(stock.codepoints - points or preserve_variants)
                face['_needsSupplement'] = needs_supplement
                face['_resultPoints'] = stock.codepoints
                weights = {int(ref.get('axes', {}).get('wght', ref.get('weight', weight)))
                           for ref in face.get('xmlReferences', [])}
                axes = face.get('supportedAxes') or []
                preserve_variable = bool(src.axes and ('wght' in axes or 'ital' in axes
                    or face.get('metrics', {}).get('variationAxes') or len(weights) > 1))
                fixed_roles = bool(src.role_weights) and all(
                    src.role_weights.get(role + 'Mode') == 'fixed'
                    for role in face['_replacementRoles'])
                dynamic_weight = ('wght' in axes or 'wght' in face.get('metrics', {}).get('variationAxes', {})
                                  or len(weights) > 1)
                auto_composite = bool(src.role_weights) and not fixed_roles
                if not fixed_roles and ((len(weights) > 1 and (not preserve_variable or 'wght' not in src.axes
                        or min(weights) < src.axes['wght'][0] or max(weights) > src.axes['wght'][2]))
                        or (auto_composite and dynamic_weight and 'wght' not in src.axes)):
                    face['_retainedReason'] = 'source-variable-range-missing'
                    selected.append((face, None, weight, contract, False))
                    continue
                selected.append((face, src, weight, contract, preserve_variable))
            if any(src is not None for _face, src, *_rest in selected):
                jobs[logical] = selected
            else:
                reason = selected[0][0]['_retainedReason']
                preserved[logical] = ('preserved-collection:' if len(faces) > 1 else '') + reason
        if requested is not None and set(jobs) != requested:
            reasons = ', '.join(f'{path}: {preserved.get(path, "source-unavailable")}'
                                for path in sorted(requested - jobs.keys()))
            raise StageError('所选字体无法完成请求的补齐，已保留原负载：' + reasons)
        if not jobs:
            raise StageError('所选字体不支持当前任何系统槽位：' + ', '.join(sorted(set(preserved.values()))))

        # Prepare actual character-preserving sources before resolving routes.
        # An unsupported optional collection must never prove CJK reachability.
        supplemented, scoped, anchors, role_anchors = {}, {}, {}, {}
        for logical, selected in list(jobs.items()):
            for index, (face, src, weight, contract, variable) in enumerate(selected):
                if src is None:
                    continue
                try:
                    italic = bool(face['metrics'].get('fontTraits', {}).get('italic')
                                  or face.get('style') in {'italic', 'oblique'})
                    anchor = pool.materialize(src, weight, variable, italic)
                    stock = face['_stock']
                    stock_content = preservation_digest(stock.path, stock.face_index, preservation_cache)
                    patch_key = (src.key, weight, variable, italic, stock_content, face['_replacePoints'])
                    metric_anchor = anchor
                    supplement_report = {'replacedCodepoints': len(face['_replacePoints']),
                                         'retainedStockCodepoints': len(stock.codepoints - face['_replacePoints']),
                                         'mode': 'raw-full-coverage'}
                    if face['_needsSupplement']:
                        stock.verify_unchanged()
                        if patch_key not in supplemented:
                            patched = temporary / f'supplement-{len(supplemented)}.font'
                            patch_report = supplement(anchor, stock.path, patched,
                                stock_face_index=stock.face_index, stock_weight=weight,
                                replace_codepoints=set(face['_replacePoints']))
                            stock.verify_unchanged()
                            with TTFont(patched, lazy=True, recalcTimestamp=False) as patched_font:
                                patch_axes = {axis.axisTag for axis in patched_font['fvar'].axes} if 'fvar' in patched_font else set()
                                if variable and not set(pool.materialized_axes[anchor]).issubset(patch_axes):
                                    raise StageError('原厂字符补齐未能保留动态字体轴，已取消本次应用')
                                if not stock.codepoints.issubset(preferred_unicode_codepoints(patched_font)):
                                    raise StageError('原厂字符补齐丢失字符，已取消本次应用')
                            supplemented[patch_key] = patched, patch_report
                        metric_anchor, supplement_report = supplemented[patch_key]
                    elif src.points - stock.codepoints:
                        scope_key = (str(anchor), stock.codepoints)
                        if scope_key not in scoped:
                            scoped[scope_key] = restrict_unicode_scope(anchor,
                                temporary / f'scoped-{len(scoped)}.font', stock.codepoints)
                        metric_anchor = scoped[scope_key]
                    face.update(_anchor=anchor, _metricAnchor=metric_anchor,
                                _supplementReport=supplement_report, _patchKey=patch_key, _italic=italic)
                except UnsupportedSupplementError:
                    face['_retainedReason'] = ('source-variable-supplement-unavailable' if variable
                                               else 'source-supplement-capability-missing')
                    selected[index] = (face, None, weight, contract, False)
            if not any(src is not None for _face, src, *_rest in selected):
                reason = selected[0][0]['_retainedReason']
                if requested is not None:
                    raise StageError(f'所选字体无法完成请求的补齐，已保留原负载：{logical}: {reason}')
                preserved[logical] = ('preserved-collection:' if len(selected) > 1 else '') + reason
                del jobs[logical]
        if not jobs:
            raise StageError('所选字体不支持当前任何系统槽位：' + ', '.join(sorted(set(preserved.values()))))

        existing_fallback_points = {}

        def verified_fallback_points(target: str) -> frozenset[int]:
            if target not in existing_fallback_points:
                points = set()
                path = safe_destination(stage, target)
                with path.open('rb') as stream:
                    collection = stream.read(4) == b'ttcf'
                for face in faces_for_slot(data['slots'][target]):
                    coverage = face['metrics']['coverage']
                    if coverage['hanCount'] <= int(0x3007 in coverage['cjkPunctuation']):
                        continue
                    kwargs = {'fontNumber': face.get('faceIndex', 0)} if collection else {}
                    with TTFont(path, lazy=True, recalcTimestamp=False, **kwargs) as font:
                        points.update(cp for cp in preferred_unicode_codepoints(font)
                                      if is_cjk_routing_codepoint(cp))
                existing_fallback_points[target] = frozenset(points)
            return existing_fallback_points[target]

        def route(logical: str, face: dict) -> frozenset[int]:
            coverage = face['metrics']['coverage']
            if coverage['hanCount'] > int(0x3007 in coverage['cjkPunctuation']) or not coverage['hasLatin']:
                return frozenset()
            points = set()
            for target in face.get('fallbackTargets', []):
                if target in reusable:
                    points.update(verified_fallback_points(target))
                for other, src, _weight, _contract, _variable in jobs.get(target, []):
                    if src is None:
                        continue
                    cv = other['metrics']['coverage']
                    if cv['hanCount'] > int(0x3007 in cv['cjkPunctuation']):
                        points.update(cp for cp in other['_resultPoints'] if is_cjk_routing_codepoint(cp))
            return frozenset(points)

        punctuation = {}
        for logical, selected in jobs.items():
            for face, src, weight, contract, variable in selected:
                if src is None:
                    continue
                routing = route(logical, face)
                if routing:
                    punctuation.setdefault((src.key, weight, variable, routing), set()).update(face['metrics']['coverage']['cjkPunctuation'])
        cache, compact, ink_bounds = {}, {}, {}
        prepared = []
        existing = len(reusable)
        rewritten = 0
        for logical, selected in jobs.items():
            destination = safe_destination(stage, logical)
            rewritten += int(destination.is_file())
            generated_faces = []
            for face, src, weight, contract, variable in selected:
                if src is None:
                    stock = face['_stock']
                    stock.verify_unchanged()
                    generated_faces.append((stock.path, stock.face_index))
                    report_slots.append({'slot': logical, 'faceIndex': face.get('faceIndex', 0),
                        'state': 'retained-stock', 'reason': face['_retainedReason'],
                        'weight': face.get('weight', face['metrics'].get('weightClass', weight)),
                        'replacedRoleCounts': {}, 'replacedRoles': [], 'replacedCodepoints': 0,
                        'retainedTargetRoleCounts': replacement_counts(stock.codepoints),
                        'retainedStockCodepoints': len(stock.codepoints),
                        'stockSourceVerifiedBy': stock.verified_by})
                    continue
                italic = face['_italic']
                anchor = face['_anchor']
                anchors[(src.key, weight, variable, italic)] = anchor
                if not italic and not src.mono:
                    role_anchors.setdefault(weight, anchor)
                routing = route(logical, face)
                stock_punctuation = frozenset(face['metrics']['coverage']['cjkPunctuation'])
                align_bottom = bool(routing) and not face['metrics'].get('fontTraits', {}).get('monospaced', False)
                stock = face['_stock']
                patch_key = face['_patchKey']
                metric_anchor = face['_metricAnchor']
                supplement_report = face['_supplementReport']
                key = (str(metric_anchor),
                       contract, routing, stock_punctuation, align_bottom)
                if key not in cache:
                    metric_source, removed = metric_anchor, 0
                    if routing:
                        compact_key = (str(metric_anchor), routing)
                        if compact_key not in compact:
                            compact[compact_key] = compact_routed_source(metric_anchor,
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
                generated_faces.append((output, -1))
                report_slots.append({'slot': logical, 'faceIndex': face.get('faceIndex', 0),
                    'state': 'replaced',
                    'weight': weight, 'metricsSource': 'stock', 'hhea': list(contract[1:4]),
                    'variableAxesPreserved': pool.materialized_axes[anchor],
                    'sourceWeight': src.weight,
                    'replacedRoles': [role for role, count in face['_replaceCounts'].items() if count],
                    'replacedRoleCounts': face['_replaceCounts'],
                    'retainedTargetRoleCounts': replacement_counts(stock.codepoints - face['_replacePoints']),
                    'replacedCodepoints': supplement_report['replacedCodepoints'],
                    'retainedStockCodepoints': supplement_report['retainedStockCodepoints'],
                    'supplemented': bool(face['_needsSupplement']),
                    'stockSourceVerifiedBy': stock.verified_by,
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
                                           recalcTimestamp=False, fontNumber=index)
                                    for path, index in generated_faces]
                fingerprints = [face_table_fingerprint(font) for font in collection.fonts]
                try:
                    collection.save(output, shareTables=True)
                finally:
                    collection.close()
                with TTCollection(output, lazy=True) as check:
                    if len(check.fonts) != len(selected):
                        raise StageError('生成的字体集合面数不一致')
                    if [face_table_fingerprint(font) for font in check.fonts] != fingerprints:
                        raise StageError('生成的字体集合面顺序或原始数据表发生变化')
                for face, src, *_rest in selected:
                    face['_stock'].verify_unchanged()
            else:
                output = generated_faces[0][0]
            prepared.append((output, safe_destination(stage, logical)))

        mapped_paths = set(jobs) | reusable
        # A digit clock or peripheral Latin face cannot mask a failed primary
        # Chinese face. Require each role the chosen sources can actually offer.
        candidates, primary = set(), set()
        for logical, slot in data['slots'].items():
            traits = slot.get('metrics', {}).get('fontTraits', {})
            if (not slot_roles(slot).intersection({'cjk', 'latin'})
                    or slot.get('style', 'normal') != 'normal' or traits.get('italic')
                    or int(slot.get('weight', slot.get('metrics', {}).get('weightClass', 400))) != 400):
                continue
            candidates.add(logical)
            if set(slot.get('families') or []).intersection({'sans-serif', 'system-ui', 'default'}):
                primary.add(logical)
        main_path = data.get('mainSlotPath')
        if main_path in candidates:
            primary.add(main_path)
        primary = primary or candidates
        for logical in tuple(primary):
            for face in faces_for_slot(data['slots'][logical]):
                primary.update(target for target in face.get('fallbackTargets', []) if target in candidates)
        available_roles = set()
        for source_face in pool.faces:
            if source_face.color:
                continue
            available_roles.update(role for role in ('cjk', 'latin')
                                   if pool.capabilities[source_face.key][role])
        mapped_roles = {}
        for row in report_slots:
            mapped_roles.setdefault(row['slot'], set()).update(
                role for role, count in row['replacedRoleCounts'].items() if count)
        previous_rows = {}
        for row in old_report.get('slots', []):
            if isinstance(row, dict):
                previous_rows.setdefault(row.get('slot'), []).append(row)
        for logical in primary.intersection(reusable):
            rows = previous_rows.get(logical, [])
            if rows and all(isinstance(row.get('replacedRoleCounts'), dict) for row in rows):
                mapped_roles[logical] = {role for row in rows for role, count in row['replacedRoleCounts'].items() if count}
            else:
                # Test5 proofs predate role counts. Verify the existing output's
                # real cmap before retaining that generation's primary coverage.
                points = set().union(*(face.points for face in inspect_faces(safe_destination(stage, logical))))
                mapped_roles[logical] = set()
                if any(is_han(cp) for cp in points):
                    mapped_roles[logical].add('cjk')
                if all(cp in points for cp in (*range(65, 91), *range(97, 123))):
                    mapped_roles[logical].add('latin')
        demanded = {role for logical in primary for role in slot_roles(data['slots'][logical])
                    if role in available_roles and role in {'cjk', 'latin'}}
        missing_roles = {role for role in demanded
                         if not any(role in mapped_roles.get(logical, set()) for logical in primary)}
        if main_path in primary:
            missing_roles.update(slot_roles(data['slots'][main_path]).intersection(available_roles, {'cjk', 'latin'})
                                 - mapped_roles.get(main_path, set()))
            # A replacement of an unrelated TTC face must not hide a retained
            # main UI face, even when both happen to contain the same script.
            main_slot = data['slots'][main_path]
            main_index = main_slot.get('faceIndex', 0)
            main_rows = [row for row in (previous_rows.get(main_path, []) if main_path in reusable else report_slots)
                         if row.get('slot') == main_path and row.get('faceIndex', 0) == main_index]
            if main_rows and all(isinstance(row.get('replacedRoleCounts'), dict) for row in main_rows):
                main_roles = {role for row in main_rows for role, count in row.get('replacedRoleCounts', {}).items() if count}
                missing_roles.update(slot_roles(main_slot).intersection(available_roles, {'cjk', 'latin'}) - main_roles)
        primary_replaced = {logical for logical in primary
                            if mapped_roles.get(logical, set()).intersection({'cjk', 'latin'})}
        if missing_roles or (primary and not primary_replaced):
            detail = ','.join(sorted(missing_roles)) or 'text'
            raise StageError('主要中文或英文字体尚未替换，已取消本次应用并保留原字体：' + detail)
        # Recheck evidence immediately before mutation. A source/other output
        # changing during generation cancels this isolated repair altogether.
        if requested is not None:
            if anchors_digest(store, digest_cache) != repair_anchor_digest:
                raise StageError('补齐期间字体源发生变化，已取消本次补齐')
            for logical in reusable:
                if file_digest(safe_destination(stage, logical), digest_cache) != old_manifest['files'][logical]:
                    raise StageError('补齐期间现有字体发生变化，已取消本次补齐')
            current_rows = {(row['slot'], row.get('faceIndex', 0)): row for row in report_slots}
            for logical in requested:
                for previous in previous_rows.get(logical, []):
                    current = current_rows.get((logical, previous.get('faceIndex', 0)), {})
                    counts = current.get('replacedRoleCounts', {})
                    if any(count > counts.get(role, 0)
                           for role, count in previous.get('replacedRoleCounts', {}).items()):
                        raise StageError(f'补齐减少了字体集合已有的字形替换，已保留原负载：{logical}')
        # All generation has succeeded. Mutations affect only this isolated tree.
        for output, destination in prepared:
            link_copy(output, destination)
        if requested is None:
            for logical in old_manifest.get('files', {}):
                if logical not in jobs:
                    safe_destination(stage, logical).unlink(missing_ok=True)
        font_roots = {root / 'fonts' for root in stage.iterdir()
                      if root.is_dir() and not root.is_symlink() and not root.name.startswith('.')}
        for field in ('sourceRoots', 'auxiliaryRoots', 'discoveredFontRoots'):
            for item in data.get(field, []):
                if isinstance(item, dict) and isinstance(item.get('logical'), str):
                    font_roots.add(safe_destination(stage, item['logical']))
        for fonts in font_roots if requested is None else ():
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
        if requested is None:
            for logical in preserved:
                safe_destination(stage, logical).unlink(missing_ok=True)
        if mode == 'direct' and requested is None:
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
        (stage / '.luoshu-metrics-covered.lst').write_text(''.join(path + '\n' for path in sorted(mapped_paths)), encoding='utf-8')
        summary = {'mapped': len(mapped_paths), 'generated': len(cache), 'preserved': len(preserved),
                   'inventorySlots': len(data['slots']), 'sourceInstances': len(pool.materialized),
                   'fallbackSlots': 0, 'engineRevision': REVISION}
        summary.update({'supplementedSources': len(supplemented),
                        'primaryTextMapped': len(primary_replaced)})
        summary.update({'mode': mode, 'operation': 'repair' if requested is not None else 'apply',
                        'font': family, 'inventory': len(data['slots']),
                        'requested': len(requested or []), 'matched': len(requested or []),
                        'planned': len(prepared), 'rewritten': rewritten,
                        'added': len(prepared) - rewritten, 'fallback': 0,
                        'existing': existing, 'failed': 0, 'degraded': False,
                        'seen': len(data['slots']), 'status': 'ok'})
        if old_report.get('engine') == 'inventory-font-stage-v1':
            newly_written = {row['slot'] for row in report_slots}
            report_slots += [row for row in old_report.get('slots', [])
                             if isinstance(row, dict) and row.get('slot') in mapped_paths
                             and row['slot'] not in newly_written]
        report = {'schema': 'luoshu-slot-metrics-v1', 'engine': 'inventory-font-stage-v1',
                  'slots': report_slots, 'preservedFonts': preserved, 'summary': summary,
                  'partialSlots': sorted({row['slot'] for row in report_slots
                                          if row.get('state') == 'retained-stock'
                                          or any(row.get('retainedTargetRoleCounts', {}).values())}),
                  'preservedWeightAliases': [path for path, reason in preserved.items() if reason == 'source-weight-missing'],
                  'preservedDynamicAliases': [], 'preservedStockAliases': []}
        (stage / '.luoshu-metrics-report.json').write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
        (stage / '.luoshu-coverage-summary.conf').write_text(''.join(f'{key}={value}\n' for key, value in summary.items()))
        (stage / '.luoshu-coverage-remediation.conf').write_text(''.join(
            f'{key}={str(value).lower() if isinstance(value, bool) else str(value).replace(chr(10), " ").replace(chr(13), " ")}\n'
            for key, value in summary.items()))
        manifest = {'schema': 'inventory-font-output-v1', 'inventory': inventory_digest, 'mode': mode,
                    'anchors': anchors_digest(store, digest_cache),
                    'files': {logical: file_digest(safe_destination(stage, logical), digest_cache)
                              for logical in mapped_paths}}
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
