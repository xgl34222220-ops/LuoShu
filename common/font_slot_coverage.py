"""Small cmap-only helpers for preserving stock primary/CJK fallback routing.

These helpers never load glyph outlines. Coverage is measured from the trusted
stock face during inventory scanning, not inferred from an OEM filename.
"""
from __future__ import annotations


def is_han(codepoint: int) -> bool:
    return (codepoint == 0x3007 or 0x3400 <= codepoint <= 0x4DBF
            or 0x4E00 <= codepoint <= 0x9FFF or 0xF900 <= codepoint <= 0xFAFF
            or 0x20000 <= codepoint <= 0x2EE5F or 0x2F800 <= codepoint <= 0x2FA1F
            or 0x30000 <= codepoint <= 0x3347F)


def is_cjk_punctuation(codepoint: int) -> bool:
    # Fullwidth letters and digits are deliberately not punctuation.
    return (0x3000 <= codepoint <= 0x303F or 0xFE10 <= codepoint <= 0xFE19
            or 0xFE30 <= codepoint <= 0xFE4F or 0xFF01 <= codepoint <= 0xFF0F
            or 0xFF1A <= codepoint <= 0xFF20 or 0xFF3B <= codepoint <= 0xFF40
            or 0xFF5B <= codepoint <= 0xFF65)


def is_cjk_routing_codepoint(codepoint: int) -> bool:
    return is_han(codepoint) or is_cjk_punctuation(codepoint)


def unicode_codepoints(font) -> set[int]:
    """Conservative stock coverage: any Unicode mapping prevents a false prune."""
    return {cp for table in font['cmap'].tables if table.isUnicode()
            and table.format != 14 for cp, glyph in table.cmap.items()
            if glyph != '.notdef'}


def preferred_unicode_codepoints(font) -> set[int]:
    """Only the selected Unicode cmap can prove a rendered fallback glyph.

    A format 4 entry is not reachable if a preferred full-repertoire cmap omits
    it. Do not use the union of alternate charmaps as evidence of coverage.
    """
    return {cp for cp, glyph in (font.getBestCmap() or {}).items() if glyph != '.notdef'}


def summarize_coverage(font, *, points=None) -> dict:
    points = unicode_codepoints(font) if points is None else points
    han = sum(is_han(cp) for cp in points)
    latin = sum(0x41 <= cp <= 0x5A or 0x61 <= cp <= 0x7A for cp in points)
    return {'hasHan': bool(han), 'hasLatin': bool(latin), 'hanCount': han,
            'latinCount': latin, 'unicodeCount': len(points),
            'cjkPunctuation': sorted(cp for cp in points if is_cjk_punctuation(cp))}


def valid_coverage(value) -> bool:
    if not isinstance(value, dict):
        return False
    counts = [value.get(key) for key in ('hanCount', 'latinCount', 'unicodeCount')]
    if any(type(count) is not int or not 0 <= count <= 0x110000 for count in counts):
        return False
    han, latin, total = counts
    punctuation = value.get('cjkPunctuation')
    return (type(value.get('hasHan')) is bool and value['hasHan'] == (han > 0)
            and type(value.get('hasLatin')) is bool and value['hasLatin'] == (latin > 0)
            and han <= total and latin <= min(52, total)
            and isinstance(punctuation, list) and len(punctuation) <= 256
            and all(type(cp) is int and is_cjk_punctuation(cp) for cp in punctuation)
            and len(set(punctuation)) == len(punctuation))


def remove_cjk_mappings(font, fallback_codepoints: frozenset[int],
                        stock_punctuation: frozenset[int] = frozenset()) -> int:
    """Remove only new CJK mappings whose staged fallback retains the glyph.

    No matching fallback UVS evidence is available here. Keep every source UVS
    record and its base character together, including non-default variants. A
    fallback supporting the base alone does not prove it preserves the variant.
    """
    variation_bases = {cp for table in font['cmap'].tables if table.format == 14
                       for records in table.uvsDict.values() for cp, _glyph in records}

    def remove(cp):
        return (cp in fallback_codepoints and is_cjk_routing_codepoint(cp)
                and cp not in stock_punctuation and cp not in variation_bases)

    removed = set()
    for table in font['cmap'].tables:
        if not table.isUnicode() or table.format == 14:
            continue
        discarded = [cp for cp in table.cmap if remove(cp)]
        removed.update(discarded)
        for cp in discarded:
            del table.cmap[cp]
    return len(removed)
