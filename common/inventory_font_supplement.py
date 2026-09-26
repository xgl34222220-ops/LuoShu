#!/usr/bin/env python3
"""Replace selected Unicode glyphs while retaining the stock font's remainder.

Subsets retain OpenType layout and outline dependency closures. The stock subset
is merged first, keeping its TrueType hint programs; merger-renamed component
glyphs prevent an unreplaced composite from inheriting a replacement outline.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
import tempfile

from fontTools import subset
from fontTools.cffLib import CharStrings, FDArrayIndex, FDSelect, FontDict, GlobalSubrsIndex
from fontTools.fontBuilder import FontBuilder
from fontTools.merge import Merger
from fontTools.merge.options import Options as MergeOptions
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
from fontTools.ttLib.tables.DefaultTable import DefaultTable
from fontTools.ttLib.scaleUpem import scale_upem
from fontTools.misc.psCharStrings import calcSubrBias, T2WidthExtractor
from fontTools.pens.boundsPen import BoundsPen
from fontTools.unicodedata import script
from fontTools.varLib.instancer import instantiateVariableFont

from font_slot_coverage import preferred_unicode_codepoints, unicode_codepoints


class SupplementError(RuntimeError):
    pass


class UnsupportedSupplementError(SupplementError):
    """A known representational limit, distinct from corruption or I/O errors."""


def replacement_codepoints(points) -> set[int]:
    """Default user text roles; other scripts always retain their stock glyphs."""
    return {cp for cp in points if 0x20 <= cp <= 0x7E
            or script(chr(cp)) in {'Hani', 'Latn'}
            or 0x3000 <= cp <= 0x303F or 0xFF01 <= cp <= 0xFF60}


def _open_static(path: Path, index: int, weight: int | None = None) -> TTFont:
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
    worker.subset(font)
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


def _mergeable_cff(font: TTFont) -> int:
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
        return converted
    glyphs = font.getGlyphSet()
    order = font.getGlyphOrder()
    strings = {}
    for name in order:
        pen = T2CharStringPen(font['hmtx'].metrics[name][0], glyphs, roundTolerance=0)
        glyphs[name].draw(pen)
        strings[name] = pen.getCharString()
    for tag in ('glyf', 'loca', 'CFF ', 'CFF2', 'fpgm', 'prep', 'cvt ', 'gasp',
                'VORG', 'hdmx', 'LTSH', 'VDMX'):
        if tag in font:
            del font[tag]
    builder = FontBuilder(font=font)
    builder.setupCFF('LuoShuTextSubset', {}, strings, {})
    builder.setupMaxp()
    font['post'].formatType = 3.0
    return len(order)


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
    global_count = sum(len(font['CFF '].cff.GlobalSubrs) for font in fonts)
    new_bias = calcSubrBias([None] * global_count)
    global_offset = 0
    matrices = {tuple(font['CFF '].cff[0].FontMatrix) for font in fonts}
    if len(matrices) != 1:
        raise UnsupportedSupplementError('CFF top-level coordinate matrices differ after scaling')
    for font in fonts:
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
        # Decode every reachable subroutine in its glyph's FD context before
        # changing any global index. A shared subroutine can itself call local
        # subroutines and cannot be decoded independently with an empty private.
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
            if shift and not program.needsDecompilation():
                for index, token in enumerate(program.program):
                    if token == 'callgsubr':
                        if index == 0 or not isinstance(program.program[index - 1], int):
                            raise UnsupportedSupplementError('computed CFF global subroutine operand')
                        program.program[index - 1] += shift
            program.globalSubrs = global_subrs
        global_subrs.items.extend(list(old_global))
        global_offset += len(old_global)
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
            for name in order:
                pen = BoundsPen(glyphs)
                glyphs[name].draw(pen)
                ymax = pen.bounds[3] if pen.bounds else 0
                values[name] = int(round(ymax + font['vmtx'].metrics[name][1]))
        origins.update({merged_names[offset + index]: values[name] for index, name in enumerate(order)
                        if values[name] != table.defaultVertOriginY})
        offset += len(order)
    table.VOriginRecords = origins
    return table


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

    def __init__(self, options):
        super().__init__(options)
        self.input_orders = []
        self.retained_tables = {}
        self.source_kern = None
        self._opened_inputs = []

    def _openFonts(self, files):
        fonts = super()._openFonts(files)
        self._opened_inputs.extend(fonts)
        return fonts

    def _preMerge(self, font):
        index = len(self.input_orders)
        self.input_orders.append(list(font.getGlyphOrder()))
        if index == 0:
            self.retained_tables = {tag: font[tag] for tag in ('MATH', 'BASE', 'kern')
                                    if tag in font}
        elif index == 1 and 'kern' in font:
            self.source_kern = font['kern']
        super()._preMerge(font)

    def close_inputs(self):
        for font in self._opened_inputs:
            font.close()
        self._opened_inputs.clear()


def supplement(source: Path, stock: Path, output: Path, *, source_face_index: int = -1,
               stock_face_index: int = -1,
               replace_codepoints: set[int] | None = None,
               stock_weight: int | None = None) -> dict:
    source, stock, output = Path(source), Path(stock), Path(output)
    if output.resolve() in {source.resolve(), stock.resolve()}:
        raise SupplementError('supplement output cannot overwrite either original font')
    output.parent.mkdir(parents=True, exist_ok=True)
    with _open_static(source, source_face_index) as donor:
        source_weight = int(donor['OS/2'].usWeightClass)
        requested_stock_weight = source_weight if stock_weight is None else int(stock_weight)
        with _open_static(stock, stock_face_index, requested_stock_weight) as original:
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
            # A user-supplied CJK subset often already contains precisely the
            # requested repertoire. Re-closing its 50k glyph GSUB graph needlessly
            # costs tens of seconds. Its full graph is already valid as-is.
            donor_subset_skipped = (source_points == replace == unicode_codepoints(donor)
                                    and all(cp in replace for _selector, cp in _uvs_pairs(donor)))
            if not donor_subset_skipped:
                _subset(donor, replace)
            if int(donor['head'].unitsPerEm) != upem:
                scale_upem(donor, upem)
            _match_vertical_contract(donor, original)
            stock_variants = _uvs_pairs(original)
            retained_variant_bases = _stock_variants(original, replace, _uvs_pairs(donor))
            _subset(original, retain | retained_variant_bases, preserve_base=True)
            for table in original['cmap'].tables:
                if table.isUnicode() and table.format != 14:
                    table.cmap = {cp: glyph for cp, glyph in table.cmap.items() if cp not in replace}
            if donor_subset_skipped and len(donor.getGlyphOrder()) + len(original.getGlyphOrder()) > 65535:
                # Unencoded unused source glyphs might otherwise consume the
                # remaining IDs; take the normal closure before refusing it.
                _subset(donor, replace)
            source_outline, stock_outline = _outline(donor), _outline(original)
            converted_source = converted_stock = 0
            use_cff = source_outline != 'TTF' or stock_outline != 'TTF'
            if use_cff:
                converted_stock = _mergeable_cff(original)
                converted_source = _mergeable_cff(donor)
            if len(donor.getGlyphOrder()) + len(original.getGlyphOrder()) > 65535:
                raise UnsupportedSupplementError('preserving both layout closures exceeds the OpenType glyph limit')
            options = MergeOptions()
            # MATH/BASE/kern have no complete merger. Preserve their parsed
            # references from the merger's actual serialized glyph-ID mapping.
            stock_count, source_count = len(original.getGlyphOrder()), len(donor.getGlyphOrder())
            options.drop_tables = ['DSIG', 'FFTM', 'STAT', 'MATH', 'BASE', 'kern', 'VORG']
            if use_cff:
                options.drop_tables.append('CFF ')
            with tempfile.TemporaryDirectory(prefix='.font-supplement-', dir=output.parent) as directory:
                directory = Path(directory)
                stock_file, source_file = directory / 'stock.otf', directory / 'source.otf'
                original.save(stock_file, reorderTables=False)
                donor.save(source_file, reorderTables=False)
                merger = _SupplementMerger(options)
                merged = None
                try:
                    merged = merger.merge([stock_file, source_file])
                    order = merged.getGlyphOrder()
                    if ([len(names) for names in merger.input_orders] != [stock_count, source_count]
                            or order != [name for names in merger.input_orders for name in names]):
                        raise SupplementError('merger changed the serialized glyph IDs')
                    for tag, table in merger.retained_tables.items():
                        merged[tag] = table
                    if use_cff:
                        vorg = _merged_vorg([original, donor], order)
                        if vorg is not None:
                            merged['VORG'] = vorg
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
                    merged.save(temporary, reorderTables=False)
                finally:
                    if merged is not None:
                        merged.close()
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
                os.replace(temporary, output)
            return {'replacedCodepoints': len(replace), 'retainedStockCodepoints': len(retain),
                    'coveredCodepoints': len(stock_points), 'sourceCodepoints': sorted(replace),
                    'actualFormat': actual_format, 'glyphCount': glyph_count,
                    'convertedSourceGlyphs': converted_source,
                    'convertedStockGlyphs': converted_stock, 'unitsPerEm': upem,
                    'sourceWeight': source_weight, 'retainsStockLayout': True,
                    'stockWeight': requested_stock_weight,
                    'preservedAxes': [],
                    'stockInstanceAxes': getattr(original, '_luoshu_stock_instance_axes', {}),
                    'retainedStockUvsRecords': len(stock_variants)}
