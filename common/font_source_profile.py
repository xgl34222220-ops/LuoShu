#!/usr/bin/env python3
"""Build the canonical LuoShu source-font compiler input.

Phase 3 is capability discovery only. The profile describes what imported font
faces contain; it never selects Android targets, patches XML, mounts files, or
modifies the source font.
"""
from __future__ import annotations

import argparse
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


COMPOSITE_ROLES = ("cjk", "latin", "digit")
COMPOSITE_MODES = {"auto", "fixed"}


def _profile_id(files: list[dict[str, Any]], composite: dict[str, Any] | None = None) -> str:
    material = "|".join(sorted(str(file_info["sha256"]) for file_info in files))
    if composite is not None:
        # The same files under a different role assignment, mode or axis choice
        # must never share a FontPlan or compiled artifacts.
        material += "|composite:" + json.dumps(composite, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def parse_axes(value: str) -> dict[str, float]:
    """Parse the App's ``tag=value`` list (``,`` or ``;`` separated)."""
    result: dict[str, float] = {}
    for item in re.split(r"[;,]", value or ""):
        if not item.strip():
            continue
        tag, sep, raw = item.partition("=")
        tag = tag.strip()
        if not sep or not re.fullmatch(r"[A-Za-z0-9]{4}", tag):
            raise ProfileError(f"组合轴设置无效：{item.strip()}")
        number = _float(raw.strip())
        if number is None:
            raise ProfileError(f"组合轴数值无效：{item.strip()}")
        result[tag] = number
    return result


def composite_spec(
    role_fonts: dict[str, list[Path]],
    modes: dict[str, str],
    axes: dict[str, str],
) -> dict[str, Any]:
    roles: dict[str, Any] = {}
    for role in COMPOSITE_ROLES:
        if not role_fonts.get(role):
            raise ProfileError(f"组合缺少{ {'cjk': '中文', 'latin': '英文', 'digit': '数字'}[role] }字体")
        mode = str(modes.get(role) or "auto")
        if mode not in COMPOSITE_MODES:
            raise ProfileError(f"组合模式无效：{role}={mode}")
        roles[role] = {"mode": mode, "axes": parse_axes(axes.get(role, ""))}
    return {"roles": roles}


def build(
    paths: list[Path],
    role_fonts: dict[str, list[Path]] | None = None,
    modes: dict[str, str] | None = None,
    axes: dict[str, str] | None = None,
) -> dict[str, Any]:
    composite: dict[str, Any] | None = None
    role_by_path: dict[str, set[str]] = {}
    if role_fonts is not None:
        composite = composite_spec(role_fonts, modes or {}, axes or {})
        paths = list(paths)
        for role, role_paths in role_fonts.items():
            for path in role_paths:
                role_by_path.setdefault(str(path.resolve()), set()).add(role)
                paths.append(path)
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
    if composite is not None:
        for path, file_info in zip(unique, files):
            assigned = sorted(role_by_path.get(str(path), set()))
            for face in file_info["faces"]:
                face["assignedRoles"] = assigned
        composite["roles"] = {
            role: dict(spec, faceUids=sorted(
                face["uid"] for file_info in files for face in file_info["faces"]
                if role in face.get("assignedRoles", [])
            ))
            for role, spec in composite["roles"].items()
        }
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
        "profileId": f"sha256:{_profile_id(files, composite)}",
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
    if composite is not None:
        profile["composite"] = composite
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
    composite = profile.get("composite")
    if composite is not None:
        roles = composite.get("roles") if isinstance(composite, dict) else None
        if not isinstance(roles, dict) or set(roles) != set(COMPOSITE_ROLES):
            raise ProfileError("组合 Profile 角色分工无效")
        for role, spec in roles.items():
            if not isinstance(spec, dict) or spec.get("mode") not in COMPOSITE_MODES:
                raise ProfileError(f"组合 Profile 角色模式无效：{role}")
            if not spec.get("faceUids"):
                raise ProfileError(f"组合 Profile 角色没有字体面：{role}")


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
    parser.add_argument("--role-font", action="append", default=[],
                        help="composite: ROLE:PATH, ROLE in cjk/latin/digit")
    parser.add_argument("--role-mode", action="append", default=[], help="composite: ROLE=auto|fixed")
    parser.add_argument("--role-axes", action="append", default=[], help="composite: ROLE=tag=value,...")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate", type=Path)
    args = parser.parse_args()

    try:
        if args.validate is not None:
            profile = json.loads(args.validate.read_text(encoding="utf-8"))
            if not isinstance(profile, dict):
                raise ProfileError("源字体 Profile 根节点无效")
            validate(profile)
        elif args.role_font:
            role_fonts: dict[str, list[Path]] = {}
            for item in args.role_font:
                role, sep, raw = item.partition(":")
                if not sep or role not in COMPOSITE_ROLES:
                    raise ProfileError(f"组合字体参数无效：{item}")
                role_fonts.setdefault(role, []).append(Path(raw))
            modes = dict(item.split("=", 1) for item in args.role_mode if "=" in item)
            axes = dict(item.split("=", 1) for item in args.role_axes if "=" in item)
            profile = build(args.font, role_fonts, modes, axes)
            if args.output is not None:
                _atomic_write(args.output, profile)
        else:
            profile = build(args.font)
            if args.output is not None:
                _atomic_write(args.output, profile)
    except (ProfileError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "error", "message": str(error)}, ensure_ascii=False))
        return 1

    print(json.dumps(_summary(profile), ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
