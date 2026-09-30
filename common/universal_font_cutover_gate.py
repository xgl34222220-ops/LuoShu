#!/usr/bin/env python3
"""Phase 9 production cutover readiness gate.

The gate does not discover targets and does not mutate payloads. It validates the
frozen Phase 4-7 chain and decides whether the official switch path may stage the
Universal payload or must fall back to the legacy production switcher.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import minimal_xml_router
import universal_font_compiler
import universal_font_deployment
import universal_font_plan

SCHEMA = "universal-font-cutover-gate-v1"
ALLOWED_REPLACEMENT_ROLES = {"ui-sans", "cjk", "latin", "numeric", "clock"}
PROTECTED_ROLES = {"monospace", "serif", "emoji", "symbol-icon", "special-fallback"}


class GateError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GateError(f"cannot read JSON: {path}") from error
    if not isinstance(value, dict):
        raise GateError(f"invalid JSON root: {path}")
    return value


def evaluate(
    plan: dict[str, Any],
    route: dict[str, Any],
    artifacts: dict[str, Any],
    deployment: dict[str, Any],
    payload_root: Path | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    warnings: list[str] = []

    try:
        universal_font_plan.validate_plan(plan)
        minimal_xml_router.validate_route_plan(route, font_plan=plan)
        universal_font_compiler.validate_manifest(artifacts, plan, route)
        universal_font_deployment.validate_deployment(
            deployment, plan, route, artifacts, payload_root
        )
    except Exception as error:
        reasons.append(f"identity-or-integrity:{str(error) or error.__class__.__name__}")

    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    if int(summary.get("missingRoleSlotCount") or 0) != 0:
        reasons.append("missing-role-slots")

    targets = plan.get("targets") if isinstance(plan.get("targets"), dict) else {}
    replacement_count = 0
    role_counts: dict[str, int] = {}
    action_counts: dict[str, int] = {}
    for path, target in sorted(targets.items()):
        if not isinstance(target, dict):
            reasons.append(f"invalid-target:{path}")
            continue
        role = str(target.get("role") or "")
        action = str(target.get("action") or "")
        status = str(target.get("status") or "")
        role_counts[role or "unknown"] = role_counts.get(role or "unknown", 0) + 1
        action_counts[action or "unknown"] = action_counts.get(action or "unknown", 0) + 1

        if action == "blocked" or status == "blocked":
            reasons.append(f"blocked-target:{path}")
            continue
        if action in {"replace", "compile", "compile-specialized"}:
            replacement_count += 1
            if role not in ALLOWED_REPLACEMENT_ROLES:
                reasons.append(f"replacement-role-not-allowed:{role}:{path}")
        if role in PROTECTED_ROLES and action != "preserve":
            reasons.append(f"protected-role-not-preserved:{role}:{path}")
        if role == "unknown-protected" and action != "review":
            reasons.append(f"unknown-role-not-review:{path}")

    if replacement_count == 0:
        reasons.append("no-universal-replacement-targets")

    route_summary = route.get("summary") if isinstance(route.get("summary"), dict) else {}
    if route_summary.get("routingComplete") is not True:
        reasons.append("route-plan-incomplete")

    artifact_summary = artifacts.get("summary") if isinstance(artifacts.get("summary"), dict) else {}
    if int(artifact_summary.get("blockedCount") or 0) != 0:
        reasons.append("artifact-blocked")
    if artifact_summary.get("deploymentReady") is not True:
        reasons.append("artifact-deployment-not-ready")

    deployment_summary = deployment.get("summary") if isinstance(deployment.get("summary"), dict) else {}
    if deployment_summary.get("activationReady") is not True:
        reasons.append("deployment-not-activation-ready")
    if deployment_summary.get("executableNow") is not False:
        reasons.append("deployment-executable-contract-invalid")

    if deployment.get("backendNeutral") is not True:
        reasons.append("deployment-not-backend-neutral")

    constraints = plan.get("constraints") if isinstance(plan.get("constraints"), dict) else {}
    for risk in constraints.get("risks") or []:
        risk_text = str(risk)
        if risk_text in {"missing-role-evidence", "dynamic-font-discovery-incomplete"}:
            reasons.append(risk_text)
        elif risk_text and risk_text not in {
            "data-font-layer-active",
            "unresolved-xml-routes",
        }:
            warnings.append(f"plan-risk:{risk_text}")

    preserved_math = sum(int((item.get("report") or {}).get("transformed", {}).get("layout", {}).get("preservedMathGlyphs") or 0)
                         for item in artifacts.get("artifacts", []) if isinstance(item, dict))
    preserved_marks = sum(int((item.get("report") or {}).get("transformed", {}).get("layout", {}).get("preservedSharedMarks") or 0)
                          for item in artifacts.get("artifacts", []) if isinstance(item, dict))
    preserved_count = len(route.get("preservedRoutes") or [])
    if preserved_count:
        warnings.append(f"partial-coverage:preserved-original-style-routes:{preserved_count}")
    if preserved_math:
        warnings.append(f"partial-coverage:preserved-math-glyphs:{preserved_math}")
    if preserved_marks:
        warnings.append(f"partial-coverage:preserved-shared-marks:{preserved_marks}")
    eligible = not reasons
    return {
        "schema": SCHEMA,
        "eligible": eligible,
        "decision": "universal" if eligible else "legacy-fallback",
        "fontPlanId": str(plan.get("planId") or ""),
        "routeId": str(route.get("routeId") or ""),
        "artifactManifestId": str(artifacts.get("manifestId") or ""),
        "deploymentId": str(deployment.get("deploymentId") or ""),
        "payloadDigest": str(deployment.get("payloadDigest") or ""),
        "summary": {
            "slotCount": len(targets),
            "coverage": ("partial-protected-typography" if preserved_math or preserved_marks else
                         "partial-style-preserved" if preserved_count else "planned-targets"),
            "preservedSharedMarks": preserved_marks,
            "preservedMathGlyphs": preserved_math,
            "preservedStyleRouteCount": preserved_count,
            "replacementCount": replacement_count,
            "roleCounts": dict(sorted(role_counts.items())),
            "actionCounts": dict(sorted(action_counts.items())),
            "reasonCount": len(set(reasons)),
            "warningCount": len(set(warnings)),
        },
        "reasons": sorted(set(reasons)),
        "warnings": sorted(set(warnings)),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--font-plan", required=True, type=Path)
    parser.add_argument("--route-plan", required=True, type=Path)
    parser.add_argument("--artifact-manifest", required=True, type=Path)
    parser.add_argument("--deployment", required=True, type=Path)
    parser.add_argument("--payload-root", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = evaluate(
            _load(args.font_plan),
            _load(args.route_plan),
            _load(args.artifact_manifest),
            _load(args.deployment),
            args.payload_root,
        )
    except Exception as error:
        result = {
            "schema": SCHEMA,
            "eligible": False,
            "decision": "legacy-fallback",
            "summary": {"reasonCount": 1, "warningCount": 0},
            "reasons": [f"gate-error:{str(error) or error.__class__.__name__}"],
            "warnings": [],
        }
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if result.get("eligible") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
