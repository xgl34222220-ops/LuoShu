#!/usr/bin/env python3
"""Compile an installed Noto CJK collection and independently load every face."""
import argparse
import ctypes
import ctypes.util
import json
from pathlib import Path
import resource
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'common'))
sys.path.insert(0, str(ROOT / 'tests/android-root-gate'))
import composite_collection_build as builder
from synthetic_fonts import generate
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont


def outline(font, cp):
    glyphs = font.getGlyphSet()
    pen = DecomposingRecordingPen(glyphs)
    glyphs[font.getBestCmap()[cp]].draw(pen)
    return pen.value


def vertices(commands):
    # This fixture contains straight edges only; CFF reverses contour winding.
    assert all(operator in ('moveTo', 'lineTo', 'closePath') for operator, _ in commands)
    return {point for _, points in commands for point in points}


def freetype_load(path, indexes, coordinates=None):
    library = ctypes.util.find_library('freetype')
    if not library:
        raise RuntimeError('FreeType is required for the independent collection check')
    ft = ctypes.CDLL(library)
    ft.FT_Init_FreeType.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    ft.FT_New_Face.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long,
                             ctypes.POINTER(ctypes.c_void_p)]
    ft.FT_Get_Char_Index.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    ft.FT_Get_Char_Index.restype = ctypes.c_uint
    ft.FT_Load_Glyph.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int32]
    ft.FT_Done_Face.argtypes = [ctypes.c_void_p]
    ft.FT_Done_FreeType.argtypes = [ctypes.c_void_p]
    ft.FT_Set_Var_Design_Coordinates.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                              ctypes.POINTER(ctypes.c_long)]
    context = ctypes.c_void_p()
    if ft.FT_Init_FreeType(ctypes.byref(context)):
        raise RuntimeError('FreeType initialization failed')
    try:
        for index in indexes:
            face = ctypes.c_void_p()
            error = ft.FT_New_Face(context, str(path).encode(), index, ctypes.byref(face))
            if error:
                raise RuntimeError(f'FreeType rejected collection face {index}: {error}')
            try:
                for location in coordinates or (None,):
                    if location is not None:
                        vector = (ctypes.c_long * len(location))(*(round(v * 65536) for v in location))
                        error = ft.FT_Set_Var_Design_Coordinates(face, len(location), vector)
                        if error:
                            raise RuntimeError(f'FreeType rejected face {index} axes {location}: {error}')
                    for cp in map(ord, '中永Az09'):
                        glyph = ft.FT_Get_Char_Index(face, cp)
                        error = ft.FT_Load_Glyph(face, glyph, 1) if glyph else -1
                        if error:
                            raise RuntimeError(f'FreeType rejected face {index}, U+{cp:04X}: {error}')
            finally:
                ft.FT_Done_Face(face)
    finally:
        ft.FT_Done_FreeType(context)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stock', type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='luoshu-real-collection-') as directory:
        work = Path(directory)
        source, output = work / 'donor.ttf', work / 'compiled.ttc'
        generate(source, 1)
        report = builder.build(source, args.stock, output, work, 'real-noto-regression',
                               '/system/fonts/NotoSansCJK-Regular.ttc')
        print(json.dumps({'state': 'compiled', 'stockFaces': report['stockFaces'],
                          'buildSeconds': round(time.monotonic() - started, 3)},
                         separators=(',', ':')), flush=True)
        compiled = retained = 0
        for entry in report['faces']:
            index = entry['index']
            with TTFont(args.stock, fontNumber=index, lazy=True) as original, \
                    TTFont(output, fontNumber=index, lazy=True) as result, TTFont(source) as donor:
                assert original.getBestCmap() == result.getBestCmap(), f'face {index}: cmap changed'
                assert original.getGlyphOrder() == result.getGlyphOrder(), f'face {index}: glyph IDs changed'
                assert builder.protected(original) == builder.protected(result), f'face {index}: contract changed'
                for cp in map(ord, '中永Az09'):
                    if entry['mode'] == 'compiled':
                        assert outline(original, cp) != outline(result, cp), f'face {index}: donor not applied'
                        assert vertices(outline(donor, cp)) == vertices(outline(result, cp)), \
                            f'face {index}: donor shape changed'
                        name = result.getBestCmap()[cp]
                        char = result['CFF '].cff.topDictIndex[0].CharStrings[name]
                        char.draw(DecomposingRecordingPen(None))
                        assert char.width == result['hmtx'][name][0], f'face {index}: CFF width disagrees'
                    else:
                        assert outline(original, cp) == outline(result, cp), f'face {index}: retained shape changed'
            if entry['mode'] == 'compiled':
                compiled += 1
            else:
                retained += 1
        assert compiled and retained, 'The Noto fixture must include proportional and specialized faces'
        freetype_load(output, range(report['stockFaces']))
        print(json.dumps({'result': 'PASS', 'stockFaces': report['stockFaces'],
                          'compiledFaces': compiled, 'retainedFaces': retained,
                          'outputBytes': output.stat().st_size,
                          'stockSha256': report['stockSha256'],
                          'outputSha256': report['outputSha256'],
                          'elapsedSeconds': round(time.monotonic() - started, 3),
                          'maxRssKiB': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                          'freetypeFaceLoads': report['stockFaces']}, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
