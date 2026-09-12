"""Safe physical font targets used by the legacy HyperOS full mapper.

The stock scanner must capture metrics for these targets before the mapper
replaces them. Keep this policy aligned with hyperos_full_coverage.sh; the
cross-policy regression exercises that shell implementation directly.
"""
from __future__ import annotations

from pathlib import Path


PARTITIONS = frozenset({
    "system", "system_ext", "product", "mi_ext", "vendor", "odm", "oem",
    "my_product", "hw_product", "cust",
})

_EXCLUDED = (
    "italic", "oblique", "emoji", "symbol", "icon", "serif", "arabic",
    "hebrew", "thai", "devanagari", "bengali", "tamil", "telugu", "malayalam",
    "gujarati", "gurmukhi", "kannada", "khmer", "lao", "tibetan", "myanmar",
    "vietnam", "japanese", "korean", "hangul", "hiragana", "katakana",
)
_PREFIXES = (
    "MiSans", "XiaomiSans", "MiLanPro", "Mitype", "MiClock", "AndroidClock",
    "Roboto", "GoogleSans", "NotoSans", "SourceSansPro",
)
_NUMERIC = frozenset(f"{weight}.ttf" for weight in (100, 200, 300, 350, 400, 500, 600, 700, 800, 900))


def safe_physical_font_name(name: str) -> bool:
    """Match the full mapper's single-face, upright physical filename policy."""
    if Path(name).name != name or not name.endswith((".ttf", ".otf")):
        return False
    if any(token in name.lower() for token in _EXCLUDED):
        return False
    if name.startswith(("MiSansJP", "MiSansJp", "MiSansKR", "MiSansKr")) or any(
        token in name for token in ("CJKJP", "CJKKR")
    ):
        return False
    return (name.startswith(_PREFIXES) or name == "Clockopia.ttf" or name in _NUMERIC
            or name.startswith("DroidSans") and name.endswith(".ttf"))
