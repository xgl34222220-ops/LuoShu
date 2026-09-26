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
    # A missing mount means the payload file already exists but Android did not
    # expose its parent mount. Rebuilding the same payload cannot repair that and
    # must not be advertised as a "safe retry" in the App.
    if state == "missing-mount":
        return "issue", False
    if state in {"mapping-missing", "mismatch", "not-consumed"}:
        return "issue", True
    if state == "partial":
        return "issue", "missing-mount" not in reason
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


def _read_key_values(path: Path | None) -> dict[str, str]:
    if path is None or not path.is_file():
        return {}
    result: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip():
                result[key.strip()] = value.strip()
    except OSError:
        return {}
    return result


def _mount_bucket(value: str) -> set[str]:
    result: set[str] = set()
    for raw in value.split(","):
        item = raw.strip()
        if not item:
            continue
        stem, sep, suffix = item.rpartition(":")
        if sep and suffix in {"bind", "overlay"}:
            item = stem
        result.add(item)
    return result


def _mount_failed(value: str, mount_key: str) -> bool:
    if not mount_key:
        return False
    for raw in value.split(","):
        item = raw.strip()
        if not item:
            continue
        if item == mount_key or item.startswith(mount_key + "-"):
            return True
    return False


def _slot_mount_key(logical: str, entry: dict[str, Any], inventory: dict[str, Any]) -> str:
    normalized = normalize_path(logical)
    nested = inventory.get("discoveredFontRoots") or []
    best = ""
    for raw in nested:
        if not isinstance(raw, dict):
            continue
        root = normalize_path(raw.get("logical"))
        if root and (normalized == root or normalized.startswith(root.rstrip("/") + "/")):
            if len(root) > len(best):
                best = root
    if best:
        return best.lstrip("/")

    partition = str(entry.get("partition") or "").strip()
    if not partition:
        parts = Path(normalized).parts
        partition = parts[1] if len(parts) > 1 else ""
    return f"{partition}/fonts" if partition else ""


def _physical_preserved_index(physical_root: Path) -> dict[str, str]:
    manifest = physical_root / ".luoshu-coverage-preserved.tsv"
    result: dict[str, str] = {}
    if not manifest.is_file():
        return result
    try:
        for line in manifest.read_text(encoding="utf-8", errors="replace").splitlines():
            path, sep, reason = line.partition("\t")
            logical = normalize_path(path)
            if sep and logical:
                result[logical] = reason.strip() or "coverage-preserved"
    except OSError:
        return {}
    return result


def rom_preserved_index(physical_root: Path, inventory: dict[str, Any], *, strict: bool = False) -> dict[str, str]:
    """Keep the ROM mapper's intentional omissions through generic coverage.

    The report belongs to this isolated payload, not the live or previous font.
    Only exact inventory paths can become protection entries; never interpret a
    report path as a filesystem destination on its own.
    """
    report = physical_root / ".luoshu-metrics-report.json"
    if not report.is_file():
        return {}
    try:
        data = load(report, "luoshu-slot-metrics-v1")
        result: dict[str, str] = {}
        slots = inventory.get("slots") or {}
        reasons = {
            "preservedDynamicAliases": "ROM 动态字体别名保持原厂",
            "preservedWeightAliases": "source-weight-missing",
            "preservedStockAliases": "specialized-name",
        }
        for key, reason in reasons.items():
            paths = data.get(key, [])
            if not isinstance(paths, list):
                raise TraceError("ROM 字体保护清单格式无效")
            for logical in paths:
                if (not isinstance(logical, str) or logical not in slots
                        or not logical.startswith("/") or logical.startswith("//")
                        or any(char in logical for char in "\t\r\n")
                        or any(part in {"", ".", ".."} for part in logical[1:].split("/"))):
                    continue
                result[logical] = reason
        return result
    except TraceError:
        if strict:
            raise
        return {}


