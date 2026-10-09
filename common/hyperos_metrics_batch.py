#!/usr/bin/env python3
"""Build HyperOS physical aliases in one process, without recompiling glyph outlines.

Only isolated staging trees may be passed here. Source anchors are pinned before any
alias is replaced, so neither iteration order nor a second partition changes inputs.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile

from fontTools.ttLib import TTFont
from fontTools import subset
from font_metrics_normalize import _device_build_key, _pick_face, _promote_os2_for_typo_metrics
from font_inventory import (LOGICAL_FONT_ROOTS, _generic_font_name_candidate,
                            _generic_text_slot_candidate, _heuristic_candidate,
                            _numeric_display_slot_candidate)
from font_inventory_scan import _is_ui_family, _safe_dynamic_partition_name
from font_slot_coverage import (is_han, is_cjk_routing_codepoint, remove_cjk_mappings,
                                preferred_unicode_codepoints, valid_coverage)
from hyperos_physical_policy import preserved_dynamic_alias, safe_physical_font_name

PARTS = ("system", "system_ext", "product", "mi_ext", "vendor", "odm", "oem",
         "my_product", "hw_product", "cust")


def weight_for_name(name: str) -> int:
    stem = Path(name).stem.lower()
    if stem.isdigit() and 100 <= int(stem) <= 900:
        return int(stem)
    for terms, weight in ((('extrabold', 'extra-bold'), 800),
                          (('semibold', 'semi-bold', 'demibold'), 600),
                          (('extralight', 'extra-light'), 200),
                          (('black', 'heavy'), 900), (('bold',), 700),
                          (('medium',), 500), (('light',), 300), (('thin',), 100)):
        if any(term in stem for term in terms):
            return weight
    return 400


def nonempty(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def pick_source(fonts: Path, name: str) -> Path:
    weight = weight_for_name(name)
    store = fonts / '.luoshu-font-store'
    # Numeric and exact aliases carry the actual multiweight selection. Do not
    # replace every weight with regular just because a regular anchor exists.
    candidates = (fonts / f'LuoShu-{weight}.ttf', store / f'wght-{weight}.font',
                  fonts / f'{weight}.ttf', fonts / name,
                  store / 'mix-composite.font', store / 'regular.font',
                  store / 'compact-regular.font', fonts / '400.ttf',
                  fonts / 'MiSansVF.ttf', fonts / 'Roboto-Regular.ttf')
    for path in candidates:
        if nonempty(path):
            return path
    raise ValueError(f'没有可用的源字体：{name}')


def inventory_font_roots(module: Path) -> dict[str, Path]:
    """Canonical stock roots plus the scanner's safe partition manifest."""
    roots = dict(LOGICAL_FONT_ROOTS)
    try:
        partitions = (module / 'config/device_font_partitions.conf').read_text().splitlines()
    except OSError:
        partitions = []
    for partition in partitions:
        if _safe_dynamic_partition_name(partition):
            roots[partition] = Path('/') / partition / 'fonts'
    return roots


def inventory_completion_slot(slot: object, logical: str) -> bool:
    """Reuse stock scan evidence without widening the physical name policy."""
    if not isinstance(slot, dict) or slot.get('path', logical) != logical:
        return False
    name = Path(logical).name
    # A single-face donor cannot preserve a collection's other face references.
    metrics = slot.get('metrics', {})
    # A measured digit/display face (e.g. a "clock" numeral font) is the one
    # exception to the generic name deny list. Admission uses the stock face's
    # own coverage evidence, whichever scan pass (XML/heuristic/verified) found it.
    numeric = _numeric_display_slot_candidate(name, metrics)
    if (Path(name).suffix.lower() not in {'.ttf', '.otf'} or
            slot.get('format') in {'TTC', 'OTC'} or slot.get('faceIndex', 0) != 0 or
            slot.get('style', 'normal') != 'normal' or
            not (_generic_font_name_candidate(name) or numeric)):
        return False
    if numeric:
        return True
    families = slot.get('families', [])
    return (_heuristic_candidate(name) or
            (isinstance(families, list) and any(
                isinstance(family, str) and _is_ui_family(family) for family in families)) or
            (slot.get('source') == 'verified-scan' and
             _generic_text_slot_candidate(name, metrics)))


def inventory_completion_source(fonts: Path, slot: dict, name: str) -> Path:
    """Honor the inventory weight even when an OEM filename omits its style."""
    weight = slot.get('weight', weight_for_name(name))
    if type(weight) is not int or not 1 <= weight <= 1000:
        weight = weight_for_name(name)
    role = {100: 'thin', 200: 'extralight', 300: 'light', 400: 'regular',
            500: 'medium', 600: 'semibold', 700: 'bold', 800: 'extrabold', 900: 'black'}.get(weight)
    store = fonts / '.luoshu-font-store'
    candidates = [store / f'wght-{weight}.font', fonts / f'LuoShu-{weight}.ttf']
    if role:
        candidates.append(store / f'{role}.font')
    candidates.extend((fonts / f'{weight}.ttf', fonts / name,
                       store / 'mix-composite.font', store / 'regular.font',
                       store / 'compact-regular.font', fonts / '400.ttf',
                       fonts / 'MiSansVF.ttf', fonts / 'Roboto-Regular.ttf'))
    for path in candidates:
        if nonempty(path):
            return path
    raise ValueError(f'没有可用的源字体：{name}')


