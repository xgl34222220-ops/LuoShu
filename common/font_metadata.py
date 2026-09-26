#!/usr/bin/env python3
"""Inspect a font file and expose stable SHA-256 plus per-face metadata."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from fontTools.ttLib import TTCollection, TTFont

CJK_PROBES = tuple(map(ord, "中文字体系统默认洛书汉字国一的。"))
LATIN_PROBES = tuple(map(ord, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"))
DIGIT_PROBES = tuple(map(ord, "0123456789"))
PUNCT_PROBES = tuple(map(ord, "，。！？；：（）,.!?;:()[]+-/%"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_collection(path: Path) -> bool:
    with path.open("rb") as stream:
        return stream.read(4) == b"ttcf"


def face_count(path: Path) -> int:
    if not is_collection(path):
        return 1
    collection = TTCollection(str(path), lazy=True)
    try:
        return len(collection.fonts)
    finally:
        collection.close()


def debug_name(font: TTFont, name_id: int, fallback: str = "") -> str:
    try:
        value = font["name"].getDebugName(name_id)
        return (value or fallback).strip()
    except Exception:
        return fallback


def best_family(font: TTFont) -> str:
    try:
        return (font["name"].getBestFamilyName() or debug_name(font, 1, "未知字体")).strip()
    except Exception:
        return debug_name(font, 1, "未知字体")


def best_subfamily(font: TTFont) -> str:
    try:
        return (font["name"].getBestSubFamilyName() or debug_name(font, 2, "Regular")).strip()
    except Exception:
        return debug_name(font, 2, "Regular")


def font_format(path: Path, font: TTFont) -> str:
    if is_collection(path):
        return "TTC"
    if "CFF2" in font:
        return "CFF2"
    if "CFF " in font:
        return "OTF/CFF"
    if "glyf" in font:
        return "TTF/glyf"
    return "SFNT"


def axis_name(font: TTFont, name_id: int, fallback: str) -> str:
    value = debug_name(font, name_id, fallback)
    return value or fallback


def axes(font: TTFont) -> list[dict[str, Any]]:
    if "fvar" not in font:
        return []
    result: list[dict[str, Any]] = []
    for axis in font["fvar"].axes:
        result.append(
            {
                "tag": axis.axisTag,
                "name": axis_name(font, axis.axisNameID, axis.axisTag),
                "min": float(axis.minValue),
                "default": float(axis.defaultValue),
                "max": float(axis.maxValue),
            }
        )
    return result


def os2_weight(font: TTFont) -> int:
    try:
        return int(font["OS/2"].usWeightClass)
    except Exception:
        return 400


def italic(font: TTFont) -> bool:
    try:
        return bool(int(font["head"].macStyle) & 0x02 or int(font["OS/2"].fsSelection) & 0x01 or float(font["post"].italicAngle))
    except Exception:
        return "italic" in best_subfamily(font).lower() or "oblique" in best_subfamily(font).lower()


def hit_count(cmap: dict[int, str], probes: tuple[int, ...]) -> int:
    return sum(1 for codepoint in probes if codepoint in cmap)


def protected_text_font(font: TTFont) -> bool:
    return any(tag in font for tag in ("COLR", "CBDT", "sbix", "SVG ")) or bool(
        re.search(r"emoji|dingbat|fontawesome|material.?icons|fontello|(?:^|[ _-])(?:icons?|symbols?)(?:$|[ _-])", best_family(font), re.I)
    )


def text_role_counts(cmap: dict[int, str]) -> dict[str, int]:
    """Identify actual text repertoire; a partial font is still a usable donor."""
    cmap = {cp: glyph for cp, glyph in cmap.items() if glyph != ".notdef"}
    return {
        "cjk": sum(0x3400 <= cp <= 0x4DBF or 0x4E00 <= cp <= 0x9FFF or 0xF900 <= cp <= 0xFAFF or 0x20000 <= cp <= 0x323AF for cp in cmap),
        "latin": sum(0x41 <= cp <= 0x5A or 0x61 <= cp <= 0x7A or (0xC0 <= cp <= 0x24F and cp not in (0xD7, 0xF7)) or 0x1E00 <= cp <= 0x1EFF or 0xFF21 <= cp <= 0xFF3A or 0xFF41 <= cp <= 0xFF5A for cp in cmap),
        "digit": sum(0x30 <= cp <= 0x39 or 0xFF10 <= cp <= 0xFF19 for cp in cmap),
    }


def coverage(font: TTFont) -> dict[str, Any]:
    cmap = font.getBestCmap() or {}
    cjk_hits = hit_count(cmap, CJK_PROBES)
    latin_hits = hit_count(cmap, LATIN_PROBES)
    digit_hits = hit_count(cmap, DIGIT_PROBES)
    punct_hits = hit_count(cmap, PUNCT_PROBES)
    role_counts = text_role_counts(cmap)
    cjk_count = role_counts["cjk"]
    return {
        "codepoints": len(cmap),
        "roleCounts": role_counts,
        "cjkCount": cjk_count,
        "cjkProbe": {"present": cjk_hits, "required": len(CJK_PROBES)},
        "latinProbe": {"present": latin_hits, "required": len(LATIN_PROBES)},
        "digitProbe": {"present": digit_hits, "required": len(DIGIT_PROBES)},
        "punctProbe": {"present": punct_hits, "required": len(PUNCT_PROBES)},
        "roles": {
            "cjk": role_counts["cjk"] > 0,
            "latin": role_counts["latin"] > 0,
            "digit": role_counts["digit"] > 0,
        },
    }


def inspect_face(path: Path, file_hash: str, index: int) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"lazy": True, "recalcTimestamp": False}
    if is_collection(path):
        kwargs["fontNumber"] = index
    font = TTFont(str(path), **kwargs)
    try:
        face_axes = axes(font)
        return {
            "uid": f"sha256:{file_hash}:face:{index}",
            "faceIndex": index,
            "family": best_family(font),
            "subfamily": best_subfamily(font),
            "fullName": debug_name(font, 4, best_family(font)),
            "postScriptName": debug_name(font, 6, ""),
            "format": font_format(path, font),
            "weight": os2_weight(font),
            "italic": italic(font),
            "variable": bool(face_axes),
            "axes": face_axes,
            "coverage": coverage(font),
            "glyphs": int(font["maxp"].numGlyphs) if "maxp" in font else 0,
            "tables": sorted(str(tag) for tag in font.keys()),
        }
    finally:
        font.close()


def inspect(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size < 12:
        raise ValueError("字体文件不存在或文件过小")
    file_hash = sha256(path)
    count = face_count(path)
    return {
        "status": "ok",
        "data": {
            "fileUid": f"sha256:{file_hash}",
            "sha256": file_hash,
            "fileName": path.name,
            "bytes": path.stat().st_size,
            "faceCount": count,
            "collection": count > 1,
            "faces": [inspect_face(path, file_hash, index) for index in range(count)],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("font")
    args = parser.parse_args()
    try:
        print(json.dumps(inspect(Path(args.font)), ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as error:
        print(
            json.dumps(
                {"status": "error", "message": str(error) or error.__class__.__name__},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
