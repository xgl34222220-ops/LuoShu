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
import errno
import hashlib
import json
import os
import posixpath
import re
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
        if origin == "lower":
            candidate = _snapshot_file(logical, lower_root / "lower", lower_layout=True)
        elif origin == "mirror":
            # The mirror prefix itself is trusted; aliases below it must stay
            # within the mirror, not resolve through the active system overlay.
            mirror = candidate
            for _part in Path(logical).relative_to("/").parts:
                mirror = mirror.parent
            candidate = _snapshot_file(logical, mirror, lower_layout=False)
        if candidate is not None and candidate.is_file():
            return origin, candidate
    return None


def _snapshot_path(logical: str, root: Path, lower_layout: bool) -> Path | None:
    parts = Path(logical).parts
    if not parts or parts[0] != "/" or ".." in parts or (len(parts) > 1 and parts[1] == "data"):
        return None
    if lower_layout:
        if len(parts) < 3 or parts[2] != "fonts":
            return None
        return root / f"{parts[1]}-fonts" / Path(*parts[3:])
    return root / Path(*parts[1:])


def _snapshot_logical(relative: Path, lower_layout: bool) -> str | None:
    parts = relative.parts
    if not parts or ".." in parts:
        return None
    if lower_layout:
        if not parts[0].endswith("-fonts"):
            return None
        return str(Path("/") / parts[0][:-6] / "fonts" / Path(*parts[1:]))
    return str(Path("/") / relative)


def _snapshot_file(logical: str, root: Path, *, lower_layout: bool) -> Path | None:
    """Resolve ROM aliases only through the trusted pre-mount snapshot.

    An absolute /system/fonts link copied into lower would normally open the
    active overlay. Rebase it into lower (including cross-partition aliases).
    Links to /data themes, missing lower targets and cycles have no stock input.
    """
    try:
        root = root.resolve(strict=True)
        if not root.is_dir():
            return None
        current = logical
        seen: set[str] = set()
        for _hop in range(40):
            if current in seen:
                return None
            seen.add(current)
            candidate = _snapshot_path(current, root, lower_layout)
            if candidate is None:
                return None
            parts = candidate.relative_to(root).parts
            for number in range(len(parts)):
                prefix = root / Path(*parts[:number + 1])
                if not prefix.is_symlink():
                    continue
                target = Path(os.readlink(prefix))
                # Internal snapshot links may use its physical layout; try
                # that interpretation before the original ROM path layout.
                physical = Path(posixpath.normpath(str(target if target.is_absolute() else prefix.parent / target)))
                try:
                    remapped = _snapshot_logical(physical.relative_to(root), lower_layout)
                except ValueError:
                    remapped = None
                if remapped is None:
                    source = _snapshot_logical(Path(*parts[:number + 1]), lower_layout)
                    if source is None:
                        return None
                    remapped = posixpath.normpath(str(target if target.is_absolute() else Path(source).parent / target))
                current = posixpath.normpath(str(Path(remapped) / Path(*parts[number + 1:])))
                break
            else:
                return candidate if candidate.is_file() else None
    except (OSError, RuntimeError, ValueError):
        return None
    return None


def _wanted_slots(config: Path, full: bool = False) -> list[tuple[str, str, str]]:
    """Returns (logical path, role, action) of every slot worth replaying.

    Engine v3 takes line metrics from the topology, so a lite bundle only needs
    the stock files the last build replaced (collection face counts), plus the
    small protected text bases admitted by the current partial-text policy.
    Hollowing every text font took too long on large OEM font sets."""
    # The engine itself imports this module's snapshot resolver. Import the
    # policy only when collecting, after both modules have finished loading.
    from luoshu_engine import is_partial_text_slot
    report = _load(config / "luoshu-engine-build" / "report.json")
    topology = _load(config / "device_font_topology.json")
    roles = _load(config / "device_font_roles.json").get("slots") or {}
    partial = [(logical, str((roles.get(logical) or {}).get("role") or ""), "partial-stock")
               for logical, slot in sorted((topology.get("slots") or {}).items())
               if isinstance(slot, dict) and is_partial_text_slot(logical, slot)]
    replaced = [item for item in report.get("replaced") or [] if item.get("path")]
    if replaced and not full:
        # Kept-stock slots too, so a replay can see why they were kept.
        kept = [item for item in report.get("keptStock") or [] if item.get("path")]
        wanted = [(str(item["path"]), str(item.get("role") or ""), "replace") for item in replaced] + \
            [(str(item["path"]), "", "kept") for item in kept]
        # A previous engine report did not list these protected faces. Keep
        # them for a faithful replay of the newly admitted partial routes.
        return list({item[0]: item for item in [*wanted, *partial]}.values())
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
        if is_partial_text_slot(logical, slot):
            action = "partial-stock"
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
                luoshu_merge.PARTIAL_TEXT_CODEPOINTS, font_coverage.CJK_COMMON, font_coverage.PUNCTUATION)
    for points in template.PROBE_GROUPS.values():
        keep.update(points)
    return keep