def inventory_completion_jobs(module: Path, stage: Path, inventory: dict, seen: set) -> list:
    """Complete only trusted, real, nonsymlink stock slots in isolated staging."""
    indexed = inventory.get('slots', {})
    if not isinstance(indexed, dict):
        return []
    resolved = stage.resolve()
    roots = inventory_font_roots(module)
    jobs = []
    for logical, slot in sorted(indexed.items()):
        if (not isinstance(logical, str) or logical in seen or
                preserved_dynamic_alias(inventory, logical) or
                not inventory_completion_slot(slot, logical)):
            continue
        parts = Path(logical).parts
        if (len(parts) != 4 or parts[0] != '/' or parts[2] != 'fonts' or parts[1] not in roots
                or str(Path(logical)) != logical or parts[3] in {'.', '..'}):
            continue
        partition, name = parts[1], parts[3]
        contract = contract_for_slot(inventory, logical)
        if contract[-1] != 'stock':
            continue
        stock_root = Path(os.environ.get(f'LUOSHU_{partition.upper()}_FONTS_ROOT', str(roots[partition])))
        stock = stock_root / name
        if not stock.is_file() or stock.is_symlink():
            continue
        destination = stage / partition / 'fonts' / name
        if resolved not in destination.parent.resolve().parents:
            raise ValueError('字体暂存槽位指向隔离目录之外')
        jobs.append((inventory_completion_source(stage / 'system/fonts', slot, name), destination, contract))
    return jobs


def read_inventory(module: Path) -> dict:
    try:
        data = json.loads((module / 'config/device_font_inventory.json').read_text())
        build = _device_build_key()
        if (data.get('schema') != 'device-font-inventory-v1' or
                data.get('state') != 'ready' or data.get('inventoryRevision') != 1 or
                (build and data.get('buildKey') != build)):
            return {}
        return data
    except (OSError, ValueError, AttributeError):
        return {}


def contract_for_slot(data: dict, logical: str) -> tuple:
    """Cache line metrics and the stock Skia top/bottom layout frame separately."""
    try:
        slot = (data.get('slots') or {}).get(logical, {})
        metrics = slot.get('metrics', {})
        upem = int(metrics['upem'])
        hhea = metrics['hhea']
        ascent, descent = int(hhea['ascent']), int(hhea['descent'])
        gap = int(hhea.get('lineGap', 0))
        if not (16 <= upem <= 16384 and 0 < ascent <= 32767 and
                -32768 <= descent <= 0 and 0 <= gap <= 32767):
            raise ValueError('invalid stock line metrics')
        os2 = metrics.get('os2', {})
        typo = (int(os2.get('typoAscender', ascent)),
                int(os2.get('typoDescender', descent)),
                int(os2.get('typoLineGap', gap)))
        win = (int(os2.get('winAscent', ascent)), int(os2.get('winDescent', -descent)))
        use_typo = bool(int(os2.get('fsSelection', 0)) & 128)
        if not (typo[0] > 0 and typo[1] <= 0 and typo[2] >= 0):
            if use_typo:
                raise ValueError('invalid stock typo metrics')
            typo = (ascent, descent, gap)
        values = (ascent, descent, gap, *typo, *win)
        if any(abs(v) > 4 * upem for v in values) or min(win) < 0:
            raise ValueError('invalid stock metrics')
        # Skia/FreeType reads SFNT head for top/bottom, independently of hhea
        # and OS/2. Old inventories have no head: retain their line contract,
        # but explicitly report that the padded layout frame remains unaligned.
        frame = None
        head = metrics.get('head', {})
        try:
            ymin, ymax = int(head['yMin']), int(head['yMax'])
            if -32768 <= ymin < ymax <= 32767 and ymax > 0:
                frame = (ymin, ymax)
        except (KeyError, TypeError, ValueError):
            pass
        return (upem, *values, use_typo, frame, 'stock')
    except (KeyError, TypeError, ValueError, ZeroDivisionError, AttributeError):
        # Older installations can lack a trustworthy inventory. Keep the known
        # compact fallback explicit in the report; never read the mounted overlay
        # as stock and never silently use an unnormalized raw font on errors.
        return (1000, 980, -300, 0, 980, -300, 0, 980, 350, True, None, 'fallback')


def _latin_ink_bottom(font: TTFont) -> int | None:
    """Bound Latin descenders without scanning or recompiling CJK outlines."""
    if 'fvar' in font:
        return None  # Default-axis bounds cannot prove other variable instances.
    cmap = font.getBestCmap() or {}
    names = {name for cp, name in cmap.items()
             if 0x20 <= cp <= 0x24f or 0x300 <= cp <= 0x36f}
    if not names:
        return None
    bottom = 0
    if 'glyf' in font:
        offsets, raw = font['loca'].locations, font.reader['glyf']
        for name in names:
            gid = font.getGlyphID(name)
            start, end = offsets[gid], offsets[gid + 1]
            if start == end:
                continue
            if not 0 <= start <= end - 10 <= len(raw) - 10:
                raise ValueError('invalid glyph header')
            bottom = min(bottom, struct.unpack_from('>hhhhh', raw, start)[2])
    else:
        from fontTools.pens.boundsPen import BoundsPen
        glyphs = font.getGlyphSet()
        for name in names:
            pen = BoundsPen(glyphs)
            glyphs[name].draw(pen)
            if pen.bounds is not None:
                bottom = min(bottom, pen.bounds[1])
    return bottom


