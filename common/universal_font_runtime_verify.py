#!/usr/bin/env python3
"""Phase 8 runtime verifier for LuoShu universal font deployments.

This verifier never discovers or selects new font targets. It consumes the frozen
Phase 4 FontPlan, Phase 6 artifact manifest and Phase 7 deployment, then checks
whether Android is actually exposing the exact prepared payload after reboot.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from fontTools.ttLib import TTFont

def _canonical_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


SCHEMA = "universal-font-runtime-verification-v1"
REVISION = 1
PLAN_SCHEMA = "universal-font-plan-v1"
ARTIFACT_SCHEMA = "universal-font-artifacts-v1"
DEPLOYMENT_SCHEMA = "universal-font-deployment-v1"

PROBES = {
    "latin": tuple(ord(ch) for ch in "AaZz"),
    "digits": tuple(ord(ch) for ch in "0123456789"),
    "cjk": (0x4E00, 0x4E2D, 0x4EBA, 0x56FD),
}


class VerificationError(RuntimeError):
    pass


def _load(path: Path, schema: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise VerificationError(f"cannot read JSON: {path}") from error
    if not isinstance(value, dict) or value.get("schema") != schema:
        raise VerificationError(f"unexpected schema for {path.name}: {value.get('schema')!r}")
    return value


def _read_conf(path: Path | None) -> dict[str, str]:
    result: dict[str, str] = {}
    if path is None or not path.is_file():
        return result
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        if key:
            result[key] = value.strip()
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_frozen_contract(
    deployment: dict[str, Any],
    name: str,
    path: Path,
    id_key: str,
    actual_id: str,
) -> None:
    contracts = deployment.get("verificationContracts")
    if contracts is None:
        # Compatibility with a Phase 7 payload prepared before Phase 8 existed.
        return
    if not isinstance(contracts, dict):
        raise VerificationError("deployment verificationContracts invalid")
    contract = contracts.get(name)
    if not isinstance(contract, dict):
        raise VerificationError(f"deployment verification contract missing: {name}")
    if str(contract.get(id_key) or "") != actual_id:
        raise VerificationError(f"deployment verification contract identity mismatch: {name}")
    expected = str(contract.get("sha256") or "")
    if len(expected) != 64 or _sha256(path) != expected:
        raise VerificationError(f"deployment verification contract hash mismatch: {name}")


def _visible_path(logical: str, visible_root: Path | None) -> Path:
    if visible_root is None:
        return Path(logical)
    return visible_root / logical.lstrip("/")


def _mount_unescape(value: str) -> str:
    return (
        value.replace("\\040", " ")
        .replace("\\011", "\t")
        .replace("\\012", "\n")
        .replace("\\134", "\\")
    )


def _mounts(path: Path | None) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    if path is None or not path.is_file():
        return result
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = raw.split()
        if len(parts) < 10 or "-" not in parts:
            continue
        try:
            separator = parts.index("-")
            mount_point = _mount_unescape(parts[4])
            options = set(parts[5].split(","))
            super_options = set(parts[separator + 3].split(",")) if len(parts) > separator + 3 else set()
            result[mount_point] = {
                "root": _mount_unescape(parts[3]),
                "options": sorted(options),
                "superOptions": sorted(super_options),
                "fsType": parts[separator + 1] if len(parts) > separator + 1 else "",
                "source": _mount_unescape(parts[separator + 2]) if len(parts) > separator + 2 else "",
                "readOnly": "ro" in options or "ro" in super_options,
            }
        except (ValueError, IndexError):
            continue
    return result


def _artifact_index(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in manifest.get("artifacts") or []:
        if not isinstance(item, dict):
            continue
        artifact_id = str(item.get("artifactId") or "")
        if artifact_id:
            result[artifact_id] = item
    return result


def _target_index(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = plan.get("targets")
    if not isinstance(raw, dict):
        raise VerificationError("FontPlan targets missing")
    return {str(path): item for path, item in raw.items() if isinstance(item, dict)}


def _truthy_coverage(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "none", "missing", "unknown"}
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return False


def _coverage_requirements(target: dict[str, Any]) -> list[str]:
    role = str(target.get("role") or "")
    required: set[str] = set()
    if role in {"ui-sans", "latin"}:
        required.update({"latin", "digits"})
    elif role == "cjk":
        required.add("cjk")
    elif role in {"numeric", "clock"}:
        required.add("digits")

    contract = target.get("targetContract") if isinstance(target.get("targetContract"), dict) else {}
    coverage = contract.get("coverage") if isinstance(contract.get("coverage"), dict) else {}
    for key, value in coverage.items():
        if not _truthy_coverage(value):
            continue
        lowered = str(key).lower()
        if "cjk" in lowered or "han" in lowered:
            required.add("cjk")
        elif "latin" in lowered:
            required.add("latin")
        elif "digit" in lowered or "numeric" in lowered:
            required.add("digits")
    return sorted(required)


def _font_snapshot(path: Path, face_index: int) -> dict[str, Any]:
    try:
        font = TTFont(str(path), fontNumber=max(0, face_index), lazy=True, recalcTimestamp=False)
    except Exception as error:
        raise VerificationError(f"cannot parse font {path}: {error}") from error
    try:
        cmap = font.getBestCmap() or {}
        os2 = font["OS/2"] if "OS/2" in font else None
        head = font["head"] if "head" in font else None
        hhea = font["hhea"] if "hhea" in font else None
        names: set[str] = set()
        if "name" in font:
            for record in font["name"].names:
                try:
                    value = record.toUnicode().strip()
                except Exception:
                    continue
                if value:
                    names.add(value)
        axes: dict[str, dict[str, float]] = {}
        if "fvar" in font:
            for axis in font["fvar"].axes:
                axes[str(axis.axisTag)] = {
                    "min": float(axis.minValue),
                    "default": float(axis.defaultValue),
                    "max": float(axis.maxValue),
                }
        return {
            "codepoints": set(int(cp) for cp in cmap),
            "names": sorted(names),
            "axes": axes,
            "weight": int(getattr(os2, "usWeightClass", 400)) if os2 else 400,
            "italic": bool(int(getattr(os2, "fsSelection", 0)) & 1) if os2 else False,
            "metrics": {
                "unitsPerEm": int(getattr(head, "unitsPerEm", 0)) if head else 0,
                "headYMin": int(getattr(head, "yMin", 0)) if head else 0,
                "headYMax": int(getattr(head, "yMax", 0)) if head else 0,
                "hheaAscent": int(getattr(hhea, "ascent", 0)) if hhea else 0,
                "hheaDescent": int(getattr(hhea, "descent", 0)) if hhea else 0,
                "hheaLineGap": int(getattr(hhea, "lineGap", 0)) if hhea else 0,
            },
        }
    finally:
        font.close()


def _axis_value(entry: Any) -> tuple[str, float | None]:
    if not isinstance(entry, dict):
        return "", None
    tag = str(entry.get("tag") or "").strip()
    raw = entry.get("stylevalue")
    if raw in (None, ""):
        raw = entry.get("styleValue")
    if raw in (None, ""):
        raw = entry.get("value")
    try:
        value = float(raw) if raw not in (None, "") else None
    except (TypeError, ValueError):
        value = None
    return tag, value


def _font_manager_tokens(
    logical_path: str,
    artifact: dict[str, Any],
    target: dict[str, Any],
    snapshot: dict[str, Any],
) -> list[str]:
    if artifact.get("mode") == "fixed-static-xml-v1":
        binding = artifact.get("staticXmlContract") or {}
        return [value for value in [str(logical_path), Path(logical_path).name, str(binding.get("postScriptName") or "")] if len(value) >= 3]
    tokens: set[str] = {Path(logical_path).name}
    contract = artifact.get("contract") if isinstance(artifact.get("contract"), dict) else {}
    required_ps = str(contract.get("requiredPostScriptName") or "").strip()
    if required_ps:
        tokens.add(required_ps)
    for family in target.get("families") or []:
        value = str(family).strip()
        if value:
            tokens.add(value)
    for name in snapshot.get("names") or []:
        value = str(name).strip()
        if value.startswith("LuoShuUF") or value.startswith("LuoShu-UF"):
            tokens.add(value)
    return sorted(token for token in tokens if len(token) >= 3)


def _alignment_status(artifact: dict[str, Any]) -> tuple[str, list[str]]:
    report = artifact.get("report") if isinstance(artifact.get("report"), dict) else {}
    validation = report.get("validation") if isinstance(report.get("validation"), dict) else {}
    alignment = validation.get("alignment") if isinstance(validation.get("alignment"), dict) else {}
    status = str(alignment.get("status") or "")
    issues = [str(value) for value in alignment.get("issues") or []]
    return status, issues


def _assess_font(
    logical_path: str,
    visible: Path,
    artifact: dict[str, Any],
    target: dict[str, Any],
    expected_sha: str,
    font_dump_lower: str,
    failures: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    artifact_id = str(artifact.get("artifactId") or "")
    contract = artifact.get("contract") if isinstance(artifact.get("contract"), dict) else {}
    report: dict[str, Any] = {
        "logicalPath": logical_path,
        "visiblePath": str(visible),
        "artifactId": artifact_id,
        "targetPath": str(artifact.get("targetPath") or ""),
        "role": str(target.get("role") or artifact.get("role") or ""),
        "status": "ok",
    }
    if not visible.is_file():
        failures.append(f"visible-font-missing:{logical_path}")
        report["status"] = "missing"
        return report

    actual_sha = _sha256(visible)
    report["sha256"] = actual_sha
    if expected_sha and actual_sha != expected_sha:
        failures.append(f"visible-font-hash-mismatch:{logical_path}")
        report["status"] = "hash-mismatch"
        return report

    face_index = int(contract.get("requiredFaceIndex") or 0)
    try:
        snapshot = _font_snapshot(visible, face_index)
    except VerificationError as error:
        failures.append(f"visible-font-invalid:{logical_path}")
        report["status"] = "invalid-font"
        report["message"] = str(error)
        return report

    is_static_xml = artifact.get("mode") == "fixed-static-xml-v1"
    static_binding = artifact.get("staticXmlContract") or {}
    static_contract = artifact.get("report", {}).get("renderContract", {})
    coverage_report: dict[str, Any] = {}
    required_groups = _coverage_requirements(target)
    if is_static_xml:
        coverage = static_contract.get("coverage") or {}
        required_groups = ["digits" if value == "digit" else value for value in coverage.get("exposedRoles", [])]
        points = sorted(snapshot["codepoints"])
        if (coverage.get("codepointCount") != len(points)
                or coverage.get("codepointSha256") != _canonical_hash(points)):
            failures.append(f"static-coverage-seal-mismatch:{logical_path}")
        if (static_binding.get("postScriptName") not in snapshot["names"] or snapshot["axes"]
                or snapshot["italic"] or static_binding.get("fontItalic") is not False):
            failures.append(f"static-xml-metadata-mismatch:{logical_path}")
    for group in required_groups:
        probes = PROBES[group]
        shared = ((static_contract.get("geometry", {}).get("sharedProbePoints") or {}).get(group)
                  if is_static_xml else artifact.get("report", {}).get("geometry", {}).get("sharedProbePoints", {}).get(group))
        if group == "cjk" and shared is not None:
            import device_font_slot_build_base as slot_build
            if (not isinstance(shared, list) or not 4 <= len(shared) <= 64
                    or len(set(shared)) != len(shared)
                    or any(not isinstance(cp, int) or not slot_build.is_cjk(cp) for cp in shared)):
                failures.append(f"shared-cjk-probe-contract-invalid:{logical_path}")
            else:
                probes = shared
        hits = sum(cp in snapshot["codepoints"] for cp in probes)
        coverage_report[group] = {"hits": hits, "total": len(probes)}
        if hits == 0:
            failures.append(f"coverage-{group}-missing:{logical_path}")
        elif group == "digits" and hits != len(probes):
            # Numeric and clock contracts must never accept a partially covered
            # decimal set; one missing digit is enough to fall back at runtime.
            failures.append(f"coverage-digits-incomplete:{logical_path}")
        elif hits < len(probes):
            warnings.append(f"coverage-{group}-partial:{logical_path}")
    report["coverage"] = coverage_report

    axes = snapshot["axes"]
    required_axes = contract.get("requiredAxes") if isinstance(contract.get("requiredAxes"), list) else []
    for entry in required_axes:
        tag, value = _axis_value(entry)
        if not tag:
            continue
        axis = axes.get(tag)
        if axis is None:
            failures.append(f"required-axis-missing:{logical_path}:{tag}")
            continue
        if value is not None and not (axis["min"] <= value <= axis["max"]):
            failures.append(f"required-axis-out-of-range:{logical_path}:{tag}")

    variable_required = (not is_static_xml and (bool(required_axes) or str(artifact.get("mode") or "") == "source-variable-preserve"
                         or (bool(artifact.get("report", {}).get("fixedSelection"))
                             and target.get("targetContract", {}).get("variable") is True)))
    if variable_required and not axes:
        failures.append(f"variable-contract-missing:{logical_path}")

    required_weight = int(static_binding.get("fontWeight") if is_static_xml else
                          contract.get("requiredWeight") or target.get("targetContract", {}).get("weight") or 400)
    if "wght" in axes:
        axis = axes["wght"]
        if not (axis["min"] <= required_weight <= axis["max"]):
            failures.append(f"weight-axis-mismatch:{logical_path}")
    elif abs(int(snapshot["weight"]) - required_weight) > 1:
        failures.append(f"static-weight-mismatch:{logical_path}")

    alignment_status, alignment_issues = _alignment_status(artifact)
    report["alignment"] = {
        "status": alignment_status or "missing",
        "issues": alignment_issues,
    }
    if alignment_status and alignment_status != "ready":
        failures.append(f"baseline-bbox-risk:{logical_path}")
    elif not alignment_status:
        warnings.append(f"alignment-evidence-missing:{logical_path}")

    tokens = _font_manager_tokens(logical_path, artifact, target, snapshot)
    hits = [token for token in tokens if token.lower() in font_dump_lower]
    if is_static_xml:
        registered = set(re.findall(r"(?m)^\s*style\s*=\s*FontStyle\s*\{[^}]+\},\s*path\s*=\s*([^,\s]+)", font_dump_lower))
        hits = [logical_path] if logical_path.lower() in registered else []
    report["fontManagerTokens"] = tokens
    report["fontManagerHits"] = hits
    if is_static_xml and not hits:
        warnings.append(f"static-font-manager-path-unconfirmed:{logical_path}")
    return report


def verify(
    plan: dict[str, Any],
    artifacts: dict[str, Any],
    deployment: dict[str, Any],
    *,
    runtime_conf: dict[str, str],
    mount_state: dict[str, str],
    font_dump: str,
    mountinfo: dict[str, dict[str, Any]],
    active_font: str,
    visible_root: Path | None = None,
    boot_id: str = "",
    fixed_route: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if plan.get("schema") != PLAN_SCHEMA:
        raise VerificationError("FontPlan schema mismatch")
    if artifacts.get("schema") != ARTIFACT_SCHEMA:
        raise VerificationError("artifact manifest schema mismatch")
    if deployment.get("schema") != DEPLOYMENT_SCHEMA:
        raise VerificationError("deployment schema mismatch")
    if deployment.get("fontPlanId") != plan.get("planId"):
        raise VerificationError("deployment FontPlan identity mismatch")
    if artifacts.get("fontPlanId") != plan.get("planId"):
        raise VerificationError("artifact FontPlan identity mismatch")
    if deployment.get("artifactManifestId") != artifacts.get("manifestId"):
        raise VerificationError("deployment artifact identity mismatch")

    failures: list[str] = []
    warnings: list[str] = []
    artifact_by_id = _artifact_index(artifacts)
    target_by_path = _target_index(plan)
    originals = {}
    if "fixedStaticRoute" in (deployment.get("verificationContracts") or {}):
        import font_route_contract
        if fixed_route is None:
            raise VerificationError("frozen fixed-static route missing")
        font_route_contract.validate_route_plan(fixed_route)
        if fixed_route.get("routeId") != deployment.get("routeId") or fixed_route.get("fontPlanId") != plan.get("planId"):
            raise VerificationError("frozen fixed-static route identity mismatch")
        originals = fixed_route.get("retainedOriginals") or {}
        import universal_font_deployment as deployment_contract
        import universal_font_compiler as compiler_contract
        deployment_contract.validate_payload_integrity(deployment)
        if fixed_route.get("dynamicFontGeneration") != deployment["verificationContracts"]["fixedStaticRoute"].get("dynamicFontGeneration"):
            raise VerificationError("fixed-static dynamic generation differs from frozen route")
        deployment_contract.validate_dynamic_generation(deployment, visible_root)
        if artifacts.get("manifestId") != compiler_contract._manifest_id(plan["planId"], fixed_route["routeId"], artifacts["artifacts"], artifacts.get("deferredDynamicTargets") or []):
            raise VerificationError("frozen static artifact semantic identity mismatch")
        expected_static = {}; expected_original = {}
        bindings = artifacts.get("staticXmlBindings") or {}
        for document in fixed_route["documents"].values():
            for operation in document["operations"]:
                if operation["artifact"].get("representation") != "fixed-static-xml-v1": continue
                identity = operation["artifact"]["artifactId"]; binding = bindings.get(identity) or {}
                logical = operation["assetRoot"] + "/" + str(binding.get("fileName") or "")
                expected_static.setdefault(logical, set()).add(identity)
        for identity, original in originals.items():
            expected_original.setdefault(original["assetRoot"] + "/" + original["fileName"], set()).add(identity)
        actual_static = {f["logicalPath"]: set(f.get("artifactIds") or []) for f in deployment["files"] if f.get("kind") == "xml-static-font"}
        actual_original = {f["logicalPath"]: set(f.get("originalIds") or []) for f in deployment["files"] if f.get("kind") == "xml-original"}
        if expected_static != actual_static or expected_original != actual_original:
            raise VerificationError("fixed-static runtime route membership incomplete")
        warnings.append("fixed-static-consumer-proof-pending")

    deployment_id = str(deployment.get("deploymentId") or "")
    payload_digest = str(deployment.get("payloadDigest") or "")
    if runtime_conf:
        if runtime_conf.get("state") != "active":
            failures.append("runtime-state-not-active")
        if runtime_conf.get("deploymentId") != deployment_id:
            failures.append("runtime-deployment-id-mismatch")
        if runtime_conf.get("payloadDigest") != payload_digest:
            failures.append("runtime-payload-digest-mismatch")
    else:
        failures.append("runtime-state-missing")

    if mount_state:
        if mount_state.get("state") != "mounted":
            failures.append("mount-transaction-not-mounted")
        if mount_state.get("deploymentId") and mount_state.get("deploymentId") != deployment_id:
            failures.append("mount-deployment-id-mismatch")
        if mount_state.get("payloadDigest") and mount_state.get("payloadDigest") != payload_digest:
            failures.append("mount-payload-digest-mismatch")
    else:
        failures.append("mount-state-missing")

    font_dump_lower = font_dump.lower()
    file_reports: list[dict[str, Any]] = []
    font_reports: list[dict[str, Any]] = []
    font_manager_hits = 0
    font_file_count = 0

    for item in deployment.get("files") or []:
        if not isinstance(item, dict):
            continue
        logical = str(item.get("logicalPath") or "")
        if not logical:
            continue
        visible = _visible_path(logical, visible_root)
        expected_sha = str(item.get("sha256") or "")
        report = {
            "kind": str(item.get("kind") or ""),
            "logicalPath": logical,
            "visiblePath": str(visible),
            "status": "ok",
        }
        if not visible.is_file():
            failures.append(f"visible-file-missing:{logical}")
            report["status"] = "missing"
            file_reports.append(report)
            continue
        actual_sha = _sha256(visible)
        report["sha256"] = actual_sha
        if expected_sha and actual_sha != expected_sha:
            failures.append(f"visible-file-hash-mismatch:{logical}")
            report["status"] = "hash-mismatch"
            file_reports.append(report)
            continue
        file_reports.append(report)

        if str(item.get("kind") or "") == "xml":
            continue
        font_file_count += 1
        if item.get("kind") == "xml-original":
            ids = item.get("originalIds") or []
            if not ids: failures.append(f"retained-original-contract-missing:{logical}")
            for identity in ids:
                original = originals.get(identity) or {}
                if (original.get("sha256") != expected_sha or
                        original.get("assetRoot", "") + "/" + original.get("fileName", "") != logical):
                    failures.append(f"retained-original-identity-mismatch:{logical}")
                    continue
                try: _font_snapshot(visible, int(original["faceIndex"]))
                except (VerificationError, KeyError): failures.append(f"retained-original-face-invalid:{logical}")
            registered = set(re.findall(r"(?m)^\s*style\s*=\s*FontStyle\s*\{[^}]+\},\s*path\s*=\s*([^,\s]+)", font_dump_lower))
            if logical.lower() in registered: font_manager_hits += 1
            else: warnings.append(f"retained-original-path-unconfirmed:{logical}")
            continue
        ids = item.get("artifactIds") if item.get("kind") == "xml-static-font" else [str(item.get("artifactId") or "")]
        if not isinstance(ids, list) or not ids:
            failures.append(f"static-route-artifacts-missing:{logical}")
            continue
        any_hit = False
        for artifact_id in ids:
            artifact = artifact_by_id.get(artifact_id)
            if artifact is None:
                failures.append(f"artifact-missing:{artifact_id or logical}")
                continue
            if item.get("kind") == "xml-static-font" and artifact.get("sha256") != expected_sha:
                failures.append(f"static-route-file-digest-mismatch:{logical}")
                continue
            if item.get("kind") == "xml-static-font" and artifact.get("mode") != "fixed-static-xml-v1":
                failures.append(f"static-artifact-representation-mismatch:{logical}")
                continue
            target_path = str(artifact.get("targetPath") or "")
            target = target_by_path.get(target_path)
            if target is None:
                failures.append(f"fontplan-target-missing:{target_path or logical}")
                continue
            font_report = _assess_font(logical, visible, artifact, target, expected_sha,
                                       font_dump_lower, failures, warnings)
            font_reports.append(font_report)
            any_hit = any_hit or bool(font_report.get("fontManagerHits"))
        if any_hit: font_manager_hits += 1

    dynamic_reports: list[dict[str, Any]] = []
    for item in deployment.get("dynamicMounts") or []:
        if not isinstance(item, dict):
            continue
        target_path = str(item.get("targetPath") or "")
        artifact_id = str(item.get("artifactId") or "")
        expected_sha = str(item.get("sha256") or "")
        visible = _visible_path(target_path, visible_root)
        mount_key = str(visible) if visible_root is not None else target_path
        # Phase 7 resolves symlinked /data/fonts targets before bind-mounting.
        # Match both the logical path and the same real path to avoid a false
        # missing-mount result on OEM layouts that use symlinks.
        real_mount_key = os.path.realpath(mount_key)
        mount = (
            mountinfo.get(mount_key)
            or mountinfo.get(real_mount_key)
            or mountinfo.get(target_path)
            or mountinfo.get(os.path.realpath(target_path))
        )
        dynamic_report: dict[str, Any] = {
            "targetPath": target_path,
            "visiblePath": str(visible),
            "artifactId": artifact_id,
            "mounted": mount is not None,
            "readOnly": bool(mount and mount.get("readOnly")),
            "status": "ok",
        }
        if mount is None:
            failures.append(f"dynamic-mount-missing:{target_path}")
            dynamic_report["status"] = "mount-missing"
        elif not mount.get("readOnly"):
            failures.append(f"dynamic-mount-not-readonly:{target_path}")
            dynamic_report["status"] = "mount-not-readonly"

        artifact = artifact_by_id.get(artifact_id)
        if artifact is None:
            failures.append(f"artifact-missing:{artifact_id or target_path}")
            dynamic_reports.append(dynamic_report)
            continue
        target = target_by_path.get(str(artifact.get("targetPath") or ""))
        if target is None:
            failures.append(f"fontplan-target-missing:{target_path}")
            dynamic_reports.append(dynamic_report)
            continue
        font_report = _assess_font(
            target_path, visible, artifact, target, expected_sha,
            font_dump_lower, failures, warnings,
        )
        dynamic_report["font"] = font_report
        if font_report.get("fontManagerHits"):
            font_manager_hits += 1
        dynamic_reports.append(dynamic_report)
        font_file_count += 1

    expected_dynamic = len(deployment.get("dynamicMounts") or [])
    try:
        mounted_dynamic = int(mount_state.get("dynamicMounted") or 0)
    except ValueError:
        mounted_dynamic = 0
    if expected_dynamic and mounted_dynamic < expected_dynamic:
        failures.append("dynamic-mount-count-incomplete")

    if not font_dump.strip():
        warnings.append("font-manager-dump-unavailable")
    elif font_file_count and font_manager_hits == 0:
        warnings.append("font-manager-artifact-unconfirmed")
    elif font_manager_hits < font_file_count:
        warnings.append("font-manager-partial-confirmation")

    compile_alignment_missing = sum(
        1 for report in font_reports
        if report.get("alignment", {}).get("status") == "missing"
    )
    critical = sorted(set(failures))
    caution = sorted(set(warnings) - set(critical))
    grade = "FAIL" if critical else ("WARN" if caution else "PASS")
    reason = critical[0] if critical else (caution[0] if caution else "runtime-verified")

    return {
        "schema": SCHEMA,
        "verificationRevision": REVISION,
        "grade": grade,
        "state": grade.lower(),
        "mode": "universal-runtime",
        "activeFont": active_font,
        "deploymentId": deployment_id,
        "payloadDigest": payload_digest,
        "bootId": boot_id,
        "time": int(time.time()),
        "reason": reason,
        "summary": {
            "deploymentFiles": len(deployment.get("files") or []),
            "fontFiles": font_file_count,
            "dynamicTargets": expected_dynamic,
            "dynamicMounted": mounted_dynamic,
            "fontManagerHits": font_manager_hits,
            "fontManagerAvailable": bool(font_dump.strip()),
            "alignmentEvidenceMissing": compile_alignment_missing,
            "failureCount": len(critical),
            "warningCount": len(caution),
        },
        "failures": critical,
        "warnings": caution,
        "files": file_reports,
        "fonts": font_reports,
        "dynamic": dynamic_reports,
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _write_conf(path: Path, result: dict[str, Any]) -> None:
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    lines = [
        f"schema={result.get('schema', SCHEMA)}",
        f"grade={result.get('grade', 'FAIL')}",
        f"state={result.get('state', 'fail')}",
        f"mode={result.get('mode', 'universal-runtime')}",
        f"reason={result.get('reason', 'verifier-error')}",
        f"activeFont={result.get('activeFont', '')}",
        f"deploymentId={result.get('deploymentId', '')}",
        f"payloadDigest={result.get('payloadDigest', '')}",
        f"bootId={result.get('bootId', '')}",
        f"fontFiles={summary.get('fontFiles', 0)}",
        f"dynamicTargets={summary.get('dynamicTargets', 0)}",
        f"dynamicMounted={summary.get('dynamicMounted', 0)}",
        f"fontManagerHits={summary.get('fontManagerHits', 0)}",
        f"failureCount={summary.get('failureCount', 0)}",
        f"warningCount={summary.get('warningCount', 0)}",
        f"time={result.get('time', int(time.time()))}",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o644)
    os.replace(temporary, path)


def _error_result(active_font: str, boot_id: str, message: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "verificationRevision": REVISION,
        "grade": "FAIL",
        "state": "fail",
        "mode": "universal-runtime",
        "activeFont": active_font,
        "deploymentId": "",
        "payloadDigest": "",
        "bootId": boot_id,
        "time": int(time.time()),
        "reason": "verifier-error",
        "summary": {
            "deploymentFiles": 0,
            "fontFiles": 0,
            "dynamicTargets": 0,
            "dynamicMounted": 0,
            "fontManagerHits": 0,
            "fontManagerAvailable": False,
            "alignmentEvidenceMissing": 0,
            "failureCount": 1,
            "warningCount": 0,
        },
        "failures": ["verifier-error"],
        "warnings": [],
        "message": message,
        "files": [],
        "fonts": [],
        "dynamic": [],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--font-plan", required=True, type=Path)
    parser.add_argument("--artifact-manifest", required=True, type=Path)
    parser.add_argument("--deployment", required=True, type=Path)
    parser.add_argument("--runtime-conf", type=Path)
    parser.add_argument("--mount-state", type=Path)
    parser.add_argument("--font-dump", type=Path)
    parser.add_argument("--mountinfo", type=Path)
    parser.add_argument("--visible-root", type=Path)
    parser.add_argument("--active-font", default="")
    parser.add_argument("--boot-id", default="")
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-conf", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        plan = _load(args.font_plan, PLAN_SCHEMA)
        artifacts = _load(args.artifact_manifest, ARTIFACT_SCHEMA)
        deployment = _load(args.deployment, DEPLOYMENT_SCHEMA)
        _validate_frozen_contract(
            deployment, "fontPlan", args.font_plan, "planId", str(plan.get("planId") or "")
        )
        _validate_frozen_contract(
            deployment,
            "artifactManifest",
            args.artifact_manifest,
            "manifestId",
            str(artifacts.get("manifestId") or ""),
        )
        fixed_route = None
        if "fixedStaticRoute" in (deployment.get("verificationContracts") or {}):
            route_path = args.deployment.parent / "fixed-static-route-plan.json"
            fixed_route = _load(route_path, "fixed-static-xml-route-plan-v1")
            _validate_frozen_contract(deployment, "fixedStaticRoute", route_path, "routeId", fixed_route["routeId"])
        font_dump = (
            args.font_dump.read_text(encoding="utf-8", errors="replace")
            if args.font_dump and args.font_dump.is_file()
            else ""
        )
        result = verify(
            plan,
            artifacts,
            deployment,
            runtime_conf=_read_conf(args.runtime_conf),
            mount_state=_read_conf(args.mount_state),
            font_dump=font_dump,
            mountinfo=_mounts(args.mountinfo),
            active_font=args.active_font,
            visible_root=args.visible_root,
            boot_id=args.boot_id, fixed_route=fixed_route,
        )
    except Exception as error:
        result = _error_result(args.active_font, args.boot_id, str(error) or error.__class__.__name__)

    _atomic_json(args.output_json, result)
    _write_conf(args.output_conf, result)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    if result["grade"] == "PASS":
        return 0
    if result["grade"] == "WARN":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
