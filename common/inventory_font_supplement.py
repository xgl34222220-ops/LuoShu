#!/usr/bin/env python3
"""Replace selected Unicode glyphs while retaining the stock font's remainder.

Subsets retain OpenType layout and outline dependency closures. The stock subset
is merged first, keeping its TrueType hint programs; merger-renamed component
glyphs prevent an unreplaced composite from inheriting a replacement outline.
"""
from __future__ import annotations

import copy
from array import array
from contextlib import ExitStack
import hashlib
from io import BytesIO
import math
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace

from fontTools import subset
from fontTools.cffLib import CharStrings, FDArrayIndex, FDSelect, FontDict, GlobalSubrsIndex
from fontTools.fontBuilder import FontBuilder
from fontTools.merge import Merger
from fontTools.merge.options import Options as MergeOptions
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables.DefaultTable import DefaultTable
from fontTools.ttLib.scaleUpem import scale_upem
from fontTools.misc.psCharStrings import calcSubrBias, T2CharString, T2WidthExtractor
from fontTools.pens.boundsPen import BoundsPen
from fontTools.unicodedata import script
from fontTools.varLib.instancer import instantiateVariableFont

from font_slot_coverage import preferred_unicode_codepoints, unicode_codepoints
from font_charstring_compile import compile_static_pen


class SupplementError(RuntimeError):
    pass


class UnsupportedSupplementError(SupplementError):
    """A known representational limit, distinct from corruption or I/O errors."""


def replacement_codepoints(points) -> set[int]:
    """Default user text roles; other scripts always retain their stock glyphs."""
    return {cp for cp in points if 0x20 <= cp <= 0x7E
            or script(chr(cp)) in {'Hani', 'Latn'}
            or 0x3000 <= cp <= 0x303F or 0xFF01 <= cp <= 0xFF60}


def _open_static(path: Path, index: int, weight: int | None = None, *, preserve_axes=False) -> TTFont:
    with path.open('rb') as stream:
        collection = stream.read(4) == b'ttcf'
    if collection and index < 0:
        raise SupplementError('stock/source collection requires its exact face index')
    if not collection and index not in {-1, 0}:
        raise SupplementError('non-collection font cannot supply this face index')
    font = TTFont(path, fontNumber=index if collection else -1, lazy=True,
                  recalcBBoxes=False, recalcTimestamp=False)
    if any(tag in font for tag in ('COLR', 'CBDT', 'sbix', 'SVG ')):
        font.close()
        raise UnsupportedSupplementError('color fonts cannot enter text supplementation')
    if 'fvar' in font:
        if preserve_axes:
            return font
        if weight is None:
            font.close()
            raise UnsupportedSupplementError('variable source supplementation would lose its axes; an explicit static instance is required')
        axes = {axis.axisTag: axis.defaultValue for axis in font['fvar'].axes}
        if weight is not None and 'wght' in axes:
            axis = next(axis for axis in font['fvar'].axes if axis.axisTag == 'wght')
            if not axis.minValue <= weight <= axis.maxValue:
                font.close()
                raise UnsupportedSupplementError('stock variation cannot provide requested weight')
            axes['wght'] = weight
        original = font
        try:
            font = instantiateVariableFont(original, axes, inplace=False, optimize=True)
        finally:
            original.close()
        font._luoshu_stock_instance_axes = axes
    if 'fvar' in font or 'gvar' in font:
        font.close()
        raise UnsupportedSupplementError('supplementation needs fully instantiated faces')
    return font


def _consolidate_stock_cmap(font: TTFont) -> None:
    # Preserve every stock Unicode entry without letting an alternate charmap
    # override the glyph selected by the original preferred cmap.
    mapping = {cp: glyph for table in font['cmap'].tables
               if table.isUnicode() and table.format != 14
               for cp, glyph in table.cmap.items() if glyph != '.notdef'}
    mapping.update({cp: glyph for cp, glyph in (font.getBestCmap() or {}).items()
                    if glyph != '.notdef'})
    tables = [table for table in font['cmap'].tables if table.format == 14]
    for fmt, encoding in ((4, 1), (12, 10)):
        table = CmapSubtable.newSubtable(fmt)
        table.platformID, table.platEncID, table.language = 3, encoding, 0
        table.cmap = {cp: glyph for cp, glyph in mapping.items() if fmt == 12 or cp <= 0xFFFF}
        tables.append(table)
    font['cmap'].tables = tables
    _split_default_uvs_runs(font)


def _split_default_uvs_runs(font: TTFont) -> None:
    """Keep format-14 default runs within its eight-bit additionalCount."""
    mapping = font.getBestCmap() or {}
    for table in font['cmap'].tables:
        if table.format != 14:
            continue
        for selector, entries in table.uvsDict.items():
            rewritten = []
            previous, run = -2, 0
            for cp, glyph in sorted(entries):
                if glyph is None:
                    run = run + 1 if cp == previous + 1 else 1
                    if run > 256:
                        # Both representations resolve to the exact same GID.
                        # A non-default record breaks a too-long default run
                        # that FontTools otherwise attempts to encode in u8.
                        glyph = mapping.get(cp)
                        if glyph is None:
                            raise SupplementError('default variation sequence has no base glyph')
                        run = 0
                    previous = cp
                else:
                    previous, run = -2, 0
                rewritten.append((cp, glyph))
            table.uvsDict[selector] = rewritten


def _uvs_pairs(font: TTFont) -> set[tuple[int, int]]:
    return {(selector, cp) for table in font['cmap'].tables if table.format == 14
            for selector, entries in table.uvsDict.items() for cp, _glyph in entries}


def _stock_variants(font: TTFont, replace: set[int], source_variants: set[tuple[int, int]]) -> set[int]:
    keep = set()
    mapping = font.getBestCmap() or {}
    for table in font['cmap'].tables:
        if table.format != 14:
            continue
        for selector, entries in list(table.uvsDict.items()):
            retained = []
            for cp, glyph in entries:
                if cp in replace and (selector, cp) in source_variants:
                    continue
                # A source missing this variant must not silently turn the
                # original default variant into its different replacement form.
                if cp in replace and glyph is None:
                    glyph = mapping.get(cp)
                retained.append((cp, glyph))
                keep.add(cp)
            table.uvsDict[selector] = retained
    return keep