def compact_routed_source(source: Path, output: Path, routing: frozenset[int],
                          stock_punctuation: frozenset[int]) -> tuple[Path, int]:
    """Drop unreachable CJK outlines once per donor, before per-slot metrics.

    Cmap-only removal left the entire donor in every Latin alias. Keep all
    remaining mappings, variation sequences and layout closure; CJK coverage is
    removed only where the staged fallback has already proved it can serve it.
    """
    face = _pick_face(source)
    kwargs = {'fontNumber': face} if face >= 0 else {}
    with TTFont(source, lazy=True, recalcBBoxes=False, recalcTimestamp=False, **kwargs) as font:
        removed = remove_cjk_mappings(font, routing, stock_punctuation)
        if not removed:
            return source, 0
        points = set()
        glyphs = set()
        for table in font['cmap'].tables:
            if table.format == 14:
                points.update(table.uvsDict)
                points.update(cp for entries in table.uvsDict.values() for cp, _ in entries)
                glyphs.update(name for entries in table.uvsDict.values()
                              for _, name in entries if name is not None)
            elif table.isUnicode():
                points.update(table.cmap)
            else:
                glyphs.update(table.cmap.values())
        options = subset.Options()
        options.legacy_cmap = True
        options.symbol_cmap = True
        options.name_IDs = ['*']
        options.name_languages = ['*']
        options.name_legacy = True
        options.layout_features = ['*']
        options.glyph_names = True
        options.notdef_outline = True
        worker = subset.Subsetter(options=options)
        worker.populate(unicodes=points, glyphs=glyphs)
        worker.subset(font)
        font.save(output, reorderTables=False)
    return output, removed


def write_metrics(source: Path, output: Path, contract: tuple,
                  cjk_fallback_codepoints: frozenset[int] | None = None,
                  stock_cjk_punctuation: frozenset[int] = frozenset(), *,
                  align_bitmap_bottom: bool = False) -> dict:
    # lazy + recalcBBoxes=False retains glyf/CFF/gvar as raw tables. Loading glyph
    # bounds just to change hhea/OS2 used to recompile entire CJK fonts per slot.
    face = _pick_face(source)
    options = {'fontNumber': face} if face >= 0 else {}
    with source.open('rb') as stream, TTFont(
            stream, lazy=True, recalcBBoxes=False, recalcTimestamp=False, **options) as font:
        head, hhea, os2 = font['head'], font['hhea'], font['OS/2']
        upem = int(head.unitsPerEm)
        if not 16 <= upem <= 16384:
            raise ValueError('源字体 unitsPerEm 无效')
        scale = upem / contract[0]
        values = [round(v * scale) for v in contract[1:9]]
        if any(not -32768 <= v <= 32767 for v in values[:6]):
            raise ValueError('原厂度量超出源字体数值范围')
        if any(not 0 <= v <= 65535 for v in values[6:]):
            raise ValueError('原厂 Win 度量超出源字体数值范围')
        hhea.ascent, hhea.descent, hhea.lineGap = values[:3]
        _promote_os2_for_typo_metrics(os2)
        (os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap,
         os2.usWinAscent, os2.usWinDescent) = values[3:]
        os2.fsSelection = (os2.fsSelection & ~128) | (128 if contract[9] else 0)
        source_frame = (int(head.yMin), int(head.yMax))
        if contract[10] is not None:
            frame = tuple(round(v * scale) for v in contract[10])
            if not all(-32768 <= v <= 32767 for v in frame):
                raise ValueError('原厂上下边界超出源字体数值范围')
            # Android UI compatibility envelope, deliberately not a recomputed
            # outline union. Filling a small Clock/Roboto slot with a full CJK
            # font otherwise changes includeFontPadding and vertical centering.
            # The user's font and glyf/CFF/gvar remain untouched. Only staged
            # HyperOS aliases receive this envelope; old/no stock stays explicit.
            head.yMin, head.yMax = frame
        bottom_reason = 'stock-preserved'
        bottom_correction = 0
        if align_bitmap_bottom and contract[-1] == 'stock' and contract[10] is not None:
            # QQ draws @names at -fm.top into a ceil(bottom-top) bitmap. Its
            # ALIGN_BOTTOM span does not extend the line's metrics, so excess
            # (fm.bottom-fm.descent) shifts the name above the normal baseline.
            # Change only the Latin layout envelope, never the glyph baseline.
            descent = values[4] if contract[9] else values[1]
            if descent < 0 and head.yMin < descent:
                try:
                    ink_bottom = _latin_ink_bottom(font)
                except (KeyError, ValueError, IndexError, TypeError, struct.error):
                    ink_bottom = None
                if ink_bottom is None:
                    bottom_reason = 'unproven-latin-ink-bounds'
                elif ink_bottom < descent:
                    bottom_reason = 'latin-descender-would-clip'
                else:
                    bottom_correction = descent - head.yMin
                    head.yMin = descent
                    bottom_reason = 'latin-ui-bottom-to-descent'
            else:
                bottom_reason = 'no-excess-bottom-padding'
        # MVAR can restore source line metrics at non-default variable weights.
        had_mvar = 'MVAR' in font
        if had_mvar:
            del font['MVAR']
        removed = (remove_cjk_mappings(font, cjk_fallback_codepoints, stock_cjk_punctuation)
                   if cjk_fallback_codepoints else 0)
        # cmap glyph-name resolution can lazily load CFF to learn the glyph
        # order. Discard only those unmodified decoded tables so save copies
        # their original reader bytes instead of reserializing the outlines.
        for tag in ('glyf', 'CFF ', 'CFF2', 'gvar'):
            font.tables.pop(tag, None)
        if (face >= 0 or had_mvar or removed or
                not _patch_metric_tables(source, output, font, stream.fileno())):
            font.save(output, reorderTables=False)
        report = {'sourceUpem': upem, 'sourceHead': list(source_frame),
                  'outputHead': [int(head.yMin), int(head.yMax)],
                  'layoutBoundsSource': ('stock-line-descent' if bottom_correction else
                                         'stock' if contract[10] is not None else 'source'),
                  'bitmapBaselineCorrection': bottom_correction,
                  'bitmapBaselineReason': bottom_reason,
                  'layoutBoundsDifferFromSource': source_frame != (head.yMin, head.yMax),
                  'removedCjkMappings': removed}
    os.chmod(output, 0o644)
    return report


