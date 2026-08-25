#!/usr/bin/env python3
# Packaging contract marker: device-font-slot-build-v2
"""Preserve target Android family identity in generated slot fonts."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import device_font_slot_build_base as _base
from device_font_slot_build_base import *  # noqa: F401,F403

_WEIGHT_NAMES = {
    100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Regular",
    500: "Medium", 600: "SemiBold", 700: "Bold", 800: "ExtraBold", 900: "Black",
}


def _clean_family(value: str) -> str:
    return " ".join(str(value or "").replace("\x00", " ").split()).strip()


def _postscript(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    return (cleaned or "LuoShuFont")[:63]


def target_family_identity(slot: dict[str, Any]) -> tuple[str, str, str, str]:
    # The external Android XML owns family selection. A deterministic internal identity lets slots
    # with the same weight/metric/role contract share one generated font safely and dramatically
    # reduces full-outline rewrites on OEM ROMs with many alias families.
    family = "LuoShu System"
    try:
        weight = int(slot.get("weight") or 400)
    except (TypeError, ValueError):
        weight = 400
    nearest = min(_WEIGHT_NAMES, key=lambda value: abs(value - weight))
    weight_name = _WEIGHT_NAMES[nearest]
    italic = str(slot.get("style", "normal")).lower() in ("italic", "oblique")
    typographic_style = f"{weight_name} Italic" if italic else weight_name
    legacy_style = "Bold Italic" if italic and nearest >= 700 else (
        "Italic" if italic else ("Bold" if nearest >= 700 else "Regular")
    )
    postscript = _postscript(f"LuoShuSystem-{typographic_style}")
    return family, legacy_style, typographic_style, postscript


def set_slot_identity(font: Any, slot: dict[str, Any]) -> None:
    if "name" not in font:
        return
    family, legacy_style, typographic_style, postscript = target_family_identity(slot)
    full_name = f"{family} {typographic_style}".strip()
    unique_id = _postscript(f"LuoShu-v2.4.0-{postscript}")
    table = font["name"]
    values = {
        1: family,
        2: legacy_style,
        3: unique_id,
        4: full_name,
        6: postscript,
        16: family,
        17: typographic_style,
    }
    for name_id, value in values.items():
        table.setName(value, name_id, 3, 1, 0x409)


_base.set_slot_identity = set_slot_identity


def main() -> int:
    return _base.main()


if __name__ == "__main__":
    raise SystemExit(main())
