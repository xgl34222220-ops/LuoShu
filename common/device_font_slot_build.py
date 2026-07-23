#!/usr/bin/env python3
"""Generate one stock-aligned LuoShu font for a captured device slot.

This is the first writing stage of the v2.2 engine. It only supports TrueType
outlines (including variable TrueType after static instancing). Unsupported CFF
sources fail closed instead of silently falling back to metric-only replacement.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import sys
import unicodedata
from pathlib import Path
from typing import Any, Iterable

from fontTools.misc.transform import Transform
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.scaleUpem import scale_upem
from fontTools.varLib.instancer import instantiateVariableFont

import device_font_template as template_engine

SCHEMA = "device-font-slot-build-v1"
PLAN_SCHEMA = "device-font-slot-plan-v1"

DROP_AFTER_OUTLINE_CHANGE = (
    "DSIG",
    "LTSH",
    "VDMX",
    "hdmx",
)


class BuildError(RuntimeError):
    pass


def finite(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def rounded(value: Any, fallback: int = 0) -> int:
    parsed = finite(value)
    return int(round(parsed)) if parsed is not None else fallback


def is_cjk(codepoint: int) -> bool:
    return (
        0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
        or 0x20000 <= codepoint <= 0x3134F
    )


def is_latin(codepoint: int) -> bool:
    return (
        0x0041 <= codepoint <= 0x007A
        or 0x00C0 <= codepoint <= 0x024F
        or 0x1E00 <= codepoint <= 0x1EFF
        or 0xAB30 <= codepoint <= 0xAB6F
    )


def is_digit(codepoint: int) -> bool:
    return 0x30 <= codepoint <= 0x39 or 0xFF10 <= codepoint <= 0xFF19


def is_punctuation(codepoint: int) -> bool:
    if 0x3000 <= codepoint <= 0x303F or 0xFF00 <= codepoint <= 0xFF65:
        return True
    try:
        return unicodedata.category(chr(codepoint)).startswith(("P", "S"))
    except ValueError:
        return False


def probe_for_codepoint(codepoint: int) -> str | None:
    if is_digit(codepoint):
        return "digits"
    if is_cjk(codepoint):
        return "cjk"
    if is_latin(codepoint):
        char = chr(codepoint)
        category = unicodedata.category(char)
        if char.lower() in "gjpqy" and category.startswith("L"):
            return "latinDescender"
        if category == "Lu":
            return "latinCap"
        return "latinX"
    if is_punctuation(codepoint):
        return "punctuation"
    return None


PROBE_PRIORITY = {
    "digits": 0,
    "cjk": 1,
    "latinCap": 2,
    "latinDescender": 3,
    "latinX": 4,
    "punctuation": 5,
}


def glyph_probe_map(font: TTFont) -> dict[str, str]:
    cmap = font.getBestCmap() or {}
    choices: dict[str, tuple[int, str]] = {}
    for codepoint, glyph_name in cmap.items():
        probe = probe_for_codepoint(codepoint)
        if not probe:
            continue
        priority = PROBE_PRIORITY[probe]
        current = choices.get(glyph_name)
        if current is None or priority < current[0]:
            choices[glyph_name] = (priority, probe)
    return {name: probe for name, (_priority, probe) in choices.items()}


def static_instance(font: TTFont, weight: int) -> TTFont:
    if "fvar" not in font:
        return font
    location: dict[str, float] = {}
    for axis in font["fvar"].axes:
        if axis.axisTag == "wght":
            location[axis.axisTag] = float(max(axis.minValue, min(axis.maxValue, weight)))
        else:
            location[axis.axisTag] = float(axis.defaultValue)
    try:
        instantiated = instantiateVariableFont(font, location, inplace=False, optimize=True)
    except Exception as exc:
        raise BuildError(f"可变字体静态实例化失败：{exc}") from exc
    return instantiated


def read_source(path: Path, face_index: int, weight: int) -> TTFont:
    if not path.is_file() or path.stat().st_size < 12:
        raise BuildError(f"源字体不可用：{path}")
    kwargs: dict[str, Any] = {
        "lazy": False,
        "recalcTimestamp": False,
        "recalcBBoxes": True,
    }
    with path.open("rb") as stream:
        collection = stream.read(4) == b"ttcf"
    if collection:
        kwargs["fontNumber"] = max(0, face_index)
    font = TTFont(str(path), **kwargs)
    if "glyf" not in font:
        font.close()
        raise BuildError("当前阶段仅支持 TrueType glyf 轮廓；CFF/CFF2 将在后续阶段单独实现")
    result = static_instance(font, weight)
    if result is not font:
        font.close()
    if "glyf" not in result:
        result.close()
        raise BuildError("静态实例不包含 TrueType glyf 轮廓")
    return result


def record_target_glyphs(font: TTFont, names: Iterable[str]) -> dict[str, DecomposingRecordingPen]:
    glyph_set = font.getGlyphSet()
    recordings: dict[str, DecomposingRecordingPen] = {}
    for name in names:
        if name not in glyph_set:
            continue
        pen = DecomposingRecordingPen(glyph_set)
        try:
            glyph_set[name].draw(pen)
        except Exception as exc:
            raise BuildError(f"字形 {name} 轮廓展开失败：{exc}") from exc
        recordings[name] = pen
    return recordings


def replay_glyph(
    recording: DecomposingRecordingPen,
    transform: Transform,
) -> Any:
    pen = TTGlyphPen(None)
    recording.replay(TransformPen(pen, transform))
    return pen.glyph()


def glyph_bounds(glyph: Any, glyf_table: Any) -> tuple[int, int, int, int] | None:
    try:
        glyph.recalcBounds(glyf_table)
    except Exception:
        return None
    if not hasattr(glyph, "xMin"):
        return None
    return int(glyph.xMin), int(glyph.yMin), int(glyph.xMax), int(glyph.yMax)


def transform_for_probe(slot: dict[str, Any], probe: str) -> dict[str, Any] | None:
    transforms = slot.get("transforms") if isinstance(slot.get("transforms"), dict) else {}
    transform = transforms.get(probe)
    if not isinstance(transform, dict) or transform.get("status") not in ("ready",):
        return None
    return transform


def apply_outline_transforms(font: TTFont, slot: dict[str, Any]) -> dict[str, Any]:
    roles = set(slot.get("roles") or [])
    probe_map = glyph_probe_map(font)
    recordings = record_target_glyphs(font, probe_map)
    glyf = font["glyf"]
    hmtx = font["hmtx"].metrics
    changed = 0
    centered = 0
    advances = 0
    probe_counts: dict[str, int] = {}

    for glyph_name, probe in probe_map.items():
        recording = recordings.get(glyph_name)
        transform_data = transform_for_probe(slot, probe)
        if recording is None or transform_data is None or glyph_name not in hmtx:
            continue
        scale_y = finite(transform_data.get("relativeScaleY")) or 1.0
        shift_y = finite(transform_data.get("shiftY")) or 0.0
        scale_x = 1.0
        if ("clock" in roles or "mono" in roles) and transform_data.get("relativeInkScaleX") is not None:
            scale_x = finite(transform_data.get("relativeInkScaleX")) or 1.0

        old_advance, old_lsb = hmtx[glyph_name]
        relative_advance = finite(transform_data.get("relativeAdvanceScale")) or 1.0
        target_advance = finite(transform_data.get("targetAdvance"))
        exact_advance = (
            target_advance is not None
            and (("clock" in roles and probe in ("digits", "punctuation")) or "mono" in roles)
        )
        new_advance = int(round(target_advance if exact_advance else old_advance * relative_advance))
        new_advance = max(1, min(65535, new_advance))

        base_transform = Transform(scale_x, 0, 0, scale_y, 0, shift_y)
        provisional = replay_glyph(recording, base_transform)
        bounds = glyph_bounds(provisional, glyf)
        shift_x = 0.0
        new_lsb = int(old_lsb)
        if bounds is not None and exact_advance:
            ink_width = bounds[2] - bounds[0]
            desired_x_min = (new_advance - ink_width) / 2.0
            shift_x = desired_x_min - bounds[0]
            new_lsb = int(round(desired_x_min))
            centered += 1
        elif scale_x != 1.0:
            new_lsb = int(round(old_lsb * scale_x))

        final_transform = Transform(scale_x, 0, 0, scale_y, shift_x, shift_y)
        glyph = replay_glyph(recording, final_transform)
        glyf[glyph_name] = glyph
        if glyph_bounds(glyph, glyf) is not None and exact_advance:
            new_lsb = int(glyph.xMin)
        hmtx[glyph_name] = (new_advance, new_lsb)
        changed += 1
        advances += int(new_advance != old_advance)
        probe_counts[probe] = probe_counts.get(probe, 0) + 1

    return {
        "glyphs": changed,
        "centered": centered,
        "advances": advances,
        "probes": dict(sorted(probe_counts.items())),
    }


def apply_line_contract(font: TTFont, slot: dict[str, Any]) -> None:
    contract = slot.get("lineContract") if isinstance(slot.get("lineContract"), dict) else {}
    upem = rounded(contract.get("unitsPerEm"))
    if upem <= 0:
        raise BuildError("槽位缺少有效 unitsPerEm")
    if int(font["head"].unitsPerEm) != upem:
        scale_upem(font, upem)

    hhea = font["hhea"]
    hhea.ascent = rounded(contract.get("hheaAscent"), int(hhea.ascent))
    hhea.descent = rounded(contract.get("hheaDescent"), int(hhea.descent))
    hhea.lineGap = rounded(contract.get("hheaLineGap"), int(hhea.lineGap))

    if "OS/2" not in font:
        raise BuildError("源字体缺少 OS/2 表")
    os2 = font["OS/2"]
    field_map = {
        "sTypoAscender": "typoAscender",
        "sTypoDescender": "typoDescender",
        "sTypoLineGap": "typoLineGap",
        "usWinAscent": "winAscent",
        "usWinDescent": "winDescent",
        "sCapHeight": "capHeight",
        "sxHeight": "xHeight",
        "usWeightClass": "weightClass",
        "usWidthClass": "widthClass",
        "fsSelection": "fsSelection",
    }
    for field, key in field_map.items():
        value = contract.get(key)
        if value is not None and hasattr(os2, field):
            setattr(os2, field, rounded(value, int(getattr(os2, field))))


def set_slot_identity(font: TTFont, slot: dict[str, Any]) -> None:
    if "name" not in font:
        return
    family = str(slot.get("familyNormalized") or slot.get("family") or "luoshu-slot")
    weight = rounded(slot.get("weight"), 400)
    style = "Italic" if str(slot.get("style", "normal")).lower() == "italic" else "Regular"
    safe = "".join(char if char.isalnum() else "-" for char in family).strip("-") or "LuoShuSlot"
    unique_family = f"LuoShuSlot-{safe}-{weight}"
    full_name = f"{unique_family} {style}"
    postscript = f"{unique_family}-{style}".replace(" ", "")[:63]
    table = font["name"]
    table.setName(unique_family, 1, 3, 1, 0x409)
    table.setName(style, 2, 3, 1, 0x409)
    table.setName(full_name, 4, 3, 1, 0x409)
    table.setName(postscript, 6, 3, 1, 0x409)
    table.setName(unique_family, 16, 3, 1, 0x409)
    table.setName(style, 17, 3, 1, 0x409)


def validate_saved(output: Path, slot: dict[str, Any]) -> dict[str, Any]:
    font = TTFont(str(output), lazy=True, recalcTimestamp=False)
    try:
        contract = slot["lineContract"]
        checks = {
            "unitsPerEm": int(font["head"].unitsPerEm),
            "hheaAscent": int(font["hhea"].ascent),
            "hheaDescent": int(font["hhea"].descent),
            "hheaLineGap": int(font["hhea"].lineGap),
        }
        for key, value in checks.items():
            if value != rounded(contract.get(key), value):
                raise BuildError(f"保存后的 {key} 未保持原厂槽位值")
        return checks
    finally:
        font.close()


def build_slot(source: Path, source_index: int, slot: dict[str, Any], output: Path) -> dict[str, Any]:
    if slot.get("status") != "ready":
        raise BuildError(f"槽位状态不是 ready：{slot.get('status')}")
    if not slot.get("replaceable") or "protected" in set(slot.get("roles") or []):
        raise BuildError("受保护槽位禁止生成")
    weight = rounded(slot.get("weight"), 400)
    font = read_source(source, source_index, weight)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    try:
        apply_line_contract(font, slot)
        transform_report = apply_outline_transforms(font, slot)
        set_slot_identity(font, slot)
        for tag in DROP_AFTER_OUTLINE_CHANGE:
            if tag in font:
                del font[tag]
        if "head" in font:
            font["head"].checkSumAdjustment = 0
        output.parent.mkdir(parents=True, exist_ok=True)
        font.save(str(temporary), reorderTables=False)
        os.chmod(temporary, 0o644)
        os.replace(temporary, output)
    finally:
        font.close()
        temporary.unlink(missing_ok=True)
    checks = validate_saved(output, slot)
    return {
        "schema": SCHEMA,
        "status": "ok",
        "output": str(output),
        "family": slot.get("family", ""),
        "weight": weight,
        "style": slot.get("style", "normal"),
        "roles": slot.get("roles", []),
        "transformed": transform_report,
        "checks": checks,
        "bytes": output.stat().st_size,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--source-index", type=int, default=-1)
    parser.add_argument("--slot-index", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        if plan.get("schema") != PLAN_SCHEMA:
            raise BuildError(f"不支持的槽位计划：{plan.get('schema')!r}")
        slots = plan.get("slots") if isinstance(plan.get("slots"), list) else []
        if args.slot_index < 0 or args.slot_index >= len(slots):
            raise BuildError("slot-index 超出计划范围")
        slot = copy.deepcopy(slots[args.slot_index])
        report = build_slot(args.source, args.source_index, slot, args.output)
        print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as exc:
        print(json.dumps({"schema": SCHEMA, "status": "error", "message": str(exc) or exc.__class__.__name__}, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
