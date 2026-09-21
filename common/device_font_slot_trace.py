#!/usr/bin/env python3
"""Join scan, build, mapping and boot evidence into one per-inventory-slot trace."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

SCHEMA = "device-font-slot-trace-v1"
INVENTORY_SCHEMA = "device-font-inventory-v1"
PAYLOAD_SCHEMA = "device-font-payload-v1"
OVERLAY_SCHEMA = "device-font-overlay-v1"
VERIFY_SCHEMA = "device-font-load-verification-v1"
CANDIDATE_SCHEMA = "device-font-candidates-v1"


class TraceError(RuntimeError):
    pass


def load(path: Path, schema: str, *, optional: bool = False) -> dict[str, Any]:
    if optional and not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise TraceError(f"无法读取 {path.name}：{exc}") from exc
    if not isinstance(value, dict) or value.get("schema") != schema:
        raise TraceError(f"{path.name} 格式无效：{value.get('schema') if isinstance(value, dict) else 'not-object'}")
    return value


def normalize_path(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    path = Path(text)
    return str(path) if path.is_absolute() else "/" + str(path).lstrip("/")


def index_payload(payload: dict[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    by_inventory: dict[str, list[dict[str, Any]]] = defaultdict(list)
    orphan: list[dict[str, Any]] = []
    for raw in payload.get("slots") or []:
        if not isinstance(raw, dict):
            continue
        slot = dict(raw)
        logical = normalize_path(slot.get("inventoryPath") or slot.get("stockPath"))
        if logical:
            by_inventory[logical].append(slot)
        else:
            orphan.append(slot)
    return by_inventory, orphan


def index_results(document: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    result: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for raw in document.get("slotResults") or []:
        if not isinstance(raw, dict):
            continue
        try:
            index = int(raw.get("slotIndex"))
        except (TypeError, ValueError):
            continue
        result[index].append(dict(raw))
    return result


def index_supplement(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    supplement = payload.get("inventorySupplement")
    if not isinstance(supplement, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for raw in supplement.get("slots") or []:
        if not isinstance(raw, dict):
            continue
        path = normalize_path(raw.get("path"))
        if path:
            result[path] = dict(raw)
    return result


def route_state(
    slot: dict[str, Any],
    overlay_results: dict[int, list[dict[str, Any]]],
    verify_results: dict[int, list[dict[str, Any]]],
    verification_present: bool,
) -> dict[str, Any]:
    try:
        index = int(slot.get("slotIndex"))
    except (TypeError, ValueError):
        index = -1
    record: dict[str, Any] = {
        "slotIndex": index,
        "family": str(slot.get("family") or ""),
        "weight": int(slot.get("weight") or 400),
        "style": str(slot.get("style") or "normal"),
        "sourceXml": str(slot.get("sourceXml") or ""),
        "planStatus": str(slot.get("planStatus") or "unresolved"),
        "planReason": str(slot.get("planReason") or ""),
        "generatedFile": str(slot.get("generatedFile") or ""),
        "directPhysical": bool(slot.get("directPhysical")),
    }
    if not record["generatedFile"]:
        record.update(
            state="preserved",
            reason=record["planReason"] or record["planStatus"] or "not-generated",
            route="stock",
            targetPath="",
        )
        return record

    mapped = overlay_results.get(index, [])
    if not mapped:
        record.update(state="mapping-missing", reason="generated-slot-not-in-overlay", route="", targetPath="")
        return record

    # A successful overlay emits one result per payload slot. Keep all evidence if
    # an old/diagnostic manifest happens to contain more than one.
    overlay = mapped[0]
    record["route"] = str(overlay.get("route") or "")
    record["targetPath"] = str(overlay.get("targetPath") or "")
    if overlay.get("state") != "mapped":
        record.update(state="mapping-missing", reason=str(overlay.get("reason") or "overlay-not-mapped"))
        return record

    if not verification_present:
        record.update(state="mapped-unverified", reason="boot-verification-not-available")
        return record

    verified = verify_results.get(index, [])
    if not verified:
        record.update(state="unconfirmed", reason="slot-runtime-evidence-missing")
        return record
    runtime = verified[0]
    load_state = str(runtime.get("loadState") or "unconfirmed")
    record["fontManagerConfirmed"] = bool(runtime.get("fontManagerConfirmed"))
    record["mountStatus"] = str(runtime.get("mountStatus") or "")
    record["state"] = load_state
    if load_state == "missing-mount":
        record["reason"] = "visible-mount-evidence-missing"
    elif load_state == "mismatch":
        record["reason"] = "visible-font-hash-mismatch"
    elif load_state == "mount-visible":
        record["reason"] = "visible-bytes-match-font-manager-unconfirmed"
    elif load_state == "loaded":
        record["reason"] = "visible-bytes-and-font-manager-confirmed"
    else:
        record["reason"] = str(runtime.get("reason") or load_state)
    return record


def aggregate(routes: list[dict[str, Any]], supplement: dict[str, Any] | None) -> tuple[str, str]:
    if not routes:
        if supplement and supplement.get("disposition") == "preserved":
            return "preserved", str(supplement.get("reason") or "inventory-preserved")
        return "not-consumed", "inventory-slot-not-present-in-payload"

    states = [str(item.get("state") or "unconfirmed") for item in routes]
    unique = set(states)
    if len(unique) == 1:
        state = states[0]
        reasons = [str(item.get("reason") or "") for item in routes if item.get("reason")]
        return state, reasons[0] if reasons else ""

    good = {"loaded", "mount-visible", "mapped-unverified"}
    bad = {"mapping-missing", "missing-mount", "mismatch", "unconfirmed", "not-consumed"}
    if unique & good and unique & bad:
        return "partial", ",".join(sorted(unique))
    if "mismatch" in unique:
        return "mismatch", ",".join(sorted(unique))
    if "missing-mount" in unique:
        return "missing-mount", ",".join(sorted(unique))
    if "mapping-missing" in unique:
        return "mapping-missing", ",".join(sorted(unique))
    if "unconfirmed" in unique:
        return "unconfirmed", ",".join(sorted(unique))
    if "mount-visible" in unique:
        return "mount-visible", ",".join(sorted(unique))
    if "loaded" in unique:
        return "loaded", ",".join(sorted(unique))
    if unique == {"preserved"}:
        return "preserved", ""
    return "partial", ",".join(sorted(unique))


def classify_slot_state(state: str, reason: str) -> tuple[str, bool]:
    if state == "loaded":
        return "replaced", False
    if state in {"mount-visible", "mapped-unverified", "unconfirmed"}:
        return "pending", False
    if state == "preserved":
        return "protected", False
    if state in {"mapping-missing", "missing-mount", "mismatch", "partial", "not-consumed"}:
        return "issue", True
    return "issue", False


def _candidate_index(candidates: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for raw in candidates.get("paths") or []:
        if not isinstance(raw, dict):
            continue
        logical = normalize_path(raw.get("path"))
        if logical:
            result[logical] = dict(raw)
    return result


def _physical_protection_reason(
    logical: str,
    candidate: dict[str, Any] | None,
) -> str:
    suffix = Path(logical).suffix.lower()
    if suffix in {".ttc", ".otc"}:
        return "preserved-collection"
    if candidate is not None and not bool(candidate.get("candidate", False)):
        return str(candidate.get("reason") or "scanner-protected")
    name = Path(logical).name.lower()
    if any(token in name for token in ("emoji", "icon", "icons", "math", "music", "symbol")):
        return "specialized-name"
    return ""


def build_physical_trace(
    inventory: dict[str, Any],
    physical_root: Path,
    candidates: dict[str, Any] | None = None,
    *,
    confirmed: bool = False,
    active_font: str = "",
) -> dict[str, Any]:
    """Trace the actual physical-safe payload used by current LuoShu releases.

    The foreground switcher commits .luoshu-payload-next and the next boot promotes
    it to .luoshu-payload. That path is authoritative even when the older v2
    device-font manifest/cache files do not exist.
    """
    if inventory.get("schema") != INVENTORY_SCHEMA:
        raise TraceError("inventory schema 无效")
    candidates = candidates or {}
    if candidates and candidates.get("schema") != CANDIDATE_SCHEMA:
        raise TraceError("candidates schema 无效")
    if not physical_root.is_dir():
        raise TraceError("当前物理字体负载不存在")

    candidate_by_path = _candidate_index(candidates)
    traced: list[dict[str, Any]] = []
    counts: dict[str, int] = defaultdict(int)

    for logical, raw_entry in sorted((inventory.get("slots") or {}).items()):
        if not isinstance(raw_entry, dict):
            continue
        entry = dict(raw_entry)
        logical = normalize_path(logical)
        relative = logical.lstrip("/")
        physical = physical_root / relative
        candidate = candidate_by_path.get(logical)
        protected_reason = _physical_protection_reason(logical, candidate)

        routes: list[dict[str, Any]] = []
        if physical.is_file():
            state = "loaded" if confirmed else "mapped-unverified"
            reason = (
                "active-physical-payload-confirmed"
                if confirmed
                else "active-physical-payload-awaiting-mount-confirmation"
            )
            category, safe_to_retry = classify_slot_state(state, reason)
            routes.append({
                "slotIndex": -1,
                "family": str((entry.get("families") or [""])[0] if (entry.get("families") or []) else ""),
                "weight": int(entry.get("weight") or 400),
                "style": str(entry.get("style") or "normal"),
                "sourceXml": "",
                "planStatus": "ready",
                "planReason": "physical-safe-current-payload",
                "generatedFile": physical.name,
                "directPhysical": True,
                "state": state,
                "reason": reason,
                "route": "physical-safe",
                "targetPath": relative,
            })
        elif protected_reason:
            state = "preserved"
            reason = protected_reason
            category, safe_to_retry = "protected", False
        else:
            state = "mapping-missing"
            reason = "active-physical-payload-missing-slot"
            category, safe_to_retry = "issue", True

        traced.append({
            "path": logical,
            "slotName": str(entry.get("slotName") or Path(logical).name),
            "partition": str(entry.get("partition") or ""),
            "source": str(entry.get("source") or ""),
            "format": str(entry.get("format") or entry.get("validatedFormat") or ""),
            "weight": int(entry.get("weight") or 400),
            "style": str(entry.get("style") or "normal"),
            "families": list(entry.get("families") or []),
            "state": state,
            "category": category,
            "safeToRetry": safe_to_retry,
            "reason": reason,
            "supplementDisposition": "physical-safe",
            "routes": routes,
        })
        counts[state] += 1

    inventory_paths = {normalize_path(path) for path in (inventory.get("slots") or {})}
    for raw in candidates.get("paths") or []:
        if not isinstance(raw, dict):
            continue
        logical = normalize_path(raw.get("path"))
        if not logical or logical in inventory_paths:
            continue
        reason = str(raw.get("reason") or "census-only")
        if bool(raw.get("candidate", False)) and reason == "visible-font-path":
            reason = "not-promoted-to-ui-inventory"
        traced.append({
            "path": logical,
            "slotName": str(raw.get("slotName") or Path(logical).name),
            "partition": str(raw.get("partition") or ""),
            "source": "census",
            "format": Path(logical).suffix.lower().lstrip(".").upper(),
            "weight": 400,
            "style": "normal",
            "families": [],
            "state": "protected",
            "category": "protected",
            "safeToRetry": False,
            "reason": reason,
            "supplementDisposition": "census-only",
            "routes": [],
        })

    category_counts: dict[str, int] = defaultdict(int)
    remediable = 0
    for item in traced:
        category_counts[str(item.get("category") or "issue")] += 1
        if bool(item.get("safeToRetry")):
            remediable += 1

    eligible = (
        category_counts.get("replaced", 0)
        + category_counts.get("pending", 0)
        + category_counts.get("issue", 0)
    )
    return {
        "schema": SCHEMA,
        "inventoryBuildKey": str(inventory.get("buildKey") or ""),
        "inventoryRomKind": str(inventory.get("romKind") or "generic"),
        "verificationState": "verified" if confirmed else "pending",
        "activeFont": active_font,
        "traceSource": "physical-safe",
        "summary": {
            "inventorySlots": len(inventory.get("slots") or {}),
            "censusSlots": len(traced),
            "replaceableSlots": eligible,
            "replaced": category_counts.get("replaced", 0),
            "pending": category_counts.get("pending", 0),
            "protected": category_counts.get("protected", 0),
            "issues": category_counts.get("issue", 0),
            "remediable": remediable,
            "consumed": sum(1 for item in traced if item["routes"]),
            "notConsumed": 0,
            "preserved": counts.get("preserved", 0),
            "mappedUnverified": counts.get("mapped-unverified", 0),
            "loaded": counts.get("loaded", 0),
            "mountVisible": 0,
            "mappingMissing": counts.get("mapping-missing", 0),
            "missingMount": 0,
            "mismatch": 0,
            "unconfirmed": 0,
            "partial": 0,
            "templateOnlyRoutes": 0,
        },
        "slots": traced,
        "templateOnlyRoutes": [],
    }


def build_trace(
    inventory: dict[str, Any],
    payload: dict[str, Any],
    overlay: dict[str, Any],
    verification: dict[str, Any] | None = None,
    candidates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if inventory.get("schema") != INVENTORY_SCHEMA:
        raise TraceError("inventory schema 无效")
    if payload.get("schema") != PAYLOAD_SCHEMA:
        raise TraceError("payload schema 无效")
    if overlay.get("schema") != OVERLAY_SCHEMA:
        raise TraceError("overlay schema 无效")
    verification = verification or {}
    if verification and verification.get("schema") != VERIFY_SCHEMA:
        raise TraceError("verification schema 无效")
    candidates = candidates or {}
    if candidates and candidates.get("schema") != CANDIDATE_SCHEMA:
        raise TraceError("candidates schema 无效")

    payload_by_path, orphan = index_payload(payload)
    supplement = index_supplement(payload)
    overlay_results = index_results(overlay)
    verify_results = index_results(verification)
    verification_present = bool(verification)

    traced: list[dict[str, Any]] = []
    counts: dict[str, int] = defaultdict(int)
    for logical, entry in sorted((inventory.get("slots") or {}).items()):
        if not isinstance(entry, dict):
            continue
        routes = [
            route_state(slot, overlay_results, verify_results, verification_present)
            for slot in payload_by_path.get(normalize_path(logical), [])
        ]
        supplement_record = supplement.get(normalize_path(logical))
        state, reason = aggregate(routes, supplement_record)
        category, safe_to_retry = classify_slot_state(state, reason)
        item = {
            "path": logical,
            "slotName": str(entry.get("slotName") or Path(logical).name),
            "partition": str(entry.get("partition") or ""),
            "source": str(entry.get("source") or ""),
            "format": str(entry.get("format") or entry.get("validatedFormat") or ""),
            "weight": int(entry.get("weight") or 400),
            "style": str(entry.get("style") or "normal"),
            "families": list(entry.get("families") or []),
            "state": state,
            "category": category,
            "safeToRetry": safe_to_retry,
            "reason": reason,
            "supplementDisposition": str((supplement_record or {}).get("disposition") or ""),
            "routes": routes,
        }
        traced.append(item)
        counts[state] += 1

    # Candidate census can be wider than the replaceable UI inventory. Surface
    # every census-only font explicitly as protected/unmanaged instead of hiding it
    # from the App. This keeps "scanned" and "replaceable" counts separate.
    inventory_paths = {normalize_path(path) for path in (inventory.get("slots") or {})}
    for raw in candidates.get("paths") or []:
        if not isinstance(raw, dict):
            continue
        logical = normalize_path(raw.get("path"))
        if not logical or logical in inventory_paths:
            continue
        denied = not bool(raw.get("candidate", False))
        reason = str(raw.get("reason") or ("specialized-name" if denied else "not-promoted-to-ui-inventory"))
        if not denied and reason == "visible-font-path":
            reason = "not-promoted-to-ui-inventory"
        traced.append({
            "path": logical,
            "slotName": str(raw.get("slotName") or Path(logical).name),
            "partition": str(raw.get("partition") or ""),
            "source": "census",
            "format": Path(logical).suffix.lower().lstrip(".").upper(),
            "weight": 400,
            "style": "normal",
            "families": [],
            "state": "protected",
            "category": "protected",
            "safeToRetry": False,
            "reason": reason,
            "supplementDisposition": "census-only",
            "routes": [],
        })

    # Template-only routes are useful diagnostics but are not counted as scanner
    # omissions because the inventory deliberately works at physical-file level.
    orphan_routes = [
        route_state(slot, overlay_results, verify_results, verification_present)
        for slot in orphan
    ]
    category_counts: dict[str, int] = defaultdict(int)
    remediable = 0
    for item in traced:
        category_counts[str(item.get("category") or "issue")] += 1
        if bool(item.get("safeToRetry")):
            remediable += 1

    eligible = (
        category_counts.get("replaced", 0)
        + category_counts.get("pending", 0)
        + category_counts.get("issue", 0)
    )
    return {
        "schema": SCHEMA,
        "inventoryBuildKey": str(inventory.get("buildKey") or ""),
        "inventoryRomKind": str(inventory.get("romKind") or "generic"),
        "verificationState": str(verification.get("state") or "not-run"),
        "summary": {
            "inventorySlots": len(inventory.get("slots") or {}),
            "censusSlots": len(traced),
            "replaceableSlots": eligible,
            "replaced": category_counts.get("replaced", 0),
            "pending": category_counts.get("pending", 0),
            "protected": category_counts.get("protected", 0),
            "issues": category_counts.get("issue", 0),
            "remediable": remediable,
            "consumed": sum(1 for item in traced if item["routes"]),
            "notConsumed": counts.get("not-consumed", 0),
            "preserved": counts.get("preserved", 0),
            "mappedUnverified": counts.get("mapped-unverified", 0),
            "loaded": counts.get("loaded", 0),
            "mountVisible": counts.get("mount-visible", 0),
            "mappingMissing": counts.get("mapping-missing", 0),
            "missingMount": counts.get("missing-mount", 0),
            "mismatch": counts.get("mismatch", 0),
            "unconfirmed": counts.get("unconfirmed", 0),
            "partial": counts.get("partial", 0),
            "templateOnlyRoutes": len(orphan_routes),
        },
        "slots": traced,
        "templateOnlyRoutes": orphan_routes,
    }


def atomic_write(payload: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    os.close(fd)
    temp = Path(raw)
    try:
        temp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        os.chmod(temp, 0o600)
        os.replace(temp, output)
    finally:
        temp.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--payload", type=Path)
    parser.add_argument("--overlay", type=Path)
    parser.add_argument("--physical-root", type=Path)
    parser.add_argument("--physical-confirmed", action="store_true")
    parser.add_argument("--active-font", default="")
    parser.add_argument("--verification", type=Path)
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        inventory = load(args.inventory, INVENTORY_SCHEMA)
        candidates = load(args.candidates, CANDIDATE_SCHEMA, optional=True) if args.candidates else {}
        if args.physical_root:
            result = build_physical_trace(
                inventory,
                args.physical_root,
                candidates,
                confirmed=args.physical_confirmed,
                active_font=args.active_font,
            )
        else:
            if not args.payload or not args.overlay:
                raise TraceError("缺少 payload/overlay 或 physical-root")
            result = build_trace(
                inventory,
                load(args.payload, PAYLOAD_SCHEMA),
                load(args.overlay, OVERLAY_SCHEMA),
                load(args.verification, VERIFY_SCHEMA, optional=True) if args.verification else {},
                candidates,
            )
        if args.output:
            atomic_write(result, args.output)
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc) or exc.__class__.__name__},
                         ensure_ascii=False, separators=(",", ":")), file=os.sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