def _limit_source_cmap(font: TTFont, replace: set[int]) -> None:
    """Restrict entry points while retaining an already-valid outline graph.

    A near-complete CJK source need not traverse 50k charstrings to remove a few
    non-target encodings. Unencoded glyphs remain available to layout and
    composite dependencies, but cannot replace any additional stock character.
    """
    for table in font['cmap'].tables:
        if table.format == 14:
            table.uvsDict = {selector: [(cp, glyph) for cp, glyph in entries if cp in replace]
                             for selector, entries in table.uvsDict.items()}
        elif table.isUnicode():
            table.cmap = {cp: glyph for cp, glyph in table.cmap.items() if cp in replace}


def _add_selected_variants(font: TTFont, pairs: set[tuple[int, int]]) -> None:
    """Keep each selector addressable using the selected font's base glyph."""
    if not pairs:
        return
    mapping = font.getBestCmap() or {}
    if any(cp not in mapping for _selector, cp in pairs):
        raise SupplementError('selected variation fallback has no selected base glyph')
    table = next((table for table in font['cmap'].tables if table.format == 14), None)
    if table is None:
        table = CmapSubtable.newSubtable(14)
        table.platformID, table.platEncID, table.language = 0, 5, 0
        table.cmap, table.uvsDict = {}, {}
        font['cmap'].tables.append(table)
    existing = _uvs_pairs(font)
    for selector, cp in sorted(pairs - existing):
        # An explicit reference resolves to exactly the selected default glyph.
        # It also avoids FontTools' format-14 encoder overflow for a run of
        # more than 256 consecutive default-UVS entries. The merger remaps this
        # glyph name with the donor's other references.
        table.uvsDict.setdefault(selector, []).append((cp, mapping[cp]))
    for entries in table.uvsDict.values():
        entries.sort()


def _variant_ranges(pairs: set[tuple[int, int]]) -> dict[str, list[list[int]]]:
    result = {}
    for selector, cp in sorted(pairs):
        ranges = result.setdefault(str(selector), [])
        if ranges and ranges[-1][1] + 1 == cp:
            ranges[-1][1] = cp
        else:
            ranges.append([cp, cp])
    return result


def _subset_stock(font, stock_points, replace, source_variants):
    retained_variant_bases = _stock_variants(font, replace, source_variants)
    for table in font['cmap'].tables:
        if table.isUnicode() and table.format != 14:
            table.cmap = {cp: glyph for cp, glyph in table.cmap.items() if cp not in replace}
    _subset(font, (stock_points - replace) | retained_variant_bases, preserve_base=True)


def plan_stock_glyph_union(source: Path, stock: Path, stock_face_indices,
                          replace_codepoints: set[int], stock_weight: int | None = None):
    """Plan one proven shared CID outline pool without sharing regional layout.

    No glyph conversion is performed here. Only identical original CFF and
    glyph-metric tables qualify; every face keeps its own cmap, UVS and shaping.
    None means that this collection must use independent face generation.
    """
    source, stock = Path(source), Path(stock)
    with _open_static(source, -1, preserve_axes=True) as donor:
        if 'fvar' in donor:
            return None
        source_points = set(preferred_unicode_codepoints(donor))
        replace = set(replace_codepoints) & source_points
        if not replace:
            return None
        _subset(donor, replace)
        donor_variants = _uvs_pairs(donor)
        donor_count = len(donor.getGlyphOrder())
        weight = int(donor['OS/2'].usWeightClass) if stock_weight is None else int(stock_weight)
        union, original_order, signature = set(), None, None
        for index in stock_face_indices:
            with ExitStack() as faces:
                font = faces.enter_context(_open_static(stock, int(index), weight))
                if _outline(font) != 'CFF-CID':
                    return None
                actual_signature = tuple(hashlib.sha256(font.reader[tag]).digest() if tag in font else None
                                         for tag in ('CFF ', 'hmtx', 'vmtx', 'VORG'))
                order = tuple(font.getGlyphOrder())
                if signature is None:
                    signature, original_order = actual_signature, order
                elif actual_signature != signature or order != original_order:
                    return None
                points = unicode_codepoints(font)
                if not replace.issubset(points):
                    return None
                _consolidate_stock_cmap(font)
                variants = _uvs_pairs(font)
                _subset_stock(font, points, replace, donor_variants)
                if len(font.getGlyphOrder()) + donor_count > 65535:
                    fallback = {(selector, cp) for selector, cp in variants - donor_variants if cp in replace}
                    if fallback:
                        font = faces.enter_context(_open_static(stock, int(index), weight))
                        _consolidate_stock_cmap(font)
                        _subset_stock(font, points, replace, donor_variants | fallback)
                union.update(font.getGlyphOrder())
                if len(union) + donor_count > 65535:
                    return None
        return tuple(name for name in original_order or () if name in union) or None


def _restore_stock_outline_union(font, full_stock, names):
    """Add proven unencoded CID glyphs without expanding this face's GSUB."""
    names = set(names)
    current = set(font.getGlyphOrder())
    full_order = full_stock.getGlyphOrder()
    if (_outline(full_stock) != 'CFF-CID' or not current.issubset(names)
            or not names.issubset(full_order)):
        raise SupplementError('shared stock outline plan does not contain this face dependency closure')
    order = [name for name in full_order if name in names]
    # FontTools' CFF glyph-table subset keeps raw subroutine pools and selected
    # FD indices. Deliberately do not run GSUB closure on the union: another
    # region's extra glyph must not expand this region's layout repertoire.
    cff = full_stock['CFF ']
    cff.subset_glyphs(SimpleNamespace(glyphs=names, glyphs_emptied=set(),
                                    options=SimpleNamespace(retain_gids=False)))
    font['CFF '] = cff
    for tag in ('hmtx', 'vmtx'):
        if tag in full_stock:
            metrics = full_stock[tag].metrics
            font[tag].metrics = {name: metrics[name] for name in order}
    if 'VORG' in full_stock:
        font['VORG'] = copy.deepcopy(full_stock['VORG'])
        font['VORG'].VOriginRecords = {name: value for name, value in font['VORG'].VOriginRecords.items()
                                      if name in names}
    font.setGlyphOrder(order)
    font['maxp'].numGlyphs = len(order)


