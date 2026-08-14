#!/usr/bin/env python3
"""Report practical glyph coverage and a user-facing missing-glyph map for LuoShu."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont

LATIN_BASIC = [*range(ord('A'), ord('Z') + 1), *range(ord('a'), ord('z') + 1)]
DIGIT = list(range(ord('0'), ord('9') + 1))
PUNCTUATION_TEXT = '，。！？；：、（）【】《》“”‘’…—,.!?;:()[]{}<>+-=*/_%@#&'
PUNCTUATION = sorted({ord(char) for char in PUNCTUATION_TEXT})
COMMON_CJK_SAMPLE = '的一是在不了有和人这中大为上个国我以要他时来用们生到作地于出就分对成会可主发年动同工也能下过子说产种面而方后多定行学法所民得经十三之进着等部度家电力里如水化高自二理起小物现实加量都两体制机当使点从业本去把性好应开它合还因由其些然前外天政四日那社义事平形相全表间样与关各重新线内数正心反你明看原又么利比或但质气第向道命此变条只没结解问意建月公无系军很情者最立代想已通并提直题党程展五果料象员革位入常文总次品式活设及管特件长求老头基资边流路级少图山统接知较将组见计别她手角期根论运农指几九区强放决西被干做必战先回则任取据处理世车器温传思院界打复走并院'
SIMPLIFIED_SAMPLE = '汉语简体字体设置网络应用阅读微信商店状态系统开发测试颜色时间金额数字标题正文通知安全更新备份恢复组合方案'
TRADITIONAL_SAMPLE = '漢語繁體字體設定網路應用閱讀微信商店狀態系統開發測試顏色時間金額數字標題正文通知安全更新備份恢復組合方案'
JAPANESE_SAMPLE = 'あいうえおかきくけこアイウエオカキクケコ日本語文字設定更新保存復元'
KOREAN_SAMPLE = '가나다라마바사아자차카타파하한글문자설정업데이트백업복원'
MATH_SAMPLE = '∀∂∃∅∆∇∈∉∋∏∑−∕∙√∞∧∨∩∪∫≈≠≡≤≥⊂⊃⊕⊗'

CJK_UNIFIED = [*range(0x3400, 0x4DC0), *range(0x4E00, 0xA000)]
HIRAGANA = list(range(0x3041, 0x3097))
KATAKANA = list(range(0x30A1, 0x30FB))
HANGUL = list(range(0xAC00, 0xD7A4))
LATIN_EXTENDED = list(range(0x00C0, 0x0250))
MATH_SYMBOLS = list(range(0x2200, 0x2300))
PUA_BMP = list(range(0xE000, 0xF900))


def points(text: str) -> list[int]:
    return sorted({ord(ch) for ch in text})


def coverage(cmap: set[int], probe: list[int]) -> dict[str, int | float]:
    present = sum(1 for point in probe if point in cmap)
    total = len(probe)
    return {
        'present': present,
        'total': total,
        'percent': round((present / total * 100.0) if total else 100.0, 1),
    }


def missing_text(cmap: set[int], text: str, limit: int = 48) -> str:
    seen: set[int] = set()
    missing: list[str] = []
    for char in text:
        cp = ord(char)
        if cp in seen or cp in cmap:
            continue
        seen.add(cp)
        missing.append(char)
        if len(missing) >= limit:
            break
    return ''.join(missing)


def load_best_cmap(path: Path) -> tuple[set[int], int, int]:
    with path.open('rb') as stream:
        magic = stream.read(4)
    if magic == b'ttcf':
        collection = TTCollection(str(path), lazy=True)
        try:
            candidates = [(set((font.getBestCmap() or {}).keys()), index) for index, font in enumerate(collection.fonts)]
            cmap, index = max(candidates, key=lambda item: len(item[0]), default=(set(), -1))
            return cmap, index, len(collection.fonts)
        finally:
            collection.close()
    font = TTFont(str(path), lazy=True, recalcTimestamp=False)
    try:
        return set((font.getBestCmap() or {}).keys()), 0, 1
    finally:
        font.close()


def recommendation(groups: dict[str, dict[str, int | float]]) -> str:
    cjk = float(groups['cjkUnified']['percent'])
    latin = float(groups['latinBasic']['percent'])
    digit = float(groups['digit']['percent'])
    if cjk >= 90 and latin >= 95 and digit == 100:
        return '适合全局使用'
    if cjk < 35 and latin >= 95:
        return '更适合作为英文字体'
    if digit == 100 and cjk < 35:
        return '适合作为数字/英文字体'
    if cjk >= 70:
        return '可用于中文组合，建议先查看缺字'
    return '建议仅在组合模式中使用'


def inspect(path: Path) -> dict[str, object]:
    cmap, face, faces = load_best_cmap(path)
    groups = {
        'cjkUnified': coverage(cmap, CJK_UNIFIED),
        'simplifiedSample': coverage(cmap, points(SIMPLIFIED_SAMPLE)),
        'traditionalSample': coverage(cmap, points(TRADITIONAL_SAMPLE)),
        'japaneseKana': coverage(cmap, sorted(set(HIRAGANA + KATAKANA))),
        'koreanHangul': coverage(cmap, HANGUL),
        'latinBasic': coverage(cmap, LATIN_BASIC),
        'latinExtended': coverage(cmap, LATIN_EXTENDED),
        'digit': coverage(cmap, DIGIT),
        'punctuation': coverage(cmap, PUNCTUATION),
        'math': coverage(cmap, MATH_SYMBOLS),
        'pua': coverage(cmap, PUA_BMP),
    }
    common_missing = missing_text(cmap, COMMON_CJK_SAMPLE)
    missing_by_group = {
        'simplified': missing_text(cmap, SIMPLIFIED_SAMPLE),
        'traditional': missing_text(cmap, TRADITIONAL_SAMPLE),
        'japanese': missing_text(cmap, JAPANESE_SAMPLE),
        'korean': missing_text(cmap, KOREAN_SAMPLE),
        'math': missing_text(cmap, MATH_SAMPLE),
    }
    # Keep legacy fields so the current App can consume the richer backend before its UI is upgraded.
    return {
        'status': 'ok',
        'data': {
            'file': path.name,
            'glyphs': len(cmap),
            'face': face,
            'faces': faces,
            'cjk': groups['cjkUnified'],
            'latin': groups['latinBasic'],
            'digit': groups['digit'],
            'punctuation': groups['punctuation'],
            'groups': groups,
            'missingSample': common_missing,
            'missingByGroup': missing_by_group,
            'recommendation': recommendation(groups),
        },
    }


def main() -> int:
    path = Path(sys.argv[1])
    if not path.is_file():
        raise FileNotFoundError(path)
    print(json.dumps(inspect(path), ensure_ascii=False, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({'status': 'error', 'message': str(error)}, ensure_ascii=False, separators=(',', ':')))
        raise SystemExit(1)
