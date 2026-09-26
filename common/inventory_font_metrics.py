#!/usr/bin/env python3
"""Data-driven stock layout contracts; no ROM or filename policy."""
from __future__ import annotations
import os
import shutil
import struct
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.DefaultTable import DefaultTable
from fontTools import subset
from font_metrics_normalize import _pick_face, _promote_os2_for_typo_metrics
from font_slot_coverage import remove_cjk_mappings

def _latin_ink_bottom(font: TTFont, limit: int | None = None) -> int | None:
    """Prove the retained face fits before reducing its bitmap envelope.

    A Latin UI alias can still encode extended Latin, Greek, combining marks,
    protected CJK variations and GSUB alternates. The old ASCII/Latin-only
    probe could crop these after concluding that the face fit the descent.
    Stop as soon as any reachable glyph disproves the requested bound.
    """
    if 'fvar' in font:
        return None  # Default-axis bounds cannot prove other variable instances.
    names = set()
    for table in font['cmap'].tables:
        if table.format == 14:
            names.update(name for entries in table.uvsDict.values()
                         for _, name in entries if name is not None)
        else:
            names.update(table.cmap.values())
    if 'GSUB' in font:
        closure = subset.Subsetter()
        closure.glyphs = names
        font['GSUB'].closure_glyphs(closure)
        names = closure.glyphs
    if not names:
        return None
    # Color and bitmap bounds are not covered by this outline-only proof.
    if any(tag in font for tag in ('COLR', 'SVG ', 'CBDT', 'sbix')):
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
            if limit is not None and bottom < limit:
                return bottom
    else:
        from fontTools.pens.boundsPen import BoundsPen
        glyphs = font.getGlyphSet()
        for name in names:
            pen = BoundsPen(glyphs)
            glyphs[name].draw(pen)
            if pen.bounds is not None:
                bottom = min(bottom, pen.bounds[1])
                if limit is not None and bottom < limit:
                    return bottom
    return bottom


def restrict_unicode_scope(source: Path, output: Path, allowed: frozenset[int]) -> Path:
    """Trim newly introduced mappings without decoding/recompiling outlines."""
    with TTFont(source, lazy=True, recalcBBoxes=False, recalcTimestamp=False) as font:
        for table in font['cmap'].tables:
            if table.format == 14:
                table.uvsDict = {selector: [(point, glyph) for point, glyph in entries if point in allowed]
                                 for selector, entries in table.uvsDict.items()}
                table.uvsDict = {selector: entries for selector, entries in table.uvsDict.items() if entries}
            elif table.isUnicode():
                table.cmap = {point: glyph for point, glyph in table.cmap.items() if point in allowed}
        raw = font.getTableData('cmap')
        font.tables.clear()
        table = DefaultTable('cmap'); table.data = raw; font['cmap'] = table
        font.save(output, reorderTables=None)
    return output


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
        font.save(output, reorderTables=None)
    return output, removed


def write_metrics(source: Path, output: Path, contract: tuple,
                  cjk_fallback_codepoints: frozenset[int] | None = None,
                  stock_cjk_punctuation: frozenset[int] = frozenset(), *,
                  align_bitmap_bottom: bool = False,
                  ink_bounds_cache: dict | None = None) -> dict:
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
            # outline union. Filling a compact Latin slot with a full CJK
            # font otherwise changes includeFontPadding and vertical centering.
            # The user's font and glyf/CFF/gvar remain untouched. Only generated aliases receive this envelope.
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
                    # Probe the common source BEFORE per-slot cmap pruning:
                    # its punctuation union bounds every slot that reuses this
                    # cache entry, including a later slot retaining a deep mark.
                    # Moving remove_cjk_mappings above this point requires the
                    # routing/punctuation contract in the cache key as well.
                    bounds_key = (str(source), descent)
                    if ink_bounds_cache is not None and bounds_key in ink_bounds_cache:
                        ink_bottom = ink_bounds_cache[bounds_key]
                    else:
                        ink_bottom = _latin_ink_bottom(font, descent)
                        if ink_bounds_cache is not None:
                            ink_bounds_cache[bounds_key] = ink_bottom
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
        if 'MVAR' in font:
            del font['MVAR']
        removed = (remove_cjk_mappings(font, cjk_fallback_codepoints, stock_cjk_punctuation)
                   if cjk_fallback_codepoints else 0)
        # cmap glyph-name resolution can lazily load CFF to learn the glyph
        # order. Discard only those unmodified decoded tables so save copies
        # their original reader bytes instead of reserializing the outlines.
        changed = {tag: font.getTableData(tag) for tag in
                   ('head', 'hhea', 'OS/2', *(('cmap',) if removed else ()))}
        font.tables.clear()
        for tag, raw in changed.items():
            table = DefaultTable(tag)
            table.data = raw
            font[tag] = table
        font.save(output, reorderTables=None)
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


def link_copy(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary = dest.with_name(dest.name + f'.tmp.{os.getpid()}')
    try:
        try:
            os.link(source, temporary)
        except OSError:
            shutil.copyfile(source, temporary)
        os.chmod(temporary, 0o644)
        os.replace(temporary, dest)
    finally:
        temporary.unlink(missing_ok=True)



def contract_for_face(face: dict) -> tuple:
    """A complete, valid stock contract is required; no generic guessed ratios."""
    try:
        metrics = face['metrics']
        upem = int(metrics['upem'])
        hhea, os2, head = metrics['hhea'], metrics['os2'], metrics['head']
        values = tuple(int(value) for value in (
            hhea['ascent'], hhea['descent'], hhea.get('lineGap', 0),
            os2['typoAscender'], os2['typoDescender'], os2.get('typoLineGap', 0),
            os2['winAscent'], os2['winDescent']))
        frame = (int(head['yMin']), int(head['yMax']))
        typo = bool(int(os2.get('fsSelection', 0)) & 128)
        if (not 16 <= upem <= 16384 or not 0 < values[0] <= 32767
                or not -32768 <= values[1] <= 0 or values[2] < 0
                or any(abs(value) > 4 * upem for value in values)
                or any(not -32768 <= value <= 32767 for value in values[:6])
                or any(not 0 <= value <= 65535 for value in values[6:])
                or not -32768 <= frame[0] < frame[1] <= 32767):
            raise ValueError('invalid metric range')
        if typo and (values[3] <= 0 or values[4] > 0 or values[5] < 0):
            raise ValueError('invalid typo contract')
        return (upem, *values, typo, frame, 'stock')
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError('原厂槽位度量不完整或无效，请重新扫描') from exc
