#!/usr/bin/env python3
"""Build a deterministic universal FontPlan from topology, roles and source profile.

Phase 4 is planning only. It never writes Android font XML, builds replacement
font files, mounts paths, or changes /data/fonts.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import time
from pathlib import Path
from typing import Any

SCHEMA = "universal-font-plan-v1"
PLAN_REVISION = 3
TOPOLOGY_SCHEMA = "device-font-topology-v1"
ROLES_SCHEMA = "device-font-roles-v1"
SOURCE_SCHEMA = "source-font-profile-v1"

PROTECTED_ROLES = {
    "monospace", "serif", "emoji", "symbol-icon", "special-fallback",
}
TEXT_ROLES = {"ui-sans", "cjk", "latin"}
SPECIALIZED_ROLES = {"numeric", "clock"}


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
    # A physical face may back both normal and italic XML routes. Their style
    # is a per-reference contract, not an OR over the physical slot's users.
    metrics = slot.get("metrics")
    if isinstance(metrics, dict):
        os2 = metrics.get("os2")
        if isinstance(os2, dict):
            flags = _int(os2.get("fsSelection"))
            if flags is not None:
                return bool(flags & (1 | (1 << 9)))
    refs = slot.get("xmlRefs")
    if isinstance(refs, list):
        styles = {
            str(ref.get("style") or "normal").lower() in {"italic", "oblique"}
            for ref in refs if isinstance(ref, dict)
        }
        if len(styles) == 1:
            return styles.pop()
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


def _route_axis_values(raw: Any) -> dict[str, float]:
    result: dict[str, float] = {}
    for axis in raw if isinstance(raw, list) else []:
        if not isinstance(axis, dict):
            continue
        tag = str(axis.get("tag") or "")
        for key in ("stylevalue", "styleValue", "value"):
            value = _float(axis.get(key))
            if value is not None:
                result[tag] = value
                break
    return result


def _source_style_contract(
    face: dict[str, Any], target_italic: bool, requested: dict[str, float],
) -> dict[str, Any]:
    axes = {
        str(axis.get("tag")): axis
        for axis in _face_variation(face).get("axes", [])
        if isinstance(axis, dict)
    }
    source_axes = {tag: value for tag, value in requested.items() if tag in axes}
    risks: list[str] = []
    style_values: dict[str, float] = {}
    for tag in ("ital", "slnt"):
        axis = axes.get(tag)
        if axis is None:
            # A static italic face can satisfy ital=1, but its boolean style
            # alone does not establish an exact nonzero slant angle.
            if tag == "slnt" and requested.get(tag, 0) != 0:
                risks.append("source-style-axis-missing")
            continue
        minimum, maximum = _float(axis.get("min")), _float(axis.get("max"))
        default = _float(axis.get("default"), 0.0) or 0.0
        value = requested.get(tag)
        if value is None:
            value = default
            if not target_italic:
                value = 0.0
            elif tag == "ital" and "slnt" not in requested:
                value = 1.0
        if minimum is None or maximum is None or not minimum <= value <= maximum:
            risks.append("source-style-axis-out-of-range")
        source_axes[tag] = value
        style_values[tag] = value
    source_italic = (
        any(value != 0 for value in style_values.values())
        if style_values else _face_style(face).get("italic") is True
    )
    return {
        "italicMatch": source_italic == target_italic,
        "sourceAxes": dict(sorted(source_axes.items())),
        "styleAxisRisks": sorted(set(risks)),
    }


def _weight_distance(face: dict[str, Any], target_weight: float) -> tuple[float, str]:
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
    target_weight: float,
    target_italic: bool,
    target_axes: dict[str, float] | None = None,
) -> tuple[tuple[float, float, float, float, str, int], dict[str, Any]] | None:
    compatible, reasons = _face_meets_role(face, role, slot)
    if not compatible:
        return None

    style = _face_style(face)
    style_contract = _source_style_contract(face, target_italic, target_axes or {})
    italic_penalty = (0.0 if style_contract["italicMatch"] else 10000.0) + (
        10000.0 * len(style_contract["styleAxisRisks"])
    )
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
        **style_contract,
    }
    return score, details


def _select_face(
    faces: list[dict[str, Any]],
    role: str,
    slot: dict[str, Any],
    *,
    target_weight: float | None = None,
    target_italic: bool | None = None,
    target_axes: dict[str, float] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    target_weight = _target_weight(slot) if target_weight is None else target_weight
    target_italic = _target_italic(slot) if target_italic is None else target_italic
    ranked: list[tuple[tuple[float, float, float, float, str, int], dict[str, Any], dict[str, Any]]] = []
    rejected: dict[str, int] = {}

    for face in faces:
        compatible, reject_reasons = _face_meets_role(face, role, slot)
        if not compatible:
            for reason in reject_reasons:
                rejected[reason] = rejected.get(reason, 0) + 1
            continue
        candidate = _candidate_score(face, role, slot, target_weight, target_italic, target_axes)
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
    result = {
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
    if isinstance(face.get("mixedSelection"), dict):
        result["mixedSelection"] = copy.deepcopy(face["mixedSelection"])
    return result


def _face_from_source_ref(source: dict[str, Any]) -> dict[str, Any]:
    face = copy.deepcopy(source)
    face.update({
        "_sourcePath": source.get("sourcePath", ""),
        "_sourceContainer": source.get("sourceContainer", ""),
        "_conversionRequired": source.get("sourceContainer") in {"WOFF", "WOFF2"},
        "style": {"weight": source.get("weight", 400), "italic": source.get("italic") is True},
        "variation": {"variable": source.get("variable") is True, "axes": source.get("axes", [])},
        "names": {key: source.get(key, "") for key in ("family", "subfamily", "postScriptName")},
    })
    return face


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


def is_fixed_composite_selection(source: dict[str, Any]) -> bool:
    """Recognize only frozen, hash-bound fixed-role intent, never generic static fonts."""
    policy = source.get("mixedSelection")
    if not isinstance(policy, dict) or policy.get("policy") != "fixed-composite-selection-v1":
        return False
    digest = str(policy.get("fontSha256") or "")
    if (len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest)
            or source.get("fileUid") != f"sha256:{digest}" or not policy.get("requestId")):
        return False
    if source.get("variable") is True or _face_variation(source).get("variable") is True:
        return False
    roles = policy.get("roles")
    if not isinstance(roles, dict) or set(roles) != {"cjk", "latin", "digit"}:
        return False
    for value in roles.values():
        if not isinstance(value, dict) or value.get("mode") != "fixed":
            return False
        axes = value.get("selectedAxes")
        if not isinstance(axes, dict) or any(_float(number) is None for number in axes.values()):
            return False
    return True


def _compile_requirements(
    role: str,
    slot: dict[str, Any],
    face: dict[str, Any],
    selection: dict[str, Any],
) -> tuple[str, list[str], list[str]]:
    requirements: list[str] = []
    risks: list[str] = []
    target_weight = float(selection["targetWeight"])
    style = _face_style(face)
    source_weight = _int(style.get("weight"), 400) or 400
    weight_mode = str(selection.get("weightMode") or "static")
    target_variable = _target_variable(slot)
    source_variable = _face_variation(face).get("variable") is True
    fixed_selection = is_fixed_composite_selection(face)

    if fixed_selection:
        requirements.append("fixed-composite-selection")

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
    elif source_weight != target_weight and not fixed_selection:
        risks.append("static-weight-fallback")

    if target_variable and not source_variable:
        risks.append("static-source-for-variable-target")
    if selection.get("italicMatch") is not True:
        risks.append("italic-style-mismatch")
    risks.extend(selection.get("styleAxisRisks") or [])

    requirements = sorted(set(requirements))
    risks = sorted(set(risks))
    if role in SPECIALIZED_ROLES:
        compiler = "specialized"
    elif requirements:
        compiler = "compatibility"
    else:
        compiler = "direct"
    return compiler, requirements, risks


def route_target(target: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    """Resolve a fresh source and safety contract for one exact XML reference.

    Candidate identities are part of FontPlan's hash. Both the router and the
    compiler recompute this mapping; physical-only targets retain their own
    contract and cannot borrow another route's successful selection.
    """
    # Avoid copying the entire shared reference graph into every route artifact.
    result = copy.deepcopy({key: value for key, value in target.items()
                            if key not in {"sourceCandidates", "xmlRefs"}})
    result["xmlRefs"] = [copy.deepcopy(node)]
    contract = result.setdefault("targetContract", {})
    axes = _route_axis_values(node.get("axes"))
    style = str(node.get("style") or "normal").lower()
    italic = style in {"italic", "oblique"}
    if "ital" in axes or "slnt" in axes:
        italic = axes.get("ital", 0) != 0 or axes.get("slnt", 0) != 0
    xml_weight = _int(node.get("weight"), 400) or 400
    contract.update({
        "weight": xml_weight,
        "italic": italic,
        "faceIndex": max(0, _int(node.get("index"), 0) or 0),
        "style": style,
        "axes": copy.deepcopy(node.get("axes") or []),
    })
    slot = {
        "slotName": target.get("slotName"),
        "metrics": contract.get("metrics", {}),
        "xmlRefs": [node],
    }
    raw_candidates = target.get("sourceCandidates")
    if not isinstance(raw_candidates, list):
        # Old plans can only recheck their frozen source, never invent one.
        raw_candidates = [target["source"]] if isinstance(target.get("source"), dict) else []
    faces = [_face_from_source_ref(source) for source in raw_candidates if isinstance(source, dict)]
    role = str(target.get("role") or "")
    face, selection = _select_face(
        faces, role, slot, target_weight=axes.get("wght", xml_weight),
        target_italic=italic, target_axes=axes,
    )
    result["selection"] = selection
    if face is None:
        result.update(action="blocked", status="blocked", compiler="none", source=None,
                      requirements=[], risks=sorted((selection.get("rejected") or {}).keys()),
                      reasons=["no-compatible-source-face"])
        return result
    compiler, requirements, risks = _compile_requirements(role, slot, face, selection)
    result.update(
        source=_source_ref(face), compiler=compiler, requirements=requirements, risks=risks,
        reasons=list(selection.get("roleReasons") or []),
        status="conditional" if risks else "ready",
        action=("compile-specialized" if role in SPECIALIZED_ROLES else
                "replace" if compiler == "direct" else "compile"),
    )
    return result


def _plan_slot(
    path: str,
    slot: dict[str, Any],
    role_info: dict[str, Any],
    faces: list[dict[str, Any]],
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
            **({"dynamicIdentity": copy.deepcopy(slot["dynamicIdentity"]),
                 "dynamicReferences": copy.deepcopy(_xml_refs(slot))}
               if isinstance(slot.get("dynamicIdentity"), dict) else {}),
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

    face, selection = _select_face(faces, role, slot)
    base["sourceCandidates"] = [
        _source_ref(candidate)
        for candidate in sorted(faces, key=lambda item: (
            str(item.get("uid") or ""), _int(item.get("faceIndex"), 0) or 0,
            str(item.get("_sourcePath") or ""),
        ))
        if _face_meets_role(candidate, role, slot)[0]
    ]
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
    if _int(topology.get("topologyRevision"), 0) != 3:
        raise UniversalPlanError("设备字体拓扑版本已过期，需要重新采集")
    if _int(roles.get("roleRevision"), 0) != 3:
        raise UniversalPlanError("字体角色版本已过期，需要重新分类")
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

    dynamic = runtime.get("dynamicFontsEvidence")
    dynamic_incomplete = isinstance(dynamic, dict) and dynamic.get("complete") is not True
    requirements: list[str] = []
    risks: list[str] = []
    if dynamic_incomplete:
        requirements.append("resolve-dynamic-font-discovery")
        risks.append("dynamic-font-discovery-incomplete")
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
        "dynamicDiscoveryComplete": not dynamic_incomplete,
        "dynamicUnresolvedCount": len(dynamic.get("unresolved") or []) if isinstance(dynamic, dict) else 0,
        "dataFontFileCount": data_font_files,
        "dataFontConfigReferenceCount": data_font_refs,
        "unresolvedXmlRefCount": unresolved_count,
        "missingRoleSlotCount": len(missing_role_slots),
    }


def build_plan(
    topology: dict[str, Any],
    roles: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    build_key, profile_id = _validate_inputs(topology, roles, profile)
    slots = _topology_slots(topology)
    role_slots = _role_slots(roles)
    faces = _source_faces(profile)

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
        targets[path] = _plan_slot(path, slots[path], role_info, faces)

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
        if role in SPECIALIZED_ROLES and action not in {"compile-specialized", "blocked"}:
            raise UniversalPlanError(f"Clock/Numeric 不得走普通替换：{path}")
        if role in TEXT_ROLES and action not in {"replace", "compile", "blocked"}:
            raise UniversalPlanError(f"文本目标包含无效动作：{path}")
        if role not in PROTECTED_ROLES | TEXT_ROLES | SPECIALIZED_ROLES | {"unknown-protected"}:
            if action != "preserve":
                raise UniversalPlanError(f"未知扩展角色不得自动替换：{path}")
        if action in {"replace", "compile", "compile-specialized"} and not isinstance(item.get("source"), dict):
            raise UniversalPlanError(f"替换目标缺少源 face：{path}")

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
            plan = build_plan(topology, roles, profile)
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