PATCHED_METRIC_TABLES = ('head', 'hhea', 'OS/2')


def _patch_metric_tables(source: Path, output: Path, font: TTFont, descriptor: int) -> bool:
    """Write a metrics-only alias as a kernel copy plus three table patches.

    Re-saving with fontTools rereads and re-checksums every table, ~1.8 s for a
    20 MB CJK donor on a desktop and several seconds per distinct stock contract
    on a phone. When only head/hhea/OS/2 change and their compiled sizes are
    unchanged, the result is the source file with those tables (and their
    directory checksums plus head.checkSumAdjustment) rewritten in place.
    Returns False, writing nothing, whenever that equivalence does not hold.
    """
    try:
        # pread on the writer's own descriptor: no extra open, no seek race
        # with the lazy fontTools reader that shares this stream.
        header = os.pread(descriptor, 12, 0)
        if len(header) != 12:
            return False
        version, count = header[:4], struct.unpack('>H', header[4:6])[0]
        if version not in (b'\x00\x01\x00\x00', b'OTTO', b'true') or not 1 <= count <= 512:
            return False
        directory = os.pread(descriptor, 16 * count, 12)
        if len(directory) != 16 * count:
            return False
        entries = {}
        for index in range(count):
            tag, checksum, offset, length = struct.unpack_from('>4sIII', directory, 16 * index)
            entries[tag.decode('latin-1')] = (index, checksum, offset, length)
        compiled = {}
        for tag in PATCHED_METRIC_TABLES:
            if tag not in entries:
                return False
            data = font[tag].compile(font)
            if len(data) != entries[tag][3]:
                return False
            compiled[tag] = data
        size = source.stat().st_size
        if any(not 0 < offset and offset + length <= size
               for _index, _checksum, offset, length in entries.values()):
            return False
    except Exception:
        return False
    from fontTools.ttLib.sfnt import calcChecksum
    output.unlink(missing_ok=True)
    try:
        shutil.copyfile(source, output)
        table_directory = bytearray(header + directory)
        with output.open('r+b') as stream:
            for tag, data in compiled.items():
                index, _checksum, offset, _length = entries[tag]
                if tag == 'head':
                    data = data[:8] + b'\0\0\0\0' + data[12:]
                stream.seek(offset)
                stream.write(data)
                struct.pack_into('>I', table_directory, 12 + 16 * index + 4, calcChecksum(data))
            stream.seek(0)
            stream.write(table_directory)
            total = calcChecksum(bytes(table_directory))
            for index in range(count):
                total += struct.unpack_from('>I', table_directory, 12 + 16 * index + 4)[0]
            adjustment = (0xB1B0AFBA - total) & 0xFFFFFFFF
            stream.seek(entries['head'][2] + 8)
            stream.write(struct.pack('>I', adjustment))
        return True
    except Exception:
        output.unlink(missing_ok=True)
        return False


