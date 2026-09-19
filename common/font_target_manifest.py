#!/usr/bin/env python3
"""Compile a device-specific replaceable font target manifest from the stock inventory.

The stock scanner remains the authority for what is safe to replace. This compiler
turns its rich metrics inventory into a compact runtime contract so ROM adapters do
not fall back to filename guesses after installation.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
from typing import Any

from hyperos_physical_policy import (
    PARTITIONS as HYPEROS_PARTITIONS,
    preserved_dynamic_alias,
    safe_physical_font_name,
)

SCHEMA = "device-font-target-manifest-v1"
REVISION = 1


class TargetManifestError(RuntimeError):
    pass


def _load_inventory(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise TargetManifestError(f"无法读取原厂字体清单：{error}") from error
    if data.get("schema") != "device-font-inventory-v1" or data.get("state") != "ready":
        raise TargetManifestError("原厂字体清单未就绪")
    if not isinstance(data.get("slots"), dict) or not data["slots"]:
        raise TargetManifestError("原厂字体清单没有可替换槽位")
    return data


def _parse_logical(logical: str) -> tuple[str, str] | None:
    path = PurePosixPath(logical)
    parts = path.parts
    if len(parts) != 4 or parts[0] != "/" or parts[2] != "fonts":
        return None
    partition, name = parts[1], parts[3]
    if not partition or not name or "/" in name or "\x00" in name:
        return None
    return partition, name


def _slot_format(entry: dict[str, Any]) -> str:
    value = entry.get("validatedFormat") or entry.get("format") or ""
    return str(value).upper()


def _hyperos_physical(data: dict[str, Any], logical: str, partition: str,
                      name: str, entry: dict[str, Any]) -> bool:
    if data.get("romKind") != "hyperos":
        return False
    if partition not in HYPEROS_PARTITIONS:
        return False
    if preserved_dynamic_alias(data, logical):
        return False
    if not safe_physical_font_name(name):
        return False
    if _slot_format(entry) not in {"TTF", "OTF"}:
        return False
    try:
        face = int(entry.get("faceIndex", 0))
    except (TypeError, ValueError):
        return False
    if face != 0:
        return False
    style = str(entry.get("style", "normal")).lower()
    return style not in {"italic", "oblique"}


def compile_manifest(data: dict[str, Any]) -> dict[str, Any]:
    targets: list[dict[str, Any]] = []
    for logical, raw in sorted(data["slots"].items()):
        if not isinstance(raw, dict):
            continue
        parsed = _parse_logical(logical)
        if parsed is None:
            continue
        partition, name = parsed
        physical = _hyperos_physical(data, logical, partition, name, raw)
        targets.append({
            "path": logical,
            "partition": partition,
            "name": name,
            "mode": "physical" if physical else "inventory",
            "format": _slot_format(raw) or "UNKNOWN",
            "faceIndex": int(raw.get("faceIndex", 0) or 0),
            "weight": int(raw.get("weight", 400) or 400),
            "style": str(raw.get("style", "normal")),
            "source": str(raw.get("source", "xml")),
            "families": [str(item) for item in raw.get("families", []) if str(item)],
        })

    if not targets:
        raise TargetManifestError("没有生成任何可替换字体目标")

    physical = [item for item in targets if item["mode"] == "physical"]
    by_partition: dict[str, int] = {}
    for item in targets:
        by_partition[item["partition"]] = by_partition.get(item["partition"], 0) + 1

    return {
        "schema": SCHEMA,
        "revision": REVISION,
        "buildKey": str(data.get("buildKey", "")),
        "romKind": str(data.get("romKind", "generic")),
        "inventoryScannerRevision": int(data.get("scannerRevision", 0) or 0),
        "inventoryMetricsRevision": int(data.get("metricsRevision", 0) or 0),
        "replaceableCount": len(targets),
        "physicalCount": len(physical),
        "inventoryOnlyCount": len(targets) - len(physical),
        "partitionCounts": dict(sorted(by_partition.items())),
        "preservedDynamicAliases": sorted((data.get("preservedDynamicAliases") or {}).keys()),
        "targets": targets,
    }


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _list_text(manifest: dict[str, Any]) -> str:
    lines = [
        f"# schema={manifest['schema']}",
        f"# revision={manifest['revision']}",
        f"# buildKey={manifest['buildKey']}",
        f"# romKind={manifest['romKind']}",
    ]
    for item in manifest["targets"]:
        fields = (item["path"], item["partition"], item["name"], item["mode"])
        if any("|" in str(field) or "\n" in str(field) or "\r" in str(field) for field in fields):
            continue
        lines.append("|".join(map(str, fields)))
    return "\n".join(lines) + "\n"


def _emit(manifest: dict[str, Any], mode: str) -> None:
    for item in manifest["targets"]:
        if mode == "physical-paths" and item["mode"] != "physical":
            continue
        if mode == "all-paths":
            print(item["path"])
        elif mode == "physical-paths":
            print(item["path"])
        elif mode == "physical-list":
            if item["mode"] == "physical":
                print(f"{item['path']}|{item['partition']}|{item['name']}|physical")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--list-output", type=Path)
    parser.add_argument("--emit", choices=("all-paths", "physical-paths", "physical-list"))
    args = parser.parse_args()

    try:
        manifest = compile_manifest(_load_inventory(args.inventory))
        if args.output:
            _atomic_write(args.output, json.dumps(
                manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ) + "\n")
        if args.list_output:
            _atomic_write(args.list_output, _list_text(manifest))
        if args.emit:
            _emit(manifest, args.emit)
        if not args.emit:
            print(json.dumps({
                "status": "ok",
                "schema": manifest["schema"],
                "romKind": manifest["romKind"],
                "replaceableCount": manifest["replaceableCount"],
                "physicalCount": manifest["physicalCount"],
                "partitionCount": len(manifest["partitionCounts"]),
            }, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as error:
        print(json.dumps({
            "status": "error",
            "message": str(error) or error.__class__.__name__,
        }, ensure_ascii=False, separators=(",", ":")), file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
