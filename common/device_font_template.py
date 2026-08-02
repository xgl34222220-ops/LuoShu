#!/usr/bin/env python3
# Packaging contract markers: device-font-template-v1; CAPTURE_REVISION = 2
"""Script-aware Android font template policy.

The original scanner remains the source of truth for XML parsing and stock metrics.
This layer fixes one over-broad rule: Android language fallback families are not all
untouchable. Chinese and explicit Latin text fallbacks are candidates for replacement;
emoji, symbols and unsupported scripts remain protected.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import device_font_template_base as _base
from device_font_template_base import *  # noqa: F401,F403

_ORIGINAL_CLASSIFY_ROLES = _base.classify_roles

_CJK_LANG_PREFIXES = (
    "zh", "cmn", "yue", "wuu", "hak", "nan", "hans", "hant",
)
_LATIN_LANG_PREFIXES = (
    "en", "fr", "de", "es", "it", "pt", "nl", "sv", "no", "da", "fi",
    "pl", "cs", "sk", "sl", "hr", "hu", "ro", "tr", "vi", "id", "ms",
    "latn",
)
_UNSUPPORTED_LANG_PREFIXES = (
    "ja", "ko", "ar", "fa", "ur", "he", "iw", "th", "lo", "km", "my",
    "hi", "bn", "gu", "kn", "ml", "mr", "ne", "pa", "si", "ta", "te",
    "bo", "ka", "hy", "am", "ethi", "deva", "arab", "hebr", "thai",
    "jpan", "kore",
)
_CJK_IDENTITY_TOKENS = (
    "hans", "hant", "zh-cn", "zh-tw", "zh-hk", "zh-hans", "zh-hant",
    "notosanssc", "notosanstc", "sourcehans", "sourcehan-sans-sc",
    "sourcehan-sans-tc", "misanstcvf", "misansl3", "droidsansfallback",
)
_LATIN_IDENTITY_TOKENS = (
    "latin", "roboto", "google-sans", "source-sans", "sys-sans-en",
    "op-sans-en", "opposans-en", "opsans-en",
)


def _attributes(ref: Any) -> dict[str, str]:
    raw = getattr(ref, "family_attrs", {}) or {}
    return {str(key).strip().lower(): str(value).strip() for key, value in raw.items() if value}


def _tokens(value: str) -> tuple[str, ...]:
    normalized = _base.normalize(value)
    for separator in (",", ";", ":"):
        normalized = normalized.replace(separator, " ")
    return tuple(item for item in normalized.split() if item)


def fallback_script(ref: Any, resolved: Path | None = None) -> str:
    """Return cjk, latin or other for an actual Android fallback family."""
    attrs = _attributes(ref)
    language_values = " ".join(
        value for key, value in attrs.items() if key in ("lang", "language", "locale")
    )
    language_tokens = _tokens(language_values)

    for token in language_tokens:
        if token.startswith(_UNSUPPORTED_LANG_PREFIXES):
            return "other"
    for token in language_tokens:
        if token.startswith(_CJK_LANG_PREFIXES):
            return "cjk"
    for token in language_tokens:
        if token.startswith(_LATIN_LANG_PREFIXES):
            return "latin"

    family = _base.normalize(getattr(ref, "family", ""))
    declared = _base.normalize(getattr(ref, "declared", ""))
    postscript = _base.normalize(getattr(ref, "postscript_name", ""))
    filename = _base.normalize(resolved.name if resolved else "")
    identity = " ".join((family, declared, postscript, filename))
    if any(token in identity for token in _CJK_IDENTITY_TOKENS):
        return "cjk"
    if any(token in identity for token in _LATIN_IDENTITY_TOKENS):
        return "latin"
    return "other"


def classify_roles(ref: Any, resolved: Path | None) -> list[str]:
    roles = list(_ORIGINAL_CLASSIFY_ROLES(ref, resolved))
    attrs = _attributes(ref)
    has_language = any(key in attrs for key in ("lang", "language", "locale"))
    has_fallback_for = any(key in attrs for key in ("fallbackfor", "fallback-for"))

    # AOSP uses variant="elegant|compact" on ordinary text families. The previous
    # rule treated variant alone as a fallback marker and silently skipped those UI
    # slots, which left parts of one ROM on the stock font.
    if "fallback" in roles and not has_language and not has_fallback_for:
        roles = [role for role in roles if role != "fallback"]
        if not roles:
            roles.append("other")
        return list(dict.fromkeys(roles))

    if "fallback" in roles:
        kind = fallback_script(ref, resolved)
        if kind in ("cjk", "latin"):
            roles = [role for role in roles if role != "fallback"]
            roles.append(f"fallback-{kind}")
            # Keep Android's XML order and language attributes. Marking the slot as a
            # UI candidate only allows the planner to assess source glyph coverage;
            # unsupported sources are rejected by device_font_slot_plan.py.
            roles.append("global-ui")
        else:
            roles.append("fallback-other")
    return list(dict.fromkeys(roles))


# build_template() resolves this symbol in the base module at runtime.
_base.classify_roles = classify_roles


def main() -> int:
    return _base.main()


if __name__ == "__main__":
    raise SystemExit(main())