def link_copy(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary = dest.with_name(dest.name + f'.tmp.{os.getpid()}')
    try:
        # A previous interrupted writer may leave a linked temporary leaf.
        # Never let the copy fallback overwrite its shared/live inode.
        temporary.unlink(missing_ok=True)
        try:
            os.link(source, temporary)
        except OSError:
            shutil.copyfile(source, temporary)
        os.chmod(temporary, 0o644)
        os.replace(temporary, dest)
    finally:
        temporary.unlink(missing_ok=True)


def _specialized_slot(logical: str, slot: dict) -> bool:
    label = ' '.join([Path(logical).name, *slot.get('families', [])]).lower()
    return any(token in label for token in
               ('clock', 'mitype', 'mono', 'symbol', 'icon', 'emoji', 'math', 'music'))


def _latin_ui_slot(logical: str, slot: dict) -> bool:
    name = Path(logical).name.lower()
    families = [str(family).lower().replace('_', '-') for family in slot.get('families', [])]
    return (name in {'notosans.ttf', 'notosans.otf', 'notosansui.ttf', 'notosansui.otf'}
            or any(family.startswith(('sans-serif', 'system-ui', 'system-sans', 'roboto',
                                  'google-sans', 'misans', 'mi-sans', 'sys-sans', 'oppo-sans',
                                  'oplus-sans')) for family in families)
            or name.startswith(('roboto', 'misanslatin', 'googlesans', 'syssans', 'sysfont',
                                'sourcesanspro', 'opposans', 'oplussans', 'opsans',
                                'notosans-', 'notosansui-', 'droidsans')))


def bitmap_bottom_slot(data: dict, logical: str, contract: tuple) -> bool:
    """Limit the correction to Latin UI; preserve the working OEM main/clock."""
    slot = (data.get('slots') or {}).get(logical, {})
    if (contract[-1] != 'stock' or contract[10] is None or
            logical == data.get('mainSlotPath') or _specialized_slot(logical, slot)):
        return False
    coverage = slot.get('metrics', {}).get('coverage')
    if valid_coverage(coverage) and (_stock_has_cjk_ideographs(coverage) or not coverage['hasLatin']):
        return False
    name = Path(logical).name.lower()
    return name.startswith(('roboto', 'misanslatin', 'googlesans', 'sysfont-regular',
                            'sysfont-static', 'syssans-en-', 'sysfont-en-',
                            'opposans-en-', 'opsans-en-', 'sourcesanspro',
                            'notosans-', 'notosansui-', 'droidsans'))


def _stock_has_cjk_ideographs(coverage: dict) -> bool:
    # summarize_coverage correctly counts U+3007 IDEOGRAPHIC NUMBER ZERO as Han.
    # Stock MiSansLatinVF includes that numeral, but no CJK ideographs. Treating
    # this one shared numeral as a Chinese font lets the replacement's whole Han
    # repertoire take over Latin UI slots. Original U+3007 stays protected by the
    # stock cjkPunctuation set when new Han mappings are pruned below.
    shared_zero = int(0x3007 in coverage['cjkPunctuation'])
    return coverage['hanCount'] > shared_zero



def _fallback_job(data: dict, destination: Path, contract: tuple, stage: Path) -> bool:
    logical = '/' + destination.relative_to(stage).as_posix()
    slot = (data.get('slots') or {}).get(logical, {})
    coverage = slot.get('metrics', {}).get('coverage')
    return (contract[-1] == 'stock' and valid_coverage(coverage)
            and _stock_has_cjk_ideographs(coverage) and not _specialized_slot(logical, slot)
            and (logical == data.get('mainSlotPath') or Path(logical).name in
                 {'MiSansVF.ttf', 'MiSansVF_Overlay.ttf', 'MiSansTCVF.ttf', 'MiSansL3.otf'}))


def final_fallback_codepoints(path: Path, candidates: frozenset[int]) -> tuple:
    """Geometric proof from the actual generated default-instance SFNT.

    Empty/unsupported glyphs do not authorize primary pruning. Positive bounds
    are not raster/shaping proof; optional legal spaces simply stay in primary.
    """
    from fontTools.pens.boundsPen import BoundsPen
    with TTFont(path, lazy=True, recalcBBoxes=False, recalcTimestamp=False) as font:
        cmap = font.getBestCmap() or {}
        mapped = candidates & cmap.keys()
        # Preserve the existing fallback eligibility contract: an actual Latin
        # or punctuation-only output is not a CJK fallback, even in a Han slot.
        if not any(is_han(cp) and name != '.notdef' for cp, name in cmap.items()):
            return frozenset(), frozenset(mapped), 0
        # Do not decode large image/SVG programs for ordinary outline routing.
        if any(tag in font for tag in ('CBDT', 'CBLC', 'EBDT', 'EBLC', 'sbix', 'SVG ')):
            return frozenset(), frozenset(mapped), 0
        color_names = set()
        if 'COLR' in font:
            colr = font['COLR']; color_names.update(getattr(colr, 'ColorLayers', {}) or {})
            table = getattr(colr, 'table', None)
            for attribute in ('BaseGlyphRecordArray', 'BaseGlyphList'):
                records = getattr(table, attribute, None)
                records = (getattr(records, 'BaseGlyphRecord', None)
                           or getattr(records, 'BaseGlyphPaintRecord', None) or [])
                color_names.update(record.BaseGlyph for record in records)
        glyphs = font.getGlyphSet() if mapped else {}
        names = {cmap[cp] for cp in mapped}
        cache = {name: False for name in names
                 if name == '.notdef' or name not in glyphs or name in color_names}
        pending = [name for name in sorted(names) if name not in cache]
        # glyphsDrawn keeps counting every outline given a geometric verdict.
        drawn = len(pending)
        # A CJK donor maps tens of thousands of glyphs. Drawing every outline in
        # Python took ~50 s on a desktop for a 20 MB font (minutes on a phone).
        # Well-formed simple TrueType glyphs are proven from their own glyf
        # record instead; anything else is still drawn exactly as before.
        if 'glyf' in font and pending:
            fast = _glyf_simple_outline_proof(font, pending)
            cache.update(fast)
            pending = [name for name in pending if name not in fast]
        cache.update(_draw_outline_proof(path, glyphs, pending, BoundsPen))
        proven = {cp for cp in mapped if cache.get(cmap[cp], False)}
        return frozenset(proven), frozenset(mapped), drawn


def _glyf_simple_outline_proof(font: TTFont, names: list) -> dict:
    """Prove non-empty simple glyf outlines without decoding coordinates.

    The glyf record of a simple glyph carries the bounding box of its control
    points. For quadratic outlines the exact outline bounds have positive width
    (height) exactly when the control points do, so a positive stored box is the
    same proof the BoundsPen draw gives. The record is also checked to be
    structurally complete (contour end points, instructions, flags inside the
    record). Composite, empty, malformed or degenerate records are not decided
    here: they return no verdict and are drawn by the caller.
    """
    try:
        raw = font.reader['glyf']
        locations = font['loca'].locations
        order = {name: index for index, name in enumerate(font.getGlyphOrder())}
    except Exception:
        return {}
    size = len(raw)
    verdict = {}
    unpack = struct.unpack_from
    for name in names:
        index = order.get(name)
        if index is None or index + 1 >= len(locations):
            continue
        start, end = locations[index], locations[index + 1]
        if not 0 <= start <= end <= size or end - start < 10:
            continue
        contours, x_min, y_min, x_max, y_max = unpack('>hhhhh', raw, start)
        if contours <= 0 or x_max <= x_min or y_max <= y_min:
            continue
        cursor = start + 10 + 2 * contours
        if cursor + 2 > end:
            continue
        ends = unpack(f'>{contours}H', raw, start + 10)
        if any(later < earlier for earlier, later in zip(ends, ends[1:])):
            continue
        instructions = unpack('>H', raw, cursor)[0]
        cursor += 2 + instructions
        # At least one flag byte must follow the instructions, and the points
        # must fit into the remaining record (one flag byte can repeat, each
        # coordinate needs zero to two bytes per axis).
        if cursor >= end or ends[-1] + 1 > 255 * (end - cursor):
            continue
        verdict[name] = True
    return verdict


def _draw_names(path: Path, names: list, pen_class) -> dict:
    result = {}
    with TTFont(path, lazy=True, recalcBBoxes=False, recalcTimestamp=False) as font:
        glyphs = font.getGlyphSet()
        for name in names:
            result[name] = _draw_one(glyphs, name, pen_class)
    return result


def _draw_one(glyphs, name: str, pen_class) -> bool:
    try:
        pen = pen_class(glyphs); glyphs[name].draw(pen)
        bounds = pen.bounds
        return (bounds is not None and all(math.isfinite(v) for v in bounds)
                and bounds[2] > bounds[0] and bounds[3] > bounds[1])
    except MemoryError:
        raise
    except Exception:
        # A malformed optional fallback glyph is not proof that
        # the already visible primary can safely be removed.
        return False


# Below this many outlines a fork costs more than it saves.
PARALLEL_DRAW_MIN_GLYPHS = 1500


def _draw_outline_proof(path: Path, glyphs, names: list, pen_class) -> dict:
    """Draw remaining outlines (CFF/CFF2, composites) on all CPU cores.

    Android Python has no working multiprocessing semaphores, so plain
    fork()+pipe workers are used. Each worker reopens the font (no shared
    file offset) and returns one byte per glyph. Any worker failure falls back
    to drawing the whole set in-process, so the verdict never depends on it.
    """
    if not names:
        return {}
    try:
        workers = min(len(os.sched_getaffinity(0)), 8)
    except (AttributeError, OSError):
        workers = os.cpu_count() or 1
    if (len(names) < PARALLEL_DRAW_MIN_GLYPHS or workers < 2 or
            not hasattr(os, 'fork') or os.environ.get('LUOSHU_SERIAL_GLYPH_PROOF') == '1'):
        return {name: _draw_one(glyphs, name, pen_class) for name in names}
    chunks = [names[index::workers] for index in range(workers)]
    children = []  # (pid, read_fd or None, chunk)
    result = {}
    failed = False
    try:
        for chunk in chunks:
            read_fd, write_fd = os.pipe()
            pid = os.fork()
            if pid == 0:  # pragma: no cover - exercised through the parent
                code = 1
                try:
                    os.close(read_fd)
                    verdict = _draw_names(path, chunk, pen_class)
                    view = memoryview(bytes(1 if verdict[name] else 0 for name in chunk))
                    while view:
                        view = view[os.write(write_fd, view):]
                    code = 0
                finally:
                    os._exit(code)
            os.close(write_fd)
            children.append([pid, read_fd, chunk])
    except OSError:
        failed = True
    for child in children:
        pid, read_fd, chunk = child
        data = b''
        try:
            with os.fdopen(read_fd, 'rb') as stream:
                child[1] = None
                data = stream.read()
        except OSError:
            failed = True
        finally:
            if child[1] is not None:
                try:
                    os.close(child[1])
                except OSError:
                    pass
        try:
            _pid, status = os.waitpid(pid, 0)
        except OSError:
            status = -1
        if status != 0 or len(data) != len(chunk):
            failed = True
            continue
        result.update((name, bool(flag)) for name, flag in zip(chunk, data))
    if failed:
        return {name: _draw_one(glyphs, name, pen_class) for name in names}
    return result


def prepare_cjk_routing(data: dict, jobs: list, stage: Path, outputs: Path, *, writer=None) -> tuple:
    """Generate final fallback temps once, before authorizing any primary trim.

    Only actual prune candidates are inspected. Cache is private to this build,
    whose sources are pinned until every output is ready; no persistent receipt
    or mtime-only acceptance is introduced here.
    """
    writer = writer or write_metrics
    source_points = {}; by_slot = {}; candidates = set()
    for source, destination, contract in jobs:
        logical = '/' + destination.relative_to(stage).as_posix()
        routing, punctuation, _reason = _cjk_routing(data, logical, frozenset({0x4E2D}))
        if not routing or contract[-1] != 'stock': continue
        info = source.stat()
        # Weight aliases can be hardlinks. Reuse byte-derived face/cmap data
        # only within this pinned build, and invalidate ordinary mutations
        # even when mtime is restored. Slot punctuation stays outside cache.
        identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if identity not in source_points:
            face = _pick_face(source); options = {'fontNumber': face} if face >= 0 else {}
            with TTFont(source, lazy=True, recalcBBoxes=False, **options) as font:
                variants = {cp for table in font['cmap'].tables if table.format == 14
                            for records in table.uvsDict.values() for cp, _name in records}
                source_points[identity] = {cp for table in font['cmap'].tables
                    if table.isUnicode() and table.format != 14 for cp in table.cmap
                    if is_cjk_routing_codepoint(cp) and cp not in variants}
        points = source_points[identity] - punctuation
        by_slot[logical] = points; candidates.update(points)
    prepared = {}; cache = {}; proof = set(); failed = set(); draws = 0
    if candidates:
        for source, destination, contract in jobs:
            if not _fallback_job(data, destination, contract, stage): continue
            info = source.stat()
            key = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, contract)
            if key not in cache:
                output = outputs / f'fallback-{len(cache)}.font'
                logical = '/' + destination.relative_to(stage).as_posix()
                report = writer(source, output, contract,
                                align_bitmap_bottom=bitmap_bottom_slot(data, logical, contract))
                proven, mapped, drawn = final_fallback_codepoints(output, frozenset(candidates))
                cache[key] = (output, report); proof.update(proven); failed.update(mapped - proven); draws += drawn
            prepared[destination] = cache[key]
    # XML fallback order is not proved here: a mapped empty glyph in any
    # eligible output cannot be cured by a different output's positive glyph.
    proof.difference_update(failed)
    evidence = {'candidateCodepoints': len(candidates), 'provenCodepoints': len(proof),
                'glyphsDrawn': draws, 'finalFallbackOutputs': len(cache),
                'method': 'final-default-outline-bounds-v1',
                'unprovenBySlot': {logical: len(points - proof) for logical, points in by_slot.items()}}
    return frozenset(proof), prepared, evidence


