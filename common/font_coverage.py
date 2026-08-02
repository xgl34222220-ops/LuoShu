#!/usr/bin/env python3
"""Read-only glyph coverage gate for fonts used as a global Android face."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont


# A tiny phrase is not enough for a system-wide font: many decorative/subset fonts
# happen to contain those characters but still render most Chinese UI as tofu boxes.
# Check both representative high-frequency characters and the actual unified Han count.
CJK_COMMON = tuple(
    map(
        ord,
        "的一是不了在人有我他这中大来上个国到说们为子和你地出道也时年得就那要下以生会自着去之过家学对可她里后小么心多天而能好都然没日于起还发成事只作当想看文无开手十用主行方又如前所本见经头面公同三已老从动两长知民样现分将外但身些与高意进把法此实回二理力它点正其者还",
    )
)
LATIN = tuple(map(ord, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"))
DIGITS = tuple(map(ord, "0123456789"))
PUNCTUATION = tuple(map(ord, ".,!?-:;()[]/+'\""))

# GB2312 contains 6,763 Han characters. A font replacing every Android UI slot
# should provide roughly that level of core Chinese coverage. Smaller artistic or
# Latin-only fonts remain usable through LuoShu's composite-font feature.
MIN_CORE_HAN = 6000
CORE_HAN_RANGES = (
    (0x3400, 0x4DBF),  # CJK Unified Ideographs Extension A
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
)


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


def count_core_han(cmap: set[int]) -> int:
    return sum(
        1
        for codepoint in cmap
        if any(start <= codepoint <= end for start, end in CORE_HAN_RANGES)
    )


def inspect(path: Path) -> dict[str, object]:
    faces = load_cmaps(path)
    candidates = []
    for index, cmap in enumerate(faces):
        groups = {
            "cjk": ratio(cmap, CJK_COMMON),
            "latin": ratio(cmap, LATIN),
            "digits": ratio(cmap, DIGITS),
            "punctuation": ratio(cmap, PUNCTUATION),
        }
        han_count = count_core_han(cmap)
        score = sum(value[2] for value in groups.values())
        # Prefer the face with real Chinese breadth first, then general probe coverage.
        candidates.append((han_count, score, index, groups))

    han_count, _score, face, groups = max(
        candidates, default=(0, 0.0, -1, {})
    )
    safe = bool(groups) and (
        han_count >= MIN_CORE_HAN
        and groups["cjk"][2] >= 0.95
        and groups["latin"][2] >= 0.95
        and groups["digits"][2] == 1.0
        and groups["punctuation"][2] >= 0.75
    )
    percentages = {name: round(values[2] * 100) for name, values in groups.items()}
    return {
        "safe": safe,
        "face": face,
        "faces": len(faces),
        "coreHan": han_count,
        "minimumCoreHan": MIN_CORE_HAN,
        "coverage": percentages,
        "message": (
            f"字形覆盖通过：核心汉字 {han_count} 个"
            if safe
            else (
                "字形覆盖不足：核心汉字 {han}/{minimum} 个、常用中文 {cjk}%、"
                "英文 {latin}%、数字 {digits}%、标点 {punctuation}%"
            ).format(
                han=han_count,
                minimum=MIN_CORE_HAN,
                **percentages,
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
