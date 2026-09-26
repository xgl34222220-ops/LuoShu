#!/usr/bin/env python3
# Packaging contract marker: device-font-payload-v1
"""Per-device builder with inventory-first physical-slot supplementation.

The trusted XML template remains the metric/layout authority for declared Android
families. The install-time stock inventory is the authoritative list of additional
replaceable physical UI slots that are not represented by that template.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import device_font_payload_build_base as _base
import font_inventory as inventory_engine
from device_font_payload_build_base import *  # noqa: F401,F403

_ORIGINAL_BUILD_SIGNATURE = _base.build_signature
_ORIGINAL_BUILD_PAYLOAD = _base.build_payload
_LEGACY_HYPEROS_DIRECT = re.compile(
    r"^(?:MiSans(?:VF(?:_Overlay)?|LatinVF|TCVF|L3|Clock[A-Za-z0-9_.-]*)|"
    r"Mitype[A-Za-z0-9_.-]*|MiClock[A-Za-z0-9_.-]*|AndroidClock[A-Za-z0-9_.-]*|Clockopia|"
    r"GoogleSans(?:Text|Flex)?[A-Za-z0-9_.-]*|Roboto(?:Flex|Static)?[A-Za-z0-9_.-]*|"
    r"SourceSansPro[A-Za-z0-9_.-]*|(?:100|200|300|350|400|500|600|700|800|900))"
    r"\.(?:ttf|otf)$", re.I
)
_DENY = ("italic", "oblique", "emoji", "symbol", "icon", "serif", "math", "music")
_LEGACY_ROOTS = ("system", "system_ext", "product", "mi_ext", "my_product", "vendor", "odm", "oem", "cust", "hw_product")


def build_signature(slot: dict[str, Any], source_profile: dict[str, Any], source_weight: int) -> str:
    return _ORIGINAL_BUILD_SIGNATURE(slot, source_profile, source_weight)


def _module_root() -> Path:
    override = os.environ.get("LUOSHU_DEVICE_FONT_MODULE", "").strip()
    return Path(override) if override else Path(__file__).resolve().parent.parent


def _inventory_path(module: Path) -> Path:
    override = os.environ.get("LUOSHU_DEVICE_FONT_INVENTORY", "").strip()
    return Path(override) if override else module / "config/device_font_inventory.json"


def _load_inventory(module: Path) -> dict[str, Any] | None:
    path = _inventory_path(module)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        inventory_engine.validate_inventory(data)
    except (OSError, ValueError, TypeError, inventory_engine.InventoryError):
        return None
    return data


def _weight(name: str) -> int:
    lower = name.lower().replace("-", "").replace("_", "")
    hit = re.search(r"(?:^|[^0-9])(100|200|300|350|400|500|600|700|800|900)(?:[^0-9]|$)", name)
    if hit:
        return int(hit.group(1))
    for token, value in (
        ("thin", 100), ("extralight", 200), ("light", 300), ("medium", 500),
        ("semibold", 600), ("bold", 700), ("extrabold", 800), ("black", 900),
    ):
        if token in lower:
            return value
    return 400


def _inventory_roles(entry: dict[str, Any]) -> list[str]:
    name = str(entry.get("slotName") or Path(str(entry.get("path") or "")).name).lower()
    families = " ".join(str(item).lower() for item in entry.get("families") or [])
    if "clock" in name or "clock" in families:
        return ["clock", "global-ui"]
    if "mono" in name or "mono" in families:
        return ["mono", "global-ui"]
    if "display" in name or "display" in families:
        return ["display", "global-ui"]
    return ["global-ui"]


def _safe_inventory_logical(logical: str, entry: dict[str, Any]) -> tuple[str, Path] | None:
    """Validate an inventory path anywhere below a trusted system/OEM partition."""
    if (not isinstance(logical, str) or not logical.startswith("/")
            or logical.startswith("//") or any(c in logical for c in "\r\n\t\x00")
            or any(part in ("", ".", "..") for part in logical[1:].split("/"))
            or str(entry.get("path", logical)) != logical):
        return None
    path = Path(logical)
    parts = path.parts
    if len(parts) < 3 or parts[0] != "/":
        return None
    partition = parts[1]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_]{0,63}", partition):
        return None
    if partition in {"data", "data_mirror", "storage", "sdcard", "mnt", "proc", "sys", "dev", "apex", "cache", "tmp"}:
        return None
    if str(entry.get("partition") or partition) != partition:
        return None
    relative = Path(*parts[2:])
    if not relative.parts or any(part in ("", ".", "..") for part in relative.parts):
        return None
    # This is called only for entries of a validated stock inventory. Font
    # tables established the format during scanning; an OEM .bin or opaque
    # filename must retain the same eligibility as a .ttf spelling.
    return partition, relative


def _nested_stock_root(module: Path, partition: str, relative: Path) -> tuple[str, Path] | None:
    manifest = module / "config/device_font_roots.conf"
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    best: tuple[int, str, Path] | None = None
    for line in lines:
        fields = line.split("|")
        if len(fields) != 3 or fields[0] != partition:
            continue
        root_rel = Path(fields[1])
        key = fields[2]
        if not root_rel.parts or any(part in ("", ".", "..") for part in root_rel.parts):
            continue
        try:
            remainder = relative.relative_to(root_rel)
        except ValueError:
            continue
        candidate = (len(root_rel.parts), key, remainder)
        if best is None or candidate[0] > best[0]:
            best = candidate
    return (best[1], best[2]) if best is not None else None


def _stock_slot_file(module: Path, logical: str, entry: dict[str, Any]) -> Path | None:
    parsed = _safe_inventory_logical(logical, entry)
    if parsed is None:
        return None
    partition, relative = parsed

    # Deterministic test/diagnostic override. Production never sets this.
    test_root = os.environ.get("LUOSHU_DEVICE_FONT_STOCK_ROOT", "").strip()
    if test_root:
        candidate = Path(test_root) / logical.lstrip("/")
        return candidate if candidate.is_file() else None

    state_root = Path(os.environ.get("LUOSHU_SELF_MOUNT_STATE_ROOT", "/data/adb/luoshu/self-mount"))
    if relative.parts and relative.parts[0] == "fonts":
        lower = state_root / "lower" / f"{partition}-fonts" / Path(*relative.parts[1:])
        if lower.is_file():
            return lower
    else:
        nested = _nested_stock_root(module, partition, relative)
        if nested is not None:
            key, remainder = nested
            lower = state_root / "lower" / key / remainder
            if lower.is_file():
                return lower

    for prefix in (
        Path("/debug_ramdisk/.magisk/mirror"),
        Path("/sbin/.magisk/mirror"),
        Path("/data/adb/magisk/mirror"),
    ):
        candidate = prefix / partition / relative
        if candidate.is_file():
            return candidate

    # If LuoShu already owns this exact path in either the compatibility view
    # or the canonical private payload, the live path may be our overlay.
    # Fail closed instead of learning metrics from our own generated output.
    if ((module / partition / relative).exists()
            or (module / ".luoshu-payload" / partition / relative).exists()):
        return None
    live = Path("/") / partition / relative
    return live if live.is_file() else None


def _annotate_template_matches(
    template_slots: list[dict[str, Any]],
    logical: str,
    entry: dict[str, Any],
) -> int:
    matched = 0
    for slot in template_slots:
        if str(slot.get("resolvedPath") or "") != logical:
            continue
        slot["inventoryPath"] = logical
        slot["inventorySource"] = str(entry.get("source") or "inventory")
        slot["inventoryDisposition"] = "template"
        matched += 1
    return matched


def _inventory_direct_slot(
    module: Path,
    logical: str,
    entry: dict[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    style = str(entry.get("style") or "normal").lower()
    if style in ("italic", "oblique"):
        return None, "preserved-style"
    fmt = str(entry.get("format") or entry.get("validatedFormat") or "").upper()
    if fmt == "TTC":
        # A physical TTC/OTC carries a face-index contract. Replacing the whole
        # container with one generated TTF would corrupt unrelated faces.
        return None, "preserved-collection"
    if fmt not in {"TTF", "OTF"}:
        return None, "unsupported-format"

    stock = _stock_slot_file(module, logical, entry)
    if stock is None:
        return None, "stock-source-unavailable"
    face_index = int(entry.get("faceIndex") or 0)
    try:
        profile = _base.template_engine.inspect_font(stock, face_index, hash_fonts=False)
    except Exception as exc:
        return None, f"stock-profile-error:{exc.__class__.__name__}"

    name = str(entry.get("slotName") or Path(logical).name)
    partition = str(entry.get("partition") or Path(logical).parts[1])
    family = f"inventory-{partition}-{name}"
    return {
        "family": family,
        "familyNormalized": _base.template_engine.normalize(family),
        "familyAttributes": {},
        "sourceXml": "",
        "declared": name,
        "postScriptName": "",
        "weight": int(entry.get("weight") or _weight(name)),
        "style": "normal",
        "index": 0,
        "axes": "",
        "roles": _inventory_roles(entry),
        "replaceable": True,
        "resolvedPath": logical,
        "directPhysical": True,
        "inventoryPath": logical,
        "inventorySource": str(entry.get("source") or "inventory"),
        "inventoryDisposition": "direct",
        "font": profile,
    }, "direct"


def _enrich_inventory(template: dict[str, Any]) -> dict[str, Any]:
    module = _module_root()
    inventory = _load_inventory(module)
    if inventory is None:
        return _enrich_hyperos_legacy(template)

    slots = template.get("slots") if isinstance(template.get("slots"), list) else []
    coverage: list[dict[str, Any]] = []
    template_paths = {
        str(item.get("resolvedPath") or "")
        for item in slots
        if isinstance(item, dict) and str(item.get("resolvedPath") or "")
    }
    matched = 0
    direct = 0
    preserved = 0

    for logical, entry in sorted((inventory.get("slots") or {}).items()):
        if not isinstance(entry, dict):
            continue
        record = {
            "path": logical,
            "slotName": str(entry.get("slotName") or Path(logical).name),
            "partition": str(entry.get("partition") or ""),
            "source": str(entry.get("source") or ""),
            "weight": int(entry.get("weight") or 400),
            "style": str(entry.get("style") or "normal"),
            "format": str(entry.get("format") or entry.get("validatedFormat") or ""),
        }
        if logical in template_paths:
            hits = _annotate_template_matches(slots, logical, entry)
            matched += 1
            record.update(disposition="template", templateMatches=hits)
            coverage.append(record)
            continue

        extra, disposition = _inventory_direct_slot(module, logical, entry)
        if extra is not None:
            slots.append(extra)
            template_paths.add(logical)
            direct += 1
            record["disposition"] = "direct"
        else:
            preserved += 1
            record["disposition"] = "preserved"
            record["reason"] = disposition
        coverage.append(record)

    template["slots"] = slots
    template["inventorySupplement"] = {
        "schema": "device-font-inventory-link-v1",
        "inventoryBuildKey": str(inventory.get("buildKey") or ""),
        "inventoryRomKind": str(inventory.get("romKind") or "generic"),
        "inventorySlotCount": len(coverage),
        "templateMatched": matched,
        "directAdded": direct,
        "preserved": preserved,
        "slots": coverage,
    }
    summary = template.setdefault("summary", {})
    summary["inventorySlots"] = len(coverage)
    summary["inventoryTemplateMatched"] = matched
    summary["inventoryDirectAdded"] = direct
    summary["inventoryPreserved"] = preserved
    summary["slots"] = len(slots)
    summary["replaceable"] = sum(1 for item in slots if item.get("replaceable"))
    summary["directPhysical"] = sum(1 for item in slots if item.get("directPhysical"))
    return template


# Compatibility fallback only for an old install whose canonical stock inventory
# is absent. New/healthy installs always take the inventory-first path above.
def _legacy_roles(name: str) -> list[str]:
    lower = name.lower()
    if any(token in lower for token in _DENY) or not _LEGACY_HYPEROS_DIRECT.fullmatch(name):
        return []
    if "clock" in lower:
        return ["clock", "global-ui"]
    if lower.startswith("mitype"):
        return ["display", "global-ui"]
    return ["global-ui"]


def _legacy_stock_file(module: Path, partition: str, name: str) -> Path | None:
    logical = Path("/") / partition / "fonts" / name
    state_root = Path(os.environ.get("LUOSHU_SELF_MOUNT_STATE_ROOT", "/data/adb/luoshu/self-mount"))
    lower = state_root / "lower" / f"{partition}-fonts" / name
    if lower.is_file():
        return lower
    for prefix in (
        Path("/debug_ramdisk/.magisk/mirror"),
        Path("/sbin/.magisk/mirror"),
        Path("/data/adb/magisk/mirror"),
    ):
        candidate = prefix / partition / "fonts" / name
        if candidate.is_file():
            return candidate
    if (module / partition / "fonts" / name).exists():
        return None
    return logical if logical.is_file() else None


def _enrich_hyperos_legacy(template: dict[str, Any]) -> dict[str, Any]:
    module = _module_root()
    slots = template.get("slots") if isinstance(template.get("slots"), list) else []
    existing = {str(item.get("resolvedPath", "")) for item in slots if isinstance(item, dict)}
    candidates: list[tuple[str, str, Path, list[str]]] = []
    hyperos_marker = False
    for partition in _LEGACY_ROOTS:
        lower_root = Path(os.environ.get("LUOSHU_SELF_MOUNT_STATE_ROOT", "/data/adb/luoshu/self-mount")) / "lower" / f"{partition}-fonts"
        live_root = Path("/") / partition / "fonts"
        names: set[str] = set()
        for root in (lower_root, live_root):
            if not root.is_dir():
                continue
            try:
                names.update(item.name for item in root.iterdir() if item.is_file())
            except OSError:
                pass
        for name in sorted(names):
            roles = _legacy_roles(name)
            if not roles:
                continue
            if name.lower().startswith(("misans", "mitype", "miclock")):
                hyperos_marker = True
            logical = str(Path("/") / partition / "fonts" / name)
            if logical in existing:
                continue
            stock = _legacy_stock_file(module, partition, name)
            if stock is not None:
                candidates.append((partition, name, stock, roles))
    if not hyperos_marker:
        return template
    for partition, name, stock, roles in candidates:
        logical = str(Path("/") / partition / "fonts" / name)
        try:
            profile = _base.template_engine.inspect_font(stock, -1, hash_fonts=False)
        except Exception:
            continue
        slots.append({
            "family": f"physical-{name}",
            "familyNormalized": f"physical-{name}".lower(),
            "familyAttributes": {},
            "sourceXml": "",
            "declared": name,
            "postScriptName": "",
            "weight": _weight(name),
            "style": "normal",
            "index": 0,
            "axes": "",
            "roles": roles,
            "replaceable": True,
            "resolvedPath": logical,
            "directPhysical": True,
            "inventoryDisposition": "legacy-fallback",
            "font": profile,
        })
        existing.add(logical)
    template["slots"] = slots
    summary = template.setdefault("summary", {})
    summary["slots"] = len(slots)
    summary["replaceable"] = sum(1 for item in slots if item.get("replaceable"))
    summary["directPhysical"] = sum(1 for item in slots if item.get("directPhysical"))
    return template


def build_payload(template, source_dir, source_prefix, output_dir, manifest_path):
    return _ORIGINAL_BUILD_PAYLOAD(_enrich_inventory(template), source_dir, source_prefix, output_dir, manifest_path)


_base.build_signature = build_signature
_base.build_payload = build_payload


def main() -> int:
    return _base.main()


if __name__ == "__main__":
    raise SystemExit(main())
