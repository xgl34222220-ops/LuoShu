#!/usr/bin/env python3
"""Build the canonical LuoShu source-font compiler input.

Phase 3 is capability discovery only. The profile describes what imported font
faces contain; it never selects Android targets, patches XML, mounts files, or
modifies the source font.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable

from fontTools.ttLib import TTCollection, TTFont

import font_coverage as global_coverage
import font_web_convert

SCHEMA = "source-font-profile-v1"
PROFILE_REVISION = 1
FONT_MAGIC = {
    b"ttcf": "TTC",
    b"OTTO": "OTF",
    b"true": "TTF",
    b"\x00\x01\x00\x00": "TTF",
    b"\x00\x02\x00\x00": "TTF",
    b"wOFF": "WOFF",
    b"wOF2": "WOFF2",
}
COLOR_TABLES = {"COLR", "CPAL", "CBDT", "CBLC", "sbix", "SVG "}
VARIABLE_TABLES = {"fvar", "avar", "STAT", "HVAR", "VVAR", "MVAR"}
SHAPING_TABLES = {"GSUB", "GPOS", "GDEF", "BASE", "JSTF"}
SCRIPT_RANGES: dict[str, tuple[tuple[int, int], ...]] = {
    "han": (
        (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF),
        (0x20000, 0x2EE5F), (0x2F800, 0x2FA1F), (0x30000, 0x3347F),
    ),
    "latin": ((0x0041, 0x005A), (0x0061, 0x007A), (0x00C0, 0x024F)),
    "cyrillic": ((0x0400, 0x052F),),
    "greek": ((0x0370, 0x03FF),),
    "arabic": ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF)),
    "hebrew": ((0x0590, 0x05FF),),
    "devanagari": ((0x0900, 0x097F),),
    "thai": ((0x0E00, 0x0E7F),),
    "hangul": ((0x1100, 0x11FF), (0x3130, 0x318F), (0xAC00, 0xD7AF)),
    "hiragana": ((0x3040, 0x309F),),
    "katakana": ((0x30A0, 0x30FF), (0x31F0, 0x31FF)),
}
EMOJI_RANGES = (
    (0x1F000, 0x1FAFF),
    (0x2600, 0x27BF),
)


class ProfileError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _file_magic(path: Path) -> bytes:
    with path.open("rb") as stream:
        return stream.read(4)


def _source_container(path: Path) -> str:
    return FONT_MAGIC.get(_file_magic(path), "UNKNOWN")


def _face_count(path: Path, container: str) -> int:
    if container != "TTC":
        return 1
    collection = TTCollection(str(path), lazy=True)
    try:
        return len(collection.fonts)
    finally:
        collection.close()


def _clean(value: Any, fallback: str = "") -> str:
    return " ".join(str(value or fallback).replace("\r", " ").replace("\n", " ").split())


def _debug_name(font: TTFont, name_id: int, fallback: str = "") -> str:
    try:
        return _clean(font["name"].getDebugName(name_id), fallback)
    except Exception:
        return fallback


def _best_family(font: TTFont) -> str:
    try:
        return _clean(font["name"].getBestFamilyName(), _debug_name(font, 1, "ImportedFont"))
    except Exception:
        return _debug_name(font, 1, "ImportedFont")


def _best_subfamily(font: TTFont) -> str:
    try:
        return _clean(font["name"].getBestSubFamilyName(), _debug_name(font, 2, "Regular"))
    except Exception:
        return _debug_name(font, 2, "Regular")


def _normalized_family(value: str) -> str:
    return re.sub(r"[^0-9a-z]+", "-", value.lower()).strip("-") or "unknown"


def _int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _float(value: Any, default: float | None = None) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return result if math.isfinite(result) else default


def _font_format(font: TTFont, container: str) -> str:
    if container == "WOFF":
        return "WOFF"
    if container == "WOFF2":
        return "WOFF2"
    if "CFF2" in font:
        return "OTF/CFF2"
    if "CFF " in font:
        return "OTF/CFF"
    if "glyf" in font:
        return "TTF/glyf"
    return "SFNT"


def _outline_kind(font: TTFont) -> str:
    if "glyf" in font:
        return "glyf"
    if "CFF2" in font:
        return "CFF2"
    if "CFF " in font:
        return "CFF"
    return "unknown"


def _weight(font: TTFont) -> int:
    try:
        return max(1, min(1000, int(font["OS/2"].usWeightClass)))
    except Exception:
        return 400


def _width_class(font: TTFont) -> int:
    try:
        return max(1, min(9, int(font["OS/2"].usWidthClass)))
    except Exception:
        return 5


def _italic(font: TTFont, subfamily: str) -> bool:
    try:
        if bool(int(font["head"].macStyle) & 0x02):
            return True
    except Exception:
        pass
    try:
        if bool(int(font["OS/2"].fsSelection) & 0x01):
            return True
    except Exception:
        pass
    lowered = subfamily.lower()
    return "italic" in lowered or "oblique" in lowered


def _fixed_pitch(font: TTFont) -> bool:
    try:
        return bool(font["post"].isFixedPitch)
    except Exception:
        return False


def _axes(font: TTFont) -> list[dict[str, Any]]:
    if "fvar" not in font:
        return []
    result: list[dict[str, Any]] = []
    for axis in font["fvar"].axes:
        result.append({
            "tag": str(axis.axisTag),
            "name": _debug_name(font, int(axis.axisNameID), str(axis.axisTag)),
            "min": float(axis.minValue),
            "default": float(axis.defaultValue),
            "max": float(axis.maxValue),
        })
    return result


def _instances(font: TTFont) -> list[dict[str, Any]]:
    if "fvar" not in font:
        return []
    result: list[dict[str, Any]] = []
    for instance in font["fvar"].instances:
        coordinates = {
            str(tag): float(value)
            for tag, value in sorted(instance.coordinates.items())
        }
        ps_name_id = _int(getattr(instance, "postscriptNameID", None), 0xFFFF)
        result.append({
            "name": _debug_name(font, int(instance.subfamilyNameID), "Instance"),
            "postScriptName": (
                _debug_name(font, int(ps_name_id), "")
                if ps_name_id is not None and ps_name_id != 0xFFFF
                else ""
            ),
            "coordinates": coordinates,
        })
    return result


def _metrics(font: TTFont) -> dict[str, Any]:
    head = font["head"] if "head" in font else None
    hhea = font["hhea"] if "hhea" in font else None
    os2 = font["OS/2"] if "OS/2" in font else None
    result: dict[str, Any] = {
        "unitsPerEm": _int(getattr(head, "unitsPerEm", None)),
        "head": {
            "xMin": _int(getattr(head, "xMin", None)),
            "yMin": _int(getattr(head, "yMin", None)),
            "xMax": _int(getattr(head, "xMax", None)),
            "yMax": _int(getattr(head, "yMax", None)),
        },
        "hhea": {
            "ascent": _int(getattr(hhea, "ascent", None)),
            "descent": _int(getattr(hhea, "descent", None)),
            "lineGap": _int(getattr(hhea, "lineGap", None)),
            "advanceWidthMax": _int(getattr(hhea, "advanceWidthMax", None)),
        },
        "os2": {
            "weightClass": _int(getattr(os2, "usWeightClass", None)),
            "widthClass": _int(getattr(os2, "usWidthClass", None)),
            "fsSelection": _int(getattr(os2, "fsSelection", None)),
            "typoAscender": _int(getattr(os2, "sTypoAscender", None)),
            "typoDescender": _int(getattr(os2, "sTypoDescender", None)),
            "typoLineGap": _int(getattr(os2, "sTypoLineGap", None)),
            "winAscent": _int(getattr(os2, "usWinAscent", None)),
            "winDescent": _int(getattr(os2, "usWinDescent", None)),
            "capHeight": _int(getattr(os2, "sCapHeight", None)),
            "xHeight": _int(getattr(os2, "sxHeight", None)),
        },
    }
    return result


def _count_ranges(codepoints: Iterable[int], ranges: tuple[tuple[int, int], ...]) -> int:
    return sum(1 for cp in codepoints if any(start <= cp <= end for start, end in ranges))


def _probe(cmap: set[int], probes: tuple[int, ...]) -> dict[str, Any]:
    hits = sum(cp in cmap for cp in probes)
    total = len(probes)
    ratio = hits / total if total else 1.0
    return {"hits": hits, "total": total, "ratio": round(ratio, 6)}


def _coverage(font: TTFont) -> dict[str, Any]:
    cmap = set((font.getBestCmap() or {}).keys())
    scripts = {
        name: _count_ranges(cmap, ranges)
        for name, ranges in SCRIPT_RANGES.items()
    }
    probes = {
        "cjk": _probe(cmap, global_coverage.CJK_COMMON),
        "latin": _probe(cmap, global_coverage.LATIN),
        "digits": _probe(cmap, global_coverage.DIGITS),
        "punctuation": _probe(cmap, global_coverage.PUNCTUATION),
    }
    core_han = global_coverage.count_core_han(cmap)
    emoji_approx = _count_ranges(cmap, EMOJI_RANGES)
    return {
        "codepoints": len(cmap),
        "coreHan": core_han,
        "minimumCoreHan": global_coverage.MIN_CORE_HAN,
        "scriptCounts": scripts,
        "emojiCodepointsApprox": emoji_approx,
        "probes": probes,
    }


def _table_contract(font: TTFont) -> dict[str, Any]:
    tables = sorted(str(tag) for tag in font.keys())
    table_set = set(tables)
    color = sorted(table_set.intersection(COLOR_TABLES))
    variable = sorted(table_set.intersection(VARIABLE_TABLES))
    shaping = sorted(table_set.intersection(SHAPING_TABLES))
    return {
        "all": tables,
        "outline": _outline_kind(font),
        "color": color,
        "variable": variable,
        "shaping": shaping,
    }


def _capabilities(
    coverage: dict[str, Any],
    tables: dict[str, Any],
    axes: list[dict[str, Any]],
    fixed_pitch: bool,
) -> dict[str, Any]:
    probes = coverage["probes"]
    core_han = int(coverage["coreHan"])
    latin_ratio = float(probes["latin"]["ratio"])
    digit_ratio = float(probes["digits"]["ratio"])
    punct_ratio = float(probes["punctuation"]["ratio"])
    cjk_ratio = float(probes["cjk"]["ratio"])
    latin_ui = latin_ratio >= 0.95 and digit_ratio == 1.0 and punct_ratio >= 0.75
    cjk_ui = (
        core_han >= global_coverage.MIN_CORE_HAN
        and cjk_ratio >= 0.95
        and latin_ui
    )
    axis_tags = {axis["tag"] for axis in axes}
    color_font = bool(tables["color"])
    return {
        "text": int(coverage["codepoints"]) >= 64,
        "latinUi": latin_ui,
        "cjkUi": cjk_ui,
        "numeric": digit_ratio == 1.0,
        "punctuationUi": punct_ratio >= 0.75,
        "monospaceCandidate": fixed_pitch and latin_ratio >= 0.95,
        "variable": bool(axes),
        "variableWeight": "wght" in axis_tags,
        "variableWidth": "wdth" in axis_tags,
        "variableOpticalSize": "opsz" in axis_tags,
        "colorFont": color_font,
        "globalUiCandidate": cjk_ui and not color_font,
    }


def _warnings(
    capabilities: dict[str, Any],
    tables: dict[str, Any],
    metrics: dict[str, Any],
    container: str,
) -> list[str]:
    warnings: list[str] = []
    if container in {"WOFF", "WOFF2"}:
        warnings.append("web-container-requires-sfnt-conversion")
    if capabilities["colorFont"]:
        warnings.append("color-font-not-for-generic-ui-replacement")
    if not capabilities["latinUi"]:
        warnings.append("latin-ui-coverage-incomplete")
    if not capabilities["numeric"]:
        warnings.append("digit-coverage-incomplete")
    if metrics.get("unitsPerEm") in (None, 0):
        warnings.append("units-per-em-missing")
    if not tables["shaping"]:
        warnings.append("no-opentype-shaping-tables")
    return warnings


def _open_face(path: Path, container: str, index: int) -> TTFont:
    kwargs: dict[str, Any] = {"lazy": True, "recalcTimestamp": False}
    if container == "TTC":
        kwargs["fontNumber"] = index
    return TTFont(str(path), **kwargs)


def _inspect_face(
    path: Path,
    file_hash: str,
    open_container: str,
    source_container: str,
    source_file_name: str,
    index: int,
) -> dict[str, Any]:
    font = _open_face(path, open_container, index)
    try:
        family = _best_family(font)
        subfamily = _best_subfamily(font)
        axes = _axes(font)
        coverage = _coverage(font)
        tables = _table_contract(font)
        metrics = _metrics(font)
        fixed_pitch = _fixed_pitch(font)
        capabilities = _capabilities(coverage, tables, axes, fixed_pitch)
        return {
            "uid": f"sha256:{file_hash}:face:{index}",
            "fileUid": f"sha256:{file_hash}",
            "fileName": source_file_name,
            "faceIndex": index,
            "names": {
                "family": family,
                "familyNormalized": _normalized_family(family),
                "subfamily": subfamily,
                "fullName": _debug_name(font, 4, family),
                "postScriptName": _debug_name(font, 6, ""),
            },
            "format": _font_format(font, open_container),
            "style": {
                "weight": _weight(font),
                "widthClass": _width_class(font),
                "italic": _italic(font, subfamily),
                "fixedPitch": fixed_pitch,
            },
            "metrics": metrics,
            "variation": {
                "variable": bool(axes),
                "axes": axes,
                "namedInstances": _instances(font),
            },
            "tables": tables,
            "coverage": coverage,
            "capabilities": capabilities,
            "warnings": _warnings(capabilities, tables, metrics, source_container),
        }
    finally:
        font.close()


def _inspect_file(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size < 12:
        raise ProfileError(f"字体文件不存在或过小：{path}")
    source_container = _source_container(path)
    if source_container == "UNKNOWN":
        raise ProfileError(f"无法识别字体容器：{path.name}")
    file_hash = _sha256(path)
    analysis_path = path
    analysis_container = source_container
    temp_context: tempfile.TemporaryDirectory[str] | None = None
    conversion: dict[str, Any] | None = None

    try:
        if source_container == "WOFF2":
            temp_context = tempfile.TemporaryDirectory(prefix="luoshu-woff2-profile-")
            conversion = font_web_convert.convert(path, Path(temp_context.name))
            analysis_path = Path(str(conversion["outputPath"]))
            analysis_container = _source_container(analysis_path)
            if analysis_container not in {"TTF", "OTF", "TTC"}:
                raise ProfileError("WOFF2 临时转换没有产生有效 SFNT/TTC")

        count = _face_count(analysis_path, analysis_container)
        if count < 1 or count > 128:
            raise ProfileError(f"字体面数量异常：{path.name}")
        faces = [
            _inspect_face(
                analysis_path,
                file_hash,
                analysis_container,
                source_container,
                path.name,
                index,
            )
            for index in range(count)
        ]
    except ProfileError:
        raise
    except Exception as error:
        if source_container == "WOFF2":
            raise ProfileError(f"WOFF2 解析/转换失败：{error}") from error
        raise ProfileError(f"fontTools 无法解析字体 {path.name}：{error}") from error
    finally:
        if temp_context is not None:
            temp_context.cleanup()

    result = {
        "fileUid": f"sha256:{file_hash}",
        "sha256": file_hash,
        "sourcePath": str(path),
        "fileName": path.name,
        "bytes": int(path.stat().st_size),
        "container": source_container,
        "collection": analysis_container == "TTC",
        "requiresSfntConversion": source_container in {"WOFF", "WOFF2"},
        "faceCount": count,
        "faces": faces,
    }
    if conversion is not None:
        result["analysisConversion"] = {
            "decodeMethod": conversion.get("decodeMethod"),
            "outputFormat": conversion.get("outputFormat"),
            "outputSha256": conversion.get("outputSha256"),
        }
    return result


def _group_families(files: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = {}
    for file_info in files:
        for face in file_info["faces"]:
            key = str(face["names"]["familyNormalized"])
            group = groups.setdefault(key, {
                "family": face["names"]["family"],
                "faceUids": [],
                "weights": [],
                "italicFaces": 0,
                "variableFaces": 0,
                "capabilities": {
                    "latinUi": False,
                    "cjkUi": False,
                    "numeric": False,
                    "monospaceCandidate": False,
                    "globalUiCandidate": False,
                },
            })
            group["faceUids"].append(face["uid"])
            weight = int(face["style"]["weight"])
            if weight not in group["weights"]:
                group["weights"].append(weight)
            if face["style"]["italic"]:
                group["italicFaces"] += 1
            if face["variation"]["variable"]:
                group["variableFaces"] += 1
            for name in group["capabilities"]:
                if face["capabilities"].get(name) is True:
                    group["capabilities"][name] = True
    for group in groups.values():
        group["weights"].sort()
        group["faceUids"].sort()
    return dict(sorted(groups.items()))


FIXED_SELECTION_POLICY = "fixed-composite-selection-v1"
MIXED_ROLES = {"cjk", "latin", "digit"}


def _selection_axes(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ProfileError("固定混合选择缺少轴信息")
    result = {}
    for tag, number in value.items():
        if not isinstance(tag, str) or not re.fullmatch(r"[ -~]{4}", tag):
            raise ProfileError("固定混合选择轴标签无效")
        if isinstance(number, bool) or not isinstance(number, (float, int)) or not math.isfinite(number):
            raise ProfileError("固定混合选择轴数值无效")
        result[tag] = float(number)
    return result


def _validate_mixed_selection(selection: Any, file_info: dict[str, Any], face: dict[str, Any]) -> None:
    if not isinstance(selection, dict) or selection.get("policy") != FIXED_SELECTION_POLICY:
        raise ProfileError("固定混合选择 policy 无效")
    request = selection.get("requestId")
    if not isinstance(request, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", request):
        raise ProfileError("固定混合选择 requestId 无效")
    sha = selection.get("fontSha256")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha) or sha != file_info.get("sha256"):
        raise ProfileError("固定混合选择字体哈希不匹配")
    if face.get("fileUid") != "sha256:" + sha:
        raise ProfileError("固定混合选择字体面哈希不匹配")
    if selection.get("fontPath") != file_info.get("sourcePath"):
        raise ProfileError("固定混合选择字体路径不匹配")
    report_hash = selection.get("reportSha256")
    if not isinstance(report_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", report_hash):
        raise ProfileError("固定混合选择报告哈希无效")
    if file_info.get("collection") or file_info.get("faceCount") != 1 or file_info.get("container") not in {"TTF", "OTF"}:
        raise ProfileError("固定混合选择必须绑定单个 SFNT 字体面")
    if face.get("variation", {}).get("variable") or {"fvar", "gvar", "HVAR", "VVAR", "MVAR", "avar", "cvar"}.intersection(face.get("tables", {}).get("all", [])):
        raise ProfileError("固定混合选择不能用于可变字体")
    roles = selection.get("roles")
    if not isinstance(roles, dict) or set(roles) != MIXED_ROLES:
        raise ProfileError("固定混合选择必须包含中文、英文和数字")
    for role, entry in roles.items():
        if not isinstance(entry, dict) or entry.get("mode") != "fixed":
            raise ProfileError("固定混合选择不能包含 auto 组件")
        axes = _selection_axes(entry.get("selectedAxes"))
        provenance = entry.get("axisProvenance")
        if provenance not in {"generation-hash-only", "verified-instance-report", "static-instance-report", "static-component"}:
            raise ProfileError("固定混合选择轴来源无效")
        actual = _selection_axes(entry.get("effectiveAxes"))
        if provenance == "verified-instance-report":
            if any(actual.get(tag) != number for tag, number in axes.items()):
                raise ProfileError("固定混合选择包含被截断的组件轴：" + role)
        elif actual or "actualAxes" in entry:
            raise ProfileError("固定混合选择不能把静态权重冒充实际轴坐标")
        if provenance in {"static-instance-report", "static-component"} and any(tag != "wght" for tag in axes):
            raise ProfileError("静态混合组件不支持所选轴")
        if "componentWeightClass" in entry:
            weight = entry["componentWeightClass"]
            if type(weight) is not int or not 1 <= weight <= 1000:
                raise ProfileError("固定混合组件静态字重无效")
        if provenance != "generation-hash-only":
            keys = ("componentSha256",) if provenance == "static-component" else ("componentSha256", "instanceReportSha256")
            for key in keys:
                if not re.fullmatch(r"[0-9a-f]{64}", str(entry.get(key, ""))):
                    raise ProfileError("固定混合组件来源哈希无效")


def _attach_mixed_selection(files: list[dict[str, Any]], path: Path) -> None:
    """Explicit-only metadata opt-in: never discover an adjacent source.json."""
    report_path = path.resolve(strict=True)
    try:
        raw = report_path.read_bytes()
        report = json.loads(raw)
    except (OSError, ValueError) as error:
        raise ProfileError("无法读取固定混合选择报告") from error
    if not isinstance(report, dict) or report.get("schema") != "universal-mixed-source-v1" or report.get("mode") != "fixed":
        raise ProfileError("固定混合选择报告格式无效")
    selection = copy.deepcopy(report.get("mixedSelection"))
    if not isinstance(selection, dict) or selection.get("requestId") != report.get("requestId"):
        raise ProfileError("固定混合选择报告请求不匹配")
    relative = Path(str(selection.get("fontPath", "")))
    if relative.is_absolute() or len(relative.parts) != 2 or relative.parts[0] != "fonts" or relative.parts[1] in {".", ".."} or relative.suffix.lower() not in {".ttf", ".otf"}:
        raise ProfileError("固定混合选择报告字体路径无效")
    fonts_dir = report_path.parent / "fonts"
    if fonts_dir.resolve(strict=True) != fonts_dir:
        raise ProfileError("固定混合选择字体越出冻结目录")
    font_path = (report_path.parent / relative).resolve(strict=True)
    if font_path.parent != fonts_dir:
        raise ProfileError("固定混合选择字体越出冻结目录")
    matches = [item for item in files if item.get("sourcePath") == str(font_path)]
    if len(matches) != 1:
        raise ProfileError("固定混合选择报告没有匹配的冻结字体")
    file_info = matches[0]
    if _sha256(font_path) != selection.get("fontSha256") or file_info.get("sha256") != selection.get("fontSha256"):
        raise ProfileError("固定混合选择冻结字体内容已变化")
    selection["fontPath"] = str(font_path)
    selection["reportSha256"] = hashlib.sha256(raw).hexdigest()
    for face in file_info["faces"]:
        _validate_mixed_selection(selection, file_info, face)
        face["mixedSelection"] = copy.deepcopy(selection)


def _profile_id(files: list[dict[str, Any]]) -> str:
    material = "|".join(sorted(str(file_info["sha256"]) for file_info in files))
    selections = [
        {"fileSha256": file_info["sha256"], "faceIndex": face["faceIndex"], "selection": face["mixedSelection"]}
        for file_info in files for face in file_info["faces"] if "mixedSelection" in face
    ]
    if selections:
        material += "|mixed-selection:" + json.dumps(sorted(selections, key=lambda item: (item["fileSha256"], item["faceIndex"])), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode("ascii")).hexdigest()


def build(paths: list[Path], mixed_selection: Path | None = None) -> dict[str, Any]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        absolute = path.resolve()
        key = str(absolute)
        if key in seen:
            continue
        seen.add(key)
        unique.append(absolute)
    if not unique:
        raise ProfileError("没有指定字体文件")

    files = [_inspect_file(path) for path in unique]
    if mixed_selection is not None:
        _attach_mixed_selection(files, mixed_selection)
    faces = [face for file_info in files for face in file_info["faces"]]
    families = _group_families(files)
    axis_tags = sorted({
        axis["tag"]
        for face in faces
        for axis in face["variation"]["axes"]
    })
    capabilities = {
        name: any(face["capabilities"].get(name) is True for face in faces)
        for name in (
            "latinUi", "cjkUi", "numeric", "monospaceCandidate",
            "variable", "variableWeight", "colorFont", "globalUiCandidate",
        )
    }
    profile = {
        "schema": SCHEMA,
        "profileRevision": PROFILE_REVISION,
        "state": "ready",
        "generatedAt": int(time.time()),
        "profileId": f"sha256:{_profile_id(files)}",
        "summary": {
            "fileCount": len(files),
            "faceCount": len(faces),
            "familyCount": len(families),
            "containers": sorted({str(file_info["container"]) for file_info in files}),
            "weights": sorted({int(face["style"]["weight"]) for face in faces}),
            "axisTags": axis_tags,
            "requiresSfntConversion": any(file_info["requiresSfntConversion"] for file_info in files),
            "capabilities": capabilities,
        },
        "families": families,
        "files": files,
    }
    validate(profile)
    return profile


def validate(profile: dict[str, Any]) -> None:
    if profile.get("schema") != SCHEMA or profile.get("state") != "ready":
        raise ProfileError("源字体 Profile 格式无效")
    if int(profile.get("profileRevision", 0)) != PROFILE_REVISION:
        raise ProfileError("源字体 Profile 版本无效")
    files = profile.get("files")
    if not isinstance(files, list) or not files:
        raise ProfileError("源字体 Profile 没有文件")
    if len(files) > 128:
        raise ProfileError("源字体 Profile 文件数量异常")
    for file_info in files:
        if not isinstance(file_info, dict):
            raise ProfileError("源字体 Profile 文件项无效")
        faces = file_info.get("faces")
        if not isinstance(faces, list) or not faces:
            raise ProfileError("源字体 Profile 文件没有字体面")
        if len(faces) > 128:
            raise ProfileError("源字体 Profile 字体面数量异常")
        for face in faces:
            if not isinstance(face, dict):
                raise ProfileError("源字体 Profile 字体面无效")
            if not isinstance(face.get("metrics"), dict):
                raise ProfileError("源字体 Profile 缺少度量")
            if not isinstance(face.get("coverage"), dict):
                raise ProfileError("源字体 Profile 缺少覆盖信息")
            if not isinstance(face.get("capabilities"), dict):
                raise ProfileError("源字体 Profile 缺少能力信息")
            if "mixedSelection" in face:
                _validate_mixed_selection(face["mixedSelection"], file_info, face)
    if any("mixedSelection" in face for item in files for face in item["faces"]):
        if profile.get("profileId") != "sha256:" + _profile_id(files):
            raise ProfileError("固定混合选择 Profile 身份哈希不匹配")


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".tmp.{os.getpid()}")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temp, 0o600)
    os.replace(temp, path)


def _summary(profile: dict[str, Any]) -> dict[str, Any]:
    summary = profile["summary"]
    return {
        "status": "ok",
        "schema": profile["schema"],
        "profileId": profile["profileId"],
        "fileCount": summary["fileCount"],
        "faceCount": summary["faceCount"],
        "familyCount": summary["familyCount"],
        "weights": summary["weights"],
        "axisTags": summary["axisTags"],
        "requiresSfntConversion": summary["requiresSfntConversion"],
        "capabilities": summary["capabilities"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", action="append", default=[], type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mixed-selection", type=Path)
    parser.add_argument("--validate", type=Path)
    args = parser.parse_args()

    try:
        if args.validate is not None:
            profile = json.loads(args.validate.read_text(encoding="utf-8"))
            if not isinstance(profile, dict):
                raise ProfileError("源字体 Profile 根节点无效")
            validate(profile)
        else:
            profile = build(args.font, mixed_selection=args.mixed_selection)
            if args.output is not None:
                _atomic_write(args.output, profile)
    except (ProfileError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "error", "message": str(error)}, ensure_ascii=False))
        return 1

    print(json.dumps(_summary(profile), ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