def build_physical_trace(
    inventory: dict[str, Any],
    physical_root: Path,
    candidates: dict[str, Any] | None = None,
    *,
    confirmed: bool = False,
    prepared: bool = False,
    active_font: str = "",
    mount_state: Path | None = None,
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
    preserved_by_path = _physical_preserved_index(physical_root)
    preserved_by_path.update(rom_preserved_index(physical_root, inventory))
    # A previous boot's mount evidence cannot confirm or invalidate a new tree.
    confirmed = confirmed and not prepared
    mount_info = {} if prepared else _read_key_values(mount_state)
    mount_state_name = mount_info.get("state", "")
    mount_backend = mount_info.get("backend", "")
    mounted_roots = _mount_bucket(mount_info.get("mounted", ""))
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
        style = str(entry.get("style") or "normal").strip().lower()
        if not protected_reason and style not in {"", "normal", "regular"}:
            protected_reason = f"preserved-style-{style}"

        routes: list[dict[str, Any]] = []
        if physical.is_file():
            mount_key = _slot_mount_key(logical, entry, inventory)
            mount_failed = bool(
                _mount_failed(mount_info.get("failed", ""), mount_key)
                and mount_key not in mounted_roots
            )
            mount_confirmed = bool(
                confirmed
                and (
                    mount_backend == "external-mount"
                    or not mount_key
                    or mount_key in mounted_roots
                    or (not mounted_roots and mount_state_name in {"mounted", "confirmed"})
                )
            )
            if prepared:
                state = "mapped-unverified"
                reason = "next-boot-payload-awaiting-reboot"
            elif mount_failed:
                state = "missing-mount"
                reason = "physical-payload-present-but-partition-mount-failed"
            elif mount_confirmed:
                state = "loaded"
                reason = "active-physical-payload-and-mount-confirmed"
            else:
                state = "mapped-unverified"
                reason = "active-physical-payload-awaiting-mount-confirmation"
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
                "mountKey": mount_key,
                "mountState": mount_state_name,
                "mountBackend": mount_backend,
            })
        elif logical in preserved_by_path:
            state = "preserved"
            reason = preserved_by_path[logical]
            category, safe_to_retry = "protected", False
        elif protected_reason:
            state = "preserved"
            reason = protected_reason
            category, safe_to_retry = "protected", False
        else:
            state = "mapping-missing"
            reason = "active-physical-payload-missing-slot"
            category, safe_to_retry = "issue", not prepared

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
    census_only: list[dict[str, Any]] = []
    for raw in candidates.get("paths") or []:
        if not isinstance(raw, dict):
            continue
        logical = normalize_path(raw.get("path"))
        if not logical or logical in inventory_paths:
            continue
        reason = str(raw.get("reason") or "census-only")
        if bool(raw.get("candidate", False)) and reason == "visible-font-path":
            reason = "not-promoted-to-ui-inventory"
        census_only.append({
            "path": logical,
            "slotName": str(raw.get("slotName") or Path(logical).name),
            "partition": str(raw.get("partition") or ""),
            "source": "census",
            "format": Path(logical).suffix.lower().lstrip(".").upper(),
            "reason": reason,
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
        "verificationState": "pending-reboot" if prepared else ("verified" if confirmed else "pending"),
        "rebootRequired": prepared,
        "activeFont": active_font,
        "traceSource": "physical-prepared" if prepared else "physical-safe",
        "summary": {
            "inventorySlots": len(inventory.get("slots") or {}),
            "censusSlots": len(traced) + len(census_only),
            "censusOnlySlots": len(census_only),
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
            "missingMount": counts.get("missing-mount", 0),
            "mismatch": counts.get("mismatch", 0),
            "unconfirmed": 0,
            "partial": 0,
            "templateOnlyRoutes": 0,
        },
        "slots": traced,
        "censusOnly": census_only,
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

    # Candidate census is intentionally wider than the UI-slot inventory. Keep
    # those paths as separate diagnostics instead of mixing them into "font slots".
    # The flashing page and the App must use the exact same inventory slot set.
    inventory_paths = {normalize_path(path) for path in (inventory.get("slots") or {})}
    census_only: list[dict[str, Any]] = []
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
        census_only.append({
            "path": logical,
            "slotName": str(raw.get("slotName") or Path(logical).name),
            "partition": str(raw.get("partition") or ""),
            "source": "census",
            "format": Path(logical).suffix.lower().lstrip(".").upper(),
            "reason": reason,
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
            "censusSlots": len(traced) + len(census_only),
            "censusOnlySlots": len(census_only),
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
        "censusOnly": census_only,
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


def atomic_write_plan(payload: dict[str, Any], output: Path) -> None:
    paths = sorted({
        normalize_path(item.get("path"))
        for item in payload.get("slots") or []
        if isinstance(item, dict) and bool(item.get("safeToRetry")) and normalize_path(item.get("path"))
    })
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    os.close(fd)
    temp = Path(raw)
    try:
        temp.write_text("".join(f"{path}\n" for path in paths), encoding="utf-8")
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
    parser.add_argument("--physical-prepared", action="store_true")
    parser.add_argument("--rom-preserves", action="store_true", help="以 TSV 输出当前负载的 ROM 保护槽位")
    parser.add_argument("--active-font", default="")
    parser.add_argument("--mount-state", type=Path)
    parser.add_argument("--verification", type=Path)
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--remediation-plan", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        inventory = load(args.inventory, INVENTORY_SCHEMA)
        if args.rom_preserves:
            if not args.physical_root:
                raise TraceError("ROM 保护清单缺少 physical-root")
            for logical, reason in sorted(rom_preserved_index(args.physical_root, inventory, strict=True).items()):
                print(f"{logical}\t{reason}")
            return 0
        candidates = load(args.candidates, CANDIDATE_SCHEMA, optional=True) if args.candidates else {}
        if args.physical_root:
            result = build_physical_trace(
                inventory,
                args.physical_root,
                candidates,
                confirmed=args.physical_confirmed,
                prepared=args.physical_prepared,
                active_font=args.active_font,
                mount_state=args.mount_state,
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
        if args.remediation_plan:
            atomic_write_plan(result, args.remediation_plan)
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc) or exc.__class__.__name__},
                         ensure_ascii=False, separators=(",", ":")), file=os.sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