def _hollow_face(font: Any, keep_points: set[int]) -> None:
    from fontTools.ttLib.tables._g_l_y_f import Glyph
    from luoshu_merge import partial_ligatures
    cmap = font.getBestCmap() or {}
    keep = {".notdef"} | {name for point, name in cmap.items() if point in keep_points}
    # Partial text substitution also draws these unencoded GSUB outputs. Keep
    # only the same unambiguous Latin/text sequences admitted by the merger.
    keep.update(partial_ligatures(font).values())
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


FONT_SUFFIXES = (".ttf", ".otf", ".ttc", ".otc", ".font", ".woff", ".woff2")
THEME_FONT_DIR = Path("/data/system/theme/fonts")
PROCESS_EVIDENCE_LIMIT = 400
PROCESS_MAP_LIMIT = 256
PROCESS_READ_ERROR_LIMIT = 100


def _stat_text(path: Path) -> dict[str, Any]:
    try:
        info = path.stat()
    except OSError:
        return {}
    return {"dev": info.st_dev, "inode": info.st_ino, "bytes": info.st_size}


def _read_error(error: OSError) -> str:
    return errno.errorcode.get(error.errno, type(error).__name__)


def _font_map_candidate(path: str) -> str | None:
    """Retain explicitly font-named maps; never label every anonymous map a font."""
    lower = path.lower()
    if lower.startswith(("/memfd:", "memfd:", "[anon:", "[anon_shmem:")):
        if re.search(r"(?<![a-z0-9])fonts?(?![a-z0-9])", lower):
            return "font-named-memory"
        return None
    if not lower.startswith("/data/"):
        return None
    parts = lower.split("/")
    font_dirs = {"font", "fonts", "fontcache", "font-cache", "font_cache"}
    if any(part in font_dirs or re.match(r"^fonts?[-_](?:cache|preview|download)", part)
           for part in parts[:-1]) or re.search(r"(?<![a-z0-9])fonts?(?![a-z0-9])", parts[-1]):
        return "font-cache-path"
    return None


