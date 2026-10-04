#!/usr/bin/env python3
"""Export a Universal Font Engine diagnostic bundle.

The bundle holds everything needed to replay the engine on a computer with the
device's real inputs: stock font XML snapshots, the stock font files of every
slot the engine may compile (read from the pre-mount lower/mirror snapshot, never
from LuoShu's own overlay), the user's source fonts of recent switches, every
engine stage JSON and the recent logs. Read-only for the device; writes one zip.

tools/replay_diagnostics.py replays a bundle on the host.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

SCHEMA = "luoshu-engine-diagnostic-v1"
STOCK_TOTAL_LIMIT = 600 * 1024 * 1024
SOURCE_TOTAL_LIMIT = 400 * 1024 * 1024
SMALL_PRESERVED_LIMIT = 2 * 1024 * 1024
CONFIG_FILE_LIMIT = 8 * 1024 * 1024
LOG_TAIL_BYTES = 2 * 1024 * 1024
RECENT_PROFILES = 3
SKIPPED_ROLES = {"emoji", "symbol-icon"}
CONFIG_DIRS = (
    "font-config-source",
    "source-font-profiles",
    "universal-font-plans",
    "minimal-xml-route-plans",
    "universal-font-artifact-manifests",
)
PROPS = (
    "ro.product.brand", "ro.product.manufacturer", "ro.product.model", "ro.product.device",
    "ro.build.fingerprint", "ro.build.display.id", "ro.build.version.release",
    "ro.build.version.sdk", "ro.build.version.incremental",
    "ro.miui.ui.version.name", "ro.mi.os.version.name", "ro.mi.os.version.incremental",
    "ro.build.version.oplusrom", "ro.build.version.opporom", "ro.oplus.image.my_product.type",
    "ro.product.locale", "persist.sys.locale",
)


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _props() -> dict[str, str]:
    result: dict[str, str] = {}
    for name in PROPS:
        try:
            value = subprocess.run(
                ["getprop", name], check=False, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            value = ""
        if value:
            result[name] = value
    return result


def _active_font(config: Path) -> str:
    try:
        return (config / "active_font.conf").read_text(encoding="utf-8").splitlines()[0].strip()
    except (OSError, IndexError):
        return ""


def _stock_candidates(logical: str, lower_root: Path, live_ok: bool) -> list[tuple[str, Path]]:
    path = Path(logical)
    parts = path.parts
    result: list[tuple[str, Path]] = []
    if len(parts) >= 4 and parts[0] == "/" and parts[2] == "fonts":
        result.append(("lower", lower_root / "lower" / f"{parts[1]}-fonts" / Path(*parts[3:])))
    for prefix in ("/debug_ramdisk/.magisk/mirror", "/sbin/.magisk/mirror", "/data/adb/magisk/mirror"):
        result.append(("mirror", Path(prefix) / path.relative_to("/")))
    if live_ok:
        result.append(("live", path))
    return result


def _resolve_stock(logical: str, lower_root: Path, live_ok: bool) -> tuple[str, Path] | None:
    for origin, candidate in _stock_candidates(logical, lower_root, live_ok):
        if candidate.is_file():
            return origin, candidate
    return None


def _wanted_slots(config: Path) -> list[tuple[str, str, str]]:
    """Returns (logical path, role, action) of every slot worth replaying."""
    topology = _load(config / "device_font_topology.json")
    roles = _load(config / "device_font_roles.json").get("slots") or {}
    shadow = _load(config / "device_font_shadow_plan.json").get("slots") or {}
    targeted: set[str] = set()
    for plan_path in sorted((config / "universal-font-plans").glob("*.json")):
        targets = _load(plan_path).get("targets")
        if isinstance(targets, dict):
            targeted.update(str(path) for path in targets)
    result: list[tuple[str, str, str]] = []
    for logical, slot in sorted((topology.get("slots") or {}).items()):
        if not isinstance(slot, dict):
            continue
        role = str((roles.get(logical) or {}).get("role") or "")
        action = str((shadow.get(logical) or {}).get("action") or "")
        if role in SKIPPED_ROLES and logical not in targeted:
            continue
        result.append((logical, role, action))
    # Targets first, then non-preserved slots, then the preserved rest.
    rank = {"replace": 1, "conditional": 1, "specialized": 1, "review": 2}
    result.sort(key=lambda item: (0 if item[0] in targeted else rank.get(item[2], 3), item[0]))
    return result


def _recent_sources(config: Path) -> list[dict[str, Any]]:
    profiles = []
    for path in (config / "source-font-profiles").glob("*.json"):
        data = _load(path)
        if data.get("files"):
            profiles.append((int(data.get("generatedAt") or 0), path.name, data))
    profiles.sort(reverse=True)
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, name, data in profiles[:RECENT_PROFILES]:
        for item in data.get("files") or []:
            source = str(item.get("sourcePath") or "")
            if source and source not in seen:
                seen.add(source)
                result.append({"profile": name, "sourcePath": source, "bytes": int(item.get("bytes") or 0)})
    return result


def _write_tail(bundle: zipfile.ZipFile, path: Path, name: str) -> None:
    size = path.stat().st_size
    with path.open("rb") as handle:
        if size > LOG_TAIL_BYTES:
            handle.seek(size - LOG_TAIL_BYTES)
        bundle.writestr(name, handle.read())


def export(moddir: Path, output: Path, lower_root: Path) -> dict[str, Any]:
    config = moddir / "config"
    active = _active_font(config)
    # The live /system/fonts view is LuoShu's overlay while a font is active.
    live_ok = active in {"", "default"}
    index: dict[str, Any] = {
        "schema": SCHEMA,
        "generatedAt": int(time.time()),
        "module": {},
        "device": _props(),
        "activeFont": active,
        "stock": {},
        "stockSkipped": [],
        "sources": {},
        "sourcesSkipped": [],
    }
    for line in (moddir / "module.prop").read_text(encoding="utf-8", errors="replace").splitlines() \
            if (moddir / "module.prop").is_file() else []:
        key, sep, value = line.partition("=")
        if sep and key in {"version", "versionCode"}:
            index["module"][key] = value.strip()

    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + ".part")
    with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(config.iterdir()) if config.is_dir() else []:
            if path.is_file() and path.suffix in {".json", ".conf", ".state"} \
                    and path.stat().st_size <= CONFIG_FILE_LIMIT:
                bundle.write(path, f"config/{path.name}")
        for name in CONFIG_DIRS:
            root = config / name
            for path in sorted(root.rglob("*")) if root.is_dir() else []:
                if path.is_file() and path.stat().st_size <= CONFIG_FILE_LIMIT:
                    bundle.write(path, f"config/{name}/{path.relative_to(root)}")
        deployment = moddir / ".luoshu-runtime" / "deployment" / "deployment.json"
        if deployment.is_file():
            bundle.write(deployment, "runtime/deployment.json")
        for path in sorted((moddir / "logs").glob("*.log")) if (moddir / "logs").is_dir() else []:
            _write_tail(bundle, path, f"logs/{path.name}")

        stock_total = 0
        for logical, role, action in _wanted_slots(config):
            found = _resolve_stock(logical, lower_root, live_ok)
            if found is None:
                index["stockSkipped"].append({"path": logical, "reason": "no-stock-snapshot"})
                continue
            origin, actual = found
            size = actual.stat().st_size
            if action == "preserve" and size > SMALL_PRESERVED_LIMIT:
                index["stockSkipped"].append({"path": logical, "reason": "preserved-large", "bytes": size})
                continue
            if stock_total + size > STOCK_TOTAL_LIMIT:
                index["stockSkipped"].append({"path": logical, "reason": "size-limit", "bytes": size})
                continue
            stock_total += size
            name = "stock" + logical
            bundle.write(actual, name)
            index["stock"][logical] = {
                "file": name, "origin": origin, "role": role, "action": action,
                "bytes": size, "sha256": _sha256(actual),
            }

        source_total = 0
        for item in _recent_sources(config):
            source = Path(item["sourcePath"])
            if not source.is_file():
                index["sourcesSkipped"].append({"path": str(source), "reason": "missing"})
                continue
            size = source.stat().st_size
            if source_total + size > SOURCE_TOTAL_LIMIT:
                index["sourcesSkipped"].append({"path": str(source), "reason": "size-limit", "bytes": size})
                continue
            source_total += size
            name = f"sources/{len(index['sources']):02d}-{source.name}"
            bundle.write(source, name)
            index["sources"][str(source)] = {"file": name, "profile": item["profile"], "bytes": size}

        bundle.writestr("index.json", json.dumps(index, ensure_ascii=False, indent=2))
    os.replace(temp, output)
    try:
        os.chmod(output, 0o644)
    except OSError:
        pass
    return {
        "path": str(output),
        "bytes": output.stat().st_size,
        "stockCount": len(index["stock"]),
        "stockSkipped": len(index["stockSkipped"]),
        "sourceCount": len(index["sources"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--moddir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lower-root", type=Path,
                        default=Path(os.environ.get("LUOSHU_SELF_MOUNT_STATE_ROOT", "/data/adb/luoshu/self-mount")))
    args = parser.parse_args()
    try:
        result = export(args.moddir, args.output, args.lower_root)
    except (OSError, zipfile.BadZipFile, ValueError) as error:
        print(json.dumps({"status": "error", "message": f"诊断包生成失败：{error}"}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "ok", "data": result}, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