def _subset(font: TTFont, points: set[int], *, preserve_base: bool = False) -> None:
    options = subset.Options()
    options.layout_features = ['*']
    options.layout_scripts = ['*']
    options.layout_closure = True
    options.legacy_kern = True
    options.notdef_glyph = True
    options.notdef_outline = True
    options.glyph_names = True
    options.name_IDs = ['*']
    options.name_languages = ['*']
    options.name_legacy = True
    options.recalc_bounds = False
    options.recalc_timestamp = False
    # Unsupported tables must not retain stale pre-subset glyph indices.
    options.passthrough_tables = False
    base = copy.deepcopy(font['BASE']) if preserve_base and 'BASE' in font else None
    base_glyphs = set()
    if base is not None:
        # BASE format 2 references an outline point by glyph. FontTools has no
        # BASE subsetter, so close those dependencies and retain its parsed
        # names; compilation will remap the glyph IDs after subsetting.
        def references(value):
            if isinstance(value, (list, tuple)):
                for child in value:
                    references(child)
            elif hasattr(value, '__dict__'):
                glyph = getattr(value, 'ReferenceGlyph', None)
                if glyph is not None:
                    base_glyphs.add(glyph)
                for child in vars(value).values():
                    references(child)
        references(base.table)
        options.drop_tables = [*options.drop_tables, 'BASE']
    worker = subset.Subsetter(options=options)
    # UVS closure requires both the base and its selector in the request.
    # Requesting only the base silently removes every cmap format-14 record.
    selectors = {selector for selector, cp in _uvs_pairs(font) if cp in points}
    worker.populate(unicodes=points | selectors, glyphs=base_glyphs)
    cff = font.get('CFF ')
    raw_cid = cff is not None and (hasattr(cff.cff[0], 'FDSelect')
        or getattr(font, '_luoshu_cff_closed_outlines', False))
    if raw_cid:
        # CID Type2 cannot use name-based seac components. Its outline closure
        # therefore needs no charstring interpreter. Deleting glyphs changes
        # neither local nor global subroutine indices; keeping unused pools
        # and FDs is valid and preserves raw programs/hints. FontTools' normal
        # post-prune decodes every remaining outline only to shrink these pools.
        cff.closure_glyphs = lambda worker: None
        cff.prune_post_subset = lambda font, options: True
    try:
        worker.subset(font)
    finally:
        if raw_cid:
            del cff.closure_glyphs, cff.prune_post_subset
    if base is not None:
        font['BASE'] = base


def _match_vertical_contract(donor: TTFont, stock: TTFont) -> None:
    if 'vhea' not in stock or 'vmtx' not in stock:
        for tag in ('vhea', 'vmtx', 'VORG'):
            if tag in donor:
                del donor[tag]
        return
    if 'vhea' in donor and 'vmtx' in donor:
        return
    # A horizontal-only donor still needs the existing target's measured
    # vertical contract. Do not synthesize an arbitrary upem-height metric.
    stock_map, donor_map = stock.getBestCmap() or {}, donor.getBestCmap() or {}
    vertical = stock['vmtx'].metrics
    fallback = vertical[stock.getGlyphOrder()[0]]
    by_glyph = {donor_map[cp]: vertical[stock_map[cp]] for cp in donor_map if cp in stock_map}
    donor['vhea'] = copy.deepcopy(stock['vhea'])
    donor['vmtx'] = newTable('vmtx')
    donor['vmtx'].metrics = {glyph: by_glyph.get(glyph, fallback) for glyph in donor.getGlyphOrder()}


def _outline(font: TTFont) -> str:
    if 'glyf' in font:
        return 'TTF'
    if 'CFF2' in font:
        return 'CFF2'
    if 'CFF ' in font:
        return 'CFF-CID' if hasattr(font['CFF '].cff[0], 'FDSelect') else 'CFF'
    raise SupplementError('font has no supported outline table')


def _drop_truetype_outlines(font: TTFont) -> None:
    for tag in ('glyf', 'loca', 'CFF ', 'CFF2', 'fpgm', 'prep', 'cvt ', 'gasp',
                'VORG', 'hdmx', 'LTSH', 'VDMX'):
        if tag in font:
            del font[tag]


