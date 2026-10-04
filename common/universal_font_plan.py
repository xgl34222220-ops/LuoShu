#!/usr/bin/env python3
"""Build a deterministic universal FontPlan from topology, roles and source profile.

Phase 4 is planning only. It never writes Android font XML, builds replacement
font files, mounts paths, or changes /data/fonts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any

SCHEMA = "universal-font-plan-v1"
PLAN_REVISION = 1
TOPOLOGY_SCHEMA = "device-font-topology-v1"
ROLES_SCHEMA = "device-font-roles-v1"
SOURCE_SCHEMA = "source-font-profile-v1"

PROTECTED_ROLES = {
    "monospace", "serif", "emoji", "symbol-icon", "special-fallback",
}
TEXT_ROLES = {"ui-sans", "cjk", "latin"}
SPECIALIZED_ROLES = {"numeric", "clock"}
# A non-core slot that cannot be replaced safely keeps its stock font; the
# switch reports it instead of failing. Core slots never take this action.
KEEP_STOCK = "keep-stock"
CHINESE_LANG_TOKENS = ("zh", "hans", "hant", "hani")


class UniversalPlanError(RuntimeError):
    pass


def _int(value: Any, default: int | None = None) -> int | None:
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
        raise UniversalPlanError(f"无法读取计划输入：{path}") from error
    if not isinstance(value, dict):
        raise UniversalPlanError(f"计划输入根节点无效：{path}")
    return value


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".tmp.{os.getpid()}")
    temp.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(temp, 0o600)
    os.replace(temp, path)


def _canonical_hash(value: Any) -> str:
    blob = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _topology_digest(topology: dict[str, Any]) -> str:
    material = {
        "schema": topology.get("schema"),
        "topologyRevision": topology.get("topologyRevision"),
        "buildKey": topology.get("buildKey"),
        "romKind": topology.get("romKind"),
        "slots": topology.get("slots"),
        "families": topology.get("families"),
        "xmlAliases": topology.get("xmlAliases"),
        "unresolvedXmlRefs": topology.get("unresolvedXmlRefs"),
        "runtime": topology.get("runtime"),
    }
    return f"sha256:{_canonical_hash(material)}"


def _roles_digest(roles: dict[str, Any]) -> str:
    material = {
        "schema": roles.get("schema"),
        "roleRevision": roles.get("roleRevision"),
        "buildKey": roles.get("buildKey"),
        "romKind": roles.get("romKind"),
        "slots": roles.get("slots"),
    }
    return f"sha256:{_canonical_hash(material)}"


def _source_digest(profile: dict[str, Any]) -> str:
    material = {
        "schema": profile.get("schema"),
        "profileRevision": profile.get("profileRevision"),
        "profileId": profile.get("profileId"),
        "summary": profile.get("summary"),
        "families": profile.get("families"),
        "files": profile.get("files"),
    }
    return f"sha256:{_canonical_hash(material)}"


def _topology_slots(topology: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = topology.get("slots")
    if not isinstance(raw, dict):
        raise UniversalPlanError("设备拓扑缺少 slots")
    return {
        str(path): slot
        for path, slot in raw.items()
        if isinstance(slot, dict) and str(path).startswith("/")
    }


def _role_slots(roles: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = roles.get("slots")
    if not isinstance(raw, dict):
        raise UniversalPlanError("字体角色映射缺少 slots")
    return {
        str(path): value
        for path, value in raw.items()
        if isinstance(value, dict)
    }


def _source_faces(profile: dict[str, Any]) -> list[dict[str, Any]]:
    faces: list[dict[str, Any]] = []
    raw_files = profile.get("files")
    if not isinstance(raw_files, list):
        raise UniversalPlanError("源字体 Profile 缺少 files")
    for file_info in raw_files:
        if not isinstance(file_info, dict):
            continue
        source_path = str(file_info.get("sourcePath") or "")
        source_container = str(file_info.get("container") or "")
        conversion_required = file_info.get("requiresSfntConversion") is True
        raw_faces = file_info.get("faces")
        if not isinstance(raw_faces, list):
            continue
        for face in raw_faces:
            if not isinstance(face, dict):
                continue
            item = dict(face)
            item["_sourcePath"] = source_path
            item["_sourceContainer"] = source_container
            item["_conversionRequired"] = conversion_required
            faces.append(item)
    if not faces:
        raise UniversalPlanError("源字体 Profile 没有可分析的 face")
    return faces


def _coverage(slot: dict[str, Any]) -> dict[str, Any]:
    metrics = slot.get("metrics")
    if not isinstance(metrics, dict):
        return {}
    coverage = metrics.get("coverage")
    return coverage if isinstance(coverage, dict) else {}


def _target_weight(slot: dict[str, Any]) -> int:
    metrics = slot.get("metrics")
    if isinstance(metrics, dict):
        value = _int(metrics.get("weightClass"))
        if value is not None and 1 <= value <= 1000:
            return value
    refs = slot.get("xmlRefs")
    if isinstance(refs, list):
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            value = _int(ref.get("weight"))
            if value is not None and 1 <= value <= 1000:
                return value
    return 400


def _target_italic(slot: dict[str, Any]) -> bool:
    refs = slot.get("xmlRefs")
    if isinstance(refs, list):
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            style = str(ref.get("style") or "").lower()
            if style in {"italic", "oblique"}:
                return True
    name = str(slot.get("slotName") or "").lower()
    return "italic" in name or "oblique" in name


def _target_variable(slot: dict[str, Any]) -> bool:
    metrics = slot.get("metrics")
    if isinstance(metrics, dict):
        axes = metrics.get("variationAxes")
        if isinstance(axes, list) and axes:
            return True
    name = str(slot.get("slotName") or "").lower()
    return any(token in name for token in ("variable", "flex", "vf." , "vf_", "-vf"))


def _target_requires_cjk(role: str, slot: dict[str, Any]) -> bool:
    if role == "cjk":
        return True
    coverage = _coverage(slot)
    if coverage.get("hasHan") is True:
        return True
    try:
        if int(coverage.get("hanCount") or 0) > 0:
            return True
    except (TypeError, ValueError):
        pass
    refs = slot.get("xmlRefs")
    if isinstance(refs, list):
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            attrs = ref.get("familyAttributes")
            if not isinstance(attrs, dict):
                continue
            lang = str(
                attrs.get("lang")
                or attrs.get("language")
                or attrs.get("locale")
                or ""
            ).lower()
            if lang.startswith(("zh", "hans", "hant", "cmn", "yue")):
                return True
    return False


def _face_capabilities(face: dict[str, Any]) -> dict[str, Any]:
    value = face.get("capabilities")
    return value if isinstance(value, dict) else {}


def _face_style(face: dict[str, Any]) -> dict[str, Any]:
    value = face.get("style")
    return value if isinstance(value, dict) else {}


def _face_variation(face: dict[str, Any]) -> dict[str, Any]:
    value = face.get("variation")
    return value if isinstance(value, dict) else {}


def _wght_axis(face: dict[str, Any]) -> dict[str, Any] | None:
    variation = _face_variation(face)
    axes = variation.get("axes")
    if not isinstance(axes, list):
        return None
    for axis in axes:
        if isinstance(axis, dict) and str(axis.get("tag")) == "wght":
            return axis
    return None


def _weight_distance(face: dict[str, Any], target_weight: int) -> tuple[float, str]:
    axis = _wght_axis(face)
    if axis is not None:
        minimum = _float(axis.get("min"))
        maximum = _float(axis.get("max"))
        if minimum is not None and maximum is not None:
            if minimum <= target_weight <= maximum:
                return 0.0, "variable-in-range"
            return min(abs(target_weight - minimum), abs(target_weight - maximum)), "variable-clamped"
    source_weight = _int(_face_style(face).get("weight"), 400) or 400
    return float(abs(source_weight - target_weight)), "static"


def _face_meets_role(face: dict[str, Any], role: str, slot: dict[str, Any]) -> tuple[bool, list[str]]:
    caps = _face_capabilities(face)
    reasons: list[str] = []
    if caps.get("colorFont") is True:
        return False, ["color-font"]
    if face.get("_conversionRequired") is True:
        reasons.append("sfnt-conversion-required")

    if role == "ui-sans":
        if _target_requires_cjk(role, slot):
            if caps.get("cjkUi") is not True:
                return False, reasons + ["cjk-ui-coverage-missing"]
            reasons.append("cjk-ui-capable")
        else:
            if caps.get("latinUi") is not True:
                return False, reasons + ["latin-ui-coverage-missing"]
            reasons.append("latin-ui-capable")
    elif role == "cjk":
        if caps.get("cjkUi") is not True:
            return False, reasons + ["cjk-ui-coverage-missing"]
        reasons.append("cjk-ui-capable")
    elif role == "latin":
        if caps.get("latinUi") is not True:
            return False, reasons + ["latin-ui-coverage-missing"]
        reasons.append("latin-ui-capable")
    elif role in SPECIALIZED_ROLES:
        if caps.get("numeric") is not True:
            return False, reasons + ["digit-coverage-missing"]
        reasons.append("numeric-capable")
    else:
        return False, reasons + ["role-not-replaceable"]
    return True, reasons


def _candidate_score(
    face: dict[str, Any],
    role: str,
    slot: dict[str, Any],
    target_weight: int,
    target_italic: bool,
) -> tuple[tuple[float, float, float, float, str, int], dict[str, Any]] | None:
    compatible, reasons = _face_meets_role(face, role, slot)
    if not compatible:
        return None

    style = _face_style(face)
    source_italic = style.get("italic") is True
    italic_penalty = 0.0 if source_italic == target_italic else 10000.0
    weight_distance, weight_mode = _weight_distance(face, target_weight)
    web_penalty = 5000.0 if face.get("_conversionRequired") is True else 0.0
    source_weight = _int(style.get("weight"), 400) or 400
    if weight_mode == "static" and source_weight == target_weight:
        source_mode_penalty = 0.0
    elif weight_mode == "variable-in-range":
        source_mode_penalty = 1.0
    elif weight_mode == "static":
        source_mode_penalty = 2.0
    else:
        source_mode_penalty = 3.0

    caps = _face_capabilities(face)
    role_bonus = 0.0
    if role == "ui-sans" and caps.get("globalUiCandidate") is True:
        role_bonus = -200.0
    if role == "cjk" and caps.get("cjkUi") is True:
        role_bonus = -100.0

    uid = str(face.get("uid") or "")
    index = _int(face.get("faceIndex"), 0) or 0
    score = (
        italic_penalty,
        web_penalty,
        max(0.0, weight_distance + role_bonus),
        source_mode_penalty,
        uid,
        index,
    )
    details = {
        "roleReasons": reasons,
        "weightMode": weight_mode,
        "weightDistance": round(weight_distance, 4),
        "italicMatch": source_italic == target_italic,
    }
    return score, details


def _select_face(
    faces: list[dict[str, Any]],
    role: str,
    slot: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    target_weight = _target_weight(slot)
    target_italic = _target_italic(slot)
    ranked: list[tuple[tuple[float, float, float, float, str, int], dict[str, Any], dict[str, Any]]] = []
    rejected: dict[str, int] = {}

    for face in faces:
        compatible, reject_reasons = _face_meets_role(face, role, slot)
        if not compatible:
            for reason in reject_reasons:
                rejected[reason] = rejected.get(reason, 0) + 1
            continue
        candidate = _candidate_score(face, role, slot, target_weight, target_italic)
        if candidate is None:
            continue
        score, details = candidate
        ranked.append((score, face, details))

    if not ranked:
        return None, {
            "targetWeight": target_weight,
            "targetItalic": target_italic,
            "rejected": dict(sorted(rejected.items())),
        }

    ranked.sort(key=lambda item: item[0])
    _score, selected, details = ranked[0]
    return selected, {
        "targetWeight": target_weight,
        "targetItalic": target_italic,
        "candidateCount": len(ranked),
        **details,
    }


def _source_ref(face: dict[str, Any]) -> dict[str, Any]:
    names = face.get("names") if isinstance(face.get("names"), dict) else {}
    style = _face_style(face)
    variation = _face_variation(face)
    metrics = face.get("metrics") if isinstance(face.get("metrics"), dict) else {}
    coverage = face.get("coverage") if isinstance(face.get("coverage"), dict) else {}
    capabilities = _face_capabilities(face)
    warnings = face.get("warnings") if isinstance(face.get("warnings"), list) else []
    return {
        "uid": str(face.get("uid") or ""),
        "fileUid": str(face.get("fileUid") or ""),
        "sourcePath": str(face.get("_sourcePath") or ""),
        "sourceContainer": str(face.get("_sourceContainer") or ""),
        "format": str(face.get("format") or ""),
        "faceIndex": _int(face.get("faceIndex"), 0) or 0,
        "family": str(names.get("family") or ""),
        "subfamily": str(names.get("subfamily") or ""),
        "postScriptName": str(names.get("postScriptName") or ""),
        "weight": _int(style.get("weight"), 400) or 400,
        "italic": style.get("italic") is True,
        "variable": variation.get("variable") is True,
        "axes": list(variation.get("axes") or []) if isinstance(variation.get("axes"), list) else [],
        "metrics": dict(metrics),
        "coverage": dict(coverage),
        "capabilities": dict(capabilities),
        "warnings": list(warnings),
    }


def is_core_target(target: dict[str, Any]) -> bool:
    """Slots whose text the user sees everywhere: the upright UI face, the
    Chinese text fallback, and the clock/numeric faces. These must be replaced
    or the whole switch fails; every other slot may keep its stock font."""
    role = str(target.get("role") or "")
    if role in SPECIALIZED_ROLES:
        return True
    if role not in {"ui-sans", "cjk"}:
        return False
    refs = [ref for ref in target.get("xmlRefs") or [] if isinstance(ref, dict)]
    if refs:
        upright = [ref for ref in refs if str(ref.get("style") or "").lower() not in {"italic", "oblique"}]
    else:
        name = str(target.get("slotName") or target.get("path") or "").lower()
        upright = [] if "italic" in name or "oblique" in name else [{}]
    if not upright:
        return False
    if role == "ui-sans":
        return True
    for ref in upright:
        attributes = ref.get("familyAttributes") if isinstance(ref.get("familyAttributes"), dict) else {}
        for lang in re.split(r"[\s,]+", str(attributes.get("lang") or "").lower()):
            if any(part in CHINESE_LANG_TOKENS for part in lang.split("-")):
                return True
    return False


def load_exclusions(path: Path | None) -> dict[str, str]:
    """Slots a previous compile pass could not build: {path: reason}."""
    if path is None or not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    targets = raw.get("targets") if isinstance(raw, dict) else None
    if not isinstance(targets, dict):
        return {}
    return {str(key): str(value)[:300] for key, value in targets.items() if str(key).startswith("/")}


def _keep_stock(target: dict[str, Any], reason: str) -> None:
    target.update(
        action=KEEP_STOCK,
        status="ready",
        compiler="none",
        keptStockReason=reason,
        reasons=sorted({*target.get("reasons", []), "non-core-kept-stock"}),
    )


def _xml_refs(slot: dict[str, Any]) -> list[dict[str, Any]]:
    raw = slot.get("xmlRefs")
    if not isinstance(raw, list):
        return []
    return [dict(ref) for ref in raw if isinstance(ref, dict)]


def _target_metrics_ready(slot: dict[str, Any]) -> bool:
    metrics = slot.get("metrics")
    if not isinstance(metrics, dict):
        return False
    upem = _int(metrics.get("upem"))
    hhea = metrics.get("hhea") if isinstance(metrics.get("hhea"), dict) else {}
    ascent = _int(hhea.get("ascent"))
    descent = _int(hhea.get("descent"))
    return (
        upem is not None and 16 <= upem <= 16384
        and ascent is not None and ascent > 0
        and descent is not None and descent <= 0
    )


def _source_metrics_ready(face: dict[str, Any]) -> bool:
    metrics = face.get("metrics")
    if not isinstance(metrics, dict):
        return False
    upem = _int(metrics.get("unitsPerEm"))
    hhea = metrics.get("hhea") if isinstance(metrics.get("hhea"), dict) else {}
    ascent = _int(hhea.get("ascent"))
    descent = _int(hhea.get("descent"))
    return (
        upem is not None and 16 <= upem <= 16384
        and ascent is not None and ascent > 0
        and descent is not None and descent <= 0
    )


def _compile_requirements(
    role: str,
    slot: dict[str, Any],
    face: dict[str, Any],
    selection: dict[str, Any],
) -> tuple[str, list[str], list[str]]:
    requirements: list[str] = []
    risks: list[str] = []
    target_weight = int(selection["targetWeight"])
    style = _face_style(face)
    source_weight = _int(style.get("weight"), 400) or 400
    weight_mode = str(selection.get("weightMode") or "static")
    target_variable = _target_variable(slot)
    source_variable = _face_variation(face).get("variable") is True

    if face.get("_conversionRequired") is True:
        requirements.append("sfnt-conversion")
    if not _target_metrics_ready(slot):
        requirements.append("stock-metrics-capture")
        risks.append("target-metrics-missing")
    if not _source_metrics_ready(face):
        requirements.append("source-metrics-refresh")
        risks.append("source-metrics-missing")
    if role in TEXT_ROLES:
        requirements.append("metrics-normalization")
    if role in SPECIALIZED_ROLES:
        requirements.extend(["metrics-normalization", "specialized-numeric-contract"])
    if role == "clock":
        requirements.append("stock-exact-advance")
    if weight_mode == "variable-in-range":
        if not target_variable:
            requirements.append("variable-instance")
    elif weight_mode == "variable-clamped":
        requirements.append("variable-instance")
        risks.append("source-weight-axis-out-of-range")
    elif source_weight != target_weight:
        risks.append("static-weight-fallback")

    if target_variable and not source_variable:
        risks.append("static-source-for-variable-target")
    if selection.get("italicMatch") is not True:
        risks.append("italic-style-mismatch")

    requirements = sorted(set(requirements))
    risks = sorted(set(risks))
    if role in SPECIALIZED_ROLES:
        compiler = "specialized"
    elif requirements:
        compiler = "compatibility"
    else:
        compiler = "direct"
    return compiler, requirements, risks


COMPOSITE_ROLES = ("cjk", "latin", "digit")


def _composite_needs(role: str, slot: dict[str, Any]) -> list[str]:
    """Composite roles whose glyphs a stock slot of ``role`` actually shows."""
    if role == "cjk":
        return ["cjk"]
    if role in SPECIALIZED_ROLES:
        return ["digit"]
    needs = ["latin", "digit"]
    if role == "ui-sans" and _target_requires_cjk(role, slot):
        needs.insert(0, "cjk")
    return needs


def _composite_face_ok(face: dict[str, Any], composite_role: str) -> tuple[bool, str]:
    caps = _face_capabilities(face)
    if caps.get("colorFont") is True:
        return False, "color-font"
    if composite_role == "cjk":
        coverage = face.get("coverage") if isinstance(face.get("coverage"), dict) else {}
        probes = coverage.get("probes") if isinstance(coverage.get("probes"), dict) else {}
        cjk_ratio = _float((probes.get("cjk") or {}).get("ratio"), 0.0) or 0.0
        minimum = _int(coverage.get("minimumCoreHan"), 6000) or 6000
        if (_int(coverage.get("coreHan"), 0) or 0) < minimum or cjk_ratio < 0.95:
            return False, "composite-cjk-coverage-missing"
        return True, "composite-cjk-capable"
    if composite_role == "latin":
        return (True, "composite-latin-capable") if caps.get("latinUi") is True else (False, "composite-latin-coverage-missing")
    return (True, "composite-digit-capable") if caps.get("numeric") is True else (False, "composite-digit-coverage-missing")


def _select_composite_face(
    faces: list[dict[str, Any]],
    composite_role: str,
    spec: dict[str, Any],
    slot: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Pick a face only among those the user assigned to ``composite_role``."""
    axes = spec.get("axes") if isinstance(spec.get("axes"), dict) else {}
    fixed = spec.get("mode") == "fixed"
    target_weight = _target_weight(slot)
    if fixed and _float(axes.get("wght")) is not None:
        target_weight = int(round(float(axes["wght"])))
    target_italic = _target_italic(slot)
    ranked = []
    compatible: list[dict[str, Any]] = []
    rejected: dict[str, int] = {}
    for face in faces:
        if composite_role not in (face.get("assignedRoles") or []):
            continue
        ok, reason = _composite_face_ok(face, composite_role)
        if not ok:
            rejected[reason] = rejected.get(reason, 0) + 1
            continue
        compatible.append(face)
        italic_penalty = 0.0 if (_face_style(face).get("italic") is True) == target_italic else 10000.0
        distance, mode = _weight_distance(face, target_weight)
        ranked.append(((italic_penalty, distance, str(face.get("uid") or ""), _int(face.get("faceIndex"), 0) or 0),
                       face, mode, reason))
    selection: dict[str, Any] = {
        "compositeRole": composite_role,
        "mode": "fixed" if fixed else "auto",
        "targetWeight": target_weight,
        "targetItalic": target_italic,
    }
    if not ranked:
        selection["rejected"] = dict(sorted(rejected.items()))
        return None, selection
    ranked.sort(key=lambda item: item[0])
    _score, face, weight_mode, reason = ranked[0]
    selection["candidates"] = [_candidate_ref(item) for item in sorted(
        compatible, key=lambda item: (str(item.get("uid") or ""), _int(item.get("faceIndex"), 0) or 0)
    )]
    selection.update(
        candidateCount=len(ranked),
        weightMode=weight_mode,
        weightDistance=round(float(_score[1]), 4),
        italicMatch=_score[0] == 0.0,
        roleReasons=[reason],
    )
    return face, selection