def cjk_routing_report(logical: str, reason: str, evidence: dict) -> dict:
    unproven = evidence['unprovenBySlot'].get(logical, 0)
    if unproven and evidence['finalFallbackOutputs'] and reason in {'stock-latin-primary', 'no-staged-cjk-fallback'}:
        reason = ('stock-latin-primary-unproven-glyphs-preserved'
                  if reason == 'stock-latin-primary' else 'unproven-staged-cjk-fallback')
    return {'cjkRoutingReason': reason, 'cjkUnprovenMappingsPreserved': unproven,
            'cjkFallbackGeometry': {key: value for key, value in evidence.items() if key != 'unprovenBySlot'}}


def _cjk_routing(data: dict, logical: str, fallback: frozenset[int]) -> tuple:
    slot = (data.get('slots') or {}).get(logical, {})
    coverage = slot.get('metrics', {}).get('coverage')
    if not valid_coverage(coverage):
        return None, frozenset(), 'stock-coverage-refresh-pending'
    if _specialized_slot(logical, slot):
        return None, frozenset(), 'specialized-slot'
    if _stock_has_cjk_ideographs(coverage):
        return None, frozenset(), 'stock-han-slot'
    if not coverage['hasLatin'] or not _latin_ui_slot(logical, slot):
        return None, frozenset(), 'not-latin-ui-slot'
    if not fallback:
        return None, frozenset(), 'no-staged-cjk-fallback'
    return fallback, frozenset(coverage['cjkPunctuation']), 'stock-latin-primary'


