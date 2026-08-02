#!/usr/bin/env python3
"""Read-only glyph coverage gate for fonts used as a global Android face.

A global replacement is accepted only when one concrete face is a complete text
face.  Merely finding a few CJK codepoints in a collection is not enough: Latin,
digits, common punctuation and a representative CJK set must resolve to real,
diverse glyph names in the same face.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from fontTools.ttLib import TTCollection, TTFont

CJK = tuple(map(ord, "一丁七万三上下不与中为主人了二于五人今从他会但你作使入全国其分到前力十又只可同后和在地大天好学家小年心我日时有来民生的看种行要见言这"))
LATIN = tuple(map(ord, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"))
DIGITS = tuple(map(ord, "0123456789"))
PUNCTUATION = tuple(map(ord, ".,!?-:;()[]/+'\"，。！？：；（）【】《》、"))


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


def open_face(path: Path, index: int) -> TTFont:
    kwargs: dict[str, Any] = {"lazy": True, "recalcTimestamp": False}
    if is_collection(path):
        kwargs["fontNumber"] = index
    return TTFont(str(path), **kwargs)


def group(font: TTFont, probes: tuple[int, ...]) -> dict[str, object]:
    cmap = font.getBestCmap() or {}
    glyph_order = set(font.getGlyphOrder())
    missing: list[int] = []
    names: set[str] = set()
    for codepoint in probes:
        name = cmap.get(codepoint)
        if not name or name == ".notdef" or name not in glyph_order:
            missing.append(codepoint)
            continue
        names.add(name)
    hits = len(probes) - len(missing)
    return {
        "hits": hits,
        "total": len(probes),
        "ratio": hits / len(probes) if probes else 1.0,
        "uniqueGlyphs": len(names),
        "missing": missing,
    }


def inspect_face(path: Path, index: int) -> dict[str, object]:
    font = open_face(path, index)
    try:
        groups = {
            "cjk": group(font, CJK),
            "latin": group(font, LATIN),
            "digits": group(font, DIGITS),
            "punctuation": group(font, PUNCTUATION),
        }
        cjk = groups["cjk"]
        safe = (
            float(cjk["ratio"]) >= 0.95
            and int(cjk["uniqueGlyphs"]) >= max(12, int(int(cjk["hits"]) * 0.75))
            and float(groups["latin"]["ratio"]) == 1.0
            and float(groups["digits"]["ratio"]) == 1.0
            and float(groups["punctuation"]["ratio"]) >= 0.85
        )
        missing: list[int] = []
        for values in groups.values():
            missing.extend(values["missing"])  # type: ignore[arg-type]
        percentages = {
            name: round(float(values["ratio"]) * 100)
            for name, values in groups.items()
        }
        return {
            "safe": safe,
            "face": index if is_collection(path) else -1,
            "coverage": percentages,
            "uniqueCjkGlyphs": int(cjk["uniqueGlyphs"]),
            "missing": [f"U+{codepoint:04X}" for codepoint in missing[:24]],
            "score": sum(float(values["ratio"]) for values in groups.values()),
        }
    finally:
        font.close()


def inspect(path: Path) -> dict[str, object]:
    if not path.is_file() or path.stat().st_size < 4096:
        return {"safe": False, "message": "字体文件不存在或文件过小"}
    candidates = [inspect_face(path, index) for index in range(face_count(path))]
    best = max(
        candidates,
        key=lambda item: (
            1 if item["safe"] else 0,
            float(item["score"]),
        ),
        default=None,
    )
    if best is None:
        return {"safe": False, "message": "字体中没有可读取的字体面"}
    result = {
        key: value for key, value in best.items() if key != "score"
    }
    result["faces"] = len(candidates)
    result["message"] = (
        "字形覆盖通过"
        if best["safe"]
        else "字形覆盖不足：中文 {cjk}%、英文 {latin}%、数字 {digits}%、标点 {punctuation}%；请改用复合字体或完整 CJK 字体".format(
            **best["coverage"]  # type: ignore[arg-type]
        )
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("font", type=Path)
    parser.add_argument("--brief", action="store_true")
    args = parser.parse_args()
    try:
        result = inspect(args.font)
    except Exception as error:  # corrupted fonts must never reach Android's renderer
        result = {"safe": False, "message": f"无法读取字形覆盖：{error}"}
    if args.brief:
        print(result["message"])
    else:
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if result.get("safe") else 2


if __name__ == "__main__":
    raise SystemExit(main())
