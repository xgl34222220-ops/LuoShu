#!/usr/bin/env python3
"""Test helper: give a fixture font the clock characters required by the clock glyph gate.

DejaVu Sans (the CI source fixture) lacks U+FF1A. Real LuoShu sources are
composites whose CJK base carries it; map any missing clock character onto the
existing colon/space glyph so clock-slot fixtures keep exercising the builder.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from fontTools.ttLib import TTFont  # noqa: E402

import font_role_check  # noqa: E402


def with_clock_glyphs(source: Path, output: Path) -> Path:
    font = TTFont(str(source), recalcTimestamp=False)
    try:
        best = font.getBestCmap() or {}
        colon = best.get(0x003A)
        space = best.get(0x0020) or colon
        for table in font["cmap"].tables:
            if not table.isUnicode():
                continue
            for codepoint in font_role_check.CLOCK_REQUIRED:
                if codepoint not in table.cmap and (codepoint <= 0xFFFF or table.format in (12, 13)):
                    table.cmap[codepoint] = space if codepoint in (0x2007, 0x202F) else colon
        font.save(str(output))
    finally:
        font.close()
    return output
