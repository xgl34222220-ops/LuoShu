#!/usr/bin/env python3
"""Verify that Android actually loaded a generated per-device font payload.

Generation success is not enough. This verifier combines visible mount evidence,
the payload/overlay manifests and FontManagerService's dump. It deliberately emits
`unverified` instead of pretending success when a ROM's dump format lacks evidence.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

PAYLOAD_SCHEMA = "device-font-payload-v1"
OVERLAY_SCHEMA = "device-font-overlay-v1"
SCHEMA = "device-font-load-verification-v1"


class VerifyError(RuntimeError):
    pass


def normalize(value: str) -> str:
    return re.sub(r"[\s_-]+", "-", str(value or "").strip().lower()).strip("-")


def safe_family(slot: dict[str, Any]) -> str:
    family = str(slot.get("familyNormalized") or slot.get("family") or "luoshu-slot")
    safe = "".join(char if char.isalnum() else "-" for char in family).strip("-") or "LuoShuSlot"
    weight = int(slot.get("weight") or 400)
    return f"luoshuslot-{safe.lower()}-{weight}"


def load_json(path: Path, schema: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != schema:
        raise VerifyError(f"不支持的清单：{path.name} schema={payload.get('schema')!r}")
    return payload


def load_mount_evidence(path: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if not path.is_file():
        return result
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw.strip():
            continue
        parts = raw.split("|", 5)
        if len(parts) != 6:
            continue
        rel, visible, status, expected_hash, actual_hash, size = parts
        result.append({
            "relative": rel,
            "visible": visible,
            "status": status,
            "expectedSha256": expected_hash,
            "actualSha256": actual_hash,
            "bytes": int(size) if size.isdigit() else 0,
        })
    return result


def dynamic_families(overlay: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for report in overlay.get("dynamic") or []:
        if not isinstance(report, dict):
            continue
        for family in report.get("removedFamilies") or []:
            value = normalize(str(family))
            if value and value not in result:
                result.append(value)
    return result


def verify(
    payload: dict[str, Any],
    overlay: dict[str, Any],
    font_dump: str,
    mounts: list[dict[str, Any]],
    active_font: str,
    engine: dict[str, str],
) -> dict[str, Any]:
    copied = overlay.get("copiedFonts") if isinstance(overlay.get("copiedFonts"), list) else []
    expected_paths = {
        str(item.get("path"))
        for item in copied
        if isinstance(item, dict) and str(item.get("path") or "")
    }
    mount_by_rel = {str(item.get("relative")): item for item in mounts}
    missing_mounts = sorted(path for path in expected_paths if path not in mount_by_rel)
    bad_mounts = sorted(
        path for path in expected_paths
        if path in mount_by_rel and mount_by_rel[path].get("status") != "ok"
    )

    generated_files = sorted({
        str(slot.get("generatedFile"))
        for slot in payload.get("slots") or []
        if isinstance(slot, dict) and slot.get("generatedFile")
    })
    slot_names = sorted({
        safe_family(slot)
        for slot in payload.get("slots") or []
        if isinstance(slot, dict) and slot.get("generatedFile")
    })
    dynamic = dynamic_families(overlay)
    dump_lower = font_dump.lower()
    file_hits = sorted(name for name in generated_files if name.lower() in dump_lower)
    slot_hits = sorted(name for name in slot_names if name in dump_lower)
    dynamic_hits = sorted(name for name in dynamic if name in normalize(dump_lower) or name in dump_lower.replace("_", "-"))
    dynamic_missing = sorted(set(dynamic) - set(dynamic_hits))

    reasons: list[str] = []
    state = "verified"
    if missing_mounts:
        state = "failed"
        reasons.append("visible-mount-evidence-missing")
    if bad_mounts:
        state = "failed"
        reasons.append("visible-font-hash-mismatch")
    if not font_dump.strip():
        if state != "failed":
            state = "unverified"
        reasons.append("font-manager-dump-unavailable")
    elif not file_hits and not slot_hits:
        if state != "failed":
            state = "unverified"
        reasons.append("generated-font-not-found-in-font-manager-dump")
    if dynamic_missing:
        state = "failed"
        reasons.append("dynamic-family-not-loaded")

    summary = overlay.get("summary") if isinstance(overlay.get("summary"), dict) else {}
    return {
        "schema": SCHEMA,
        "state": state,
        "mode": "aligned" if state == "verified" else "compatibility",
        "activeFont": active_font,
        "time": int(time.time()),
        "engine": engine,
        "summary": {
            "expectedVisibleFonts": len(expected_paths),
            "mountEvidence": len(mounts),
            "missingMounts": len(missing_mounts),
            "badMounts": len(bad_mounts),
            "generatedFiles": len(generated_files),
            "fontManagerFileHits": len(file_hits),
            "fontManagerSlotHits": len(slot_hits),
            "dynamicFamilies": len(dynamic),
            "dynamicFamilyHits": len(dynamic_hits),
            "mappedSlots": int(summary.get("mappedSlots") or 0),
        },
        "reasons": reasons,
        "missingMounts": missing_mounts,
        "badMounts": bad_mounts,
        "fontManagerFileHits": file_hits,
        "fontManagerSlotHits": slot_hits,
        "dynamicFamilies": dynamic,
        "dynamicFamilyHits": dynamic_hits,
        "dynamicFamilyMissing": dynamic_missing,
    }


def parse_engine(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key and value:
            result[key] = value
    return result


def atomic_write(payload: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(output)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", required=True, type=Path)
    parser.add_argument("--overlay", required=True, type=Path)
    parser.add_argument("--font-dump", required=True, type=Path)
    parser.add_argument("--mount-evidence", required=True, type=Path)
    parser.add_argument("--engine-state", required=True, type=Path)
    parser.add_argument("--active-font", default="unknown")
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = load_json(args.payload, PAYLOAD_SCHEMA)
        overlay = load_json(args.overlay, OVERLAY_SCHEMA)
        font_dump = args.font_dump.read_text(encoding="utf-8", errors="replace") if args.font_dump.is_file() else ""
        result = verify(
            payload,
            overlay,
            font_dump,
            load_mount_evidence(args.mount_evidence),
            args.active_font,
            parse_engine(args.engine_state),
        )
        atomic_write(result, args.output)
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0 if result["state"] == "verified" else 2
    except Exception as exc:
        result = {
            "schema": SCHEMA,
            "state": "failed",
            "mode": "compatibility",
            "activeFont": args.active_font,
            "time": int(time.time()),
            "reasons": ["verifier-error"],
            "message": str(exc) or exc.__class__.__name__,
        }
        try:
            atomic_write(result, args.output)
        except Exception:
            pass
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1


if __name__ == "__main__":
    import sys
    raise SystemExit(main())