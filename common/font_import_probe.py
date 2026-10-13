#!/usr/bin/env python3
"""Return import-time font family and real OS/2 weight metadata."""
from __future__ import annotations

import argparse
from pathlib import Path

from fontTools.ttLib import TTFont

try:  # common/ is the script directory on device and in CI
    from font_capability import reconcile_weight, weight_from_name
except Exception:  # pragma: no cover
    reconcile_weight = None
    weight_from_name = None


CJK_UI_PROBES = tuple(map(ord, "中文字体系统默认洛书汉字ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"))


def clean(value: object, fallback: str = "") -> str:
    text = str(value or fallback).replace("|", " ").replace("\t", " ")
    return " ".join(text.replace("\r", " ").replace("\n", " ").split())


def debug_name(font: TTFont, name_id: int, fallback: str = "") -> str:
    try:
        return clean(font["name"].getDebugName(name_id), fallback)
    except Exception:
        return fallback


def best_family(font: TTFont) -> str:
    try:
        return clean(font["name"].getBestFamilyName(), debug_name(font, 1, "ImportedFont"))
    except Exception:
        return debug_name(font, 1, "ImportedFont")


def best_subfamily(font: TTFont) -> str:
    try:
        return clean(font["name"].getBestSubFamilyName(), debug_name(font, 2, "Regular"))
    except Exception:
        return debug_name(font, 2, "Regular")


def inspect(path: Path) -> tuple[str, str, int, bool, bool, bool]:
    kwargs = {"lazy": True, "recalcTimestamp": False}
    with path.open("rb") as stream:
        if stream.read(4) == b"ttcf":
            kwargs["fontNumber"] = 0
    font = TTFont(str(path), **kwargs)
    try:
        try:
            os2_weight = int(font["OS/2"].usWeightClass)
        except Exception:
            os2_weight = None
        subfamily = best_subfamily(font)
        if reconcile_weight is not None:
            # usWeightClass wins, except the generic 400 (or a missing value)
            # contradicted by an explicit style name such as "ExtraBold".
            weight, _source = reconcile_weight(os2_weight, weight_from_name(subfamily))
        else:
            weight = os2_weight if os2_weight is not None else 400
        weight = max(1, min(1000, weight))
        italic = "italic" in subfamily.lower() or "oblique" in subfamily.lower()
        try:
            italic = italic or bool(int(font["head"].macStyle) & 0x02)
        except Exception:
            pass
        try:
            italic = italic or bool(int(font["OS/2"].fsSelection) & 0x01)
        except Exception:
            pass
        cmap = font.getBestCmap() or {}
        supports_cjk = all(codepoint in cmap for codepoint in CJK_UI_PROBES)
        return best_family(font), subfamily, weight, italic, "fvar" in font, supports_cjk
    finally:
        font.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("font")
    args = parser.parse_args()
    family, subfamily, weight, italic, variable, supports_cjk = inspect(Path(args.font))
    print(
        f"{family}|{subfamily}|{weight}|{str(italic).lower()}|"
        f"{str(variable).lower()}|{str(supports_cjk).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
