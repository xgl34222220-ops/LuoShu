#!/usr/bin/env python3
"""LuoShu Phase 6 universal metrics / variable font compiler.

Consumes validated Phase 4/5 plans. It compiles artifacts but never publishes
them into Android partitions and never mounts anything.

Compiler modes:
- source-as-base: static general UI fonts keep the user's own shaping/layout.
- stock-shell: specialized/collection/fixed-axis variable targets keep the OEM
  container and exact metric/advance contracts while selected glyph outlines
  come from the user source.
- source-variable-preserve: physical variable UI targets preserve source fvar /
  gvar / HVAR only when their natural geometry already matches the stock slot
  after UPEM + line-contract normalization.

No mode silently relabels a wrong static weight as another weight.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import shutil
import tempfile
import time
import unicodedata
from pathlib import Path
from typing import Any, Iterable

from fontTools.misc.transform import Transform
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.qu2cuPen import Qu2CuPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection, TTFont
from fontTools.ttLib.scaleUpem import scale_upem
from fontTools.varLib.instancer import instantiateVariableFont

import device_font_slot_build_base as slot_build
import device_font_slot_plan as slot_plan_engine
import device_font_template as template_engine
import font_inventory
import font_web_convert
import minimal_xml_router
import universal_font_plan
from legacy_v14_4.composite_layout import (
    clear_imported_metric_variations,
    enclose_imported_bounds,
)

SCHEMA = "universal-font-artifacts-v1"
COMPILER_REVISION = 1
FONT_PLAN_SCHEMA = "universal-font-plan-v1"
ROUTE_SCHEMA = "minimal-xml-route-plan-v1"
ROUTABLE_ACTIONS = {"replace", "compile", "compile-specialized"}
SPECIALIZED_ROLES = {"clock", "numeric"}
GENERAL_ROLES = {"ui-sans", "latin", "cjk"}
COLLECTION_MAGIC = b"ttcf"
SFNT_MAGIC = {
    b"\x00\x01\x00\x00": "TTF",
    b"true": "TTF",
    b"\x00\x02\x00\x00": "TTF",
    b"OTTO": "OTF",
    b"ttcf": "COLLECTION",
}
DROP_AFTER_OUTLINE_CHANGE = {"DSIG", "LTSH", "VDMX", "hdmx"}
LATIN_COMBINING_RANGES = (
    (0x0300, 0x036F),
    (0x1AB0, 0x1AFF),
    (0x1DC0, 0x1DFF),
)
CLOCK_PUNCTUATION = set(map(ord, ":.,，。/-+%()[]"))
MAX_POST_ALIGNMENT_EM = 0.05
MAX_POST_HEIGHT_DELTA = 0.14
MAX_VARIABLE_NATURAL_ALIGNMENT_EM = 0.055
MAX_VARIABLE_HEIGHT_DELTA = 0.12


class CompilerError(RuntimeError):
    pass


def _int(value: Any, default: int = 0) -> int:
    try:
        if isinstance(value, bool):
            return default
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _float(value: Any, default: float | None = None) -> float | None:
    try:
        if isinstance(value, bool):
            return default
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return result if math.isfinite(result) else default


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CompilerError(f"无法读取 JSON：{path}") from error
    if not isinstance(value, dict):
        raise CompilerError(f"JSON 根节点不是对象：{path}")
    return value


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise CompilerError(f"无法读取文件：{path}") from error
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".tmp.{os.getpid()}")
    try:
        temp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _magic(path: Path) -> bytes:
    try:
        with path.open("rb") as stream:
            return stream.read(4)
    except OSError as error:
        raise CompilerError(f"无法读取字体：{path}") from error


def _font_container(path: Path) -> str:
    magic = _magic(path)
    if magic == COLLECTION_MAGIC:
        suffix = path.suffix.lower()
        return "OTC" if suffix == ".otc" else "TTC"
    value = SFNT_MAGIC.get(magic)
    if value == "TTF":
        return "TTF"
    if value == "OTF":
        return "OTF"
    if magic == b"wOFF":
        return "WOFF"
    if magic == b"wOF2":
        return "WOFF2"
    raise CompilerError(f"无法识别字体容器：{path}")


def _outline_kind(font: TTFont) -> str:
    if "glyf" in font:
        return "glyf"
    if "CFF2" in font:
        return "cff2"
    if "CFF " in font:
        return "cff"
    raise CompilerError("字体不包含 glyf/CFF/CFF2 轮廓")


def _file_uid_matches(source: dict[str, Any], path: Path) -> None:
    expected = str(source.get("fileUid") or "")
    if not expected.startswith("sha256:"):
        raise CompilerError("FontPlan source 缺少 fileUid")
    actual = "sha256:" + _sha256(path)
    if actual != expected:
        raise CompilerError(f"源字体内容已变化：{path.name}")


def _axis_values(raw_axes: Any) -> dict[str, float]:
    result: dict[str, float] = {}
    if not isinstance(raw_axes, list):
        return result
    for item in raw_axes:
        if not isinstance(item, dict):
            continue
        tag = str(item.get("tag") or "").strip()
        if not tag:
            continue
        value = (
            item.get("stylevalue")
            if item.get("stylevalue") not in (None, "")
            else item.get("styleValue")
            if item.get("styleValue") not in (None, "")
            else item.get("value")
        )
        parsed = _float(value)
        if parsed is not None:
            result[tag] = parsed
    return result


def _profile_from_font(font: TTFont) -> dict[str, Any]:
    if "head" not in font or "hhea" not in font:
        raise CompilerError("字体缺少 head/hhea")
    head = font["head"]
    hhea = font["hhea"]
    os2 = font["OS/2"] if "OS/2" in font else None
    metrics: dict[str, Any] = {
        "unitsPerEm": int(head.unitsPerEm),
        "headYMin": int(getattr(head, "yMin", 0)),
        "headYMax": int(getattr(head, "yMax", 0)),
        "hheaAscent": int(hhea.ascent),
        "hheaDescent": int(hhea.descent),
        "hheaLineGap": int(hhea.lineGap),
        "typoAscender": int(getattr(os2, "sTypoAscender", 0)) if os2 else None,
        "typoDescender": int(getattr(os2, "sTypoDescender", 0)) if os2 else None,
        "typoLineGap": int(getattr(os2, "sTypoLineGap", 0)) if os2 else None,
        "winAscent": int(getattr(os2, "usWinAscent", 0)) if os2 else None,
        "winDescent": int(getattr(os2, "usWinDescent", 0)) if os2 else None,
        "capHeight": int(getattr(os2, "sCapHeight", 0)) if os2 and hasattr(os2, "sCapHeight") else None,
        "xHeight": int(getattr(os2, "sxHeight", 0)) if os2 and hasattr(os2, "sxHeight") else None,
        "weightClass": int(getattr(os2, "usWeightClass", 400)) if os2 else 400,
        "widthClass": int(getattr(os2, "usWidthClass", 5)) if os2 else 5,
        "fsSelection": int(getattr(os2, "fsSelection", 0)) if os2 else 0,
    }
    return {
        "path": "",
        "faceIndex": -1,
        "names": sorted(template_engine.font_names(font)),
        "metrics": metrics,
        "probeSchema": template_engine.PROBE_SCHEMA,
        "probes": {
            name: template_engine.glyph_group(font, points)
            for name, points in template_engine.PROBE_GROUPS.items()
        },
    }


def _instantiate(font: TTFont, weight: int, axes: dict[str, float]) -> tuple[TTFont, dict[str, float]]:
    if "fvar" not in font:
        if axes:
            unknown = ", ".join(sorted(axes))
            raise CompilerError(f"静态源字体无法满足 variable axis：{unknown}")
        if "OS/2" in font:
            actual = int(font["OS/2"].usWeightClass)
            if actual != weight:
                raise CompilerError(f"静态源字重 {actual} 不能伪装成目标字重 {weight}")
        return font, {}

    location: dict[str, float] = {}
    known = {str(axis.axisTag): axis for axis in font["fvar"].axes}
    for tag in axes:
        if tag not in known:
            # For stock-shell the source does not need every target axis, but a
            # caller passes only source-relevant axes here.
            continue
    for tag, axis in known.items():
        requested = axes.get(tag)
        if requested is None:
            requested = weight if tag == "wght" else float(axis.defaultValue)
        if requested < float(axis.minValue) or requested > float(axis.maxValue):
            raise CompilerError(
                f"源字体轴 {tag}={requested:g} 超出范围 "
                f"[{float(axis.minValue):g},{float(axis.maxValue):g}]"
            )
        location[tag] = float(requested)
    try:
        instance = instantiateVariableFont(font, location, inplace=False, optimize=True)
    except Exception as error:
        raise CompilerError(f"可变字体实例化失败：{error}") from error
    return instance, location


def _open_face(path: Path, face_index: int, *, lazy: bool = False) -> TTFont:
    kwargs: dict[str, Any] = {
        "lazy": lazy,
        "recalcTimestamp": False,
        "recalcBBoxes": not lazy,
    }
    if _magic(path) == COLLECTION_MAGIC:
        kwargs["fontNumber"] = max(0, face_index)
    elif face_index > 0:
        raise CompilerError(f"单字体文件不能读取 faceIndex={face_index}：{path.name}")
    try:
        return TTFont(str(path), **kwargs)
    except Exception as error:
        raise CompilerError(f"fontTools 无法打开字体 {path.name}：{error}") from error


def _source_instance(
    source: dict[str, Any],
    weight: int,
    axes: dict[str, float],
    temp_root: Path,
) -> tuple[TTFont, dict[str, Any]]:
    raw = Path(str(source.get("sourcePath") or ""))
    if not raw.is_file():
        raise CompilerError(f"源字体不存在：{raw}")
    _file_uid_matches(source, raw)
    converted: dict[str, Any] | None = None
    source_path = raw
    container = _font_container(raw)
    if container in {"WOFF", "WOFF2"}:
        converted = font_web_convert.convert(raw, temp_root / "web")
        source_path = Path(str(converted["outputPath"]))

    face_index = max(0, _int(source.get("faceIndex"), 0))
    original = _open_face(source_path, face_index)
    try:
        instance, location = _instantiate(original, weight, axes)
        if instance is original:
            # Caller owns the returned font; do not close it here.
            original = None
        return instance, {
            "inputPath": str(raw),
            "materializedPath": str(source_path),
            "inputContainer": container,
            "faceIndex": face_index,
            "variable": bool(location),
            "location": location,
            "conversion": converted,
        }
    finally:
        if original is not None:
            original.close()


def _stock_map(path: Path | None) -> dict[str, Path]:
    if path is None:
        return {}
    raw = _load(path)
    result: dict[str, Path] = {}
    for key, value in raw.items():
        logical = str(key).strip()
        actual = str(value).strip()
        if logical.startswith("/") and actual:
            result[logical] = Path(actual)
    return result


def _lower_stock_candidate(logical: Path) -> Path | None:
    parts = logical.parts
    if len(parts) < 4 or parts[0] != "/" or parts[2] != "fonts":
        return None
    state_root = Path(
        os.environ.get("LUOSHU_SELF_MOUNT_STATE_ROOT", "/data/adb/luoshu/self-mount")
    )
    candidate = state_root / "lower" / f"{parts[1]}-fonts" / Path(*parts[3:])
    return candidate if candidate.is_file() else None


def _mirror_stock_candidate(logical: Path) -> Path | None:
    for prefix in font_inventory.MIRROR_PREFIXES:
        candidate = prefix / logical.relative_to("/")
        if candidate.is_file():
            return candidate
    return None


def _resolve_stock(
    logical_value: str,
    explicit: dict[str, Path],
    allow_live: bool,
) -> Path:
    logical = Path(logical_value)
    candidate = explicit.get(logical_value)
    if candidate is not None and candidate.is_file():
        return candidate
    candidate = _lower_stock_candidate(logical)
    if candidate is not None:
        return candidate
    candidate = _mirror_stock_candidate(logical)
    if candidate is not None:
        return candidate
    if allow_live and logical.is_file():
        return logical
    raise CompilerError(f"找不到可验证的原厂字体快照：{logical_value}")


def _validate_stock_contract(target: dict[str, Any], stock: Path, face_index: int) -> dict[str, Any]:
    contract = target.get("targetContract") if isinstance(target.get("targetContract"), dict) else {}
    font = _open_face(stock, face_index, lazy=True)
    try:
        actual = _profile_from_font(font)
        metrics = actual["metrics"]
        frozen = contract.get("metrics") if isinstance(contract.get("metrics"), dict) else {}
        expected_upem = _int(frozen.get("upem"), 0)
        expected_hhea = frozen.get("hhea") if isinstance(frozen.get("hhea"), dict) else {}
        if expected_upem and int(metrics["unitsPerEm"]) != expected_upem:
            raise CompilerError("原厂字体 UPEM 与 FontPlan targetContract 不一致")
        expected_ascent = _int(expected_hhea.get("ascent"), 0)
        expected_descent = _int(expected_hhea.get("descent"), 0)
        if expected_ascent and int(metrics["hheaAscent"]) != expected_ascent:
            raise CompilerError("原厂字体 hhea ascent 与 FontPlan 不一致")
        if expected_descent and int(metrics["hheaDescent"]) != expected_descent:
            raise CompilerError("原厂字体 hhea descent 与 FontPlan 不一致")
        return actual
    finally:
        font.close()


def _source_axis_spec_for_route(source: TTFont, artifact: dict[str, Any], weight: int) -> dict[str, float]:
    requested = _axis_values(artifact.get("requiredAxes"))
    if "fvar" not in source:
        return {}
    known = {str(axis.axisTag) for axis in source["fvar"].axes}
    result = {tag: value for tag, value in requested.items() if tag in known}
    if "wght" in known and "wght" not in result:
        result["wght"] = float(weight)
    return result


def _stock_geometry_font(
    stock: Path,
    face_index: int,
    weight: int,
    axes: dict[str, float],
) -> tuple[TTFont, dict[str, float]]:
    original = _open_face(stock, face_index)
    if "fvar" not in original:
        return original, {}
    known = {str(axis.axisTag): axis for axis in original["fvar"].axes}
    location: dict[str, float] = {}
    for tag, axis in known.items():
        requested = axes.get(tag)
        if requested is None:
            requested = weight if tag == "wght" else float(axis.defaultValue)
        requested = max(float(axis.minValue), min(float(axis.maxValue), float(requested)))
        location[tag] = requested
    try:
        instance = instantiateVariableFont(original, location, inplace=False, optimize=True)
    except Exception as error:
        original.close()
        raise CompilerError(f"原厂 variable geometry 实例化失败：{error}") from error
    original.close()
    return instance, location


def _slot_roles(role: str) -> list[str]:
    if role in SPECIALIZED_ROLES:
        return ["clock"]
    return ["global-ui"]


def _geometry_plan(
    target: dict[str, Any],
    stock_profile: dict[str, Any],
    source_profile: dict[str, Any],
    weight: int,
) -> dict[str, Any]:
    families = target.get("families") if isinstance(target.get("families"), list) else []
    family = str(families[0]) if families else ""
    spec = {
        "family": family,
        "familyNormalized": family.lower(),
        "weight": weight,
        "style": "italic" if target.get("targetContract", {}).get("italic") else "normal",
        "index": _int(target.get("targetContract", {}).get("faceIndex"), 0),
        "axes": "",
        "roles": _slot_roles(str(target.get("role") or "")),
        "sourceXml": "",
        "resolvedPath": str(target.get("path") or ""),
        "replaceable": True,
        "font": stock_profile,
    }
    plan = slot_plan_engine.slot_plan(spec, source_profile)
    if plan.get("status") != "ready":
        unsafe = list(plan.get("unsafeProbes") or [])
        degraded = list(plan.get("degradedProbes") or [])
        if unsafe:
            reason = "unsafe-probes:" + ",".join(unsafe)
        elif degraded:
            reason = "degraded-probes:" + ",".join(degraded)
        else:
            reason = str(plan.get("reason") or plan.get("status") or "unresolved")
        raise CompilerError(f"目标槽位几何计划不可安全编译：{reason}")
    return plan


def _bounds(glyph_set: Any, glyph_name: str) -> tuple[float, float, float, float] | None:
    if glyph_name not in glyph_set:
        return None
    pen = BoundsPen(glyph_set)
    try:
        glyph_set[glyph_name].draw(pen)
    except Exception:
        return None
    return tuple(float(value) for value in pen.bounds) if pen.bounds is not None else None


def _eligible_codepoint(role: str, codepoint: int) -> bool:
    probe = slot_build.probe_for_codepoint(codepoint)
    if role == "cjk":
        return probe in {"cjk", "punctuationFullwidth"}
    if role == "latin":
        if probe in {
            "latinCap", "latinX", "latinDescender",
            "digits", "punctuationBaseline", "punctuationCenter",
        }:
            return True
        return any(start <= codepoint <= end for start, end in LATIN_COMBINING_RANGES)
    if role in SPECIALIZED_ROLES:
        return slot_build.is_digit(codepoint) or codepoint in CLOCK_PUNCTUATION
    if role == "ui-sans":
        if probe is not None:
            return True
        try:
            category = unicodedata.category(chr(codepoint))
        except (ValueError, IndexError):
            return False
        return category.startswith(("L", "M", "N", "P")) or category in {"Zs", "Sc", "Sm"}
    return False


def _transform_for_codepoint(
    geometry: dict[str, Any],
    codepoint: int,
    exact_advance: bool,
) -> tuple[float, float, float]:
    upem_scale = float(geometry.get("upemScale") or 1.0)
    probe = slot_build.probe_for_codepoint(codepoint)
    if probe is None:
        if any(start <= codepoint <= end for start, end in LATIN_COMBINING_RANGES):
            probe = "latinX"
        else:
            probe = "punctuationCenter"
    transform = slot_build.transform_for_probe(geometry, probe)
    if not isinstance(transform, dict):
        return upem_scale, upem_scale, 0.0
    scale_y = _float(transform.get("outlineScaleY"), upem_scale) or upem_scale
    if exact_advance:
        scale_x = _float(transform.get("outlineScaleXForExactInk"), upem_scale) or upem_scale
    else:
        scale_x = upem_scale
    shift_y = _float(transform.get("shiftY"), 0.0) or 0.0
    return float(scale_x), float(scale_y), float(shift_y)


def _replace_glyf_outline(
    base: TTFont,
    source: TTFont,
    source_glyph_set: Any,
    base_name: str,
    source_name: str,
    transform: Transform,
) -> tuple[int, int, int, int] | None:
    source_kind = _outline_kind(source)
    source_glyf = source["glyf"] if source_kind == "glyf" else None
    if source_glyf is not None:
        glyph = source_glyf[source_name]
        if glyph.numberOfContours >= 0:
            copied = copy.deepcopy(glyph)
            if copied.numberOfContours > 0:
                copied.coordinates.transform(((transform.xx, transform.xy), (transform.yx, transform.yy)))
                copied.coordinates.translate((transform.dx, transform.dy))
                copied.coordinates.toInt()
            base["glyf"][base_name] = copied
            copied.recalcBounds(base["glyf"])
            if not hasattr(copied, "xMin"):
                copied.xMin = copied.yMin = copied.xMax = copied.yMax = 0
            if "gvar" in base:
                base["gvar"].variations.pop(base_name, None)
            return int(copied.xMin), int(copied.yMin), int(copied.xMax), int(copied.yMax)

    pen = TTGlyphPen(None)
    output_pen: Any = pen
    if source_kind in {"cff", "cff2"}:
        output_pen = Cu2QuPen(
            pen,
            max_err=max(0.5, base["head"].unitsPerEm / 2000),
            reverse_direction=True,
        )
    recorder = DecomposingRecordingPen(source_glyph_set)
    source_glyph_set[source_name].draw(recorder)
    recorder.replay(TransformPen(output_pen, transform))
    glyph = pen.glyph()
    base["glyf"][base_name] = glyph
    glyph.recalcBounds(base["glyf"])
    if not hasattr(glyph, "xMin"):
        glyph.xMin = glyph.yMin = glyph.xMax = glyph.yMax = 0
    if "gvar" in base:
        base["gvar"].variations.pop(base_name, None)
    return int(glyph.xMin), int(glyph.yMin), int(glyph.xMax), int(glyph.yMax)


def _replace_cff_outline(
    base: TTFont,
    source: TTFont,
    source_glyph_set: Any,
    base_name: str,
    source_name: str,
    transform: Transform,
    width: int,
) -> tuple[float, float, float, float] | None:
    tag = "CFF " if "CFF " in base else "CFF2"
    cff = base[tag].cff
    top = cff.topDictIndex[0]
    _old, selector = top.CharStrings.getItemAndSelector(base_name)
    if hasattr(top, "FDArray"):
        private = top.FDArray[selector or 0].Private
    else:
        private = top.Private
    is_cff2 = tag == "CFF2"
    pen = T2CharStringPen(None if is_cff2 else width, None, CFF2=is_cff2)
    output_pen: Any = pen
    if _outline_kind(source) == "glyf":
        output_pen = Qu2CuPen(
            pen,
            max_err=max(0.5, base["head"].unitsPerEm / 2000),
            all_cubic=True,
            reverse_direction=True,
        )
    recorder = DecomposingRecordingPen(source_glyph_set)
    source_glyph_set[source_name].draw(recorder)
    recorder.replay(TransformPen(output_pen, transform))
    char_string = pen.getCharString(private=private, globalSubrs=cff.GlobalSubrs)
    if selector is not None:
        char_string.fdSelectIndex = selector
    top.CharStrings[base_name] = char_string
    try:
        return tuple(float(value) for value in char_string.calcBounds(top.CharStrings))
    except Exception:
        return None


def _replace_role_glyphs(
    base: TTFont,
    source: TTFont,
    role: str,
    geometry: dict[str, Any],
) -> dict[str, Any]:
    base_cmap = base.getBestCmap() or {}
    source_cmap = source.getBestCmap() or {}
    source_glyph_set = source.getGlyphSet()
    base_kind = _outline_kind(base)
    if "gvar" in base:
        # gvar deltas are decoded against each glyph's original point count, so
        # they must be fully decoded before any outline below is replaced.
        base["gvar"].ensureDecompiled()
    source_kind = _outline_kind(source)
    exact = role in SPECIALIZED_ROLES
    replaced = 0
    missing_required: list[int] = []
    seen: set[tuple[str, str]] = set()
    base_hmtx = base["hmtx"].metrics
    source_hmtx = source["hmtx"].metrics
    exact_mismatches = 0

    required: set[int]
    if role in SPECIALIZED_ROLES:
        required = set(map(ord, "0123456789"))
    elif role == "latin":
        required = set(map(ord, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"))
    elif role == "cjk":
        required = set(template_engine.PROBE_GROUPS["cjk"])
    else:
        required = set(map(ord, "AaHhx0123456789"))
        if any(cp in base_cmap for cp in template_engine.PROBE_GROUPS["cjk"]):
            required.update(template_engine.PROBE_GROUPS["cjk"])

    for cp in sorted(set(base_cmap).intersection(source_cmap)):
        if not _eligible_codepoint(role, cp):
            continue
        base_name = base_cmap[cp]
        source_name = source_cmap[cp]
        pair = (base_name, source_name)
        if pair in seen:
            continue
        seen.add(pair)
        if base_name not in base_hmtx or source_name not in source_hmtx:
            continue
        source_bounds = _bounds(source_glyph_set, source_name)
        if source_bounds is None:
            if cp in required:
                missing_required.append(cp)
            continue

        scale_x, scale_y, shift_y = _transform_for_codepoint(geometry, cp, exact)
        source_advance, source_lsb = source_hmtx[source_name]
        old_advance, _old_lsb = base_hmtx[base_name]
        if exact:
            target_advance = int(old_advance)
            ink_width = (source_bounds[2] - source_bounds[0]) * scale_x
            desired_x_min = (target_advance - ink_width) / 2.0
            shift_x = desired_x_min - source_bounds[0] * scale_x
            new_lsb = int(round(desired_x_min))
            new_advance = target_advance
        else:
            shift_x = 0.0
            new_advance = max(1, min(65535, int(round(float(source_advance) * float(geometry.get("upemScale") or 1.0)))))
            new_lsb = int(round(float(source_lsb) * float(geometry.get("upemScale") or 1.0)))

        transform = Transform(scale_x, 0, 0, scale_y, shift_x, shift_y)
        if base_kind == "glyf":
            bounds = _replace_glyf_outline(
                base, source, source_glyph_set, base_name, source_name, transform
            )
        else:
            bounds = _replace_cff_outline(
                base, source, source_glyph_set, base_name, source_name, transform, new_advance
            )
        if bounds is not None:
            enclose_imported_bounds(base, bounds)
            if exact:
                new_lsb = int(round(float(bounds[0])))
        base_hmtx[base_name] = (new_advance, new_lsb)
        clear_imported_metric_variations(base, base_name)
        if exact and int(base_hmtx[base_name][0]) != int(old_advance):
            exact_mismatches += 1
        replaced += 1

    for cp in required:
        if cp not in source_cmap or cp not in base_cmap:
            missing_required.append(cp)
    missing_required = sorted(set(missing_required))
    if missing_required:
        preview = ",".join(f"U+{cp:04X}" for cp in missing_required[:16])
        raise CompilerError(f"目标/源字体缺少必要字形：{preview}")
    if replaced <= 0:
        raise CompilerError("没有可替换的目标脚本字形")
    if exact and exact_mismatches:
        raise CompilerError("Clock/Numeric exact-width 编译未保持原厂 advance")
    return {
        "baseOutline": base_kind,
        "sourceOutline": source_kind,
        "replacedGlyphs": replaced,
        "exactAdvance": exact,
        "exactAdvanceMismatches": exact_mismatches,
    }


def _apply_cff_source_transforms(font: TTFont, geometry: dict[str, Any]) -> dict[str, Any]:
    kind = _outline_kind(font)
    if kind not in {"cff", "cff2"}:
        raise CompilerError("CFF transform 仅接受 CFF/CFF2")
    glyph_set = font.getGlyphSet()
    probe_map = slot_build.glyph_probe_map(font)
    hmtx = font["hmtx"].metrics
    tag = "CFF " if "CFF " in font else "CFF2"
    cff = font[tag].cff
    top = cff.topDictIndex[0]
    recordings: dict[str, DecomposingRecordingPen] = {}
    for glyph_name in probe_map:
        if glyph_name not in glyph_set:
            continue
        recorder = DecomposingRecordingPen(glyph_set)
        try:
            glyph_set[glyph_name].draw(recorder)
        except Exception as error:
            raise CompilerError(f"CFF 字形 {glyph_name} 展开失败：{error}") from error
        recordings[glyph_name] = recorder

    changed = 0
    exact = "clock" in set(geometry.get("roles") or [])
    upem_scale = float(geometry.get("upemScale") or 1.0)
    for glyph_name, probe in probe_map.items():
        transform_data = slot_build.transform_for_probe(geometry, probe)
        if not isinstance(transform_data, dict) or glyph_name not in recordings or glyph_name not in hmtx:
            continue
        scale_y = _float(transform_data.get("relativeScaleY"), 1.0) or 1.0
        # apply_line_contract has already scaled UPEM, so remaining CFF transform
        # must use relative Y/X values, mirroring the glyf builder.
        scale_x = 1.0
        if exact:
            scale_x = _float(transform_data.get("relativeInkScaleX"), 1.0) or 1.0
        shift_y = _float(transform_data.get("shiftY"), 0.0) or 0.0

        old_advance, old_lsb = hmtx[glyph_name]
        target_advance = _float(transform_data.get("targetAdvance"))
        new_advance = int(round(target_advance if exact and target_advance else old_advance))
        bounds_before = _bounds(glyph_set, glyph_name)
        shift_x = 0.0
        new_lsb = int(old_lsb)
        if exact and bounds_before is not None:
            ink_width = (bounds_before[2] - bounds_before[0]) * scale_x
            desired = (new_advance - ink_width) / 2.0
            shift_x = desired - bounds_before[0] * scale_x
            new_lsb = int(round(desired))

        _old, selector = top.CharStrings.getItemAndSelector(glyph_name)
        private = top.FDArray[selector or 0].Private if hasattr(top, "FDArray") else top.Private
        is_cff2 = tag == "CFF2"
        pen = T2CharStringPen(None if is_cff2 else new_advance, None, CFF2=is_cff2)
        recordings[glyph_name].replay(
            TransformPen(pen, Transform(scale_x, 0, 0, scale_y, shift_x, shift_y))
        )
        char_string = pen.getCharString(private=private, globalSubrs=cff.GlobalSubrs)
        if selector is not None:
            char_string.fdSelectIndex = selector
        top.CharStrings[glyph_name] = char_string
        try:
            bounds_after = char_string.calcBounds(top.CharStrings)
            if bounds_after is not None:
                enclose_imported_bounds(font, bounds_after)
                if exact:
                    new_lsb = int(round(float(bounds_after[0])))
        except Exception:
            pass
        hmtx[glyph_name] = (max(1, min(65535, new_advance)), new_lsb)
        clear_imported_metric_variations(font, glyph_name)
        changed += 1
    return {"glyphs": changed, "outline": kind, "upemScale": upem_scale}


def _set_postscript_name(font: TTFont, required: str, artifact_id: str) -> str:
    if "name" not in font:
        if required:
            raise CompilerError("目标要求 PostScriptName，但字体缺少 name 表")
        return ""
    safe = re.sub(r"[^A-Za-z0-9-]+", "-", artifact_id.replace("ufc:", "LuoShuUF-"))[:55].strip("-")
    postscript = required or safe or "LuoShuUF"
    table = font["name"]
    table.setName(postscript, 6, 3, 1, 0x409)
    return postscript


def _drop_stale_tables(font: TTFont) -> None:
    for tag in DROP_AFTER_OUTLINE_CHANGE:
        if tag in font:
            del font[tag]
    if "head" in font:
        font["head"].checkSumAdjustment = 0


def _validate_compiled_file(path: Path, expected_collection: bool) -> None:
    if not path.is_file() or path.stat().st_size < 256:
        raise CompilerError("编译输出异常为空或截断")
    if expected_collection:
        try:
            collection = TTCollection(str(path), lazy=True)
        except Exception as error:
            raise CompilerError(f"编译集合字体无法重新解析：{error}") from error
        try:
            if not collection.fonts:
                raise CompilerError("编译集合字体没有 face")
            for index, font in enumerate(collection.fonts):
                if "head" not in font or "cmap" not in font:
                    raise CompilerError(f"编译集合 face {index} 缺少 head/cmap")
                _outline_kind(font)
        finally:
            collection.close()
        return
    try:
        font = TTFont(str(path), lazy=True, recalcTimestamp=False)
    except Exception as error:
        raise CompilerError(f"编译字体无法重新解析：{error}") from error
    try:
        if "head" not in font or "cmap" not in font:
            raise CompilerError("编译字体缺少 head/cmap")
        _outline_kind(font)
    finally:
        font.close()


def _save_font(font: TTFont, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    try:
        font.save(str(temp), reorderTables=False)
        _validate_compiled_file(temp, expected_collection=False)
        os.chmod(temp, 0o644)
        os.replace(temp, output)
    finally:
        temp.unlink(missing_ok=True)


def _save_collection(collection: TTCollection, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    try:
        collection.save(str(temp), shareTables=True)
        _validate_compiled_file(temp, expected_collection=True)
        os.chmod(temp, 0o644)
        os.replace(temp, output)
    finally:
        temp.unlink(missing_ok=True)


def _open_stock_container(stock: Path, face_index: int) -> tuple[TTFont, TTCollection | None]:
    if _magic(stock) != COLLECTION_MAGIC:
        if face_index > 0:
            raise CompilerError("目标要求 collection face，但原厂字体不是集合")
        return _open_face(stock, 0), None
    collection = TTCollection(str(stock), lazy=False)
    if face_index < 0 or face_index >= len(collection.fonts):
        collection.close()
        raise CompilerError(f"原厂 collection faceIndex={face_index} 越界")
    return collection.fonts[face_index], collection


def _copy_compiled_face_into_stock_container(
    stock: Path,
    face_index: int,
    compiled_face: TTFont,
    output: Path,
) -> None:
    if _magic(stock) != COLLECTION_MAGIC:
        if face_index > 0:
            raise CompilerError("目标要求 collection face，但原厂字体不是集合")
        _save_font(compiled_face, output)
        return
    collection = TTCollection(str(stock), lazy=False)
    try:
        if face_index < 0 or face_index >= len(collection.fonts):
            raise CompilerError(f"原厂 collection faceIndex={face_index} 越界")
        old = collection.fonts[face_index]
        collection.fonts[face_index] = compiled_face
        if old is not compiled_face:
            old.close()
        _save_collection(collection, output)
    finally:
        # compiled_face is owned by caller and may already be closed later.
        for index, font in enumerate(collection.fonts):
            if font is compiled_face:
                continue
            try:
                font.close()
            except Exception:
                pass


def _artifact_extension(target: dict[str, Any]) -> str:
    contract = target.get("targetContract") if isinstance(target.get("targetContract"), dict) else {}
    fmt = str(contract.get("format") or "").upper()
    suffix = Path(str(target.get("path") or "")).suffix.lower()
    if fmt == "OTC" or suffix == ".otc":
        return ".otc"
    if fmt == "TTC" or suffix == ".ttc":
        return ".ttc"
    if fmt == "OTF" or suffix == ".otf":
        return ".otf"
    return ".ttf"


def _physical_artifact(target: dict[str, Any], font_plan: dict[str, Any]) -> dict[str, Any]:
    contract = target.get("targetContract") if isinstance(target.get("targetContract"), dict) else {}
    semantic = {
        "kind": "physical-target",
        "fontPlanId": font_plan.get("planId"),
        "targetPath": target.get("path"),
        "role": target.get("role"),
        "compiler": target.get("compiler"),
        "requirements": target.get("requirements"),
        "source": target.get("source"),
        "targetContract": contract,
    }
    digest = _canonical_hash(semantic)
    ext = _artifact_extension(target)
    return {
        "artifactId": f"ufc:{digest[:32]}",
        "suggestedFileName": f"LuoShu-UF-{digest[:20]}{ext}",
        "container": "collection" if ext in {".ttc", ".otc"} else "sfnt",
        "requiredFaceIndex": max(0, _int(contract.get("faceIndex"), 0)),
        "requiredPostScriptName": "",
        "requiredAxes": [],
        "requiredWeight": _int(contract.get("weight"), 400),
        "requiredStyle": "italic" if contract.get("italic") else "normal",
        "preserveXmlAttributes": False,
        "preserveAxisChildren": False,
    }


def _collect_units(font_plan: dict[str, Any], route_plan: dict[str, Any]) -> list[dict[str, Any]]:
    targets = font_plan.get("targets")
    if not isinstance(targets, dict):
        raise CompilerError("FontPlan 缺少 targets")
    units: dict[str, dict[str, Any]] = {}

    documents = route_plan.get("documents")
    if not isinstance(documents, dict):
        raise CompilerError("RoutePlan 缺少 documents")
    for source_xml, document in documents.items():
        if not isinstance(document, dict):
            continue
        for operation in document.get("operations") or []:
            if not isinstance(operation, dict):
                continue
            artifact = operation.get("artifact")
            target_path = str(operation.get("targetPath") or "")
            target = targets.get(target_path)
            if not isinstance(artifact, dict) or not isinstance(target, dict):
                continue
            artifact_id = str(artifact.get("artifactId") or "")
            unit = units.setdefault(artifact_id, {
                "artifact": copy.deepcopy(artifact),
                "target": copy.deepcopy(target),
                "deploymentKinds": [],
                "routeNodes": [],
            })
            if unit["artifact"] != artifact or unit["target"].get("path") != target_path:
                raise CompilerError(f"同一 artifactId 对应不同编译契约：{artifact_id}")
            if "xml-route" not in unit["deploymentKinds"]:
                unit["deploymentKinds"].append("xml-route")
            unit["routeNodes"].append({
                "sourceXml": source_xml,
                "ordinal": _int(operation.get("node", {}).get("ordinal"), 0),
                "nodeFingerprint": str(operation.get("nodeFingerprint") or ""),
            })

    deferred = set(route_plan.get("deferredDynamicTargets") or [])
    physical_only = set(route_plan.get("physicalOnlyTargets") or [])
    for target_path in sorted(physical_only):
        target = targets.get(target_path)
        if not isinstance(target, dict):
            raise CompilerError(f"RoutePlan physicalOnly target 不存在于 FontPlan：{target_path}")
        if str(target.get("action") or "") not in ROUTABLE_ACTIONS:
            raise CompilerError(f"RoutePlan physicalOnly target 不是可编译目标：{target_path}")
        if target_path.startswith("/data/fonts/") or target_path in deferred:
            raise CompilerError(f"动态字体目标不得作为 physical-only artifact：{target_path}")
        artifact = _physical_artifact(target, font_plan)
        artifact_id = str(artifact["artifactId"])
        unit = units.setdefault(artifact_id, {
            "artifact": artifact,
            "target": copy.deepcopy(target),
            "deploymentKinds": [],
            "routeNodes": [],
        })
        if "physical-slot" not in unit["deploymentKinds"]:
            unit["deploymentKinds"].append("physical-slot")

    for target_path in sorted(deferred):
        target = targets.get(target_path)
        if not isinstance(target, dict):
            raise CompilerError(f"RoutePlan dynamic target 不存在于 FontPlan：{target_path}")
        if str(target.get("action") or "") not in ROUTABLE_ACTIONS:
            raise CompilerError(f"RoutePlan dynamic target 不是可编译目标：{target_path}")
        if not target_path.startswith("/data/fonts/"):
            raise CompilerError(f"dynamic target 不在 /data/fonts：{target_path}")
        artifact = _physical_artifact(target, font_plan)
        artifact_id = str(artifact["artifactId"])
        unit = units.setdefault(artifact_id, {
            "artifact": artifact,
            "target": copy.deepcopy(target),
            "deploymentKinds": [],
            "routeNodes": [],
        })
        if "dynamic-slot" not in unit["deploymentKinds"]:
            unit["deploymentKinds"].append("dynamic-slot")

    for unit in units.values():
        unit["deploymentKinds"].sort()
        unit["routeNodes"].sort(key=lambda item: (item["sourceXml"], item["ordinal"]))
    return [units[key] for key in sorted(units)]


def _target_variable_axes(target: dict[str, Any]) -> dict[str, tuple[float, float, float]]:
    contract = target.get("targetContract") if isinstance(target.get("targetContract"), dict) else {}
    metrics = contract.get("metrics") if isinstance(contract.get("metrics"), dict) else {}
    raw = metrics.get("variationAxes")
    result: dict[str, tuple[float, float, float]] = {}
    if not isinstance(raw, list):
        return result
    for axis in raw:
        if not isinstance(axis, dict):
            continue
        tag = str(axis.get("tag") or "").strip()
        minimum = _float(axis.get("minimum", axis.get("min")))
        default = _float(axis.get("default"))
        maximum = _float(axis.get("maximum", axis.get("max")))
        if tag and None not in (minimum, default, maximum):
            result[tag] = (float(minimum), float(default), float(maximum))
    return result


def _member_axis_ranges(artifact: dict[str, Any]) -> dict[str, tuple[float, float, float]]:
    """Axis ranges actually exercised by the XML nodes sharing a group artifact."""
    values: dict[str, list[float]] = {}
    for member in artifact.get("variableMembers") or []:
        for tag, value in _axis_values(member.get("axes") if isinstance(member, dict) else None).items():
            values.setdefault(tag, []).append(value)
    return {tag: (min(items), min(items), max(items)) for tag, items in values.items()}


def _validate_source_variable_compat(
    source_font: TTFont,
    target: dict[str, Any],
    artifact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if "fvar" not in source_font:
        raise CompilerError("物理 variable 目标要求源字体保持 variable，但源字体不是 variable")
    source_axes = {
        str(axis.axisTag): (float(axis.minValue), float(axis.defaultValue), float(axis.maxValue))
        for axis in source_font["fvar"].axes
    }
    if artifact is not None and artifact.get("variableGroup") is True:
        # XML nodes name the axis values Android will instantiate; the source
        # must reach exactly those, not every axis the stock file happens to have.
        target_axes = _member_axis_ranges(artifact)
    else:
        target_axes = _target_variable_axes(target)
    if not target_axes:
        raise CompilerError("FontPlan 将目标标为 variable，但缺少 target variationAxes")
    for tag, (target_min, _target_default, target_max) in target_axes.items():
        source_range = source_axes.get(tag)
        if source_range is None:
            raise CompilerError(f"源 variable font 缺少目标轴：{tag}")
        source_min, _source_default, source_max = source_range
        if source_min > target_min or source_max < target_max:
            raise CompilerError(
                f"源轴 {tag} 范围 [{source_min:g},{source_max:g}] "
                f"不能覆盖目标 [{target_min:g},{target_max:g}]"
            )
    return {"sourceAxes": source_axes, "targetAxes": target_axes}


def _line_contract_from_target(target: dict[str, Any], stock_profile: dict[str, Any]) -> dict[str, Any]:
    metrics = stock_profile.get("metrics") if isinstance(stock_profile.get("metrics"), dict) else {}
    return slot_plan_engine.line_contract(metrics)


def _apply_target_line_contract(font: TTFont, target: dict[str, Any], stock_profile: dict[str, Any]) -> None:
    slot = {"lineContract": _line_contract_from_target(target, stock_profile)}
    slot_build.apply_line_contract(font, slot)
    if "MVAR" in font:
        # Source MVAR would re-apply source-specific line deltas after Android
        # selects a variable instance. Fixed stock line metrics are intentional.
        del font["MVAR"]


def _probe_alignment(
    target_profile: dict[str, Any],
    output_profile: dict[str, Any],
    role: str,
    *,
    variable_natural: bool = False,
) -> dict[str, Any]:
    target_metrics = target_profile["metrics"]
    upem = float(target_metrics["unitsPerEm"])
    names: list[str]
    if role in SPECIALIZED_ROLES:
        names = ["digits", "punctuationCenter", "punctuationBaseline"]
    elif role == "cjk":
        names = ["cjk", "punctuationFullwidth"]
    elif role == "latin":
        names = ["latinCap", "latinX", "latinDescender", "digits"]
    else:
        names = ["latinCap", "latinX", "digits"]
        if int(target_profile["probes"].get("cjk", {}).get("hits") or 0):
            names.append("cjk")

    anchor_limit = MAX_VARIABLE_NATURAL_ALIGNMENT_EM if variable_natural else MAX_POST_ALIGNMENT_EM
    height_limit = MAX_VARIABLE_HEIGHT_DELTA if variable_natural else MAX_POST_HEIGHT_DELTA
    issues: list[str] = []
    details: dict[str, Any] = {}
    for name in names:
        target = target_profile["probes"].get(name)
        output = output_profile["probes"].get(name)
        if not isinstance(target, dict) or not isinstance(output, dict):
            continue
        if int(target.get("boundsHits") or 0) <= 0 or int(output.get("boundsHits") or 0) <= 0:
            continue
        target_height = _float(target.get("height"))
        output_height = _float(output.get("height"))
        if not target_height or not output_height:
            continue
        if name in {"latinCap", "latinX", "punctuationBaseline"}:
            target_anchor = _float(target.get("yMin"), 0.0) or 0.0
            output_anchor = _float(output.get("yMin"), 0.0) or 0.0
            anchor_kind = "baseline-bottom"
        else:
            target_anchor = _float(target.get("centerY"), 0.0) or 0.0
            output_anchor = _float(output.get("centerY"), 0.0) or 0.0
            anchor_kind = "center"
        anchor_delta = abs(output_anchor - target_anchor) / upem
        height_delta = abs(output_height - target_height) / max(target_height, 1.0)
        details[name] = {
            "anchor": anchor_kind,
            "anchorDeltaEm": round(anchor_delta, 8),
            "heightDeltaRatio": round(height_delta, 8),
        }
        if anchor_delta > anchor_limit:
            issues.append(f"{name}:anchor")
        if height_delta > height_limit:
            issues.append(f"{name}:height")
    return {
        "status": "ready" if not issues else "unsafe",
        "issues": sorted(issues),
        "probes": details,
        "anchorLimitEm": anchor_limit,
        "heightDeltaLimit": height_limit,
    }


def _instance_for_validation(font: TTFont, weight: int, axes: dict[str, float]) -> TTFont:
    if "fvar" not in font:
        return font
    known = {str(axis.axisTag): axis for axis in font["fvar"].axes}
    location: dict[str, float] = {}
    for tag, axis in known.items():
        value = axes.get(tag)
        if value is None:
            value = weight if tag == "wght" else float(axis.defaultValue)
        location[tag] = max(float(axis.minValue), min(float(axis.maxValue), float(value)))
    return instantiateVariableFont(font, location, inplace=False, optimize=True)


def _validate_output_face(
    output: Path,
    face_index: int,
    target: dict[str, Any],
    artifact: dict[str, Any],
    stock_profile: dict[str, Any],
    geometry_axes: dict[str, float],
    role: str,
    *,
    variable_natural: bool = False,
) -> dict[str, Any]:
    raw = _open_face(output, face_index)
    instance: TTFont | None = None
    try:
        instance = _instance_for_validation(
            raw,
            _int(artifact.get("requiredWeight"), _int(target.get("targetContract", {}).get("weight"), 400)),
            geometry_axes,
        )
        if instance is raw:
            raw = None
        profile = _profile_from_font(instance)
        required_ps = str(artifact.get("requiredPostScriptName") or "")
        if required_ps:
            names = template_engine.font_names(instance)
            if required_ps not in names:
                raise CompilerError(f"编译结果缺少 required PostScriptName：{required_ps}")
        required_axes = _axis_values(artifact.get("requiredAxes"))
        if required_axes:
            if "fvar" not in (instance if instance is not None else raw):
                # Validation instance is static after full instancing, so inspect
                # the uninstantiated output again for axis existence.
                axis_font = _open_face(output, face_index, lazy=True)
                try:
                    axis_tags = {str(axis.axisTag) for axis in axis_font["fvar"].axes} if "fvar" in axis_font else set()
                finally:
                    axis_font.close()
            else:
                axis_tags = {str(axis.axisTag) for axis in instance["fvar"].axes}
            missing = sorted(set(required_axes) - axis_tags)
            if missing:
                raise CompilerError("编译结果缺少 XML required axis：" + ",".join(missing))

        alignment = _probe_alignment(
            stock_profile, profile, role, variable_natural=variable_natural
        )
        if alignment["status"] != "ready":
            raise CompilerError("编译结果字形几何未通过原厂槽位校验：" + ",".join(alignment["issues"]))
        return {
            "profile": {
                "metrics": profile["metrics"],
                "probeSchema": profile["probeSchema"],
            },
            "alignment": alignment,
        }
    finally:
        if instance is not None:
            instance.close()
        if raw is not None:
            raw.close()


def _compile_source_as_base(
    target: dict[str, Any],
    artifact: dict[str, Any],
    stock: Path,
    output: Path,
    temp_root: Path,
) -> dict[str, Any]:
    source_info = target.get("source") if isinstance(target.get("source"), dict) else {}
    weight = _int(artifact.get("requiredWeight"), _int(target.get("targetContract", {}).get("weight"), 400))
    route_axes = _axis_values(artifact.get("requiredAxes"))

    probe_source_raw = Path(str(source_info.get("sourcePath") or ""))
    if not probe_source_raw.is_file():
        raise CompilerError(f"源字体不存在：{probe_source_raw}")
    _file_uid_matches(source_info, probe_source_raw)
    source_container = _font_container(probe_source_raw)
    materialized = probe_source_raw
    conversion = None
    if source_container in {"WOFF", "WOFF2"}:
        conversion = font_web_convert.convert(probe_source_raw, temp_root / "web")
        materialized = Path(str(conversion["outputPath"]))

    source_original = _open_face(materialized, max(0, _int(source_info.get("faceIndex"), 0)))
    compiled: TTFont | None = None
    stock_geometry: TTFont | None = None
    try:
        source_axes = _source_axis_spec_for_route(source_original, artifact, weight)
        compiled, source_location = _instantiate(source_original, weight, source_axes)
        if compiled is source_original:
            source_original = None

        stock_geometry, stock_location = _stock_geometry_font(
            stock,
            max(0, _int(artifact.get("requiredFaceIndex"), 0)),
            weight,
            route_axes,
        )
        stock_profile = _profile_from_font(stock_geometry)
        source_profile = _profile_from_font(compiled)
        geometry = _geometry_plan(target, stock_profile, source_profile, weight)

        target_kind = _outline_kind(stock_geometry)
        source_kind = _outline_kind(compiled)
        if target_kind != source_kind:
            raise CompilerError(
                f"source-as-base 不允许改变目标 outline flavor：{source_kind} -> {target_kind}"
            )

        slot_build.apply_line_contract(compiled, geometry)
        if source_kind == "glyf":
            transformed = slot_build.apply_outline_transforms(compiled, geometry)
        else:
            transformed = _apply_cff_source_transforms(compiled, geometry)
        if int(transformed.get("glyphs") or 0) <= 0:
            raise CompilerError("source-as-base 没有任何字形完成几何对齐")

        _set_postscript_name(compiled, str(artifact.get("requiredPostScriptName") or ""), str(artifact["artifactId"]))
        _drop_stale_tables(compiled)
        _copy_compiled_face_into_stock_container(
            stock,
            max(0, _int(artifact.get("requiredFaceIndex"), 0)),
            compiled,
            output,
        )
        validation = _validate_output_face(
            output,
            max(0, _int(artifact.get("requiredFaceIndex"), 0)),
            target,
            artifact,
            stock_profile,
            route_axes,
            str(target.get("role") or ""),
        )
        return {
            "mode": "source-as-base",
            "sourceContainer": source_container,
            "sourceLocation": source_location,
            "stockLocation": stock_location,
            "geometry": geometry,
            "transformed": transformed,
            "conversion": conversion,
            "validation": validation,
        }
    finally:
        if stock_geometry is not None:
            stock_geometry.close()
        if compiled is not None:
            compiled.close()
        if source_original is not None:
            source_original.close()


def _compile_stock_shell(
    target: dict[str, Any],
    artifact: dict[str, Any],
    stock: Path,
    output: Path,
    temp_root: Path,
) -> dict[str, Any]:
    source_info = target.get("source") if isinstance(target.get("source"), dict) else {}
    weight = _int(artifact.get("requiredWeight"), _int(target.get("targetContract", {}).get("weight"), 400))
    route_axes = _axis_values(artifact.get("requiredAxes"))
    source_path = Path(str(source_info.get("sourcePath") or ""))
    if not source_path.is_file():
        raise CompilerError(f"源字体不存在：{source_path}")
    _file_uid_matches(source_info, source_path)
    source_container = _font_container(source_path)
    materialized = source_path
    conversion = None
    if source_container in {"WOFF", "WOFF2"}:
        conversion = font_web_convert.convert(source_path, temp_root / "web")
        materialized = Path(str(conversion["outputPath"]))

    source_original = _open_face(materialized, max(0, _int(source_info.get("faceIndex"), 0)))
    source_instance: TTFont | None = None
    stock_geometry: TTFont | None = None
    base: TTFont | None = None
    collection: TTCollection | None = None
    try:
        source_axes = _source_axis_spec_for_route(source_original, artifact, weight)
        source_instance, source_location = _instantiate(source_original, weight, source_axes)
        if source_instance is source_original:
            source_original = None

        stock_geometry, stock_location = _stock_geometry_font(
            stock,
            max(0, _int(artifact.get("requiredFaceIndex"), 0)),
            weight,
            route_axes,
        )
        stock_profile = _profile_from_font(stock_geometry)
        source_profile = _profile_from_font(source_instance)
        geometry = _geometry_plan(target, stock_profile, source_profile, weight)

        base, collection = _open_stock_container(
            stock, max(0, _int(artifact.get("requiredFaceIndex"), 0))
        )
        replaced = _replace_role_glyphs(
            base,
            source_instance,
            str(target.get("role") or ""),
            geometry,
        )
        _drop_stale_tables(base)

        required_ps = str(artifact.get("requiredPostScriptName") or "")
        if required_ps:
            names = template_engine.font_names(base)
            if required_ps not in names:
                raise CompilerError(
                    f"原厂目标 face 不包含 required PostScriptName：{required_ps}"
                )

        if collection is None:
            _save_font(base, output)
        else:
            _save_collection(collection, output)

        validation = _validate_output_face(
            output,
            max(0, _int(artifact.get("requiredFaceIndex"), 0)),
            target,
            artifact,
            stock_profile,
            route_axes,
            str(target.get("role") or ""),
        )
        return {
            "mode": "stock-shell",
            "sourceContainer": source_container,
            "sourceLocation": source_location,
            "stockLocation": stock_location,
            "geometry": geometry,
            "replaced": replaced,
            "conversion": conversion,
            "validation": validation,
        }
    finally:
        if collection is not None:
            try:
                collection.close()
            except Exception:
                pass
        elif base is not None:
            base.close()
        if stock_geometry is not None:
            stock_geometry.close()
        if source_instance is not None:
            source_instance.close()
        if source_original is not None:
            source_original.close()


def _compile_source_variable_preserve(
    target: dict[str, Any],
    artifact: dict[str, Any],
    stock: Path,
    output: Path,
    temp_root: Path,
) -> dict[str, Any]:
    source_info = target.get("source") if isinstance(target.get("source"), dict) else {}
    source_path = Path(str(source_info.get("sourcePath") or ""))
    if not source_path.is_file():
        raise CompilerError(f"源字体不存在：{source_path}")
    _file_uid_matches(source_info, source_path)
    source_container = _font_container(source_path)
    if source_container in {"WOFF", "WOFF2"}:
        conversion = font_web_convert.convert(source_path, temp_root / "web")
        materialized = Path(str(conversion["outputPath"]))
    else:
        conversion = None
        materialized = source_path

    source = _open_face(materialized, max(0, _int(source_info.get("faceIndex"), 0)))
    stock_geometry: TTFont | None = None
    validation_instance: TTFont | None = None
    try:
        compatibility = _validate_source_variable_compat(source, target, artifact)
        if _outline_kind(source) != "glyf":
            raise CompilerError("物理 variable 保真模式当前只接受 glyf variable 源字体")

        grouped = artifact.get("variableGroup") is True
        if grouped:
            stock_face = max(0, _int(artifact.get("requiredFaceIndex"), 0))
            weight = _int(artifact.get("requiredWeight"), 400)
        else:
            stock_face = max(0, _int(target.get("targetContract", {}).get("faceIndex"), 0))
            weight = _int(target.get("targetContract", {}).get("weight"), 400)
        stock_geometry, stock_location = _stock_geometry_font(stock, stock_face, weight, {})
        stock_profile = _profile_from_font(stock_geometry)

        target_upem = int(stock_profile["metrics"]["unitsPerEm"])
        if int(source["head"].unitsPerEm) != target_upem:
            scale_upem(source, target_upem)
        _apply_target_line_contract(source, target, stock_profile)

        # Validate natural source geometry at the representative target weight.
        validation_instance = _instance_for_validation(source, weight, {})
        if validation_instance is source:
            source = None
        source_profile = _profile_from_font(validation_instance)
        alignment = _probe_alignment(
            stock_profile,
            source_profile,
            str(target.get("role") or ""),
            variable_natural=True,
        )
        if alignment["status"] != "ready":
            raise CompilerError(
                "物理 variable 源字体天然几何与原厂槽位不匹配；拒绝静态化或强行偏移："
                + ",".join(alignment["issues"])
            )

        variable_font = validation_instance if source is None else source
        if source is None:
            # validation_instance is static if instantiateVariableFont returned a
            # new font, so cannot be the output. Re-open original variable source.
            validation_instance.close()
            validation_instance = None
            source = _open_face(materialized, max(0, _int(source_info.get("faceIndex"), 0)))
            if int(source["head"].unitsPerEm) != target_upem:
                scale_upem(source, target_upem)
            _apply_target_line_contract(source, target, stock_profile)
            variable_font = source

        required_ps = str(artifact.get("requiredPostScriptName") or "")
        if grouped and required_ps:
            _set_postscript_name(variable_font, required_ps, str(artifact.get("artifactId") or ""))
        _drop_stale_tables(variable_font)
        _copy_compiled_face_into_stock_container(
            stock,
            stock_face,
            variable_font,
            output,
        )
        validation = _validate_output_face(
            output,
            stock_face,
            target,
            artifact,
            stock_profile,
            {},
            str(target.get("role") or ""),
            variable_natural=True,
        )
        return {
            "mode": "source-variable-preserve",
            "sourceContainer": source_container,
            "stockLocation": stock_location,
            "axisCompatibility": compatibility,
            "naturalAlignment": alignment,
            "conversion": conversion,
            "validation": validation,
        }
    finally:
        if validation_instance is not None:
            validation_instance.close()
        if stock_geometry is not None:
            stock_geometry.close()
        if source is not None:
            source.close()


def _choose_mode(
    target: dict[str, Any],
    artifact: dict[str, Any],
    deployment_kinds: list[str],
    stock: Path,
) -> str:
    role = str(target.get("role") or "")
    contract = target.get("targetContract") if isinstance(target.get("targetContract"), dict) else {}
    target_variable = contract.get("variable") is True
    is_collection = _magic(stock) == COLLECTION_MAGIC
    fixed_axes = bool(_axis_values(artifact.get("requiredAxes")))
    if artifact.get("variableGroup") is True and role not in SPECIALIZED_ROLES:
        # Several XML weights share one variable artifact (see the router).
        return "source-variable-preserve"
    if role in SPECIALIZED_ROLES or is_collection or fixed_axes:
        return "stock-shell"
    if target_variable and deployment_kinds == ["physical-slot"]:
        return "source-variable-preserve"

    source = target.get("source") if isinstance(target.get("source"), dict) else {}
    source_format = str(source.get("format") or "").upper()
    target_format = str(contract.get("format") or "").upper()
    source_kind = "cff" if "CFF" in source_format else "glyf"
    target_kind = "cff" if target_format == "OTF" else "glyf"
    if source_kind == target_kind:
        return "source-as-base"
    return "stock-shell"


def _compile_unit(
    unit: dict[str, Any],
    stock_paths: dict[str, Path],
    output_dir: Path,
    allow_live_stock: bool,
) -> dict[str, Any]:
    artifact = unit["artifact"]
    target = unit["target"]
    target_path = str(target.get("path") or "")
    artifact_id = str(artifact.get("artifactId") or "")
    output = output_dir / str(artifact.get("suggestedFileName") or "")
    result: dict[str, Any] = {
        "artifactId": artifact_id,
        "targetPath": target_path,
        "role": str(target.get("role") or ""),
        "deploymentKinds": list(unit.get("deploymentKinds") or []),
        "routeNodes": copy.deepcopy(unit.get("routeNodes") or []),
        "contract": copy.deepcopy(artifact),
        "status": "blocked",
        "output": "",
        "sha256": "",
        "bytes": 0,
        "reason": "",
    }

    try:
        if str(target.get("status") or "") == "blocked":
            raise CompilerError("FontPlan 目标已经 blocked")
        for risk in target.get("risks") or []:
            if risk in {
                "static-weight-fallback",
                "italic-style-mismatch",
                "source-weight-axis-out-of-range",
            }:
                raise CompilerError(f"FontPlan 风险不能由编译器安全消除：{risk}")

        stock = _resolve_stock(target_path, stock_paths, allow_live_stock)
        stock_face = max(0, _int(artifact.get("requiredFaceIndex"), 0))
        _validate_stock_contract(target, stock, stock_face)
        mode = _choose_mode(
            target,
            artifact,
            list(unit.get("deploymentKinds") or []),
            stock,
        )
        temp_root = output_dir / ".tmp" / artifact_id.replace(":", "-")
        temp_root.mkdir(parents=True, exist_ok=True)

        if mode == "source-as-base":
            report = _compile_source_as_base(target, artifact, stock, output, temp_root)
        elif mode == "source-variable-preserve":
            report = _compile_source_variable_preserve(target, artifact, stock, output, temp_root)
        else:
            report = _compile_stock_shell(target, artifact, stock, output, temp_root)

        result.update(
            status="ready",
            output=str(output),
            sha256=_sha256(output),
            bytes=int(output.stat().st_size),
            mode=mode,
            report=report,
            stock={
                "logicalPath": target_path,
                "sourcePath": str(stock),
                "sha256": _sha256(stock),
                "faceIndex": stock_face,
            },
        )
    except Exception as error:
        output.unlink(missing_ok=True)
        result["reason"] = str(error) or error.__class__.__name__
    finally:
        shutil.rmtree(output_dir / ".tmp" / artifact_id.replace(":", "-"), ignore_errors=True)
    return result


def _manifest_semantic(
    font_plan_id: str,
    route_id: str,
    artifacts: list[dict[str, Any]],
    deferred: list[str],
) -> dict[str, Any]:
    stable_artifacts: list[dict[str, Any]] = []
    for item in artifacts:
        stable_artifacts.append({
            key: copy.deepcopy(value)
            for key, value in item.items()
            if key not in {"output", "stock"}
        })
    return {
        "fontPlanId": font_plan_id,
        "routeId": route_id,
        "artifacts": stable_artifacts,
        "deferredDynamicTargets": list(deferred),
    }


def _manifest_id(
    font_plan_id: str,
    route_id: str,
    artifacts: list[dict[str, Any]],
    deferred: list[str],
) -> str:
    return f"sha256:{_canonical_hash(_manifest_semantic(font_plan_id, route_id, artifacts, deferred))}"


ARTIFACT_CACHE_INDEX = ".artifact-cache.json"


def _load_artifact_cache(output_dir: Path) -> dict[str, dict[str, Any]]:
    try:
        raw = json.loads((output_dir / ARTIFACT_CACHE_INDEX).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict) or _int(raw.get("compilerRevision"), 0) != COMPILER_REVISION:
        return {}
    entries = raw.get("artifacts")
    if not isinstance(entries, dict):
        return {}
    return {str(key): value for key, value in entries.items() if isinstance(value, dict)}


def _reuse_cached_artifact(
    cache: dict[str, dict[str, Any]],
    unit: dict[str, Any],
    stock_paths: dict[str, Path],
    output_dir: Path,
    allow_live_stock: bool,
) -> dict[str, Any] | None:
    """Return a previous ready artifact for this exact contract, or None.

    artifactId already hashes the FontPlan (device topology, roles and source
    file identity) and the XML contract; the stock and output bytes are
    re-hashed here so an OTA font update or a damaged cache is never reused.
    """
    artifact = unit["artifact"]
    entry = cache.get(str(artifact.get("artifactId") or ""))
    if not entry or entry.get("status") != "ready" or entry.get("contract") != artifact:
        return None
    target_path = str(unit["target"].get("path") or "")
    if entry.get("targetPath") != target_path:
        return None
    output = output_dir / Path(str(entry.get("output") or "")).name
    try:
        if not output.is_file() or _sha256(output) != entry.get("sha256"):
            return None
        stock = _resolve_stock(target_path, stock_paths, allow_live_stock)
        recorded = entry.get("stock") if isinstance(entry.get("stock"), dict) else {}
        if _sha256(stock) != recorded.get("sha256"):
            return None
    except (CompilerError, OSError):
        return None
    reused = copy.deepcopy(entry)
    reused.update(
        output=str(output),
        deploymentKinds=list(unit.get("deploymentKinds") or []),
        routeNodes=copy.deepcopy(unit.get("routeNodes") or []),
        stock=dict(recorded, logicalPath=target_path, sourcePath=str(stock)),
    )
    return reused


def _store_artifact_cache(output_dir: Path, artifacts: list[dict[str, Any]]) -> None:
    ready = {
        str(item["artifactId"]): item
        for item in artifacts
        if item.get("status") == "ready" and item.get("output")
    }
    keep = {Path(str(item["output"])).name for item in ready.values()}
    for path in output_dir.iterdir():
        if path.is_file() and path.name != ARTIFACT_CACHE_INDEX and path.name not in keep:
            path.unlink(missing_ok=True)
    _atomic_json(output_dir / ARTIFACT_CACHE_INDEX, {
        "compilerRevision": COMPILER_REVISION,
        "artifacts": ready,
    })


def _deadline() -> float:
    """Absolute epoch deadline set by the cutover controller (0 = none)."""
    value = _float(os.environ.get("LUOSHU_UNIVERSAL_DEADLINE"), 0.0) or 0.0
    return value if value > 0 else 0.0


def compile_all(
    font_plan: dict[str, Any],
    route_plan: dict[str, Any],
    stock_paths: dict[str, Path],
    output_dir: Path,
    allow_live_stock: bool,
) -> dict[str, Any]:
    if font_plan.get("schema") != FONT_PLAN_SCHEMA:
        raise CompilerError("不支持的 FontPlan")
    universal_font_plan.validate_plan(font_plan)
    if route_plan.get("schema") != ROUTE_SCHEMA:
        raise CompilerError("不支持的 XML RoutePlan")
    minimal_xml_router.validate_route_plan(route_plan, font_plan=font_plan)

    output_dir.mkdir(parents=True, exist_ok=True)
    units = _collect_units(font_plan, route_plan)
    deadline = _deadline()
    cache = _load_artifact_cache(output_dir)
    artifacts = []
    reused = 0
    for index, unit in enumerate(units):
        cached = _reuse_cached_artifact(cache, unit, stock_paths, output_dir, allow_live_stock)
        if cached is not None:
            artifacts.append(cached)
            reused += 1
            continue
        if deadline and time.time() >= deadline:
            # Leave the remaining switch budget to the legacy engine instead of
            # finishing a payload the task supervisor would kill anyway.
            raise CompilerError(
                f"通用引擎超出时间预算：已编译 {index}/{len(units)} 个字体单元"
            )
        artifacts.append(_compile_unit(unit, stock_paths, output_dir, allow_live_stock))
    _store_artifact_cache(output_dir, artifacts)
    ready = sum(item["status"] == "ready" for item in artifacts)
    blocked = sum(item["status"] == "blocked" for item in artifacts)
    deferred = list(route_plan.get("deferredDynamicTargets") or [])
    compiled_dynamic = {
        str(item.get("targetPath") or "")
        for item in artifacts
        if item.get("status") == "ready" and "dynamic-slot" in (item.get("deploymentKinds") or [])
    }
    deployment_ready = (
        blocked == 0
        and compiled_dynamic == set(deferred)
        and route_plan.get("summary", {}).get("routingComplete") is True
    )
    manifest_id = _manifest_id(
        str(font_plan.get("planId") or ""),
        str(route_plan.get("routeId") or ""),
        artifacts,
        deferred,
    )
    artifact_map = {
        str(item["artifactId"]): Path(str(item["output"])).name
        for item in artifacts
        if item.get("status") == "ready"
    }
    physical_target_map = {
        str(item["targetPath"]): str(item["artifactId"])
        for item in artifacts
        if item.get("status") == "ready" and "physical-slot" in (item.get("deploymentKinds") or [])
    }
    dynamic_target_map = {
        str(item["targetPath"]): str(item["artifactId"])
        for item in artifacts
        if item.get("status") == "ready" and "dynamic-slot" in (item.get("deploymentKinds") or [])
    }
    return {
        "schema": SCHEMA,
        "compilerRevision": COMPILER_REVISION,
        "state": "compiled" if blocked == 0 else "partial",
        "mutatesSystem": False,
        "generatedAt": int(time.time()),
        "manifestId": manifest_id,
        "fontPlanId": font_plan.get("planId"),
        "routeId": route_plan.get("routeId"),
        "summary": {
            "artifactCount": len(artifacts),
            "readyCount": ready,
            "blockedCount": blocked,
            "deferredDynamicTargetCount": len(deferred),
            "compiledDynamicTargetCount": len(dynamic_target_map),
            "deploymentReady": deployment_ready,
            "executableNow": False,
        },
        "deferredDynamicTargets": deferred,
        # Diagnostics only; not part of manifestId.
        "cache": {"reused": reused, "compiled": len(artifacts) - reused},
        "artifactMap": dict(sorted(artifact_map.items())),
        "physicalTargetMap": dict(sorted(physical_target_map.items())),
        "dynamicTargetMap": dict(sorted(dynamic_target_map.items())),
        "artifacts": artifacts,
    }


def validate_manifest(
    manifest: dict[str, Any],
    font_plan: dict[str, Any],
    route_plan: dict[str, Any],
) -> None:
    if manifest.get("schema") != SCHEMA:
        raise CompilerError("Universal Font Artifacts manifest 格式无效")
    if _int(manifest.get("compilerRevision"), 0) != COMPILER_REVISION:
        raise CompilerError("Universal Font Artifacts compilerRevision 无效")
    if manifest.get("mutatesSystem") is not False:
        raise CompilerError("Phase 6 不得修改系统")
    if manifest.get("fontPlanId") != font_plan.get("planId"):
        raise CompilerError("Artifact manifest 与 FontPlan 不一致")
    if manifest.get("routeId") != route_plan.get("routeId"):
        raise CompilerError("Artifact manifest 与 RoutePlan 不一致")
    summary = manifest.get("summary")
    artifacts = manifest.get("artifacts")
    if not isinstance(summary, dict) or not isinstance(artifacts, list):
        raise CompilerError("Artifact manifest 缺少 summary/artifacts")
    if summary.get("executableNow") is not False:
        raise CompilerError("Phase 6 不得声明可直接执行")
    artifact_map = manifest.get("artifactMap")
    physical_map = manifest.get("physicalTargetMap")
    dynamic_map = manifest.get("dynamicTargetMap")
    if not isinstance(artifact_map, dict) or not isinstance(physical_map, dict) or not isinstance(dynamic_map, dict):
        raise CompilerError("Artifact manifest 缺少 artifactMap/physicalTargetMap/dynamicTargetMap")
    ids: set[str] = set()
    expected_artifact_map: dict[str, str] = {}
    expected_physical_map: dict[str, str] = {}
    expected_dynamic_map: dict[str, str] = {}
    ready = blocked = 0
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise CompilerError("Artifact manifest 条目无效")
        artifact_id = str(artifact.get("artifactId") or "")
        if not artifact_id.startswith("ufc:") or artifact_id in ids:
            raise CompilerError("Artifact manifest artifactId 无效或重复")
        ids.add(artifact_id)
        status = str(artifact.get("status") or "")
        if status == "ready":
            ready += 1
            path = Path(str(artifact.get("output") or ""))
            if not path.is_file() or _sha256(path) != artifact.get("sha256"):
                raise CompilerError(f"Artifact 文件缺失或摘要不一致：{artifact_id}")
            expected_artifact_map[artifact_id] = path.name
            if "physical-slot" in (artifact.get("deploymentKinds") or []):
                expected_physical_map[str(artifact.get("targetPath") or "")] = artifact_id
            if "dynamic-slot" in (artifact.get("deploymentKinds") or []):
                expected_dynamic_map[str(artifact.get("targetPath") or "")] = artifact_id
        elif status == "blocked":
            blocked += 1
            if not str(artifact.get("reason") or ""):
                raise CompilerError(f"Blocked artifact 缺少 reason：{artifact_id}")
        else:
            raise CompilerError(f"Artifact 状态无效：{artifact_id}")

    expected = {
        "artifactCount": len(artifacts),
        "readyCount": ready,
        "blockedCount": blocked,
        "deferredDynamicTargetCount": len(manifest.get("deferredDynamicTargets") or []),
        "compiledDynamicTargetCount": len(expected_dynamic_map),
        "deploymentReady": (
            blocked == 0
            and set(expected_dynamic_map) == set(manifest.get("deferredDynamicTargets") or [])
            and route_plan.get("summary", {}).get("routingComplete") is True
        ),
        "executableNow": False,
    }
    if summary != expected:
        raise CompilerError("Artifact manifest summary 与 artifacts 不一致")
    if artifact_map != dict(sorted(expected_artifact_map.items())):
        raise CompilerError("Artifact manifest artifactMap 与 ready artifacts 不一致")
    if physical_map != dict(sorted(expected_physical_map.items())):
        raise CompilerError("Artifact manifest physicalTargetMap 与 ready artifacts 不一致")
    if dynamic_map != dict(sorted(expected_dynamic_map.items())):
        raise CompilerError("Artifact manifest dynamicTargetMap 与 ready artifacts 不一致")
    expected_manifest_id = _manifest_id(
        str(font_plan.get("planId") or ""),
        str(route_plan.get("routeId") or ""),
        artifacts,
        list(manifest.get("deferredDynamicTargets") or []),
    )
    if manifest.get("manifestId") != expected_manifest_id:
        raise CompilerError("Artifact manifest manifestId 完整性校验失败")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--font-plan", required=True, type=Path)
    parser.add_argument("--route-plan", required=True, type=Path)
    parser.add_argument("--stock-map", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--validate", type=Path)
    parser.add_argument("--allow-live-stock", action="store_true")
    args = parser.parse_args()

    try:
        font_plan = _load(args.font_plan)
        route_plan = _load(args.route_plan)
        universal_font_plan.validate_plan(font_plan)
        minimal_xml_router.validate_route_plan(route_plan, font_plan=font_plan)

        if args.validate is not None:
            manifest = _load(args.validate)
            validate_manifest(manifest, font_plan, route_plan)
        else:
            if args.output_dir is None or args.manifest is None:
                raise CompilerError("编译需要 --output-dir 与 --manifest")
            manifest = compile_all(
                font_plan,
                route_plan,
                _stock_map(args.stock_map),
                args.output_dir,
                args.allow_live_stock,
            )
            _atomic_json(args.manifest, manifest)

        print(json.dumps({
            "status": "ok",
            "schema": manifest["schema"],
            "manifestId": manifest["manifestId"],
            **manifest["summary"],
        }, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as error:
        print(json.dumps({
            "status": "error",
            "message": str(error) or error.__class__.__name__,
        }, ensure_ascii=False, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