def _candidate_ref(face: dict[str, Any]) -> dict[str, Any]:
    """Minimal per-face reference the compiler uses to pick a weight per node."""
    full = _source_ref(face)
    return {key: full[key] for key in (
        "uid", "fileUid", "sourcePath", "sourceContainer", "format", "faceIndex",
        "weight", "italic", "variable", "axes",
    )}


def _composite_identity(ref: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(ref.get("uid") or ""),
        str(ref.get("compositeMode") or "auto"),
        json.dumps(ref.get("compositeAxes") or {}, sort_keys=True),
    )


def _composite_source_ref(face: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    ref = _source_ref(face)
    ref["compositeMode"] = "fixed" if spec.get("mode") == "fixed" else "auto"
    axes = spec.get("axes") if isinstance(spec.get("axes"), dict) else {}
    ref["compositeAxes"] = {str(k): float(v) for k, v in sorted(axes.items())}
    return ref


def _plan_slot(
    path: str,
    slot: dict[str, Any],
    role_info: dict[str, Any],
    faces: list[dict[str, Any]],
    composite: dict[str, Any] | None = None,
) -> dict[str, Any]:
    role = str(role_info.get("role") or "unknown-protected")
    confidence = _int(role_info.get("confidence"), 0) or 0
    role_action = str(role_info.get("action") or "review")
    base: dict[str, Any] = {
        "path": path,
        "slotName": str(slot.get("slotName") or Path(path).name),
        "partition": str(slot.get("partition") or ""),
        "families": list(slot.get("families") or []) if isinstance(slot.get("families"), list) else [],
        "xmlRefs": _xml_refs(slot),
        "role": role,
        "roleConfidence": confidence,
        "roleAction": role_action,
        "runtimeEvidence": dict(slot.get("runtimeEvidence") or {}) if isinstance(slot.get("runtimeEvidence"), dict) else {},
        "legacyReplaceable": slot.get("legacyReplaceable") if isinstance(slot.get("legacyReplaceable"), bool) else None,
        "targetContract": {
            "format": str(slot.get("format") or slot.get("validatedFormat") or ""),
            "faceIndex": max(0, _int(slot.get("faceIndex"), 0) or 0),
            "weight": _target_weight(slot),
            "italic": _target_italic(slot),
            "variable": _target_variable(slot),
            "metrics": dict(slot.get("metrics") or {}) if isinstance(slot.get("metrics"), dict) else {},
            "coverage": dict(_coverage(slot)),
        },
        "action": "review",
        "status": "review",
        "compiler": "none",
        "requirements": [],
        "risks": [],
        "reasons": [],
    }

    if role in PROTECTED_ROLES:
        base.update(
            action="preserve",
            status="ready",
            reasons=["protected-role"],
        )
        return base
    if role == "unknown-protected" or role_action == "review":
        base.update(
            action="review",
            status="review",
            reasons=["insufficient-role-evidence"],
        )
        return base
    if role not in TEXT_ROLES | SPECIALIZED_ROLES:
        base.update(
            action="preserve",
            status="ready",
            reasons=["role-not-in-universal-replacement-scope"],
        )
        return base

    composite_sources: dict[str, Any] | None = None
    if composite is not None:
        # The user's assignment decides every glyph class; capability-based
        # auto selection across all imported faces must not apply here.
        roles_spec = composite.get("roles") if isinstance(composite.get("roles"), dict) else {}
        needs = _composite_needs(role, slot)
        composite_sources = {}
        selections: dict[str, Any] = {}
        face = None
        selection: dict[str, Any] = {}
        for composite_role in needs:
            spec = roles_spec.get(composite_role) if isinstance(roles_spec.get(composite_role), dict) else {}
            picked, picked_selection = _select_composite_face(faces, composite_role, spec, slot)
            selections[composite_role] = picked_selection
            if picked is None:
                face = None
                selection = dict(picked_selection, compositeNeeds=needs)
                break
            composite_sources[composite_role] = _composite_source_ref(picked, spec)
            composite_sources[composite_role]["candidates"] = picked_selection.pop("candidates")
            if face is None:
                # Primary source: CJK when the slot shows Han, otherwise Latin
                # (or the digit source for clock/numeric slots).
                face, selection = picked, dict(picked_selection)
        else:
            selection["compositeNeeds"] = needs
            selection["compositeSelections"] = selections
        if face is None:
            composite_sources = None
    else:
        face, selection = _select_face(faces, role, slot)
    base["selection"] = selection
    if face is None:
        base.update(
            action="blocked",
            status="blocked",
            reasons=["no-compatible-source-face"],
            risks=sorted((selection.get("rejected") or {}).keys()),
        )
        return base

    compiler, requirements, risks = _compile_requirements(role, slot, face, selection)
    base["source"] = _source_ref(face)
    if composite_sources is not None:
        primary_role = next(iter(composite_sources))
        base["source"] = dict(composite_sources[primary_role])
        base["compositeSources"] = composite_sources
        if len({_composite_identity(ref) for ref in composite_sources.values()}) > 1:
            requirements = sorted(set(requirements) | {"composite-multi-source"})
            compiler = "compatibility" if compiler == "direct" else compiler
    base["compiler"] = compiler
    base["requirements"] = requirements
    base["risks"] = risks
    base["reasons"] = list(selection.get("roleReasons") or [])

    if role in SPECIALIZED_ROLES:
        base["action"] = "compile-specialized"
    elif compiler == "direct":
        base["action"] = "replace"
    else:
        base["action"] = "compile"

    # Phase 4 never claims a risky mapping is ready for execution. Phase 6 must
    # resolve these compiler risks before later execution phases can consume it.
    if risks:
        base["status"] = "conditional"
    else:
        base["status"] = "ready"
    return base


def _validate_inputs(
    topology: dict[str, Any],
    roles: dict[str, Any],
    profile: dict[str, Any],
) -> tuple[str, str]:
    if topology.get("schema") != TOPOLOGY_SCHEMA or topology.get("state") != "ready":
        raise UniversalPlanError("设备字体拓扑未就绪")
    if roles.get("schema") != ROLES_SCHEMA or roles.get("state") != "ready":
        raise UniversalPlanError("字体角色映射未就绪")
    if profile.get("schema") != SOURCE_SCHEMA or profile.get("state") != "ready":
        raise UniversalPlanError("源字体 Profile 未就绪")

    build_key = str(topology.get("buildKey") or "unknown")
    role_build_key = str(roles.get("buildKey") or "unknown")
    if build_key != "unknown" and role_build_key != "unknown" and build_key != role_build_key:
        raise UniversalPlanError("角色映射与设备拓扑 buildKey 不一致")

    profile_id = str(profile.get("profileId") or "")
    if not profile_id.startswith("sha256:"):
        raise UniversalPlanError("源字体 Profile 缺少稳定 profileId")
    return build_key, profile_id


def _global_constraints(
    topology: dict[str, Any],
    missing_role_slots: list[str],
) -> dict[str, Any]:
    summary = topology.get("summary") if isinstance(topology.get("summary"), dict) else {}
    runtime = topology.get("runtime") if isinstance(topology.get("runtime"), dict) else {}
    unresolved = topology.get("unresolvedXmlRefs")
    unresolved_count = len(unresolved) if isinstance(unresolved, list) else 0

    def count(name: str) -> int:
        value = _int(summary.get(name), 0)
        return max(0, value or 0)

    data_font_files = count("dataFontFileCount")
    data_font_refs = count("dataFontConfigReferenceCount")
    if not data_font_files:
        files = runtime.get("dataFontFiles")
        if isinstance(files, list):
            data_font_files = len(files)
    if not data_font_refs:
        config = runtime.get("dataFontsConfig")
        if isinstance(config, dict):
            refs = config.get("references")
            if isinstance(refs, list):
                data_font_refs = len(refs)

    requirements: list[str] = []
    risks: list[str] = []
    if data_font_files or data_font_refs:
        requirements.append("data-font-layer-review")
        risks.append("data-font-layer-active")
    if unresolved_count:
        requirements.append("resolve-unresolved-xml-refs")
        risks.append("unresolved-xml-routes")
    if missing_role_slots:
        requirements.append("complete-role-map")
        risks.append("missing-role-evidence")
    return {
        "requirements": sorted(requirements),
        "risks": sorted(risks),
        "dataFontFileCount": data_font_files,
        "dataFontConfigReferenceCount": data_font_refs,
        "unresolvedXmlRefCount": unresolved_count,
        "missingRoleSlotCount": len(missing_role_slots),
    }


def build_plan(
    topology: dict[str, Any],
    roles: dict[str, Any],
    profile: dict[str, Any],
    exclusions: dict[str, str] | None = None,
) -> dict[str, Any]:
    build_key, profile_id = _validate_inputs(topology, roles, profile)
    slots = _topology_slots(topology)
    role_slots = _role_slots(roles)
    faces = _source_faces(profile)
    composite = profile.get("composite") if isinstance(profile.get("composite"), dict) else None

    targets: dict[str, dict[str, Any]] = {}
    missing_role_slots: list[str] = []
    for path in sorted(slots):
        role_info = role_slots.get(path)
        if role_info is None:
            missing_role_slots.append(path)
            role_info = {
                "role": "unknown-protected",
                "confidence": 0,
                "action": "review",
            }
        target = _plan_slot(path, slots[path], role_info, faces, composite)
        if not is_core_target(target):
            if target["action"] == "blocked":
                _keep_stock(target, "no-compatible-source-face:" + ",".join(target.get("risks") or []))
            elif exclusions and path in exclusions and target["action"] in {"replace", "compile", "compile-specialized"}:
                _keep_stock(target, exclusions[path])
        targets[path] = target

    action_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    compiler_counts: dict[str, int] = {}
    for item in targets.values():
        for key, bucket in (
            ("action", action_counts),
            ("status", status_counts),
            ("compiler", compiler_counts),
        ):
            value = str(item.get(key) or "unknown")
            bucket[value] = bucket.get(value, 0) + 1

    inputs = {
        "topologyDigest": _topology_digest(topology),
        "rolesDigest": _roles_digest(roles),
        "sourceProfileId": profile_id,
        "sourceProfileRevision": profile.get("profileRevision"),
        "sourceDigest": _source_digest(profile),
    }
    constraints = _global_constraints(topology, missing_role_slots)
    semantic = {
        "inputs": inputs,
        "buildKey": build_key,
        "topologyRevision": topology.get("topologyRevision"),
        "roleRevision": roles.get("roleRevision"),
        "missingRoleSlots": missing_role_slots,
        "constraints": constraints,
        "targets": targets,
    }
    plan_id = f"sha256:{_canonical_hash(semantic)}"
    plan = {
        "schema": SCHEMA,
        "planRevision": PLAN_REVISION,
        "state": "planned",
        "mutatesSystem": False,
        "generatedAt": int(time.time()),
        "planId": plan_id,
        "inputs": inputs,
        "device": {
            "buildKey": build_key,
            "romKind": str(topology.get("romKind") or "generic"),
            "topologyRevision": topology.get("topologyRevision"),
            "roleRevision": roles.get("roleRevision"),
        },
        "source": {
            "profileId": profile_id,
            "fileCount": profile.get("summary", {}).get("fileCount"),
            "faceCount": profile.get("summary", {}).get("faceCount"),
            "familyCount": profile.get("summary", {}).get("familyCount"),
            "capabilities": dict(profile.get("summary", {}).get("capabilities") or {}),
            **({"composite": True} if composite is not None else {}),
        },
        "constraints": constraints,
        "summary": {
            "slotCount": len(targets),
            "actionCounts": dict(sorted(action_counts.items())),
            "statusCounts": dict(sorted(status_counts.items())),
            "compilerCounts": dict(sorted(compiler_counts.items())),
            "missingRoleSlotCount": len(missing_role_slots),
            "executableNow": False,
        },
        "missingRoleSlots": missing_role_slots,
        "targets": targets,
    }
    validate_plan(
        plan,
        expected_build_key=build_key,
        expected_profile_id=profile_id,
        expected_topology_digest=inputs["topologyDigest"],
        expected_roles_digest=inputs["rolesDigest"],
        expected_source_digest=inputs["sourceDigest"],
        expected_source_revision=_int(profile.get("profileRevision")),
    )
    return plan


def validate_plan(
    plan: dict[str, Any],
    expected_build_key: str | None = None,
    expected_profile_id: str | None = None,
    expected_topology_digest: str | None = None,
    expected_roles_digest: str | None = None,
    expected_source_digest: str | None = None,
    expected_source_revision: int | None = None,
) -> None:
    if plan.get("schema") != SCHEMA or plan.get("state") != "planned":
        raise UniversalPlanError("Universal FontPlan 格式无效")
    if _int(plan.get("planRevision"), 0) != PLAN_REVISION:
        raise UniversalPlanError("Universal FontPlan 版本无效")
    if plan.get("mutatesSystem") is not False:
        raise UniversalPlanError("Phase 4 FontPlan 不得修改系统")
    summary = plan.get("summary")
    if not isinstance(summary, dict):
        raise UniversalPlanError("Universal FontPlan 缺少 summary")
    if summary.get("executableNow") is not False:
        raise UniversalPlanError("Phase 4 FontPlan 不得声明可直接执行")
    device = plan.get("device") if isinstance(plan.get("device"), dict) else {}
    source = plan.get("source") if isinstance(plan.get("source"), dict) else {}
    if expected_build_key and expected_build_key != "unknown":
        if device.get("buildKey") != expected_build_key:
            raise UniversalPlanError("Universal FontPlan 与设备 buildKey 不一致")
    if expected_profile_id and source.get("profileId") != expected_profile_id:
        raise UniversalPlanError("Universal FontPlan 与源字体 Profile 不一致")
    inputs = plan.get("inputs") if isinstance(plan.get("inputs"), dict) else {}
    if expected_topology_digest and inputs.get("topologyDigest") != expected_topology_digest:
        raise UniversalPlanError("Universal FontPlan 与设备拓扑摘要不一致")
    if expected_roles_digest and inputs.get("rolesDigest") != expected_roles_digest:
        raise UniversalPlanError("Universal FontPlan 与角色摘要不一致")
    if expected_source_digest and inputs.get("sourceDigest") != expected_source_digest:
        raise UniversalPlanError("Universal FontPlan 与源字体摘要不一致")
    if expected_source_revision is not None and _int(inputs.get("sourceProfileRevision")) != expected_source_revision:
        raise UniversalPlanError("Universal FontPlan 与源字体 Profile revision 不一致")
    targets = plan.get("targets")
    if not isinstance(targets, dict):
        raise UniversalPlanError("Universal FontPlan 缺少 targets")
    for path, item in targets.items():
        if not isinstance(item, dict):
            raise UniversalPlanError(f"Universal FontPlan 目标无效：{path}")
        role = str(item.get("role") or "")
        action = str(item.get("action") or "")
        if role in PROTECTED_ROLES and action != "preserve":
            raise UniversalPlanError(f"受保护字体不得进入替换计划：{path}")
        if role == "unknown-protected" and action != "review":
            raise UniversalPlanError(f"未知字体不得自动替换：{path}")
        if action == KEEP_STOCK and is_core_target(item):
            raise UniversalPlanError(f"核心字体不得保留原厂：{path}")
        if role in SPECIALIZED_ROLES and action not in {"compile-specialized", "blocked", KEEP_STOCK}:
            raise UniversalPlanError(f"Clock/Numeric 不得走普通替换：{path}")
        if role in TEXT_ROLES and action not in {"replace", "compile", "blocked", KEEP_STOCK}:
            raise UniversalPlanError(f"文本目标包含无效动作：{path}")
        if role not in PROTECTED_ROLES | TEXT_ROLES | SPECIALIZED_ROLES | {"unknown-protected"}:
            if action != "preserve":
                raise UniversalPlanError(f"未知扩展角色不得自动替换：{path}")
        if action in {"replace", "compile", "compile-specialized"} and not isinstance(item.get("source"), dict):
            raise UniversalPlanError(f"替换目标缺少源 face：{path}")
        composite_sources = item.get("compositeSources")
        if composite_sources is not None:
            if (
                not isinstance(composite_sources, dict)
                or not composite_sources
                or not set(composite_sources) <= set(COMPOSITE_ROLES)
                or not all(isinstance(ref, dict) and ref.get("uid") for ref in composite_sources.values())
            ):
                raise UniversalPlanError(f"组合目标来源无效：{path}")
            if item.get("source") not in composite_sources.values():
                raise UniversalPlanError(f"组合目标主来源不在分工内：{path}")

    missing_role_slots = plan.get("missingRoleSlots")
    if not isinstance(missing_role_slots, list):
        raise UniversalPlanError("Universal FontPlan 缺少 missingRoleSlots")
    constraints = plan.get("constraints")
    if not isinstance(constraints, dict):
        raise UniversalPlanError("Universal FontPlan 缺少 constraints")

    action_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    compiler_counts: dict[str, int] = {}
    for item in targets.values():
        for key, bucket in (
            ("action", action_counts),
            ("status", status_counts),
            ("compiler", compiler_counts),
        ):
            value = str(item.get(key) or "unknown")
            bucket[value] = bucket.get(value, 0) + 1
    expected_summary = {
        "slotCount": len(targets),
        "actionCounts": dict(sorted(action_counts.items())),
        "statusCounts": dict(sorted(status_counts.items())),
        "compilerCounts": dict(sorted(compiler_counts.items())),
        "missingRoleSlotCount": len(missing_role_slots),
        "executableNow": False,
    }
    if summary != expected_summary:
        raise UniversalPlanError("Universal FontPlan summary 与 targets 不一致")
    if _int(constraints.get("missingRoleSlotCount"), -1) != len(missing_role_slots):
        raise UniversalPlanError("Universal FontPlan constraints 与角色缺口不一致")

    semantic = {
        "inputs": inputs,
        "buildKey": device.get("buildKey"),
        "topologyRevision": device.get("topologyRevision"),
        "roleRevision": device.get("roleRevision"),
        "missingRoleSlots": missing_role_slots,
        "constraints": constraints,
        "targets": targets,
    }
    expected_plan_id = f"sha256:{_canonical_hash(semantic)}"
    if plan.get("planId") != expected_plan_id:
        raise UniversalPlanError("Universal FontPlan planId 完整性校验失败")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topology", required=True, type=Path)
    parser.add_argument("--roles", required=True, type=Path)
    parser.add_argument("--source-profile", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate", type=Path)
    parser.add_argument("--exclusions", type=Path, help="non-core slots to keep stock: {targets:{path:reason}}")
    args = parser.parse_args()

    try:
        topology = _load(args.topology)
        roles = _load(args.roles)
        profile = _load(args.source_profile)
        build_key, profile_id = _validate_inputs(topology, roles, profile)
        if args.validate is not None:
            plan = _load(args.validate)
            validate_plan(
                plan,
                build_key,
                profile_id,
                _topology_digest(topology),
                _roles_digest(roles),
                _source_digest(profile),
                _int(profile.get("profileRevision")),
            )
        else:
            plan = build_plan(topology, roles, profile, load_exclusions(args.exclusions))
            if args.output is not None:
                _atomic_write(args.output, plan)
    except (UniversalPlanError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "error", "message": str(error)}, ensure_ascii=False))
        return 1

    summary = plan["summary"]
    print(json.dumps({
        "status": "ok",
        "schema": plan["schema"],
        "planId": plan["planId"],
        "slotCount": summary["slotCount"],
        "actionCounts": summary["actionCounts"],
        "statusCounts": summary["statusCounts"],
        "compilerCounts": summary["compilerCounts"],
        "executableNow": summary["executableNow"],
    }, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
