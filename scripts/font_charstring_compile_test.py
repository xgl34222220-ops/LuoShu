#!/usr/bin/env python3
"""Exact bytes and numeric behavior for converted CFF1 outlines."""
from pathlib import Path
import logging
import random
import sys
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'common'), str(ROOT / 'common/python/lib/python3.14/site-packages')]
from fontTools.misc.psCharStrings import encodeIntT2, encodeFixed, T2CharString
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.recordingPen import RecordingPen
from font_charstring_compile import compile_static_pen, _encode_number, NUMBER_CACHE_LIMIT


class CharstringCompileTests(unittest.TestCase):
    def setUp(self):
        _encode_number.cache_clear()

    def check_pen(self, pen):
        reference = pen.getCharString()
        tokens = len(reference.program)
        reference.compile()
        compiled, actual_tokens = compile_static_pen(pen)
        self.assertEqual(compiled, reference.bytecode)
        self.assertEqual(actual_tokens, tokens)
        private = SimpleNamespace(nominalWidthX=0, defaultWidthX=0, Subrs=[])
        a = T2CharString(bytecode=compiled, private=private, globalSubrs=[])
        b = T2CharString(bytecode=reference.bytecode, private=private, globalSubrs=[])
        actual, expected = RecordingPen(), RecordingPen()
        a.draw(actual); b.draw(expected)
        self.assertEqual(actual.value, expected.value)
        self.assertEqual(a.width, b.width)

    def test_curves_lines_movements_width_and_empty_glyph(self):
        for width in (None, 0, 600, 600.5):
            self.check_pen(T2CharStringPen(width, None, roundTolerance=0))
            pen = T2CharStringPen(width, None, roundTolerance=0)
            pen.moveTo((100 / 3, -20 / 3)); pen.lineTo((200, -20 / 3))
            pen.lineTo((200, 300)); pen.curveTo((200, 400 / 3), (500 / 3, 480), (600, 600))
            pen.qCurveTo((17, 23), (100, -200), (500, 250))
            pen.closePath(); self.check_pen(pen)

    def test_stack_splitting_and_specialization_rounding(self):
        rng = random.Random(4763)
        for _ in range(50):
            pen = T2CharStringPen(rng.randrange(2048), None, roundTolerance=0)
            pen.moveTo((rng.randrange(-50, 50) / 3, 100))
            for index in range(60):
                if index % 3:
                    pen.curveTo(*[(rng.randrange(-2000, 2000) / 3, rng.randrange(-2000, 2000) / 3) for _ in range(3)])
                else:
                    pen.lineTo((rng.randrange(-2000, 2000), rng.randrange(-2000, 2000)))
            pen.closePath(); self.check_pen(pen)

    def test_integer_float_boundaries_and_half_ties(self):
        values = [-32768, -1132, -1131, -108, -107, -1, 0, 1, 107, 108, 1131, 1132, 32767]
        for integer in values:
            for value in (integer, float(integer), integer + 0.5 / 65536, integer - 0.5 / 65536):
                encoder = encodeIntT2 if isinstance(value, int) else encodeFixed
                try:
                    expected = encoder(value)
                except Exception as error:
                    with self.assertRaises(type(error)):
                        _encode_number(value)
                else:
                    self.assertEqual(_encode_number(value), expected)
        self.assertEqual(_encode_number(-0.0), encodeFixed(-0.0))

    def test_nonfinite_and_typed_cache_exceptions(self):
        for value in (float('nan'), float('inf'), float('-inf'), 32768.5, -32769.5):
            try:
                encodeFixed(value)
            except Exception as error:
                with self.assertRaises(type(error)):
                    _encode_number(value)
            else:
                self.fail('expected FontTools to reject invalid real operand')
        logger = logging.getLogger('fontTools.misc.psCharStrings')
        old_disabled = logger.disabled
        logger.disabled = True
        try:
            # Check both operand types through their original encoder,
            # including FontTools' legacy 32-bit integer compatibility branch.
            integer, real = _encode_number(40000), _encode_number(40000.0)
            self.assertEqual(integer, encodeIntT2(40000))
            self.assertEqual(real, encodeFixed(40000.0))
        finally:
            logger.disabled = old_disabled

    def test_cache_bound_and_clear(self):
        # Valid fractional operands exercise more unique keys than the cache.
        for index in range(NUMBER_CACHE_LIMIT + 1024):
            _encode_number(index / 65536)
        self.assertEqual(_encode_number.cache_info().currsize, NUMBER_CACHE_LIMIT)
        _encode_number.cache_clear()
        self.assertEqual(_encode_number.cache_info().currsize, 0)

    def test_cff2_is_not_silently_reencoded_as_cff1(self):
        with self.assertRaises(ValueError):
            compile_static_pen(T2CharStringPen(None, None, CFF2=True))


if __name__ == '__main__':
    unittest.main()