def _process_fonts(proc: Path = Path("/proc")) -> dict[str, Any]:
    """Read process map metadata, without opening any app assets or private files.

    A mapped font path or APK is evidence of a possible source, not proof of the
    Typeface used for a particular screen. Unknown, deleted and unreadable views
    remain explicit so a system-font map cannot hide the missing app evidence.
    """
    snapshot: dict[str, Any] = {
        "schema": "luoshu-process-fonts-v2", "capturedAt": int(time.time()),
        "renderingVerified": False, "processes": [], "processReadErrors": [],
        "procStatus": "read", "truncated": False,
    }
    processes = snapshot["processes"]
    named_processes = 0
    unreadable_names = 0
    try:
        entries = sorted((item for item in proc.iterdir() if item.name.isdigit()),
                         key=lambda item: int(item.name))
    except OSError as error:
        snapshot.update(procStatus="unavailable", procError=_read_error(error),
                        finishedAt=int(time.time()), observedProcessNames=[])
        return snapshot
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            name = (entry / "cmdline").read_bytes().split(b"\0", 1)[0].decode("utf-8", "replace")
        except OSError as error:
            unreadable_names += 1
            if len(snapshot["processReadErrors"]) < PROCESS_READ_ERROR_LIMIT:
                snapshot["processReadErrors"].append({"pid": int(entry.name),
                    "reason": "cmdline-unavailable", "error": _read_error(error)})
            continue
        if not name or name.startswith("/") or "." not in name and name not in {"system_server", "zygote", "zygote64"}:
            continue
        named_processes += 1
        if len(processes) >= PROCESS_EVIDENCE_LIMIT:
            continue
        fonts: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        apks: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        candidates: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        map_limits = {"fonts": False, "apkMaps": False, "fontCandidates": False}
        maps_status, maps_error = "read", None
        lines_seen = 0
        try:
            with (entry / "maps").open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    lines_seen += 1
                    parts = line.split(None, 5)
                    if len(parts) != 6 or not parts[4].isdigit() \
                            or not re.fullmatch(r"[0-9a-fA-F]+", parts[2]) \
                            or not re.fullmatch(r"[0-9a-fA-F]+:[0-9a-fA-F]+", parts[3]):
                        continue
                    path = parts[5].strip()
                    deleted = path.endswith(" (deleted)")
                    if deleted:
                        path = path[:-len(" (deleted)")]
                    record: dict[str, Any] = {"path": path, "device": parts[3], "inode": parts[4], "offset": parts[2]}
                    if deleted:
                        record["deleted"] = True
                    kind = None
                    if path.lower().endswith(FONT_SUFFIXES):
                        group, field = fonts, "fonts"
                    elif path.lower().endswith(".apk"):
                        group, field = apks, "apkMaps"
                    elif (kind := _font_map_candidate(path)) is not None:
                        record["kind"] = kind
                        group, field = candidates, "fontCandidates"
                    else:
                        continue
                    key = (path, parts[3], parts[4], parts[2])
                    if key in group or len(group) < PROCESS_MAP_LIMIT:
                        group[key] = record
                    else:
                        map_limits[field] = True
        except OSError as error:
            maps_status = "partial" if lines_seen else "unavailable"
            maps_error = _read_error(error)
        theme = _stat_text(entry / "root" / str(THEME_FONT_DIR).lstrip("/") / "Roboto-Regular.ttf")
        unknown = ["rendered-typeface-not-observed"]
        if apks:
            unknown.append("apk-font-use-unconfirmed")
        if candidates:
            unknown.append("opaque-or-memory-font-use-unconfirmed")
        if not fonts and not apks and not candidates:
            unknown.append("no-font-source-observed")
        if maps_status != "read":
            unknown.append("maps-unavailable" if maps_status == "unavailable" else "maps-partially-read")
        if any(map_limits.values()):
            unknown.append("map-evidence-truncated")
        row = {"pid": int(entry.name), "process": name, "theme": theme,
               "mapsStatus": maps_status, "fontSourceStatus": "unconfirmed", "unknownSources": unknown,
               "fonts": [fonts[key] for key in sorted(fonts)],
               "apkMaps": [apks[key] for key in sorted(apks)],
               "fontCandidates": [candidates[key] for key in sorted(candidates)]}
        if maps_error is not None:
            row["mapsError"] = maps_error
        if any(map_limits.values()):
            row["mapsTruncated"] = map_limits
        processes.append(row)
    snapshot.update(finishedAt=int(time.time()), observedProcessNames=sorted({row["process"] for row in processes}),
                    truncated=named_processes > len(processes), namedProcessCount=named_processes,
                    cmdlineUnreadableCount=unreadable_names,
                    processReadErrorsTruncated=unreadable_names > len(snapshot["processReadErrors"]))
    return snapshot


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
    # System files on some ROMs (ColorOS) carry 1970 mtimes, which zip rejects
    # unless timestamps are clamped.
    with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6,
                         strict_timestamps=False) as bundle:
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
        deployment = moddir / ".luoshu-payload" / ".luoshu-runtime" / "deployment" / "deployment.json"
        if deployment.is_file():
            bundle.write(deployment, "runtime/deployment.json")
        # FontManager dump captured by the last boot verification.
        dump = Path(os.environ.get("LUOSHU_VERIFY_STATE_ROOT", "/data/adb/luoshu/runtime-verify")) / "font-manager.txt"
        if dump.is_file():
            _write_tail(bundle, dump, "runtime/font-manager.txt")
        try:
            fonts_seen = _process_fonts()
            fonts_seen["themeGlobal"] = _stat_text(THEME_FONT_DIR / "Roboto-Regular.ttf")
            fonts_seen["themeViews"] = {path.name: _stat_text(path) for path in
                                        sorted((config / "hyperos-theme-font-early").glob("*.ttf"))}
            fonts_seen["themeViews"].update({path.name: _stat_text(path) for path in
                                             sorted((config / "hyperos-theme-font").glob("*.ttf"))})
            bundle.writestr("runtime/process-fonts.json", json.dumps(fonts_seen, ensure_ascii=False, indent=1))
        except Exception as error:  # evidence only; never fail the bundle over it
            bundle.writestr("runtime/process-fonts.json", json.dumps({"error": str(error)}))
        for path in sorted(THEME_FONT_DIR.glob("*")) if THEME_FONT_DIR.is_dir() else []:
            try:
                if path.is_file() and path.stat().st_size <= SMALL_PRESERVED_LIMIT:
                    bundle.write(path, f"theme/{path.name}")
            except OSError:
                pass
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
            if not full and action == "partial-stock" and size > SMALL_PRESERVED_LIMIT:
                index["stockSkipped"].append({"path": logical, "reason": "partial-stock-too-large", "bytes": size})
                continue
            if action == "preserve" and size > SMALL_PRESERVED_LIMIT:
                index["stockSkipped"].append({"path": logical, "reason": "preserved-large", "bytes": size})
                continue
            if stock_total + size > STOCK_TOTAL_LIMIT:
                index["stockSkipped"].append({"path": logical, "reason": "size-limit", "bytes": size})
                continue
            name = "stock" + logical
            try:
                # A partial output retains the stock's other glyphs and their
                # component dependencies. Hollowing its base would change the
                # merger's safety decisions and cannot faithfully replay it.
                hollow = _add_font(bundle, actual, name, None if action == "partial-stock" else scratch, keep_points)
            except (OSError, ValueError) as error:  # one unreadable slot must not lose the bundle
                index["stockSkipped"].append({"path": logical, "reason": f"error:{type(error).__name__}: {error}"[:200]})
                continue
            stock_total += size
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
            name = f"sources/{len(index['sources']):02d}-{source.name}"
            try:
                hollow = _add_font(bundle, source, name, scratch, keep_points)
            except (OSError, ValueError) as error:
                index["sourcesSkipped"].append({"path": str(source), "reason": f"error:{type(error).__name__}: {error}"[:200]})
                continue
            source_total += size
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
        print(json.dumps({"status": "error", "message": message}, ensure_ascii=False, separators=(",", ":")))
        return 1
    print(json.dumps({"status": "ok", "data": result}, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
