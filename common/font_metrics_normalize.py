#!/usr/bin/env python3
"""Normalize Android UI font metrics and optionally create a stable monospace face.

The helper never edits the user's source file. It writes a standalone font face with
balanced hhea/OS/2 metrics so fixed-height TextView/EditText controls do not push text
upward or overlap adjacent labels. TTC/OTC inputs are reduced to the best CJK-capable
face before normalization.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import tempfile
from pathlib import Path
from typing import Iterable

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTCollection, TTFont

CJK_PROBES = tuple(map(ord, "中文字体系统默认洛书国永"))
UI_PROBES = tuple(map(ord, "中文国永AaHhx0123456789gjpqy"))
CAP_PROBES = tuple(map(ord, "AHIOX"))
XHEIGHT_PROBES = (ord("x"),)
ASCII_CODEPOINTS = tuple(range(0x20, 0x7F))
# Keep the line box aligned with stock Roboto (hhea ascent 1900/2048, descent 500/2048).
# Drifting away from these ratios makes custom faces and stock fallback faces sit on
# different baselines, which shows up as shifted/raised text in mixed-font screens.
TYPO_ASCENDER_RATIO = 0.928
TYPO_DESCENDER_RATIO = 0.244
# Android TextView defaults to includeFontPadding=true and reads top/bottom from the
# OS/2 win metrics. CJK fonts often carry huge yMax/yMin extremes; trusting them adds
# a large blank band above every line ("文字抬高/页面偏移"). Cap win metrics instead.
WIN_ASCENT_CAP_RATIO = 0.98
WIN_DESCENT_CAP_RATIO = 0.35
# hhea additionally encloses real outline extremes for includeFontPadding=false apps, but
# pathological sources (symbol/emoji mashups) must not blow line boxes up without bound.
HHEA_ASCENT_CAP_RATIO = 1.60
HHEA_DESCENT_CAP_RATIO = 0.90


class MetricsError(RuntimeError):
    pass


def _is_collection(path: Path) -> bool:
    with path.open("rb") as stream:
        return stream.read(4) == b"ttcf"


def _score_face(font: TTFont) -> tuple[int, int]:
    cmap = font.getBestCmap() or {}
    cjk_hits = sum(1 for codepoint in CJK_PROBES if codepoint in cmap)
    ui_hits = sum(1 for codepoint in UI_PROBES if codepoint in cmap)
    return cjk_hits, ui_hits


def _pick_face(path: Path) -> int:
    if not _is_collection(path):
        return -1
    collection = TTCollection(str(path), lazy=True)
    try:
        count = len(collection.fonts)
    finally:
        collection.close()
    best: tuple[tuple[int, int], int] | None = None
    for index in range(count):
        font = TTFont(str(path), fontNumber=index, lazy=True, recalcTimestamp=False)
        try:
            score = _score_face(font)
        finally:
            font.close()
        if best is None or score > best[0]:
            best = score, index
    if best is None:
        raise MetricsError(f"{path.name} 不包含可用字体面")
    return best[1]


def load_font(path: Path) -> tuple[TTFont, int]:
    if not path.is_file() or path.stat().st_size < 12:
        raise MetricsError(f"字体源文件不可用：{path}")
    face = _pick_face(path)
    kwargs: dict[str, object] = {
        "lazy": False,
        "recalcTimestamp": False,
        "recalcBBoxes": True,
    }
    if face >= 0:
        kwargs["fontNumber"] = face
    return TTFont(str(path), **kwargs), face


def glyph_bounds(font: TTFont, codepoints: Iterable[int]) -> dict[int, tuple[float, float, float, float]]:
    cmap = font.getBestCmap() or {}
    glyph_set = font.getGlyphSet()
    result: dict[int, tuple[float, float, float, float]] = {}
    for codepoint in codepoints:
        glyph_name = cmap.get(codepoint)
        if not glyph_name or glyph_name not in glyph_set:
            continue
        pen = BoundsPen(glyph_set)
        try:
            glyph_set[glyph_name].draw(pen)
        except Exception:
            continue
        if pen.bounds is not None:
            result[codepoint] = tuple(float(value) for value in pen.bounds)
    return result


def _median(values: Iterable[float], fallback: float) -> float:
    items = list(values)
    return float(statistics.median(items)) if items else float(fallback)


def _clamp_signed(value: int) -> int:
    return max(-32768, min(32767, int(value)))


def _clamp_unsigned(value: int) -> int:
    return max(0, min(65535, int(value)))


def _normalize_monospace(font: TTFont, upem: int) -> dict[str, int]:
    if "hmtx" not in font:
        return {"advance": 0, "glyphs": 0}
    cmap = font.getBestCmap() or {}
    bounds = glyph_bounds(font, ASCII_CODEPOINTS)
    widths: list[int] = []
    bbox_widths: list[float] = []
    for codepoint in ASCII_CODEPOINTS:
        glyph_name = cmap.get(codepoint)
        if not glyph_name or glyph_name not in font["hmtx"].metrics:
            continue
        widths.append(int(font["hmtx"].metrics[glyph_name][0]))
        if codepoint in bounds:
            x_min, _y_min, x_max, _y_max = bounds[codepoint]
            bbox_widths.append(x_max - x_min)
    typical = int(round(_median(widths, upem * 0.62)))
    required = int(round(max(bbox_widths, default=upem * 0.55) + upem * 0.06))
    advance = max(int(upem * 0.56), typical, required)
    advance = min(upem, advance)
    changed: set[str] = set()
    for codepoint in ASCII_CODEPOINTS:
        glyph_name = cmap.get(codepoint)
        if not glyph_name or glyph_name in changed or glyph_name not in font["hmtx"].metrics:
            continue
        changed.add(glyph_name)
        width = 0.0
        if codepoint in bounds:
            x_min, _y_min, x_max, _y_max = bounds[codepoint]
            width = x_max - x_min
        left = max(0, int(round((advance - width) / 2)))
        font["hmtx"].metrics[glyph_name] = (advance, left)
    if "post" in font:
        font["post"].isFixedPitch = 1
    if "OS/2" in font and hasattr(font["OS/2"], "panose"):
        try:
            font["OS/2"].panose.bProportion = 9
        except Exception:
            pass
    return {"advance": advance, "glyphs": len(changed)}


def _promote_os2_for_typo_metrics(os2) -> None:
    """Promote legacy OS/2 tables to v4 without leaving required fields undefined."""
    defaults = {
        # Added in OS/2 v1.
        "ulCodePageRange1": 0,
        "ulCodePageRange2": 0,
        # Added in OS/2 v2 and still required by v4.
        "sxHeight": 0,
        "sCapHeight": 0,
        "usDefaultChar": 0,
        "usBreakChar": 32,
        "usMaxContext": 2,
    }
    for field, default in defaults.items():
        if not hasattr(os2, field):
            setattr(os2, field, default)
    if int(getattr(os2, "version", 0)) < 4:
        os2.version = 4


def normalize_font_metrics(font: TTFont, monospaced: bool = False) -> dict[str, object]:
    if "head" not in font or "hhea" not in font or "OS/2" not in font:
        raise MetricsError("字体缺少 head、hhea 或 OS/2 度量表")
    upem = int(font["head"].unitsPerEm)
    if upem < 16:
        raise MetricsError("字体 unitsPerEm 无效")

    ui_bounds = glyph_bounds(font, UI_PROBES)
    tops = [item[3] for item in ui_bounds.values()]
    bottoms = [item[1] for item in ui_bounds.values()]
    ui_top = max(tops, default=upem * 0.82)
    ui_bottom = min(bottoms, default=-upem * 0.18)
    # Android control baselines are derived from hhea/OS/2 ratios. Deriving those values from each
    # font's extreme glyph bounds keeps bad source metrics alive and makes two selected fonts sit at
    # different heights. Use one stable em-relative contract for every direct, variable, weighted
    # and composite output. usWinAscent/usWinDescent below are capped so includeFontPadding
    # cannot inflate line boxes with CJK outline extremes.
    ascender = int(round(upem * TYPO_ASCENDER_RATIO))
    descender_abs = int(round(upem * TYPO_DESCENDER_RATIO))
    ascender = _clamp_signed(ascender)
    descender = _clamp_signed(-descender_abs)

    head = font["head"]
    y_max = int(getattr(head, "yMax", ascender))
    y_min = int(getattr(head, "yMin", -descender_abs))

    # Apps rendering with includeFontPadding=false lay out (and clip) against the hhea line
    # box. When a CJK face's ink extends past the declared box, the overflow paints into the
    # next line (标题与热度重叠) or is clipped off (标签少一截). Enclose the real outline
    # extremes in hhea — floored at the stable contract so compact faces keep stock spacing —
    # while typo/win stay on the contract, leaving includeFontPadding=true spacing unchanged.
    hhea_ascent = _clamp_signed(min(max(ascender, y_max), int(round(upem * HHEA_ASCENT_CAP_RATIO))))
    hhea_descent_abs = min(max(descender_abs, -y_min), int(round(upem * HHEA_DESCENT_CAP_RATIO)))
    hhea = font["hhea"]
    hhea.ascent = hhea_ascent
    hhea.descent = _clamp_signed(-int(hhea_descent_abs))
    hhea.lineGap = 0

    os2 = font["OS/2"]
    _promote_os2_for_typo_metrics(os2)
    os2.sTypoAscender = ascender
    os2.sTypoDescender = descender
    os2.sTypoLineGap = 0
    os2.fsSelection |= 1 << 7
    win_ascent_cap = int(round(upem * WIN_ASCENT_CAP_RATIO))
    win_descent_cap = int(round(upem * WIN_DESCENT_CAP_RATIO))
    os2.usWinAscent = _clamp_unsigned(min(max(ascender, y_max), win_ascent_cap))
    os2.usWinDescent = _clamp_unsigned(min(max(descender_abs, -y_min), win_descent_cap))

    cap_bounds = glyph_bounds(font, CAP_PROBES)
    x_bounds = glyph_bounds(font, XHEIGHT_PROBES)
    if cap_bounds:
        os2.sCapHeight = _clamp_signed(int(round(_median((b[3] for b in cap_bounds.values()), ascender))))
    if x_bounds:
        os2.sxHeight = _clamp_signed(int(round(_median((b[3] for b in x_bounds.values()), upem * 0.5))))

    # A variable font's MVAR can restore the source's unbalanced vertical metrics after selection.
    if "MVAR" in font:
        del font["MVAR"]

    mono_report = _normalize_monospace(font, upem) if monospaced else {"advance": 0, "glyphs": 0}
    return {
        "upem": upem,
        "ascender": ascender,
        "descender": descender,
        "lineGap": 0,
        "uiTop": int(round(ui_top)),
        "uiBottom": int(round(ui_bottom)),
        "monospaced": bool(monospaced),
        "monoAdvance": mono_report["advance"],
        "monoGlyphs": mono_report["glyphs"],
    }


def atomic_save(font: TTFont, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    os.close(descriptor)
    try:
        font.save(temporary, reorderTables=False)
        if os.path.getsize(temporary) < 1024:
            raise MetricsError("归一化字体输出异常为空")
        os.chmod(temporary, 0o644)
        os.replace(temporary, output)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def normalize_path(source: Path, output: Path, monospaced: bool = False) -> dict[str, object]:
    font, face = load_font(source)
    try:
        report = normalize_font_metrics(font, monospaced=monospaced)
        atomic_save(font, output)
    finally:
        font.close()
    report.update({"status": "ok", "input": str(source), "output": str(output), "face": face})
    return report


def run_batch(manifest: Path) -> int:
    """Normalize many fonts in one process. Manifest lines: input<TAB>output[<TAB>mono]."""
    failures = 0
    for raw in manifest.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        source, output = Path(parts[0]), Path(parts[1])
        monospaced = len(parts) > 2 and parts[2] == "mono"
        try:
            report = normalize_path(source, output, monospaced)
            print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
        except Exception as error:
            failures += 1
            output.unlink(missing_ok=True)
            print(json.dumps({"status": "error", "input": str(source), "message": str(error) or error.__class__.__name__}, ensure_ascii=False, separators=(",", ":")), file=os.sys.stderr)
    return 2 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--monospace", action="store_true")
    parser.add_argument("--batch", type=Path, help="批量清单：每行 input<TAB>output[<TAB>mono]，单进程处理全部字重")
    args = parser.parse_args()
    if args.batch:
        return run_batch(args.batch)
    if not args.input or not args.output:
        parser.error("--input 与 --output 为必填（或使用 --batch）")
    try:
        print(json.dumps(normalize_path(args.input, args.output, args.monospace), ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as error:
        args.output.unlink(missing_ok=True)
        print(json.dumps({"status": "error", "message": str(error) or error.__class__.__name__}, ensure_ascii=False, separators=(",", ":")), file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
