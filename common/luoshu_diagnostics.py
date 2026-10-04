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
import struct
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

SCHEMA = "luoshu-engine-diagnostic-v1"
STOCK_TOTAL_LIMIT = 600 * 1024 * 1024
SOURCE_TOTAL_LIMIT = 400 * 1024 * 1024
SMALL_PRESERVED_LIMIT = 2 * 1024 * 1024
CONFIG_FILE_LIMIT = 8 * 1024 * 1024
LOG_TAIL_BYTES = 512 * 1024
RECENT_PROFILES = 3
# Lite bundles (default) hollow every font: all tables, glyph order, metrics,
# cmap and variation data stay, but only the glyphs the engine actually
# inspects or copies (probes, Latin, digits, punctuation) keep outlines.
SKIPPED_ROLES = {"emoji", "symbol-icon"}
CONFIG_DIRS = (
    "font-config-source",
    "luoshu-engine-build",
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


def _wanted_slots(config: Path, full: bool = False) -> list[tuple[str, str, str]]:
    """Returns (logical path, role, action) of every slot worth replaying.

    Engine v3 takes line metrics from the topology, so a lite bundle only needs
    the stock files the last build replaced (collection face counts); hollowing
    every text font took too long on phones with large OEM font sets."""
    report = _load(config / "luoshu-engine-build" / "report.json")
    replaced = [item for item in report.get("replaced") or [] if item.get("path")]
    if replaced and not full:
        return [(str(item["path"]), str(item.get("role") or ""), "replace") for item in replaced]
    topology = _load(config / "device_font_topology.json")
    roles = _load(config / "device_font_roles.json").get("slots") or {}
    shadow = _load(config / "device_font_shadow_plan.json").get("slots") or {}
    targeted: set[str] = {str(item["path"]) for item in replaced}
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
    """Source fonts of the last engine build (its report records the spec)."""
    spec = _load(config / "luoshu-engine-build" / "report.json").get("sources") or {}
    paths = list(spec.get("files") or [])
    for role in (spec.get("roles") or {}).values():
        paths.extend((role or {}).get("files") or [])
    result: list[dict[str, Any]] = []
    for source in dict.fromkeys(str(path) for path in paths):
        result.append({"profile": "luoshu-engine-build", "sourcePath": source})
    return result


def _keep_codepoints() -> set[int]:
    import device_font_template as template
    import font_coverage
    import luoshu_merge
    keep = set(range(0x20, 0x7F)) | set(range(0xA0, 0x180))
    keep.update(luoshu_merge.LATIN_CODEPOINTS, luoshu_merge.DIGIT_CODEPOINTS,
                font_coverage.CJK_COMMON, font_coverage.PUNCTUATION)
    for points in template.PROBE_GROUPS.values():
        keep.update(points)
    return keep


def _hollow_face(font: Any, keep_points: set[int]) -> None:
    from fontTools.ttLib.tables._g_l_y_f import Glyph
    cmap = font.getBestCmap() or {}
    keep = {".notdef"} | {name for point, name in cmap.items() if point in keep_points}
    if "glyf" in font:
        glyf = font["glyf"]
        # Keep the glyphs that set the font's extreme bounds, read from each
        # glyph header without expanding outlines, so bbox checks still match.
        extremes: dict[int, tuple[int, str]] = {}
        for name, glyph in glyf.glyphs.items():
            data = getattr(glyph, "data", None)
            if data and len(data) >= 10:
                bounds = struct.unpack(">hhhhh", data[:10])[1:]
            elif hasattr(glyph, "xMin"):
                bounds = (glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax)
            else:
                continue
            for index, value in enumerate(bounds):
                key = value if index >= 2 else -value
                if index not in extremes or key > extremes[index][0]:
                    extremes[index] = (key, name)
        keep.update(name for _, name in extremes.values())
        pending = list(keep)
        while pending:
            name = pending.pop()
            if name in glyf.glyphs and glyf[name].isComposite():
                for component in glyf[name].getComponentNames(glyf):
                    if component not in keep:
                        keep.add(component)
                        pending.append(component)
        for name in font.getGlyphOrder():
            if name not in keep:
                glyf.glyphs[name] = Glyph()
        if "gvar" in font:
            variations = font["gvar"].variations
            for name in font.getGlyphOrder():
                if name not in keep and name in variations:
                    variations[name] = []
    for tag in ("CFF ", "CFF2"):
        if tag not in font:
            continue
        top = font[tag].cff.topDictIndex[0]
        strings = top.CharStrings
        for name in font.getGlyphOrder():
            if name in keep or name not in strings:
                continue
            charstring = strings[name]
            charstring.decompile()
            charstring.program = [] if tag == "CFF2" else ["endchar"]


def _hollow(source: Path, target: Path, keep_points: set[int]) -> None:
    from fontTools.ttLib import TTCollection, TTFont
    with source.open("rb") as handle:
        collection = handle.read(4) == b"ttcf"
    if collection:
        fonts = TTCollection(str(source), lazy=True, recalcBBoxes=False, recalcTimestamp=False)
        for face in fonts.fonts:
            _hollow_face(face, keep_points)
        fonts.save(str(target))
        fonts.close()
        return
    font = TTFont(str(source), lazy=True, recalcBBoxes=False, recalcTimestamp=False)
    try:
        _hollow_face(font, keep_points)
        font.save(str(target))
    finally:
        font.close()


def _add_font(bundle: zipfile.ZipFile, actual: Path, name: str, scratch: Path | None,
              keep_points: set[int] | None) -> bool:
    """Writes the font, hollowed in lite mode; returns whether it was hollowed."""
    if scratch is None or keep_points is None:
        bundle.write(actual, name)
        return False
    target = scratch / "font"
    try:
        _hollow(actual, target, keep_points)
    except Exception:  # unusual container: ship it whole rather than drop it
        bundle.write(actual, name)
        return False
    bundle.write(target, name)
    target.unlink()
    return True


def _write_tail(bundle: zipfile.ZipFile, path: Path, name: str) -> None:
    size = path.stat().st_size
    with path.open("rb") as handle:
        if size > LOG_TAIL_BYTES:
            handle.seek(size - LOG_TAIL_BYTES)
        bundle.writestr(name, handle.read())


def export(moddir: Path, output: Path, lower_root: Path, full: bool = False) -> dict[str, Any]:
    config = moddir / "config"
    keep_points = None if full else _keep_codepoints()
    active = _active_font(config)
    # The live /system/fonts view is LuoShu's overlay while a font is active.
    live_ok = active in {"", "default"}
    index: dict[str, Any] = {
        "schema": SCHEMA,
        "generatedAt": int(time.time()),
        "mode": "full" if full else "lite",
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
    scratch_dir = None if full else tempfile.TemporaryDirectory(prefix="luoshu-diag-", dir=str(output.parent))
    scratch = None if scratch_dir is None else Path(scratch_dir.name)
    with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(config.iterdir()) if config.is_dir() else []:
            if path.is_file() and path.suffix in {".json", ".conf", ".state"} \
                    and path.stat().st_size <= CONFIG_FILE_LIMIT:
                bundle.write(path, f"config/{path.name}")
        for name in CONFIG_DIRS:
            root = config / name
            for path in sorted(root.rglob("*")) if root.is_dir() else []:
                if name == "luoshu-engine-build" and path.suffix != ".json":
                    continue  # the built payload fonts are reproducible
                if path.is_file() and path.stat().st_size <= CONFIG_FILE_LIMIT:
                    bundle.write(path, f"config/{name}/{path.relative_to(root)}")
        deployment = moddir / ".luoshu-runtime" / "deployment" / "deployment.json"
        if deployment.is_file():
            bundle.write(deployment, "runtime/deployment.json")
        # FontManager dump captured by the last boot verification.
        dump = Path(os.environ.get("LUOSHU_VERIFY_STATE_ROOT", "/data/adb/luoshu/runtime-verify")) / "font-manager.txt"
        if dump.is_file():
            _write_tail(bundle, dump, "runtime/font-manager.txt")
        for path in sorted((moddir / "logs").glob("*.log")) if (moddir / "logs").is_dir() else []:
            _write_tail(bundle, path, f"logs/{path.name}")

        stock_total = 0
        for logical, role, action in _wanted_slots(config, full):
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
            hollow = _add_font(bundle, actual, name, scratch, keep_points)
            index["stock"][logical] = {
                "file": name, "origin": origin, "role": role, "action": action,
                "bytes": size, "sha256": _sha256(actual), "hollow": hollow,
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
            hollow = _add_font(bundle, source, name, scratch, keep_points)
            index["sources"][str(source)] = {
                "file": name, "profile": item["profile"], "bytes": size, "hollow": hollow,
            }

        bundle.writestr("index.json", json.dumps(index, ensure_ascii=False, indent=2))
    if scratch_dir is not None:
        scratch_dir.cleanup()
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
        "mode": index["mode"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--moddir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lower-root", type=Path,
                        default=Path(os.environ.get("LUOSHU_SELF_MOUNT_STATE_ROOT", "/data/adb/luoshu/self-mount")))
    parser.add_argument("--full", action="store_true", help="ship fonts whole instead of hollowed")
    args = parser.parse_args()
    try:
        result = export(args.moddir, args.output, args.lower_root, args.full)
    except Exception as error:  # report every failure to the App, never a bare exit
        import traceback
        try:
            log = args.moddir / "logs" / "diagnostics.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a", encoding="utf-8") as handle:
                handle.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + traceback.format_exc() + "\n")
        except OSError:
            pass
        message = f"诊断包生成失败：{type(error).__name__}: {error}"[:300]
        print(json.dumps({"status": "error", "message": message}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "ok", "data": result}, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
