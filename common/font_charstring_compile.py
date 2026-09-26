"""Compile generated static Type 2 outlines without a large Python token stream.

The bundled FontTools specializer and number encoders remain authoritative. A
bounded cache avoids encoding the same relative coordinate thousands of times.
This helper accepts T2CharStringPen drawing commands, not arbitrary CFF programs.
"""
from functools import lru_cache

from fontTools.cffLib.specializer import specializeCommands
from fontTools.misc.psCharStrings import T2CharString, encodeFixed, encodeIntT2
from fontTools.misc.roundTools import otRound


NUMBER_CACHE_LIMIT = 16384
_OPERATOR_BYTES = {operator: bytes(code) for operator, code in T2CharString.opcodes.items()}


@lru_cache(maxsize=NUMBER_CACHE_LIMIT, typed=True)
def _encode_number(value):
    # Keep operand types distinct so each FontTools encoder remains
    # authoritative, including its exception behavior for invalid values.
    return encodeIntT2(value) if isinstance(value, int) else encodeFixed(value)


def compile_static_pen(pen):
    """Return (compiled bytes, original program token count) for a CFF1 pen.

    Keep specialization unchanged: bypassing it changes topology and can change
    accumulated 16.16 coordinates. The token count retains the caller's exact
    conservative error bound when measuring a converted glyph's vertical origin.
    """
    if pen._CFF2:
        raise ValueError('compile_static_pen requires a static CFF1 drawing pen')
    commands = specializeCommands(pen._commands, generalizeFirst=False, maxstack=48)
    chunks = []
    token_count = 1  # endchar
    if pen._width is not None:
        chunks.append(_encode_number(otRound(pen._width)))
        token_count += 1
    for operator, args in commands:
        chunks.append(b''.join(map(_encode_number, args)))
        token_count += len(args)
        if operator:
            chunks.append(_OPERATOR_BYTES[operator])
            token_count += 1
    chunks.append(b'\x0e')
    return b''.join(chunks), token_count