class _BoundedT2Pen(T2CharStringPen):
    """Measure the converted curves during their existing drawing pass."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bounds_pen = BoundsPen(None)

    def _moveTo(self, point):
        self.bounds_pen.moveTo(point)
        super()._moveTo(point)

    def _lineTo(self, point):
        self.bounds_pen.lineTo(point)
        super()._lineTo(point)

    def _curveToOne(self, first, second, last):
        self.bounds_pen.curveTo(first, second, last)
        super()._curveToOne(first, second, last)

    def _closePath(self):
        self.bounds_pen.closePath()
        super()._closePath()

    def _endPath(self):
        self.bounds_pen.endPath()
        super()._endPath()


def _mergeable_cff(font: TTFont, *, outline_cache=None, outline_key=None) -> int:
    """Convert only selected TTF/CFF2 glyphs; existing CFF programs stay intact."""
    kind = _outline(font)
    if kind == 'CFF-CID':
        return 0
    if kind == 'CFF':
        # CID output cannot encode name-based Type2 seac components. Expand
        # only glyphs that actually use this legacy form, preserving all other
        # programs and private hints exactly.
        class ComponentDetector(T2WidthExtractor):
            has_components = False

            def op_endchar(self, index):
                self.has_components = bool(self.popallWidth())

        top = font['CFF '].cff[0]
        glyphs = font.getGlyphSet()
        converted = 0
        for name in font.getGlyphOrder():
            char = top.CharStrings[name]
            detector = ComponentDetector(getattr(char.private, 'Subrs', []), char.globalSubrs,
                                         char.private.nominalWidthX, char.private.defaultWidthX)
            detector.execute(char)
            if not detector.has_components:
                continue
            width = font['hmtx'].metrics[name][0]
            encoded_width = None if width == char.private.defaultWidthX else width - char.private.nominalWidthX
            pen = T2CharStringPen(encoded_width, glyphs, roundTolerance=0)
            glyphs[name].draw(pen)
            top.CharStrings[name] = pen.getCharString(private=char.private, globalSubrs=char.globalSubrs)
            converted += 1
        font._luoshu_cff_closed_outlines = True
        return converted
    # Conversion depends on the source outline and its scale, never on the
    # target's cmap, regional layout or inherited vertical contract. Reusing a
    # whole prepared donor conflates those concerns and repeats this expensive
    # pass for each regional TTC face with a different character repertoire.
    entry = (outline_cache.get('outline_entries', {}).get(outline_key)
             if outline_cache is not None and outline_key is not None else None)
    if entry is not None:
        _drop_truetype_outlines(font)
        table = newTable('CFF ')
        table.decompile(entry['data'], font)
        font['CFF '] = table
        font.sfntVersion = 'OTTO'
        FontBuilder(font=font).setupMaxp()
        font['post'].formatType = 3.0
        font._luoshu_cff_ymax = entry['ymax']
        font._luoshu_encoded_cff_size = len(entry['data'])
        font._luoshu_outline_cache_hit = True
        font._luoshu_cff_closed_outlines = True
        return entry['converted']
    glyphs = font.getGlyphSet()
    order = font.getGlyphOrder()
    strings = {}
    measured_ymax = array('d') if 'vmtx' in font else None
    for name in order:
        glyph = font['glyf'].glyphs[name] if kind == 'TTF' else None
        raw_glyph = getattr(glyph, 'data', None)
        pen_class = _BoundedT2Pen if measured_ymax is not None else T2CharStringPen
        pen = pen_class(font['hmtx'].metrics[name][0], glyphs, roundTolerance=0)
        glyphs[name].draw(pen)
        compiled, token_count = compile_static_pen(pen)
        charstring = T2CharString(bytecode=compiled)
        if measured_ymax is not None:
            bounds = pen.bounds_pen.bounds
            ymax = bounds[3] if bounds else 0
            # Type2 serializes relative real operands as 16.16 numbers. Their
            # accumulated coordinate error is bounded by half an ulp per
            # operand; use a full ulp per token as a conservative bound. A
            # Bezier curve stays within its control points' error envelope.
            # Only a result near a half-integer can alter VORG's integer
            # rounding after adding an integer vmtx bearing. Those rare
            # boundaries are measured from the exact compiled CFF below.
            error = token_count / 65536.0 + 1e-9
            near_boundary = abs(ymax - (math.floor(ymax) + 0.5)) <= error
            measured_ymax.append(float('nan') if near_boundary else ymax)
        # Retaining 50k Python command lists alongside expanded TrueType
        # coordinates can exceed a gigabyte. The exact serialized Type2 bytes
        # are all subsequent stages need, so finish each program immediately.
        strings[name] = charstring
        if glyph is not None:
            if raw_glyph is not None:
                glyph.__dict__.clear()
                glyph.data = raw_glyph
            else:
                glyph.compact(font['glyf'], recalcBBoxes=False)
    _drop_truetype_outlines(font)
    builder = FontBuilder(font=font)
    builder.setupCFF('LuoShuTextSubset', {}, strings, {})
    builder.setupMaxp()
    font['post'].formatType = 3.0
    font._luoshu_cff_closed_outlines = True
    if measured_ymax is not None:
        font._luoshu_cff_ymax = measured_ymax
    if outline_cache is not None and outline_key is not None:
        data = font.getTableData('CFF ')
        font._luoshu_encoded_cff_size = len(data)
        size = len(data) + len(order) * 8
        limit = 64 * 1024 * 1024
        if size <= limit:
            entries = outline_cache.setdefault('outline_entries', {})
            total = sum(item['size'] for item in entries.values())
            while entries and total + size > limit:
                total -= entries.pop(next(iter(entries)))['size']
            prepared = outline_cache.get('entries', {})
            prepared_size = sum(len(item[0]) for item in prepared.values())
            while prepared and total + size + prepared_size > limit:
                prepared_size -= len(prepared.pop(next(iter(prepared)))[0])
            ymax = measured_ymax if measured_ymax is not None else array('d')
            entries[outline_key] = {'data': data, 'size': size, 'converted': len(order), 'ymax': ymax}
            # Store outline bounds independently of target vertical bearings.
            # The first VORG pass fills this array; later regional faces only
            # add their own exact inherited vmtx bearings to these same bounds.
            font._luoshu_cff_ymax = ymax
    return len(order)


def _cff_global_layout(fonts: list[TTFont]) -> tuple[list[int], int]:
    """Keep the largest outline program's global-subroutine operands unchanged.

    Global subroutine order is independent of glyph order. At a Type2 bias
    boundary a short prefix of unused ``return`` programs can preserve the
    largest input's exact operands. This avoids decoding and recompiling tens
    of thousands of CJK charstrings merely to shift a subroutine number.
    """
    counts = [len(font['CFF '].cff.GlobalSubrs) for font in fonts]
    total = sum(counts)
    # A converted TrueType donor has no global subroutines at all. Choosing it
    # as anchor only adds padding and forces every retained stock charstring to
    # be decoded and rebased. Preserve the largest program that actually calls
    # this pool; a font with an empty pool has no operands to protect.
    candidates = [index for index, count in enumerate(counts) if count]
    anchor = max(candidates or range(len(fonts)), key=lambda index: len(fonts[index].getGlyphOrder()))
    old_bias = calcSubrBias(fonts[anchor]['CFF '].cff.GlobalSubrs)
    for bias in (107, 1131, 32768):
        padding = bias - old_bias
        count = total + padding
        if padding < 0 or count > 65535 or calcSubrBias(range(count)) != bias:
            continue
        offsets = [0] * len(fonts)
        offset = padding
        for index in [anchor, *(i for i in range(len(fonts)) if i != anchor)]:
            offsets[index] = offset
            offset += counts[index]
        return offsets, count
    # Very large pools need the compact layout even if every operand changes.
    offsets, offset = [], 0
    for count in counts:
        offsets.append(offset)
        offset += count
    if offset > 65535:
        raise UnsupportedSupplementError('CFF global subroutines exceed the format limit')
    return offsets, offset


def _merged_cff_table(fonts: list[TTFont]) -> DefaultTable:
    """Combine CFF programs and private dictionaries without redrawing glyphs.

    Each local-subroutine pool and hint dictionary remains independent. Only
    callgsubr operands change as the global pools are concatenated. Glyph IDs
    match the stock-first layout merger; CID names are merely serialized IDs.
    """
    dictionaries = FDArrayIndex()
    select = FDSelect()
    global_subrs = GlobalSubrsIndex()
    glyphs = []
    global_offsets, global_count = _cff_global_layout(fonts)
    new_bias = calcSubrBias([None] * global_count)
    # Distinct objects: later changes to an individual program must not mutate
    # every padding entry. All padding is unreachable from the input programs.
    global_subrs.items = [T2CharString(bytecode=b'\x0b', globalSubrs=global_subrs)
                         for _ in range(global_count)]
    matrices = {tuple(font['CFF '].cff[0].FontMatrix) for font in fonts}
    if len(matrices) != 1:
        raise UnsupportedSupplementError('CFF top-level coordinate matrices differ after scaling')
    for font, global_offset in zip(fonts, global_offsets):
        cff = font['CFF '].cff
        top = cff[0]
        old_global = cff.GlobalSubrs
        shift = calcSubrBias(old_global) + global_offset - new_bias
        fd_offset = len(dictionaries)
        if hasattr(top, 'FDArray'):
            fds = list(top.FDArray)
            indexes = list(top.FDSelect.gidArray)
        else:
            fd = FontDict()
            fd.Private = top.Private
            fds = [fd]
            indexes = [0] * len(font.getGlyphOrder())
        if fd_offset + len(fds) > 256:
            raise UnsupportedSupplementError('CFF private dictionaries exceed the format limit')
        charstrings = [top.CharStrings[name] for name in font.getGlyphOrder()]
        # Decode only when operands actually change. Untouched CID programs
        # and their hints stay byte-for-byte intact in the common large-source
        # case. Changed pools still need each glyph's FD context, since a
        # global subroutine can itself call private local subroutines.
        if shift and len(old_global):
            for charstring in charstrings:
                charstring.decompile()
        programs = [*charstrings, *old_global]
        for fd in fds:
            programs.extend(getattr(fd.Private, 'Subrs', []))
            dictionaries.append(fd)
        seen = set()
        for program in programs:
            if id(program) in seen:
                continue
            seen.add(id(program))
            # A raw subroutine left here is unreachable from every glyph;
            # retain its unused bytes without inventing a decoding FD context.
            if shift and len(old_global) and not program.needsDecompilation():
                for index, token in enumerate(program.program):
                    if token == 'callgsubr':
                        if index == 0 or not isinstance(program.program[index - 1], int):
                            raise UnsupportedSupplementError('computed CFF global subroutine operand')
                        program.program[index - 1] += shift
            program.globalSubrs = global_subrs
        global_subrs.items[global_offset:global_offset + len(old_global)] = list(old_global)
        glyphs.extend(charstrings)
        select.gidArray.extend(fd_offset + index for index in indexes)
    table = fonts[0]['CFF ']
    cff, top = table.cff, table.cff[0]
    names = ['.notdef', *(f'cid{index:05d}' for index in range(1, len(glyphs)))]
    top.charset = names
    top.numGlyphs = len(names)
    top.ROS = ('Adobe', 'Identity', 0)
    top.CIDCount = len(names)
    top.FDArray, top.FDSelect = dictionaries, select
    for key in ('Private', 'Encoding'):
        if hasattr(top, key):
            delattr(top, key)
        top.rawDict.pop(key, None)
    top.CharStrings = CharStrings(None, names, global_subrs, None, select, dictionaries)
    top.CharStrings.charStrings = dict(zip(names, glyphs))
    cff.GlobalSubrs = global_subrs
    top.GlobalSubrs = global_subrs
    # Other merged tables still refer to their original names. Compiling CFF
    # separately preserves those tables' numeric glyph IDs without renaming
    # every GSUB/GPOS reference or decompiling their layout a second time.
    with TTFont(recalcBBoxes=False, recalcTimestamp=False) as container:
        container.setGlyphOrder(names)
        raw = DefaultTable('CFF ')
        raw.data = table.compile(container)
    return raw


def _merged_vorg(fonts: list[TTFont], merged_names: list[str]):
    if not any('VORG' in font for font in fonts):
        return None
    table = newTable('VORG')
    table.majorVersion, table.minorVersion = 1, 0
    table.defaultVertOriginY = next(font['VORG'].defaultVertOriginY for font in fonts if 'VORG' in font)
    origins = {}
    offset = 0
    for font in fonts:
        order = font.getGlyphOrder()
        if 'VORG' in font:
            source = font['VORG']
            values = {name: source.VOriginRecords.get(name, source.defaultVertOriginY) for name in order}
        else:
            glyphs = font.getGlyphSet()
            values = {}
            cached_ymax = getattr(font, '_luoshu_cff_ymax', None)
            bounds_ready = cached_ymax is not None and len(cached_ymax) == len(order)
            for index, name in enumerate(order):
                if bounds_ready and not math.isnan(cached_ymax[index]):
                    values[name] = int(round(cached_ymax[index] + font['vmtx'].metrics[name][1]))
                    continue
                charstring = font['CFF '].cff[0].CharStrings[name] if 'CFF ' in font else None
                bytecode = charstring.bytecode if charstring is not None else None
                pen = BoundsPen(glyphs)
                glyphs[name].draw(pen)
                ymax = pen.bounds[3] if pen.bounds else 0
                if cached_ymax is not None:
                    if bounds_ready:
                        cached_ymax[index] = ymax
                    else:
                        cached_ymax.append(ymax)
                values[name] = int(round(ymax + font['vmtx'].metrics[name][1]))
                if bytecode is not None:
                    # Bounds extraction expands Type2 tokens too. Release that
                    # temporary program instead of accumulating the full CJK
                    # library a second time after outline conversion.
                    charstring.setBytecode(bytecode)
            source = newTable('VORG')
            source.majorVersion, source.minorVersion = 1, 0
            source.defaultVertOriginY = table.defaultVertOriginY
            source.VOriginRecords = {name: value for name, value in values.items()
                                    if value != source.defaultVertOriginY}
            font['VORG'] = source
        origins.update({merged_names[offset + index]: values[name] for index, name in enumerate(order)
                        if values[name] != table.defaultVertOriginY})
        offset += len(order)
    table.VOriginRecords = origins
    return table


_VARIATION_TABLES = ('fvar', 'avar', 'STAT', 'gvar', 'HVAR', 'VVAR', 'MVAR', 'cvar')


def _check_variable_source(font, stock):
    if 'glyf' not in font or 'gvar' not in font or 'glyf' not in stock or 'VARC' in font:
        raise UnsupportedSupplementError('variable supplementation requires glyf/gvar source and glyf stock')
    for tag in ('GDEF', 'BASE'):
        if tag in font and getattr(font[tag].table, 'VarStore', None) is not None:
            raise UnsupportedSupplementError('variable layout stores need a separate layout-preserving merger')
    for tag in ('GSUB', 'GPOS'):
        if tag in font and getattr(font[tag].table, 'FeatureVariations', None) is not None:
            raise UnsupportedSupplementError('conditional variable layout needs a separate layout-preserving merger')
    if 'VVAR' in font and ('vhea' not in stock or 'vmtx' not in stock):
        raise UnsupportedSupplementError('variable vertical metrics require a stock vertical contract')


def _restore_variations(merged, tables, source_order, stock_order):
    for tag, table in tables.items():
        merged[tag] = table
    merged['gvar'].variations.update({name: [] for name in stock_order})
    for tag, advance, maps in (
        ('HVAR', 'AdvWidthMap', ('AdvWidthMap', 'LsbMap', 'RsbMap')),
        ('VVAR', 'AdvHeightMap', ('AdvHeightMap', 'TsbMap', 'BsbMap', 'VOrgMap')),
    ):
        if tag not in merged:
            continue
        table = merged[tag].table
        for name in maps:
            mapping = getattr(table, name, None)
            if mapping is None and name != advance:
                continue
            if mapping is None:
                # An absent advance map means implicit glyph-ID indices. Make
                # that mapping explicit before appending invariant stock IDs.
                mapping = otTables.VarIdxMap()
                mapping.mapping = {glyph: index for index, glyph in enumerate(source_order)}
                setattr(table, name, mapping)
            mapping.mapping.update({glyph: otTables.NO_VARIATION_INDEX for glyph in stock_order})


class _SupplementMerger(Merger):
    """Retain layout using the names decoded from the serialized glyph IDs.

    A post-format-3 TrueType font has no persisted glyph names. Saving a subset
    without a replaced character's cmap entry can therefore rename a retained
    component from e.g. ``A`` to ``glyph00001`` when the merger reopens it. The
    glyph ID and outline have not changed. Load the otherwise dropped tables
    only after Merger has installed its final (collision-free) glyph names, so
    every MATH/BASE/kern reference is decoded against the same ID/name mapping
    as glyf, GSUB and GPOS. Never transplant pre-serialization name references.
    """

    def __init__(self, options, *, variable_source=False):
        super().__init__(options)
        self.input_orders = []
        self.retained_tables = {}
        self.source_kern = None
        self._opened_inputs = []
        self.variable_source = variable_source
        self.stock_index = 1 if variable_source else 0
        self.variation_tables = {}
        self.required_features = {}

    def _openFonts(self, files):
        # Merger opens each font once to copy its glyph names, then reopens it
        # for remapped tables. Keeping both passes retains another complete
        # large CFF buffer even though the first pass will never be read again.
        for font in self._opened_inputs:
            font.close()
            font.tables.clear()
        self._opened_inputs.clear()
        fonts = super()._openFonts(files)
        self._opened_inputs.extend(fonts)
        return fonts

    def _preMerge(self, font):
        index = len(self.input_orders)
        self.input_orders.append(list(font.getGlyphOrder()))
        if index == self.stock_index:
            self.retained_tables = {tag: font[tag] for tag in ('MATH', 'BASE', 'kern')
                                    if tag in font}
        elif 'kern' in font:
            self.source_kern = font['kern']
        if self.variable_source:
            if index == 0:
                self.variation_tables = {tag: font[tag] for tag in _VARIATION_TABLES if tag in font}
            font['glyf'].axisTags = [axis.axisTag for axis in self.variation_tables['fvar'].axes]
        super()._preMerge(font)
        # FontTools cannot combine LangSys records with required features.
        # Keep their already-remapped lookup objects and restore a required
        # feature for each merged script/language before final index mapping.
        for tag in ('GSUB', 'GPOS'):
            if tag not in font or font[tag].table.ScriptList is None:
                continue
            for record in font[tag].table.ScriptList.ScriptRecord:
                languages = [(None, record.Script.DefaultLangSys),
                             *((lang.LangSysTag, lang.LangSys) for lang in record.Script.LangSysRecord)]
                for language, system in languages:
                    if system is None or system.ReqFeatureIndex == 0xFFFF:
                        continue
                    key = (tag, record.ScriptTag, language)
                    self.required_features.setdefault(key, []).append(system.ReqFeatureIndex)
                    system.ReqFeatureIndex = 0xFFFF

    def _postMerge(self, font):
        for tag in ('GSUB', 'GPOS'):
            if tag not in font or font[tag].table.ScriptList is None:
                continue
            table = font[tag].table
            for record in table.ScriptList.ScriptRecord:
                languages = [(None, record.Script.DefaultLangSys),
                             *((lang.LangSysTag, lang.LangSys) for lang in record.Script.LangSysRecord)]
                for language, system in languages:
                    required = self.required_features.get((tag, record.ScriptTag, language), [])
                    if not required:
                        continue
                    feature = otTables.FeatureRecord()
                    feature.FeatureTag = required[0].FeatureTag
                    feature.Feature = otTables.Feature()
                    params = [item.Feature.FeatureParams for item in required]
                    if len(required) > 1 and any(value is not None for value in params):
                        raise UnsupportedSupplementError('required layout features have incompatible parameters')
                    feature.Feature.FeatureParams = params[0]
                    lookups, seen = [], set()
                    for item in required:
                        for lookup in item.Feature.LookupListIndex:
                            if id(lookup) not in seen:
                                lookups.append(lookup)
                                seen.add(id(lookup))
                    feature.Feature.LookupListIndex = lookups
                    feature.Feature.LookupCount = len(lookups)
                    system.ReqFeatureIndex = feature
                    table.FeatureList.FeatureRecord.append(feature)
            if table.FeatureList is not None:
                table.FeatureList.FeatureRecord.sort(key=lambda feature: feature.FeatureTag)
        super()._postMerge(font)

    def close_inputs(self):
        for font in self._opened_inputs:
            font.close()
            font.tables.clear()
        self._opened_inputs.clear()
        self.retained_tables.clear()
        self.variation_tables.clear()
        self.required_features.clear()
        self.source_kern = None


def _prepared_source_key(source, index, donor, stock, replace, upem, use_cff):
    digest = hashlib.sha256()
    with source.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    vertical = None
    if 'vhea' in stock and 'vmtx' in stock:
        if 'vhea' in donor and 'vmtx' in donor:
            vertical = 'source-vertical'
        else:
            # Horizontal-only sources inherit these exact target metrics. They
            # cannot reuse a donor prepared for a different vertical contract.
            vertical = hashlib.sha256(stock.getTableData('vhea') + stock.getTableData('vmtx')
                                      + stock.getTableData('cmap')).digest()
    return (digest.digest(), index, frozenset(replace), upem, use_cff, vertical)


def _cache_prepared_source(cache, key, font, converted, *, subset_complete=False,
                           source_cmap=None):
    if cache is None:
        return
    limit = 64 * 1024 * 1024
    outline_size = sum(entry['size'] for entry in cache.get('outline_entries', {}).values())
    # A prepared font cannot be smaller than its already-encoded CFF table.
    # Avoid serializing 60+ MiB twice per regional face just to reject that
    # cache entry once the shared outline cache has consumed the same budget.
    if getattr(font, '_luoshu_encoded_cff_size', 0) + outline_size > limit:
        return
    stream = BytesIO()
    augmented_cmap = None
    if source_cmap is not None:
        augmented_cmap = font['cmap']
        font['cmap'] = newTable('cmap')
        font['cmap'].decompile(source_cmap, font)
    try:
        _split_default_uvs_runs(font)
        font.save(stream, reorderTables=False)
    finally:
        if augmented_cmap is not None:
            font['cmap'] = augmented_cmap
    data = stream.getvalue()
    if len(data) + outline_size > limit:
        return
    entries = cache.setdefault('entries', {})
    total = sum(len(entry[0]) for entry in entries.values())
    while entries and total + len(data) + outline_size > limit:
        oldest = next(iter(entries))
        total -= len(entries.pop(oldest)[0])
    entries[key] = (data, converted, subset_complete)


def supplement(source: Path, stock: Path, output: Path, *, source_face_index: int = -1,
               stock_face_index: int = -1,
               replace_codepoints: set[int] | None = None,
               stock_weight: int | None = None,
               prepared_cache: dict | None = None,
               retained_stock_glyphs=None) -> dict:
    source, stock, output = Path(source), Path(stock), Path(output)
    if output.resolve() in {source.resolve(), stock.resolve()}:
        raise SupplementError('supplement output cannot overwrite either original font')
    output.parent.mkdir(parents=True, exist_ok=True)
    with ExitStack() as inputs:
        donor = inputs.enter_context(_open_static(source, source_face_index, preserve_axes=True))
        source_weight = int(donor['OS/2'].usWeightClass)
        requested_stock_weight = source_weight if stock_weight is None else int(stock_weight)
        with _open_static(stock, stock_face_index, requested_stock_weight) as original:
            variable_source = 'fvar' in donor
            if variable_source:
                _check_variable_source(donor, original)
            source_points = set(preferred_unicode_codepoints(donor))
            stock_points = unicode_codepoints(original)
            _consolidate_stock_cmap(original)
            requested = replacement_codepoints(source_points) if replace_codepoints is None else set(replace_codepoints)
            replace = requested & source_points & stock_points
            if not replace:
                raise SupplementError('source provides none of the requested stock text glyphs')
            retain = stock_points - replace
            source_name = copy.deepcopy(donor['name']) if 'name' in donor else None
            source_style = int(donor['head'].macStyle)
            # Scale only the replacement font. Its inherited vertical metrics
            # below are already in stock units and must not be scaled twice.
            upem = int(original['head'].unitsPerEm)
            source_outline = _outline(donor)
            use_cff = source_outline != 'TTF' or _outline(original) != 'TTF'
            cache_key = (_prepared_source_key(source, source_face_index, donor, original, replace, upem, use_cff)
                         if prepared_cache is not None else None)
            cached = prepared_cache.get('entries', {}).get(cache_key) if prepared_cache is not None else None
            # A user-supplied CJK subset often already contains precisely the
            # requested repertoire. Re-closing its 50k glyph GSUB graph needlessly
            # costs tens of seconds. Its full graph is already valid as-is.
            donor_subset_skipped = len(unicode_codepoints(donor) - replace) <= len(source_points) // 20
            source_subset_complete = False
            if cached is not None:
                stream = BytesIO(cached[0])
                stream.name = '<luoshu-prepared-source>'
                donor = inputs.enter_context(TTFont(stream, lazy=True,
                                                   recalcBBoxes=False, recalcTimestamp=False))
                source_subset_complete = bool(len(cached) > 2 and cached[2])
                if 'CFF ' in donor:
                    # Every prepared CFF has passed _mergeable_cff, so all
                    # name-based seac components have already been expanded.
                    donor._luoshu_cff_closed_outlines = True
            else:
                if donor_subset_skipped:
                    _limit_source_cmap(donor, replace)
                else:
                    _subset(donor, replace)
                    source_subset_complete = True
                if int(donor['head'].unitsPerEm) != upem:
                    scale_upem(donor, upem)
                _match_vertical_contract(donor, original)
            if retained_stock_glyphs is not None and not source_subset_complete:
                # The collection planner uses one complete donor closure for
                # every face, so their common CFF table has identical GIDs.
                _subset(donor, replace)
                source_subset_complete = True
            stock_variants = _uvs_pairs(original)
            _subset_stock(original, stock_points, replace, _uvs_pairs(donor))
            if (donor_subset_skipped and not source_subset_complete
                    and len(donor.getGlyphOrder()) + len(original.getGlyphOrder()) > 65535):
                # Unencoded unused source glyphs might otherwise consume the
                # remaining IDs; take the normal closure before refusing it.
                prior_order = tuple(donor.getGlyphOrder())
                _subset(donor, replace)
                source_subset_complete = True
                # No removed glyph means its complete outline dependency graph
                # is still the original graph; cmap/layout pruning does not
                # prevent reusing the independently converted outlines.
                donor_subset_skipped = tuple(donor.getGlyphOrder()) == prior_order
            selected_variant_fallbacks = set()
            if len(donor.getGlyphOrder()) + len(original.getGlyphOrder()) > 65535:
                # A regional stock CJK face can retain tens of thousands of
                # replaced glyphs solely for variation selectors absent from
                # the user's source. At the glyph-ID capacity limit, keep all
                # selector pairs but resolve those selected characters to the
                # selected base glyph. Non-selected characters and their UVS
                # remain exact stock glyphs. This policy is reported explicitly.
                donor_variants = _uvs_pairs(donor)
                selected_variant_fallbacks = {(selector, cp)
                    for selector, cp in stock_variants - donor_variants if cp in replace}
                if selected_variant_fallbacks:
                    original.close()
                    original = inputs.enter_context(_open_static(
                        stock, stock_face_index, requested_stock_weight))
                    _consolidate_stock_cmap(original)
                    _subset_stock(original, stock_points, replace, donor_variants | selected_variant_fallbacks)
            if retained_stock_glyphs is not None:
                if len(retained_stock_glyphs) + len(donor.getGlyphOrder()) > 65535:
                    raise UnsupportedSupplementError('shared collection outline pool exceeds the OpenType glyph limit')
                full_stock = inputs.enter_context(_open_static(stock, stock_face_index, requested_stock_weight))
                _restore_stock_outline_union(original, full_stock, retained_stock_glyphs)
            converted_source = converted_stock = 0
            if use_cff:
                converted_stock = _mergeable_cff(original)
                # A source hash, face, scale and exact subset contract fully
                # determine its outline graph. Target cmap and vertical tables
                # do not: regional TTC faces must not repeat this conversion.
                outline_key = ((cache_key[0], source_face_index, upem, tuple(donor.getGlyphOrder()),
                                frozenset(replace) if source_subset_complete else None)
                               if cache_key is not None else None)
                converted_source = cached[1] if cached is not None else _mergeable_cff(
                    donor, outline_cache=prepared_cache, outline_key=outline_key)
            if cached is None and prepared_cache is not None:
                _cache_prepared_source(prepared_cache, cache_key, donor, converted_source,
                                       subset_complete=source_subset_complete)
            if len(donor.getGlyphOrder()) + len(original.getGlyphOrder()) > 65535:
                raise UnsupportedSupplementError('preserving both layout closures exceeds the OpenType glyph limit')
            # Keep regional selector additions out of both reusable donor
            # caches. They belong to this target face's final cmap only.
            source_cmap = donor.getTableData('cmap') if selected_variant_fallbacks else None
            _add_selected_variants(donor, selected_variant_fallbacks)
            options = MergeOptions()
            # MATH/BASE/kern have no complete merger. Preserve their parsed
            # references from the merger's actual serialized glyph-ID mapping.
            stock_count, source_count = len(original.getGlyphOrder()), len(donor.getGlyphOrder())
            options.drop_tables = ['DSIG', 'FFTM', 'STAT', 'MATH', 'BASE', 'kern', 'VORG']
            if variable_source:
                options.drop_tables.extend(_VARIATION_TABLES)
            if use_cff:
                options.drop_tables.append('CFF ')
            with tempfile.TemporaryDirectory(prefix='.font-supplement-', dir=output.parent) as directory:
                directory = Path(directory)
                stock_file, source_file = directory / 'stock.otf', directory / 'source.otf'
                _split_default_uvs_runs(original)
                _split_default_uvs_runs(donor)
                original.save(stock_file, reorderTables=False)
                donor.save(source_file, reorderTables=False)
                merger = _SupplementMerger(options, variable_source=variable_source)
                merged = None
                try:
                    files = [source_file, stock_file] if variable_source else [stock_file, source_file]
                    expected_counts = [source_count, stock_count] if variable_source else [stock_count, source_count]
                    merged = merger.merge(files)
                    order = merged.getGlyphOrder()
                    if ([len(names) for names in merger.input_orders] != expected_counts
                            or order != [name for names in merger.input_orders for name in names]):
                        raise SupplementError('merger changed the serialized glyph IDs')
                    for tag, table in merger.retained_tables.items():
                        merged[tag] = table
                    if variable_source:
                        _restore_variations(merged, merger.variation_tables, *merger.input_orders)
                    if use_cff:
                        cache_vertical = 'VORG' not in donor
                        vorg = _merged_vorg([original, donor], order)
                        if vorg is not None:
                            merged['VORG'] = vorg
                        if cache_vertical and 'VORG' in donor and prepared_cache is not None:
                            # This is still the independent source font; after
                            # CFF pool merging its programs may be rebased.
                            # Cache exact measured origins so other stock
                            # contracts do not redraw the same 50k outlines.
                            _cache_prepared_source(prepared_cache, cache_key, donor, converted_source,
                                subset_complete=source_subset_complete, source_cmap=source_cmap)
                        merged['CFF '] = _merged_cff_table([original, donor])
                        merged['post'].formatType = 3.0
                    source_kern = merger.source_kern
                    if source_kern is not None:
                        for table in source_kern.kernTables:
                            if table.format != 0:
                                raise UnsupportedSupplementError('unsupported source legacy kerning format')
                        if 'kern' in merged:
                            merged['kern'].kernTables.extend(source_kern.kernTables)
                        else:
                            merged['kern'] = source_kern
                    if source_name is not None:
                        merged['name'] = source_name
                    merged['OS/2'].usWeightClass = source_weight
                    merged['head'].macStyle = source_style
                    merged.recalcBBoxes = False
                    merged.recalcTimestamp = False
                    temporary = directory / 'complete.otf'
                    _split_default_uvs_runs(merged)
                    merged.save(temporary, reorderTables=False)
                finally:
                    if merged is not None:
                        merged.close()
                        merged.tables.clear()
                    merger.close_inputs()
                with TTFont(temporary, lazy=True, recalcBBoxes=False, recalcTimestamp=False) as checked:
                    actual_points = set(preferred_unicode_codepoints(checked))
                    if actual_points != stock_points:
                        raise SupplementError('supplementation changed the stock Unicode repertoire')
                    if not stock_variants.issubset(_uvs_pairs(checked)):
                        raise SupplementError('supplementation dropped stock Unicode variation sequences')
                    for tag in ('head', 'hhea', 'OS/2', 'maxp', 'cmap', 'hmtx'):
                        checked[tag]
                    actual_format = 'TTF' if 'glyf' in checked else 'OTF'
                    glyph_count = len(checked.getGlyphOrder())
                    preserved_axes = ([axis.axisTag for axis in checked['fvar'].axes]
                                      if variable_source else [])
                os.replace(temporary, output)
            return {'replacedCodepoints': len(replace), 'retainedStockCodepoints': len(retain),
                    'coveredCodepoints': len(stock_points), 'sourceCodepoints': sorted(replace),
                    'actualFormat': actual_format, 'glyphCount': glyph_count,
                    'convertedSourceGlyphs': converted_source,
                    'convertedStockGlyphs': converted_stock, 'unitsPerEm': upem,
                    'preparedSourceCacheHit': cached is not None,
                    'outlineSourceCacheHit': bool(getattr(donor, '_luoshu_outline_cache_hit', False)),
                    'selectedVariantFallbacks': len(selected_variant_fallbacks),
                    'selectedVariantFallbackRanges': _variant_ranges(selected_variant_fallbacks),
                    'selectedVariantFallbackSource': ('selected-base-glyph' if selected_variant_fallbacks else None),
                    'sharedStockGlyphCount': len(retained_stock_glyphs) if retained_stock_glyphs is not None else None,
                    'sourceWeight': source_weight, 'retainsStockLayout': True,
                    'stockWeight': requested_stock_weight,
                    'preservedAxes': preserved_axes,
                    'stockInstanceAxes': getattr(original, '_luoshu_stock_instance_axes', {}),
                    'retainedStockUvsRecords': len(stock_variants)}
