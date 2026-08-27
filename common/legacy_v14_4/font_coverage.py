#!/usr/bin/env python3
"""Read-only glyph coverage gate for fonts used as a global Android face."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont


CJK = tuple(map(ord, "中文字体系统默认汉字国家的一是"))
LATIN = tuple(map(ord, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"))
DIGITS = tuple(map(ord, "0123456789"))
PUNCTUATION = tuple(map(ord, ".,!?-:;()[]/+'\""))


def load_cmaps(path: Path) -> list[set[int]]:
    with path.open("rb") as stream:
        magic = stream.read(4)
    if magic == b"ttcf":
        collection = TTCollection(str(path), lazy=True)
        try:
            return [set((font.getBestCmap() or {}).keys()) for font in collection.fonts]
        finally:
            collection.close()
    font = TTFont(str(path), lazy=True, recalcTimestamp=False)
    try:
        return [set((font.getBestCmap() or {}).keys())]
    finally:
        font.close()


def ratio(cmap: set[int], probes: tuple[int, ...]) -> tuple[int, int, float]:
    hits = sum(codepoint in cmap for codepoint in probes)
    total = len(probes)
    return hits, total, hits / total if total else 1.0


def inspect(path: Path) -> dict[str, object]:
    faces = load_cmaps(path)
    candidates = []
    for index, cmap in enumerate(faces):
        groups = {
            "cjk": ratio(cmap, CJK),
            "latin": ratio(cmap, LATIN),
            "digits": ratio(cmap, DIGITS),
            "punctuation": ratio(cmap, PUNCTUATION),
        }
        score = sum(value[2] for value in groups.values())
        candidates.append((score, index, groups))
    _score, face, groups = max(candidates, default=(0.0, -1, {}))
    safe = bool(groups) and (
        groups["cjk"][2] >= 0.80
        and groups["latin"][2] >= 0.95
        and groups["digits"][2] == 1.0
        and groups["punctuation"][2] >= 0.75
    )
    percentages = {name: round(values[2] * 100) for name, values in groups.items()}
    return {
        "safe": safe,
        "face": face,
        "faces": len(faces),
        "coverage": percentages,
        "message": (
            "字形覆盖通过"
            if safe
            else "字形覆盖不足：中文 {cjk}%、英文 {latin}%、数字 {digits}%、标点 {punctuation}%".format(
                **percentages
            )
        ),
    }


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
