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
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTCollection, TTFont

CJK_PROBES = tuple(map(ord, "中文字体系统默认洛书国永"))
UI_PROBES = tuple(map(ord, "中文国永AaHhx0123456789gjpqy"))
CAP_PROBES = tuple(map(ord, "AHIOX"))
XHEIGHT_PROBES = (ord("x"),)
ASCII_CODEPOINTS = tuple(range(0x20, 0x7F))
# Historical fallback used when no valid per-device inventory exists. Normal operation reads the
# main stock UI slot's real hhea ratios from config/device_font_inventory.json.
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
INVENTORY_SCHEMA = "device-font-inventory-v1"


class MetricsError(RuntimeError):
    pass


def default_inventory_path() -> Path:
    override = os.environ.get("LUOSHU_FONT_INVENTORY", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "config/device_font_inventory.json"


def _device_build_key() -> str:
    override = os.environ.get("LUOSHU_BUILD_KEY", "").strip()
    if override:
        return override
    for prop in ("ro.build.fingerprint", "ro.build.display.id"):
        try:
            result = subprocess.run(
                ["getprop", prop],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=3,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        value = result.stdout.strip()
        if value:
            return value
    return ""


def load_inventory_contract(path: Path | None = None) -> dict[str, Any] | None:
    inventory = path or default_inventory_path()
    try:
        payload = json.loads(inventory.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict) or payload.get("schema") != INVENTORY_SCHEMA or payload.get("state") != "ready":
        return None
    try:
        revision = int(payload.get("inventoryRevision", 0))
    except (TypeError, ValueError):
        return None
    if revision != 1:
        return None
    current_key = _device_build_key()
    recorded_key = str(payload.get("buildKey", ""))
    if current_key and recorded_key != current_key:
        return None
    main_slot = payload.get("mainSlot")
    if not isinstance(main_slot, dict):
        return None
    metrics = main_slot.get("metrics")
    if not isinstance(metrics, dict):
        return None
    hhea = metrics.get("hhea")
    if not isinstance(hhea, dict):
        return None
    try:
        upem = int(metrics.get("upem", 0))
        ascent = int(hhea.get("ascent", 0))
        descent = int(hhea.get("descent", 0))
    except (TypeError, ValueError):
        return None
    if upem <= 0 or ascent <= 0 or descent >= 0:
        return None
    ascent_ratio = ascent / upem
    descent_ratio = abs(descent) / upem
    if not (0.40 <= ascent_ratio <= 1.60 and 0.05 <= descent_ratio <= 0.90):
        return None
    return {
        "source": "inventory",
        "inventory": str(inventory),
        "buildKey": str(payload.get("buildKey", "")),
        "slot": str(main_slot.get("slotName", main_slot.get("path", ""))),
        "upem": upem,
        "ascent": ascent,
        "descent": descent,
        "ascentRatio": ascent_ratio,
        "descentRatio": descent_ratio,
    }


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


def _outline_extremes(font: TTFont) -> tuple[float, float] | None:
    """True outline ink extremes across every glyph, from the outlines themselves.

    head.yMax/yMin is only a cached bounding box: composite builds import outlines and the
    box is not recalculated until save time, and CFF sources may carry a stale box too.
    Drawing every glyph through BoundsPen works for both glyf and CFF outlines.
    """
    try:
        glyph_set = font.getGlyphSet()
        order = font.getGlyphOrder()
    except Exception:
        return None
    top: float | None = None
    bottom: float | None = None
    for name in order:
        pen = BoundsPen(glyph_set)
        try:
            glyph_set[name].draw(pen)
        except Exception:
            continue
        if pen.bounds is None:
            continue
        _x0, y0, _x1, y1 = pen.bounds
        top = y1 if top is None else max(top, y1)
        bottom = y0 if bottom is None else min(bottom, y0)
    if top is None or bottom is None:
        return None
    return bottom, top


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


def normalize_font_metrics(
    font: TTFont,
    monospaced: bool = False,
    target_contract: dict[str, Any] | None = None,
) -> dict[str, object]:
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
    # Android control baselines are derived from hhea/OS/2 ratios. Prefer the main stock UI slot
    # discovered on this ROM; only fall back to the historical Roboto contract when the inventory
    # is missing, stale or malformed. The hhea/typo enclosure logic below is intentionally unchanged.
    if target_contract is not None:
        ascender_ratio = float(target_contract["ascentRatio"])
        descender_ratio = float(target_contract["descentRatio"])
        metrics_source = "inventory"
    else:
        ascender_ratio = TYPO_ASCENDER_RATIO
        descender_ratio = TYPO_DESCENDER_RATIO
        metrics_source = "fixed-fallback"
    ascender = int(round(upem * ascender_ratio))
    descender_abs = int(round(upem * descender_ratio))
    ascender = _clamp_signed(ascender)
    descender = _clamp_signed(-descender_abs)

    head = font["head"]
    y_max = int(getattr(head, "yMax", ascender))
    y_min = int(getattr(head, "yMin", -descender_abs))
    # head.yMax/yMin can be stale (composite builds recalc the box only at save time),
    # so enclose the true outline extremes as well; otherwise hhea/typo stay contracted
    # and ink still overflows the line box (标题压热度 / 标签少一截).
    extremes = _outline_extremes(font)
    if extremes is not None:
        import math
        y_min = min(y_min, int(math.floor(extremes[0])))
        y_max = max(y_max, int(math.ceil(extremes[1])))

    # Apps rendering with includeFontPadding=false lay out (and clip) against the hhea line
    # box. When a CJK face's ink extends past the declared box, the overflow paints into the
    # next line (标题与热度重叠) or is clipped off (标签少一截). Enclose the real outline
    # extremes in hhea — floored at the stable contract so compact faces keep stock spacing —
    # typo mirrors this enclosed box (see below); win stays capped on the contract, leaving
    # includeFontPadding=true spacing unchanged.
    hhea_ascent = _clamp_signed(min(max(ascender, y_max), int(round(upem * HHEA_ASCENT_CAP_RATIO))))
    hhea_descent_abs = min(max(descender_abs, -y_min), int(round(upem * HHEA_DESCENT_CAP_RATIO)))
    hhea = font["hhea"]
    hhea.ascent = hhea_ascent
    hhea.descent = _clamp_signed(-int(hhea_descent_abs))
    hhea.lineGap = 0

    os2 = font["OS/2"]
    _promote_os2_for_typo_metrics(os2)
    # fsSelection bit 7 (USE_TYPO_METRICS) makes engines lay out with the typo values,
    # so a contract-only typo still lets CJK ink overflow the line box exactly as before
    # (标题压热度 / 标签少一截). Keep typo identical to the enclosed hhea box; compact
    # faces stay on the contract because hhea is floored at it.
    os2.sTypoAscender = hhea_ascent
    os2.sTypoDescender = _clamp_signed(-int(hhea_descent_abs))
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
        "monospace": bool(monospaced),
        "monoAdvance": mono_report["advance"],
        "monoGlyphs": mono_report["glyphs"],
        "metricsSource": metrics_source,
        "targetSlot": target_contract.get("slot", "") if target_contract else "",
        "targetBuildKey": target_contract.get("buildKey", "") if target_contract else "",
        "targetUpem": int(target_contract.get("upem", 0)) if target_contract else 0,
        "targetAscent": int(target_contract.get("ascent", 0)) if target_contract else 0,
        "targetDescent": int(target_contract.get("descent", 0)) if target_contract else 0,
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


def normalize_path(
    source: Path,
    output: Path,
    monospaced: bool = False,
    inventory: Path | None = None,
    target_contract: dict[str, Any] | None = None,
) -> dict[str, object]:
    contract = target_contract if target_contract is not None else load_inventory_contract(inventory)
    font, face = load_font(source)
    try:
        report = normalize_font_metrics(font, monospaced=monospaced, target_contract=contract)
        atomic_save(font, output)
    finally:
        font.close()
    report.update({"status": "ok", "input": str(source), "output": str(output), "face": face})
    return report


def run_batch(manifest: Path, inventory: Path | None = None) -> int:
    """Normalize many fonts in one process. Manifest lines: input<TAB>output[<TAB>mono]."""
    failures = 0
    contract = load_inventory_contract(inventory)
    for raw in manifest.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        source, output = Path(parts[0]), Path(parts[1])
        monospaced = len(parts) > 2 and parts[2] == "mono"
        try:
            report = normalize_path(source, output, monospaced, inventory=inventory, target_contract=contract)
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
    parser.add_argument("--inventory", type=Path, default=default_inventory_path(), help="设备原厂字体清单")
    args = parser.parse_args()
    if args.batch:
        return run_batch(args.batch, args.inventory)
    if not args.input or not args.output:
        parser.error("--input 与 --output 为必填（或使用 --batch）")
    try:
        print(json.dumps(normalize_path(args.input, args.output, args.monospace, inventory=args.inventory), ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as error:
        args.output.unlink(missing_ok=True)
        print(json.dumps({"status": "error", "message": str(error) or error.__class__.__name__}, ensure_ascii=False, separators=(",", ":")), file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
