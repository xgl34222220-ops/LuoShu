#!/usr/bin/env python3
"""Report practical glyph coverage for LuoShu's native diagnostics."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from fontTools.ttLib import TTFont


LATIN = [*range(ord("A"), ord("Z") + 1), *range(ord("a"), ord("z") + 1)]
DIGIT = list(range(ord("0"), ord("9") + 1))
PUNCTUATION_TEXT = "，。！？；：、（）【】《》“”‘’…—,.!?;:()[]{}<>+-=*/_%@#&"
PUNCTUATION = sorted({ord(char) for char in PUNCTUATION_TEXT})
COMMON_CJK_SAMPLE = "的一是在不了有和人这中大为上个国我以要他时来用们生到作地于出就分对成会可主发年动同工也能下过子说产种面而方后多定行学法所民得经十三之进着等部度家电力里如水化高自二理起小物现实加量都两体制机当使点从业本去把性好应开它合还因由其些然前外天政四日那社义事平形相全表间样与关各重新线内数正心反你明看原又么利比或但质气第向道命此变条只没结解问意建月公无系军很情者最立代想已通并提直题党程展五果料象员革位入常文总次品式活设及管特件长求老头基资边流路级少图山统接知较将组见计别她手角期根论运农指几九区强放决西被干做必战先回则任取据处理世车器温传思院界打复走并院"


def coverage(cmap: set[int], points: list[int]) -> dict[str, int]:
    return {
        "present": sum(1 for point in points if point in cmap),
        "total": len(points),
    }


def main() -> int:
    path = Path(sys.argv[1])
    if not path.is_file():
        raise FileNotFoundError(path)

    kwargs: dict[str, object] = {"lazy": True, "recalcTimestamp": False}
    if path.read_bytes()[:4] == b"ttcf":
        kwargs["fontNumber"] = 0

    font = TTFont(str(path), **kwargs)
    try:
        best = font.getBestCmap() or {}
        cmap = set(best.keys())
        cjk_points = [*range(0x3400, 0x4DC0), *range(0x4E00, 0xA000)]
        missing_sample = "".join(char for char in COMMON_CJK_SAMPLE if ord(char) not in cmap)[:32]
        result = {
            "status": "ok",
            "data": {
                "file": path.name,
                "glyphs": len(cmap),
                "cjk": coverage(cmap, cjk_points),
                "latin": coverage(cmap, LATIN),
                "digit": coverage(cmap, DIGIT),
                "punctuation": coverage(cmap, PUNCTUATION),
                "missingSample": missing_sample,
            },
        }
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    finally:
        font.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(
            json.dumps(
                {"status": "error", "message": str(error)},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        raise SystemExit(1)
