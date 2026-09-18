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

DYNAMIC_OVERLAY_PATH = "/system/fonts/MiSansVF_Overlay.ttf"
DYNAMIC_OVERLAY_TARGET = "/data/system/fonts/theme_webview/Roboto-Regular.ttf"


def preserved_dynamic_alias(data: dict, logical: str) -> bool:
    """Only the ROM-proven, framework-managed HyperOS WebView alias is exempt."""
    if logical != DYNAMIC_OVERLAY_PATH:
        return False
    alias = (data.get("preservedDynamicAliases") or {}).get(logical, {})
    if (alias.get("source") == "hyperos-framework-symlink"
            and alias.get("target") == DYNAMIC_OVERLAY_TARGET):
        return True
    # Test6 recorded this exact ROM symlink but incorrectly assumed its init
    # seed remained Roboto after the framework had selected a locale font.
    # This migration allows reapply before its deferred inventory refresh.
    slot = (data.get("slots") or {}).get(logical, {})
    return (slot.get("source") == "hyperos-rom-reference"
            and slot.get("metricsReferencePath") == "/system/fonts/Roboto-Regular.ttf")

_EXCLUDED = (
    "italic", "oblique", "emoji", "symbol", "serif", "arabic",
    "hebrew", "thai", "devanagari", "bengali", "tamil", "telugu", "malayalam",
    "gujarati", "gurmukhi", "kannada", "khmer", "lao", "tibetan", "myanmar",
    "vietnam", "japanese", "korean", "hangul", "hiragana", "katakana", "odia", "oriya",
    "cjkjp", "cjkkr",
)
_PREFIXES = (
    "MiSans", "XiaomiSans", "MiLanPro", "Mitype", "MiClock", "AndroidClock",
    "Roboto", "GoogleSans", "SourceSansPro",
)
_NOTO_UI_PREFIXES = (
    "NotoSans-", "NotoSansUI-", "NotoSansSC", "NotoSansTC", "NotoSansHK",
    "NotoSansHans", "NotoSansHant", "NotoSansCJKSC", "NotoSansCJKTC", "NotoSansCJKHK",
    "NotoSansCJKsc", "NotoSansCJKtc", "NotoSansCJKhk",
)
# These are Latin UI families, not language fallback prefixes. v4.3.0's
# narrowed NotoSans whitelist accidentally removed them from scanning, staging
# and boot repair. Match exact family names or a hyphenated style suffix, never
# restore the broad NotoSans* matcher that copied CJK into unrelated scripts.
_NOTO_LATIN_UI_FAMILIES = (
    "NotoSansMono", "NotoSansDisplay", "NotoSansCondensed",
    "NotoSansSemiCondensed", "NotoSansExtraCondensed",
    "NotoSansVF", "NotoSansVariable", "NotoSansUIVF",
    "NotoSansMonoVF", "NotoSansDisplayVF", "NotoSansCondensedVF",
)
_UI_NAMES = frozenset({
    "NotoSans.ttf", "NotoSans.otf", "NotoSansUI.ttf", "NotoSansUI.otf",
    "DroidSans.ttf", "DroidSans-Regular.ttf", "DroidSans-Bold.ttf", "Clockopia.ttf",
    "DroidSansMono.ttf", "DroidSansFallback.ttf",
})
_NUMERIC = frozenset(f"{weight}.ttf" for weight in (100, 200, 300, 350, 400, 500, 600, 700, 800, 900))


def safe_physical_font_name(name: str) -> bool:
    """Match the full mapper's single-face, upright physical filename policy."""
    if Path(name).name != name or not name.endswith((".ttf", ".otf")):
        return False
    lower = name.lower()
    # "SemiCondensed" contains the substring "icon" across a word boundary.
    # Ignore that style token only; an additional Icon/Icons token still fails.
    if "icon" in lower.replace("semicondensed", ""):
        return False
    if any(token in lower for token in _EXCLUDED):
        return False
    if name.startswith((
        "MiSansJP", "MiSansJp", "MiSansKR", "MiSansKr",
        "MiSansTC", "MiSansHant", "MiSansHK", "MiSansL3",
        "XiaomiSansJP", "XiaomiSansKR", "XiaomiSansTC", "XiaomiSansHant",
        "XiaomiSansHK", "XiaomiSansL3",
        "NotoSansSC", "NotoSansTC", "NotoSansHK", "NotoSansHans",
        "NotoSansHant", "NotoSansCJK",
    )) or any(token in name for token in ("CJKJP", "CJKKR")):
        # These are language/repertoire fallbacks, not generic UI faces. A
        # single user donor rarely covers TC/HK/L3 or every regional CJK set;
        # replacing them is a direct route to tofu/garbled text.
        return False
    # NotoSans is also the prefix of hundreds of unrelated script fallbacks.
    # A blacklist cannot enumerate them reliably; replacing each with the full
    # selected CJK donor both removes language coverage and multiplies storage.
    stem = Path(name).stem
    return (name.startswith(_PREFIXES + _NOTO_UI_PREFIXES)
            or name in _UI_NAMES or name in _NUMERIC
            or any(stem == family or stem.startswith(family + "-")
                   for family in _NOTO_LATIN_UI_FAMILIES))
