#!/usr/bin/env python3
"""Build a normalized per-device Android font topology snapshot.

This layer is intentionally read-only. It merges the trusted stock inventory with
runtime FontManager evidence and /data/fonts state, but never decides what should be
replaced. Future replacement planners consume this file instead of re-scanning or
hard-coding ROM-specific filenames.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "device-font-topology-v1"
TOPOLOGY_REVISION = 3
FONT_EXTENSIONS = (".ttf", ".otf", ".ttc", ".otc")
ABS_FONT_PATH_RE = re.compile(
    r"(/[A-Za-z0-9_./+@=~-]+\.(?:ttf|otf|ttc|otc))",
    re.IGNORECASE,
)


class TopologyError(RuntimeError):
    pass


class TopologyRefreshBlocked(TopologyError):
    """Visible dynamic bytes are overlaid; preserve sealed stock evidence."""


def _inventory_digest(inventory: dict[str, Any]) -> str:
    # A new capture timestamp is not new evidence. Everything else, including
    # routes, metrics and trusted roots, contributes to cache identity.
    material = {key: value for key, value in inventory.items() if key != "generatedAt"}
    blob = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def _dynamic_mount_targets(mount_text: str) -> set[str]:
    result: set[str] = set()
    for line in mount_text.splitlines():
        fields = line.split()
        if len(fields) > 5 and " - " in line:
            target = fields[4].replace(r"\040", " ").replace(r"\134", "\\")
            if target.startswith("/data/fonts/"):
                result.add(target)
    return result


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TopologyError(f"无法读取设备字体清单：{path}") from error
    if not isinstance(value, dict):
        raise TopologyError("设备字体清单根节点不是对象")
    return value


def _read_text(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _sha256(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".tmp.{os.getpid()}")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temp, path)


def _partition_for_path(path: str, slots: dict[str, dict[str, Any]]) -> str:
    entry = slots.get(path)
    if isinstance(entry, dict):
        value = str(entry.get("partition") or "").strip()
        if value:
            return value
    parts = Path(path).parts
    if len(parts) >= 2 and parts[0] == "/":
        return parts[1]
    if path.startswith("/"):
        pieces = [piece for piece in path.split("/") if piece]
        return pieces[0] if pieces else "unknown"
    return "unknown"


def _known_family_paths(inventory: dict[str, Any]) -> dict[str, list[str]]:
    raw = inventory.get("families")
    if not isinstance(raw, dict):
        return {}
    result: dict[str, list[str]] = {}
    for name, values in raw.items():
        family = str(name).strip()
        if not family or not isinstance(values, list):
            continue
        paths: list[str] = []
        for value in values:
            path = str(value).strip()
            if path and path not in paths:
                paths.append(path)
        if paths:
            result[family] = paths
    return result


def _slot_family_index(families: dict[str, list[str]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for family, paths in families.items():
        for path in paths:
            bucket = result.setdefault(path, [])
            if family not in bucket:
                bucket.append(family)
    return result


def _font_manager_evidence(
    dump_text: str,
    slots: dict[str, dict[str, Any]],
    families: dict[str, list[str]],
) -> dict[str, Any]:
    if not dump_text.strip():
        return {
            "available": False,
            "confirmedSlots": [],
            "confirmedFamilies": [],
            "reportedFontPaths": [],
            "reportedDataFontPaths": [],
        }

    lowered = dump_text.lower()
    reported_paths = sorted({match.group(1) for match in ABS_FONT_PATH_RE.finditer(dump_text)})
    confirmed_slots: list[str] = []
    for path, entry in slots.items():
        slot_name = str(entry.get("slotName") or Path(path).name)
        if path.lower() in lowered or (slot_name and slot_name.lower() in lowered):
            confirmed_slots.append(path)

    confirmed_families = sorted(
        family
        for family in families
        if family and family.lower() in lowered
    )
    data_paths = [path for path in reported_paths if path.lower().startswith("/data/fonts/")]
    return {
        "available": True,
        "confirmedSlots": sorted(confirmed_slots),
        "confirmedFamilies": confirmed_families,
        "reportedFontPaths": reported_paths,
        "reportedDataFontPaths": data_paths,
    }


def _mount_evidence(
    mount_text: str,
    slots: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if not mount_text.strip():
        return {"available": False, "confirmedSlots": [], "fontMountLineCount": 0}
    lowered = mount_text.lower()
    confirmed: list[str] = []
    for path, entry in slots.items():
        slot_name = str(entry.get("slotName") or Path(path).name)
        if path.lower() in lowered or (slot_name and slot_name.lower() in lowered):
            confirmed.append(path)
    interesting = [
        line
        for line in mount_text.splitlines()
        if "/fonts" in line.lower() or "font_fallback" in line.lower() or "fonts.xml" in line.lower()
    ]
    return {
        "available": True,
        "confirmedSlots": sorted(confirmed),
        "fontMountLineCount": len(interesting),
    }


def _xml_font_references(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {
            "available": False,
            "version": "",
            "fontReferences": [],
            "namedReferences": [],
        }
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return {
            "available": True,
            "version": "",
            "fontReferences": [],
            "namedReferences": [],
            "parseError": True,
        }

    version = (
        root.get("configVersion")
        or root.get("version")
        or root.get("generation")
        or ""
    )
    font_refs: set[str] = set()
    named_refs: set[str] = set()

    def consider(value: str, key: str = "") -> None:
        cleaned = value.strip()
        if not cleaned:
            return
        lowered = cleaned.lower()
        if lowered.endswith(FONT_EXTENSIONS) or "/data/fonts/" in lowered:
            font_refs.add(cleaned)
        if key.lower() in {"name", "family", "familyname", "postscriptname", "psname"}:
            named_refs.add(cleaned)

    for element in root.iter():
        if element.text:
            consider(element.text)
        for key, value in element.attrib.items():
            consider(value, key)

    return {
        "available": True,
        "version": str(version),
        "fontReferences": sorted(font_refs),
        "namedReferences": sorted(named_refs),
    }


def _scan_data_fonts(path: Path | None, limit: int = 2048) -> list[dict[str, Any]]:
    if path is None or not path.is_dir():
        return []
    result: list[dict[str, Any]] = []
    try:
        candidates = sorted(path.rglob("*"), key=lambda item: str(item).lower())
    except OSError:
        return []
    for item in candidates:
        if len(result) >= limit:
            break
        if item.suffix.lower() not in FONT_EXTENSIONS:
            continue
        try:
            if not item.is_file():
                continue
            stat = item.stat()
        except OSError:
            continue
        result.append({
            "path": str(item),
            "fileName": item.name,
            "bytes": int(stat.st_size),
        })
    return result


def validate_topology(data: dict[str, Any], expected_build_key: str | None = None) -> None:
    if data.get("schema") != SCHEMA or data.get("state") != "ready":
        raise TopologyError("设备字体拓扑格式无效")
    try:
        revision = int(data.get("topologyRevision", 0))
    except (TypeError, ValueError) as error:
        raise TopologyError("设备字体拓扑版本无效") from error
    if revision != TOPOLOGY_REVISION:
        raise TopologyError("设备字体拓扑版本已过期")
    if expected_build_key and expected_build_key != "unknown":
        if str(data.get("buildKey") or "") != expected_build_key:
            raise TopologyError("设备字体拓扑与当前系统构建不匹配")
    if not isinstance(data.get("slots"), dict) or not isinstance(data.get("families"), dict):
        raise TopologyError("设备字体拓扑缺少槽位或 family 图")
    if not isinstance(data.get("summary"), dict) or not isinstance(data.get("runtime"), dict):
        raise TopologyError("设备字体拓扑缺少摘要或运行时证据")


def build_topology(
    inventory: dict[str, Any],
    candidates: dict[str, Any] | None,
    font_manager_dump: str,
    data_fonts_config: Path | None,
    data_fonts_dir: Path | None,
    mount_text: str,
) -> dict[str, Any]:
    if inventory.get("schema") != "device-font-inventory-v1" or inventory.get("state") != "ready":
        raise TopologyError("原厂字体清单尚未就绪，不能生成字体拓扑")
    if inventory.get("scannerRevision") != 6:
        raise TopologyError("原厂字体清单扫描版本已过期，需要可信原厂重扫")
    raw_slots = inventory.get("slots")
    if not isinstance(raw_slots, dict) or not raw_slots:
        raise TopologyError("原厂字体清单没有可用槽位")

    slots: dict[str, dict[str, Any]] = {}
    for path, value in raw_slots.items():
        logical = str(path).strip()
        if not logical or not isinstance(value, dict):
            continue
        slots[logical] = copy.deepcopy(value)

    # The legacy inventory intentionally contains only replaceable UI slots.
    # Topology must describe *all* visible stock fonts, including protected
    # emoji/serif/symbol/fallback faces, so merge the full physical candidate probe.
    candidate_entries = candidates.get("paths") if isinstance(candidates, dict) else []
    if isinstance(candidate_entries, list):
        for raw in candidate_entries:
            if not isinstance(raw, dict):
                continue
            logical = str(raw.get("path") or "").strip()
            if not logical.startswith("/") or not logical.lower().endswith(FONT_EXTENSIONS):
                continue
            current = slots.setdefault(logical, {
                "slotName": str(raw.get("slotName") or Path(logical).name),
                "path": logical,
                "partition": str(raw.get("partition") or _partition_for_path(logical, slots)),
                "source": "physical-scan",
                "families": [],
            })
            current["physicalCandidate"] = raw.get("candidate") is True
            current["physicalReason"] = str(raw.get("reason") or "")

    if not slots:
        raise TopologyError("原厂字体清单槽位为空")

    families = _known_family_paths(inventory)

    # Scanner revision 5 preserves the complete XML semantic graph separately
    # from legacy replaceable slots. Merge family attrs/lang/variant/fallbackFor
    # into topology without changing current production replacement behavior.
    xml_graph = inventory.get("xmlGraph")
    xml_refs = xml_graph.get("refs") if isinstance(xml_graph, dict) else []
    unresolved_xml_refs: list[dict[str, Any]] = []
    if isinstance(xml_refs, list):
        for raw in xml_refs:
            if not isinstance(raw, dict):
                continue
            family = str(raw.get("family") or "").strip()
            logical = str(raw.get("resolvedPath") or "").strip()
            if family and logical:
                bucket = families.setdefault(family, [])
                if logical not in bucket:
                    bucket.append(logical)
            if not logical or logical not in slots:
                unresolved_xml_refs.append(dict(raw))
                continue
            entry = slots[logical]
            refs = entry.setdefault("xmlRefs", [])
            ref_copy = dict(raw)
            if ref_copy not in refs:
                refs.append(ref_copy)
            if family:
                names = entry.setdefault("families", [])
                if family not in names:
                    names.append(family)

    data_config = _xml_font_references(data_fonts_config)
    data_files = _scan_data_fonts(data_fonts_dir)
    from font_dynamic_topology import discover as discover_dynamic_fonts
    reported_data = sorted({match.group(1) for match in ABS_FONT_PATH_RE.finditer(font_manager_dump)
                            if match.group(1).startswith("/data/fonts/")})
    dynamic_mounts = _dynamic_mount_targets(mount_text)
    dynamic_slots, dynamic_evidence = discover_dynamic_fonts(
        data_fonts_config, data_fonts_dir, inventory, reported_data, data_files, dynamic_mounts)
    slots.update(dynamic_slots)
    for logical, entry in dynamic_slots.items():
        for family in entry.get("families", []):
            if logical not in families.setdefault(family, []):
                families[family].append(logical)

    slot_families = _slot_family_index(families)
    manager = _font_manager_evidence(font_manager_dump, slots, families)
    mounts = _mount_evidence(mount_text, slots)
    manager_slots = set(manager["confirmedSlots"])
    mount_slots = set(mounts["confirmedSlots"])

    normalized_slots: dict[str, dict[str, Any]] = {}
    for path in sorted(slots):
        entry = dict(slots[path])
        merged_families: list[str] = []
        for name in entry.get("families") or []:
            family = str(name).strip()
            if family and family not in merged_families:
                merged_families.append(family)
        for family in slot_families.get(path, []):
            if family not in merged_families:
                merged_families.append(family)
        entry["families"] = sorted(merged_families)
        entry["legacyReplaceable"] = path in raw_slots
        entry["runtimeEvidence"] = {
            "fontManager": path in manager_slots,
            "mount": path in mount_slots,
        }
        normalized_slots[path] = entry

    normalized_families: dict[str, dict[str, Any]] = {}
    manager_families = set(manager["confirmedFamilies"])
    for family in sorted(families):
        paths = [path for path in families[family] if path]
        partitions = sorted({_partition_for_path(path, slots) for path in paths})
        normalized_families[family] = {
            "paths": paths,
            "partitions": partitions,
            "runtimeConfirmed": family in manager_families,
        }

    partitions = sorted({
        str(entry.get("partition") or _partition_for_path(path, slots))
        for path, entry in normalized_slots.items()
    })
    edges = [
        {"family": family, "slot": path}
        for family in sorted(families)
        for path in families[family]
        if path in normalized_slots
    ]

    xml_sources = inventory.get("xmlSources")
    if not isinstance(xml_sources, list):
        xml_sources = []

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "topologyRevision": TOPOLOGY_REVISION,
        "state": "ready",
        "generatedAt": int(time.time()),
        "buildKey": str(inventory.get("buildKey") or "unknown"),
        "romKind": str(inventory.get("romKind") or "generic"),
        "scannerRevision": inventory.get("scannerRevision"),
        "inventoryRevision": inventory.get("inventoryRevision"),
        "inventoryDigest": _inventory_digest(inventory),
        "summary": {
            "slotCount": len(normalized_slots),
            "legacyUiSlotCount": len(raw_slots),
            "physicalFontCount": len(normalized_slots),
            "familyCount": len(normalized_families),
            "edgeCount": len(edges),
            "partitionCount": len(partitions),
            "xmlSourceCount": len(xml_sources),
            "xmlRefCount": len(xml_refs) if isinstance(xml_refs, list) else 0,
            "unresolvedXmlRefCount": len(unresolved_xml_refs),
            "runtimeConfirmedSlotCount": len(manager_slots | mount_slots),
            "runtimeConfirmedFamilyCount": len(manager_families),
            "dataFontFileCount": len(data_files),
            "dataFontConfigReferenceCount": len(data_config.get("fontReferences") or []),
            "dynamicResolvedTargetCount": len(dynamic_slots),
            "dynamicUnresolvedCount": len(dynamic_evidence["unresolved"]),
        },
        "partitions": partitions,
        "xmlSources": [str(value) for value in xml_sources],
        "xmlAliases": list(xml_graph.get("aliases") or []) if isinstance(xml_graph, dict) else [],
        "unresolvedXmlRefs": unresolved_xml_refs,
        "families": normalized_families,
        "slots": normalized_slots,
        "edges": edges,
        "runtime": {
            "fontManager": manager,
            "mounts": mounts,
            "dataFontsConfig": data_config,
            "dataFontFiles": data_files,
            "dynamicFontsEvidence": dynamic_evidence,
        },
    }
    validate_topology(payload, str(inventory.get("buildKey") or "unknown"))
    return payload


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload["summary"]
    return {
        "status": "ok",
        "schema": payload["schema"],
        "buildKey": payload["buildKey"],
        "romKind": payload["romKind"],
        "slotCount": summary["slotCount"],
        "familyCount": summary["familyCount"],
        "runtimeConfirmedSlotCount": summary["runtimeConfirmedSlotCount"],
        "dataFontFileCount": summary["dataFontFileCount"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--font-manager-dump", type=Path)
    parser.add_argument("--data-fonts-config", type=Path)
    parser.add_argument("--data-fonts-dir", type=Path)
    parser.add_argument("--mountinfo", type=Path)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--validate-current", action="store_true")
    args = parser.parse_args()

    if args.validate or args.validate_current:
        try:
            topology = _load_json(args.output)
            expected = None
            if args.inventory and args.inventory.is_file():
                expected = str(_load_json(args.inventory).get("buildKey") or "unknown")
            validate_topology(topology, expected)
            if args.validate_current:
                inventory = _load_json(args.inventory) if args.inventory else {}
                if inventory.get("scannerRevision") != 6 or topology.get("scannerRevision") != 6:
                    raise TopologyError("字体扫描版本已过期")
                dynamic = topology.get("runtime", {}).get("dynamicFontsEvidence", {})
                current_config = args.data_fonts_config or Path("/data/fonts/config/config.xml")
                current_files = args.data_fonts_dir or Path("/data/fonts/files")
                mounts = _dynamic_mount_targets(_read_text(args.mountinfo or Path("/proc/self/mountinfo")))
                if "/data/fonts/config/config.xml" in mounts:
                    raise TopologyRefreshBlocked("动态字体配置已覆盖，需要恢复可信原始配置后重试")
                for logical, slot in topology.get("slots", {}).items():
                    if not str(logical).startswith("/data/fonts/"):
                        continue
                    identity = slot.get("dynamicIdentity") or {}
                    try:
                        relative = Path(logical).relative_to("/data/fonts/files")
                    except ValueError as error:
                        raise TopologyError("动态字体缓存路径无效") from error
                    if ".." in relative.parts:
                        raise TopologyError("动态字体缓存路径无效")
                    current_font = current_files / relative
                    changed = (not identity.get("fontSha256") or
                               identity.get("fontSha256") != _sha256(current_font))
                    if changed and logical in mounts:
                        raise TopologyRefreshBlocked("动态字体已覆盖，需要恢复可信原始字体后重试：" + str(logical))
                    if changed:
                        raise TopologyError("动态字体内容已变化，需要重新采集：" + str(logical))
                if topology.get("inventoryDigest") != _inventory_digest(inventory):
                    raise TopologyError("原厂字体清单内容已变化，需要重新采集拓扑")
                if dynamic.get("complete") is not True or dynamic.get("configSha256", "") != _sha256(current_config):
                    raise TopologyError("动态字体配置已变化或尚未解析")
                if not current_config.is_file() and _scan_data_fonts(current_files):
                    raise TopologyError("动态字体存在但缺少权威配置")
        except TopologyRefreshBlocked as error:
            print(json.dumps({"status": "blocked", "reason": "dynamic-original-view-required", "message": str(error)}, ensure_ascii=False))
            return 3
        except TopologyError as error:
            print(json.dumps({"status": "error", "message": str(error)}, ensure_ascii=False))
            return 1
        print(json.dumps(_summary(topology), ensure_ascii=False))
        return 0

    if args.inventory is None:
        print(json.dumps({"status": "error", "message": "缺少 --inventory"}, ensure_ascii=False))
        return 2

    try:
        inventory = _load_json(args.inventory)
        candidates = _load_json(args.candidates) if args.candidates and args.candidates.is_file() else None
        payload = build_topology(
            inventory,
            candidates,
            _read_text(args.font_manager_dump),
            args.data_fonts_config,
            args.data_fonts_dir,
            _read_text(args.mountinfo),
        )
        _atomic_write(args.output, payload)
    except (TopologyError, OSError) as error:
        print(json.dumps({"status": "error", "message": str(error)}, ensure_ascii=False))
        return 1

    print(json.dumps(_summary(payload), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