def build(module: Path, stage: Path, names: list[str]) -> dict:
    resolved = stage.resolve()
    live = (module / '.luoshu-payload').resolve()
    if resolved == module.resolve() or resolved == live or live in resolved.parents:
        raise ValueError('拒绝修改本次启动正在使用的字体负载')
    if not stage.is_dir():
        raise ValueError('HyperOS 字体暂存目录不存在')
    fonts = stage / 'system/fonts'
    data = read_inventory(module)
    jobs = []
    preserved_aliases = []
    excluded_aliases = []
    for part in PARTS:
        root = Path(os.environ.get(f'LUOSHU_{part.upper()}_FONTS_ROOT', f'/{part}/fonts'))
        staged_fonts = stage / part / 'fonts'
        # Resolve before existence checks: a symlinked partition may lead to an
        # outside directory whose fonts child has not been created yet.
        if staged_fonts.is_symlink() or resolved not in staged_fonts.resolve().parents:
            raise ValueError('字体暂存槽位指向隔离目录之外')
        if staged_fonts.is_dir():
            for alias in staged_fonts.iterdir():
                if (alias.name.startswith(('NotoSans', 'MiSans', 'DroidSans'))
                        and alias.suffix in ('.ttf', '.otf')
                        and not safe_physical_font_name(alias.name)):
                    excluded_aliases.append(alias)
        for name in dict.fromkeys(names):
            if Path(name).name != name or not name.endswith(('.ttf', '.otf')):
                raise ValueError(f'不安全的字体槽位：{name}')
            logical = f'/{part}/fonts/{name}'
            if not safe_physical_font_name(name):
                # Never let a stale inventory/target list recreate obsolete
                # language aliases. Removing only its isolated staged alias
                # exposes the untouched ROM font when the payload is mounted.
                excluded_aliases.append(stage / part / 'fonts' / name)
                continue
            if preserved_dynamic_alias(data, logical):
                preserved_aliases.append(stage / part / 'fonts' / name)
                continue
            if (root / name).exists():
                jobs.append((pick_source(fonts, name), stage / part / 'fonts' / name,
                             contract_for_slot(data, logical)))
    # Filename discovery serves known boot-repair aliases. Trusted inventory
    # also contains XML UI faces and verified upright text with other OEM names.
    seen = {'/' + dest.relative_to(stage).as_posix() for _source, dest, _contract in jobs}
    seen.update('/' + dest.relative_to(stage).as_posix() for dest in preserved_aliases + excluded_aliases)
    completed = inventory_completion_jobs(module, stage, data, seen)
    jobs.extend(completed)
    completed_slots = {'/' + dest.relative_to(stage).as_posix() for _source, dest, _contract in completed}
    if not jobs:
        raise ValueError('没有找到当前 ROM 的 HyperOS 字体目标')
    store = fonts / '.luoshu-font-store'
    if store.is_symlink() or resolved not in store.resolve().parents:
        raise ValueError('字体暂存供体目录指向隔离目录之外')
    store.mkdir(parents=True, exist_ok=True)
    outputs = Path(tempfile.mkdtemp(prefix='hyperos-metrics-', dir=store))
    cache = {}
    compact_sources = {}
    output_reports = {}
    # Generate every distinct source/contract before replacing even one alias.
    # Thus subsequent sources cannot accidentally refer to earlier outputs.
    prepared = []
    slot_report = []
    fallback = 0
    try:
        cjk_fallback, fallback_outputs, routing_evidence = prepare_cjk_routing(data, jobs, stage, outputs)
        for source, dest, contract in jobs:
            stat = source.stat()
            logical = '/' + dest.relative_to(stage).as_posix()
            routing, stock_punctuation, routing_reason = _cjk_routing(data, logical, cjk_fallback)
            if contract[-1] != 'stock':
                routing, stock_punctuation, routing_reason = None, frozenset(), 'invalid-stock-contract'
            align_bottom = bitmap_bottom_slot(data, logical, contract)
            key = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, contract,
                   routing, stock_punctuation, align_bottom)
            if key not in cache and dest in fallback_outputs:
                cache[key], output_reports[key] = fallback_outputs[dest]
            if key not in cache:
                output = outputs / f'{len(cache)}.font'
                metric_source, compact_removed = source, 0
                if routing:
                    source_key = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns,
                                  routing, stock_punctuation)
                    if source_key not in compact_sources:
                        compact_sources[source_key] = compact_routed_source(
                            source, outputs / f'source-{len(compact_sources)}.font',
                            routing, stock_punctuation)
                    metric_source, compact_removed = compact_sources[source_key]
                output_reports[key] = write_metrics(metric_source, output, contract, routing, stock_punctuation,
                                                    align_bitmap_bottom=align_bottom)
                output_reports[key]['removedCjkMappings'] += compact_removed
                cache[key] = output
            prepared.append((cache[key], dest))
            fallback += contract[-1] == 'fallback'
            slot_report.append({'slot': '/' + dest.relative_to(stage).as_posix(),
                                'metricsSource': contract[-1],
                                'slotSource': 'stock-inventory' if logical in completed_slots else 'physical-mapper',
                                'referenceUpem': contract[0],
                                'hhea': list(contract[1:4]),
                                'typo': list(contract[4:7]),
                                'win': list(contract[7:9]),
                                'useTypoMetrics': contract[9],
                                'cjkRoutingSource': 'stock-fallback' if routing else 'source',
                                'cjkRoutingReason': routing_reason,
                                **cjk_routing_report(logical, routing_reason, routing_evidence),
                                **output_reports[key]})
        for output, dest in prepared:
            link_copy(output, dest)
        for alias in preserved_aliases + excluded_aliases:
            # Initial generic mapping creates the alias as a regular font. Its
            # absence exposes the ROM lower symlink in OverlayFS and leaves it
            # untouched in per-file bind mode. Framework changes keep working.
            alias.unlink(missing_ok=True)
        report = stage / '.luoshu-metrics-report.json'
        descriptor, temporary_name = tempfile.mkstemp(prefix=report.name + '.tmp.', dir=stage)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                json.dump({'schema': 'luoshu-slot-metrics-v1',
                           'slots': slot_report,
                           'preservedDynamicAliases': [
                               '/' + alias.relative_to(stage).as_posix()
                               for alias in preserved_aliases],
                           'preservedStockAliases': sorted({
                               '/' + alias.relative_to(stage).as_posix()
                               for alias in excluded_aliases if alias.parent.is_dir()})},
                          stream, ensure_ascii=False)
            temporary.chmod(0o644)
            os.replace(temporary, report)
        finally:
            temporary.unlink(missing_ok=True)
    finally:
        # Every prepared result has its own hard link (or copy) in the final
        # alias. Keeping these temporary names after success only enlarges
        # cached payload copies and accumulates on repeated stage completion.
        shutil.rmtree(outputs, ignore_errors=True)
    return {'mapped': len(jobs), 'generated': len(cache), 'fallbackSlots': fallback}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('module', type=Path)
    parser.add_argument('stage', type=Path)
    args = parser.parse_args()
    try:
        report = build(args.module, args.stage, sys.stdin.read().split())
        print(json.dumps(report, ensure_ascii=False))
        if report['fallbackSlots']:
            print(f"HyperOS：{report['fallbackSlots']} 个槽位缺少有效原厂度量，使用紧凑回退；可重新扫描原厂字体", file=sys.stderr)
        return 0
    except Exception as error:
        print(f'HyperOS 字体处理失败：{error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
