#!/usr/bin/env python3
"""Build a per-device, per-slot alignment plan for LuoShu v2.2.

The planner is deliberately non-destructive. It combines a captured stock device
font template with one selected source font profile and emits the exact line-box
contract plus script-specific outline/baseline/advance transforms required for
future generated payloads.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Iterable

import device_font_template as template_engine

SCHEMA = "device-font-slot-plan-v1"
TEMPLATE_SCHEMA = "device-font-template-v1"

PROBE_ORDER = (
    "latinCap",
    "latinX",
    "latinDescender",
    "digits",
    "cjk",
    "punctuation",
)

ROLE_PROBES = {
    "clock": ("digits", "punctuation", "latinCap"),
    "mono": ("latinCap", "latinX", "latinDescender", "digits", "punctuation"),
    "display": ("latinCap", "latinX", "digits", "cjk", "punctuation"),
    "dynamic": PROBE_ORDER,
    "global-ui": PROBE_ORDER,
}

MAX_RELATIVE_SCALE_DELTA = 0.38
MAX_SHIFT_EM = 0.28
MAX_ADVANCE_DELTA = 0.42


class PlanError(RuntimeError):
    pass


def number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def integer(value: Any) -> int | None:
    parsed = number(value)
    return int(round(parsed)) if parsed is not None else None


def probe_names(roles: Iterable[str]) -> tuple[str, ...]:
    role_set = set(roles)
    selected: list[str] = []
    for role in ("clock", "mono", "display", "dynamic", "global-ui"):
        if role not in role_set:
            continue
        for name in ROLE_PROBES[role]:
            if name not in selected:
                selected.append(name)
    return tuple(selected or PROBE_ORDER)


def line_contract(metrics: dict[str, Any]) -> dict[str, int | None]:
    return {
        "unitsPerEm": integer(metrics.get("unitsPerEm")),
        "headYMin": integer(metrics.get("headYMin")),
        "headYMax": integer(metrics.get("headYMax")),
        "hheaAscent": integer(metrics.get("hheaAscent")),
        "hheaDescent": integer(metrics.get("hheaDescent")),
        "hheaLineGap": integer(metrics.get("hheaLineGap")),
        "typoAscender": integer(metrics.get("typoAscender")),
        "typoDescender": integer(metrics.get("typoDescender")),
        "typoLineGap": integer(metrics.get("typoLineGap")),
        "winAscent": integer(metrics.get("winAscent")),
        "winDescent": integer(metrics.get("winDescent")),
        "capHeight": integer(metrics.get("capHeight")),
        "xHeight": integer(metrics.get("xHeight")),
        "weightClass": integer(metrics.get("weightClass")),
        "widthClass": integer(metrics.get("widthClass")),
        "fsSelection": integer(metrics.get("fsSelection")),
    }


def probe_transform(
    target: dict[str, Any],
    source: dict[str, Any],
    source_upem: float,
    target_upem: float,
) -> dict[str, Any]:
    source_height = number(source.get("height"))
    target_height = number(target.get("height"))
    source_y_min = number(source.get("yMin"))
    source_y_max = number(source.get("yMax"))
    target_y_min = number(target.get("yMin"))
    target_y_max = number(target.get("yMax"))
    source_advance = number(source.get("advance"))
    target_advance = number(target.get("advance"))
    source_ink_width = number(source.get("inkWidth"))
    target_ink_width = number(target.get("inkWidth"))
    source_hits = integer(source.get("hits")) or 0
    target_hits = integer(target.get("hits")) or 0

    result: dict[str, Any] = {
        "sourceHits": source_hits,
        "targetHits": target_hits,
        "status": "missing",
    }
    if source_hits <= 0 or target_hits <= 0:
        return result
    if not source_height or source_height <= 0 or not target_height or target_height <= 0:
        return result
    if None in (source_y_min, source_y_max, target_y_min, target_y_max):
        return result

    upem_scale = target_upem / source_upem
    outline_scale_y = target_height / source_height
    relative_scale_y = outline_scale_y / upem_scale
    source_center = (source_y_min + source_y_max) / 2.0
    target_center = (target_y_min + target_y_max) / 2.0
    shift_y = target_center - source_center * outline_scale_y

    result.update(
        {
            "status": "ready",
            "upemScale": round(upem_scale, 8),
            "outlineScaleY": round(outline_scale_y, 8),
            "relativeScaleY": round(relative_scale_y, 8),
            "shiftY": round(shift_y, 4),
            "shiftYEm": round(shift_y / target_upem, 8),
            "targetYMin": round(target_y_min, 4),
            "targetYMax": round(target_y_max, 4),
            "targetHeight": round(target_height, 4),
        }
    )

    if source_advance and source_advance > 0 and target_advance and target_advance > 0:
        advance_scale = target_advance / source_advance
        relative_advance_scale = advance_scale / upem_scale
        result.update(
            {
                "sourceAdvance": round(source_advance, 4),
                "targetAdvance": round(target_advance, 4),
                "advanceScale": round(advance_scale, 8),
                "relativeAdvanceScale": round(relative_advance_scale, 8),
            }
        )
    else:
        relative_advance_scale = 1.0

    if source_ink_width and source_ink_width > 0 and target_ink_width and target_ink_width > 0:
        ink_scale_x = target_ink_width / source_ink_width
        result.update(
            {
                "outlineScaleXForExactInk": round(ink_scale_x, 8),
                "relativeInkScaleX": round(ink_scale_x / upem_scale, 8),
                "targetInkWidth": round(target_ink_width, 4),
            }
        )

    risks: list[str] = []
    if abs(relative_scale_y - 1.0) > MAX_RELATIVE_SCALE_DELTA:
        risks.append("vertical-scale")
    if abs(shift_y / target_upem) > MAX_SHIFT_EM:
        risks.append("vertical-shift")
    if abs(relative_advance_scale - 1.0) > MAX_ADVANCE_DELTA:
        risks.append("advance-width")
    result["risks"] = risks
    if risks:
        result["status"] = "unsafe"
    return result


def slot_plan(slot: dict[str, Any], source_profile: dict[str, Any]) -> dict[str, Any]:
    roles = list(slot.get("roles") or [])
    target_font = slot.get("font") if isinstance(slot.get("font"), dict) else {}
    target_metrics = target_font.get("metrics") if isinstance(target_font.get("metrics"), dict) else {}
    source_metrics = source_profile.get("metrics") if isinstance(source_profile.get("metrics"), dict) else {}
    target_upem = number(target_metrics.get("unitsPerEm"))
    source_upem = number(source_metrics.get("unitsPerEm"))

    result: dict[str, Any] = {
        "family": slot.get("family", ""),
        "familyNormalized": slot.get("familyNormalized", ""),
        "weight": integer(slot.get("weight")) or 400,
        "style": slot.get("style", "normal"),
        "index": integer(slot.get("index")) or 0,
        "axes": slot.get("axes", ""),
        "roles": roles,
        "sourceXml": slot.get("sourceXml", ""),
        "stockPath": slot.get("resolvedPath", ""),
        "stockFaceIndex": integer(target_font.get("faceIndex")),
        "replaceable": bool(slot.get("replaceable")),
        "status": "skipped",
        "lineContract": line_contract(target_metrics),
        "transforms": {},
    }
    if not result["replaceable"] or "protected" in roles or "fallback" in roles:
        result["reason"] = "protected-or-fallback"
        return result
    if not target_upem or target_upem <= 0:
        result["status"] = "unresolved"
        result["reason"] = "stock-metrics-missing"
        return result
    if not source_upem or source_upem <= 0:
        result["status"] = "unresolved"
        result["reason"] = "source-metrics-missing"
        return result

    target_probes = target_font.get("probes") if isinstance(target_font.get("probes"), dict) else {}
    source_probes = source_profile.get("probes") if isinstance(source_profile.get("probes"), dict) else {}
    unsafe: list[str] = []
    ready = 0
    for name in probe_names(roles):
        target = target_probes.get(name) if isinstance(target_probes.get(name), dict) else {}
        source = source_probes.get(name) if isinstance(source_probes.get(name), dict) else {}
        transform = probe_transform(target, source, source_upem, target_upem)
        result["transforms"][name] = transform
        if transform.get("status") in ("ready", "unsafe"):
            ready += 1
        if transform.get("status") == "unsafe":
            unsafe.append(name)

    result["upemScale"] = round(target_upem / source_upem, 8)
    result["targetAdvancePolicy"] = "fixed" if "mono" in roles else "stock-median"
    result["targetOutlinePolicy"] = "per-script-stock-ink-box"
    result["status"] = "ready" if ready else "unresolved"
    if unsafe:
        result["status"] = "unsafe"
        result["unsafeProbes"] = unsafe
    if not ready:
        result["reason"] = "no-shared-probes"
    return result


def build_plan(template: dict[str, Any], source_profile: dict[str, Any]) -> dict[str, Any]:
    if template.get("schema") != TEMPLATE_SCHEMA:
        raise PlanError(f"不支持的设备模板：{template.get('schema')!r}")
    source_metrics = source_profile.get("metrics") if isinstance(source_profile.get("metrics"), dict) else {}
    if not number(source_metrics.get("unitsPerEm")):
        raise PlanError("源字体缺少有效 unitsPerEm")

    plans = [slot_plan(slot, source_profile) for slot in template.get("slots", []) if isinstance(slot, dict)]
    summary = {
        "slots": len(plans),
        "ready": sum(1 for item in plans if item.get("status") == "ready"),
        "unsafe": sum(1 for item in plans if item.get("status") == "unsafe"),
        "unresolved": sum(1 for item in plans if item.get("status") == "unresolved"),
        "skipped": sum(1 for item in plans if item.get("status") == "skipped"),
    }
    return {
        "schema": SCHEMA,
        "templateSchema": TEMPLATE_SCHEMA,
        "deviceFingerprint": template.get("fingerprint", ""),
        "source": {
            "path": source_profile.get("path", ""),
            "faceIndex": integer(source_profile.get("faceIndex")),
            "sha256": source_profile.get("sha256", ""),
            "names": source_profile.get("names", []),
            "metrics": line_contract(source_metrics),
        },
        "limits": {
            "maxRelativeScaleDelta": MAX_RELATIVE_SCALE_DELTA,
            "maxShiftEm": MAX_SHIFT_EM,
            "maxAdvanceDelta": MAX_ADVANCE_DELTA,
        },
        "summary": summary,
        "slots": plans,
    }


def atomic_write(payload: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--source-index", type=int, default=-1)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        template = json.loads(args.template.read_text(encoding="utf-8"))
        source_profile = template_engine.inspect_font(
            args.source,
            args.source_index,
            hash_fonts=True,
        )
        payload = build_plan(template, source_profile)
        atomic_write(payload, args.output)
        print(json.dumps({"status": "ok", **payload["summary"], "output": str(args.output)}, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc) or exc.__class__.__name__}, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
