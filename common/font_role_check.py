#!/usr/bin/env python3
"""Fast role coverage gate used before a LuoShu composite task is queued."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont

CJK = tuple(map(ord, "中文字体系统默认洛书汉字"))
LATIN = tuple(map(ord, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"))
DIGITS = tuple(map(ord, "0123456789"))
# Lock-screen / status-bar clock separators and spacing. A clock slot rendered
# from a font without them shows tofu, so such fonts keep the stock clock glyphs.
CLOCK_REQUIRED = (0x003A, 0x2236, 0xFF1A, 0x2007, 0x202F)
CLOCK_TABULAR_WARNING = "数字非等宽，状态栏秒数可能抖动"


class RoleCheckError(RuntimeError):
    pass


def is_collection(path: Path) -> bool:
    with path.open("rb") as stream:
        return stream.read(4) == b"ttcf"


def faces(path: Path) -> range:
    if not is_collection(path):
        return range(1)
    collection = TTCollection(str(path), lazy=True)
    try:
        return range(len(collection.fonts))
    finally:
        collection.close()


def required(role: str) -> tuple[int, ...]:
    # The CJK source is the complete cmap base. It must provide the slots that
    # are mandatory for replacement, but punctuation replacement is optional
    # in composite_font.py and must not reject otherwise usable fonts.
    if role == "cjk":
        return CJK + LATIN + DIGITS
    if role == "latin":
        return LATIN
    return DIGITS


def clock_glyph_report(font: TTFont) -> dict[str, object]:
    """Clock gate: required separators/spaces present and 0-9 tabular."""
    cmap = font.getBestCmap() or {}
    missing = [codepoint for codepoint in CLOCK_REQUIRED if codepoint not in cmap]
    widths: list[int] = []
    try:
        metrics = font["hmtx"].metrics if "hmtx" in font else {}
    except Exception:
        metrics = {}
    for codepoint in DIGITS:
        glyph = cmap.get(codepoint)
        if glyph is None or glyph not in metrics:
            widths = []
            break
        widths.append(int(metrics[glyph][0]))
    tabular = bool(widths) and len(set(widths)) == 1
    return {
        "clockSafe": not missing,
        "missing": [f"U+{codepoint:04X}" for codepoint in missing],
        "missingText": "".join(chr(codepoint) for codepoint in missing),
        "tabularDigits": tabular,
        "digitAdvances": sorted(set(widths)),
        "warning": "" if tabular else CLOCK_TABULAR_WARNING,
    }


def inspect_clock(path: Path, index: int = -1) -> dict[str, object]:
    kwargs: dict[str, object] = {"lazy": True, "recalcTimestamp": False}
    if is_collection(path):
        kwargs["fontNumber"] = max(0, index)
    font = TTFont(str(path), **kwargs)
    try:
        return clock_glyph_report(font)
    finally:
        font.close()


def inspect_face(path: Path, index: int, role: str) -> dict[str, object]:
    kwargs: dict[str, object] = {"lazy": True, "recalcTimestamp": False}
    if is_collection(path):
        kwargs["fontNumber"] = index
    font = TTFont(str(path), **kwargs)
    try:
        cmap = font.getBestCmap() or {}
        probes = required(role)
        missing = [codepoint for codepoint in probes if codepoint not in cmap]
        return {
            "face": index if is_collection(path) else -1,
            "required": len(probes),
            "present": len(probes) - len(missing),
            "missing": [f"U+{codepoint:04X}" for codepoint in missing[:16]],
            "valid": not missing,
        }
    finally:
        font.close()


def check(path: Path, role: str) -> dict[str, object]:
    if not path.is_file() or path.stat().st_size < 4096:
        raise RoleCheckError("字体文件不存在或文件过小")
    if role == "clock":
        report = inspect_clock(path, 0)
        return {"status": "ok" if report["clockSafe"] else "error", "role": role, "path": str(path),
                "valid": report["clockSafe"], **report}
    results = [inspect_face(path, index, role) for index in faces(path)]
    best = max(results, key=lambda item: int(item["present"]), default=None)
    if best is None:
        raise RoleCheckError("字体中没有可读取的字体面")
    return {
        "status": "ok" if best["valid"] else "error",
        "role": role,
        "path": str(path),
        **best,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("font")
    parser.add_argument("role", choices=("cjk", "latin", "digit", "clock"))
    args = parser.parse_args()
    try:
        result = check(Path(args.font), args.role)
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0 if result["valid"] else 2
    except Exception as error:
        print(
            json.dumps(
                {"status": "error", "role": args.role, "message": str(error) or error.__class__.__name__},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
