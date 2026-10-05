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
ORIGINAL_TEXT_FILE_LIMIT = 64 * 1024 * 1024
ORIGINAL_TEXT_TOTAL_LIMIT = 160 * 1024 * 1024
KNOWN_TEXT_STOCK_ROLES = {"ui-sans", "cjk", "latin", "clock", "numeric", "serif", "monospace", "special-fallback"}
STOCK_PROBE_BYTE_LIMIT = 128 * 1024 * 1024
STOCK_PROBE_TABLE_LIMIT = 4 * 1024 * 1024
STOCK_PROBE_FACE_LIMIT = 16
STOCK_PROBE_COLLECTION_LIMIT = 4096
STOCK_PROBE_CMAP_POINT_LIMIT = 500000
STOCK_PROBE_TIME_LIMIT = 30
HOLLOW_MARKER_TAG = "LSDG"
HOLLOW_MARKER_DATA = b"luoshu-diagnostic-hollow-v1\n"
CONFIG_FILE_LIMIT = 8 * 1024 * 1024
LOG_TAIL_BYTES = 512 * 1024
RECENT_PROFILES = 3
# Lite bundles hollow ordinary replacement/source fonts: tables, order, metrics,
# cmap and variation data stay, but only the glyphs the engine actually
# inspects or copies (probes, Latin, digits, punctuation) keep outlines.
# Protected text bases stay whole within their dedicated budget for faithful
# partial replay. Unknown stock still has the conservative small-file limit.
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
    """Select trusted text/unknown stock without relying on the last report.

    Every topology path is audited separately, including excluded paths. Lite
    exports keep protected text bases whole within a bounded budget and probe
    large ones' cmap/axes
    without loading their outlines. An old replacement report is never a
    complete inventory of possible English/digit routes.
    """
    # The engine itself imports this module's snapshot resolver. Import the
    # policy only when collecting, after both modules have finished loading.
    from luoshu_engine import _partial_path_supported, _partial_protected_identity, is_partial_text_slot
    report = _load(config / "luoshu-engine-build" / "report.json")
    topology = _load(config / "device_font_topology.json")
    roles = _load(config / "device_font_roles.json").get("slots") or {}
    replaced = [item for item in report.get("replaced") or [] if isinstance(item, dict) and item.get("path")]
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
        role = str((roles.get(logical) or {}).get("role") or "unknown-protected")
        action = str((shadow.get(logical) or {}).get("action") or "")
        if not _partial_path_supported(logical) or role in SKIPPED_ROLES or _partial_protected_identity(logical, slot):
            continue
        if is_partial_text_slot(logical, slot, role):
            action = "partial-stock"
        elif role == "unknown-protected":
            action = "audit-stock"
        elif logical in targeted:
            action = "replace"
        elif role in KNOWN_TEXT_STOCK_ROLES:
            action = "preserve"
        result.append((logical, role, action))
    # Targets first, then non-preserved slots, then the preserved rest.
    rank = {"replace": 1, "conditional": 1, "specialized": 1, "review": 2}
    result.sort(key=lambda item: (0 if item[0] in targeted else rank.get(item[2], 3), item[0]))
    return result


def _stock_coverage_audit(config: Path, wanted: list[tuple[str, str, str]]) -> dict[str, dict[str, Any]]:
    """Account for every topology path; an absent probe never means zero glyphs."""
    from luoshu_engine import _partial_path_supported, _partial_protected_identity
    topology = _load(config / "device_font_topology.json").get("slots") or {}
    roles = _load(config / "device_font_roles.json").get("slots") or {}
    selected = {logical: (role, action) for logical, role, action in wanted}
    result: dict[str, dict[str, Any]] = {}
    for logical, slot in sorted(topology.items()):
        role = str((roles.get(logical) or {}).get("role") or "unknown-protected")
        record: dict[str, Any] = {"role": role, "selected": False, "probeStatus": "not-probed",
                                  "faceCount": None, "faces": []}
        if logical in selected:
            record["action"] = selected[logical][1]
        else:
            reason = "invalid-topology-slot" if not isinstance(slot, dict) else \
                "unsupported-system-font-path" if not _partial_path_supported(logical) else \
                "excluded-emoji-or-symbol" if role in SKIPPED_ROLES or _partial_protected_identity(logical, slot) else \
                "not-selected"
            record.update(probeStatus="excluded", skippedReason=reason)
        result[logical] = record
    return result


def _original_stock_skip_reason(audit: dict[str, Any], role: str,
                                size: int, text_total: int) -> str | None:
    """Bound complete bases independently from hollow replay samples."""
    if audit.get("probeStatus") != "probed" or not audit.get("faces") or \
            any(face.get("status") != "probed" or face.get("hollowMarker") for face in audit["faces"]):
        return "original-stock-metadata-unproved"
    known_text = role in KNOWN_TEXT_STOCK_ROLES
    if not known_text:
        return "audit-stock-too-large" if size > SMALL_PRESERVED_LIMIT else None
    if size > SMALL_PRESERVED_LIMIT and not any(
            (face.get("asciiLetters") or 0) > 0 or (face.get("asciiDigits") or 0) > 0 for face in audit["faces"]):
        return "original-stock-ascii-text-unproved"
    if size > ORIGINAL_TEXT_FILE_LIMIT:
        return "original-text-file-limit"
    if text_total + size > ORIGINAL_TEXT_TOTAL_LIMIT:
        return "original-text-total-limit"
    return None


def _probe_stock_coverage(path: Path, budget: dict[str, Any]) -> dict[str, Any]:
    """Read bounded sfnt metadata only; never load glyf/CFF/gvar outlines."""
    from fontTools.ttLib import TTFont
    result: dict[str, Any] = {"probeStatus": "unavailable", "faceCount": None, "faces": [],
                              "metadataBytes": 0}
    if time.monotonic() >= budget["deadline"]:
        result["probeReason"] = "metadata-time-limit"
        return result
    try:
        size = path.stat().st_size
        with path.open("rb") as stream:
            header = stream.read(12)
            if len(header) < 12:
                raise ValueError("truncated-font-header")
            collection = header[:4] == b"ttcf"
            count = struct.unpack(">I", header[8:12])[0] if collection else 1
            result["container"] = "collection" if collection else "sfnt"
            result["faceCount"] = count
            if not count or count > STOCK_PROBE_COLLECTION_LIMIT:
                result["probeReason"] = "collection-directory-limit"
                return result
            if collection:
                directory = stream.read(4 * min(count, STOCK_PROBE_FACE_LIMIT))
                if len(directory) != 4 * min(count, STOCK_PROBE_FACE_LIMIT):
                    raise ValueError("truncated-collection-directory")
                offsets = struct.unpack(">" + "I" * min(count, STOCK_PROBE_FACE_LIMIT), directory)
            else:
                offsets = (0,)
            for number, offset in enumerate(offsets):
                face: dict[str, Any] = {"index": number, "status": "unavailable",
                                         "asciiLetters": None, "asciiDigits": None, "axes": None}
                result["faces"].append(face)
                if time.monotonic() >= budget["deadline"]:
                    face["reason"] = "metadata-time-limit"
                    break
                try:
                    if offset > size - 12:
                        raise ValueError("face-directory-out-of-bounds")
                    stream.seek(offset)
                    sfnt = stream.read(12)
                    table_count = struct.unpack(">H", sfnt[4:6])[0]
                    if table_count > 128:
                        face["reason"] = "face-table-count-limit"
                        continue
                    table_bytes = stream.read(table_count * 16)
                    if len(table_bytes) != table_count * 16:
                        raise ValueError("truncated-face-directory")
                    tables = {}
                    for number_table in range(table_count):
                        tag, _checksum, table_offset, length = struct.unpack(">4sIII", table_bytes[number_table * 16:(number_table + 1) * 16])
                        if table_offset > size or length > size - table_offset:
                            raise ValueError("font-table-out-of-bounds")
                        tables[tag.decode("latin-1")] = length
                    face["format"] = "TrueType" if "glyf" in tables else "CFF2" if "CFF2" in tables else \
                        "CFF" if "CFF " in tables else "unknown"
                    face["variable"] = "fvar" in tables
                    face["hollowMarker"] = HOLLOW_MARKER_TAG in tables
                    metadata_size = 12 + table_count * 16 + sum(tables.get(tag, 0) for tag in ("cmap", "fvar", "maxp"))
                    if any(tables.get(tag, 0) > STOCK_PROBE_TABLE_LIMIT for tag in ("cmap", "fvar", "maxp")):
                        face["reason"] = "metadata-table-size-limit"
                        continue
                    if budget["bytes"] + metadata_size > STOCK_PROBE_BYTE_LIMIT:
                        face["reason"] = "metadata-byte-limit"
                        continue
                    budget["bytes"] += metadata_size
                    result["metadataBytes"] += metadata_size
                    font = TTFont(str(path), fontNumber=number, lazy=True, recalcBBoxes=False, recalcTimestamp=False)
                    try:
                        # cmap normally asks post/CFF for glyph names. Synthetic
                        # names let metadata probes avoid loading any outlines.
                        font.setGlyphOrder([f"g{glyph}" for glyph in range(font["maxp"].numGlyphs)])
                        points: set[int] = set()
                        if "cmap" in font:
                            if not _bounded_cmap(font.getTableData("cmap")):
                                face["reason"] = "metadata-cmap-expansion-limit"
                                continue
                            for table in font["cmap"].tables:
                                if table.isUnicode() and table.format != 14:
                                    points.update(table.cmap)
                        axes = []
                        if "fvar" in font:
                            variation_data = font.getTableData("fvar")
                            if len(variation_data) < 16 or struct.unpack_from(">H", variation_data, 8)[0] > 64 \
                                    or struct.unpack_from(">H", variation_data, 12)[0] > 1024:
                                face["reason"] = "metadata-axis-count-limit"
                                continue
                            for axis in font["fvar"].axes[:16]:
                                axes.append({"tag": axis.axisTag, "min": axis.minValue,
                                             "default": axis.defaultValue, "max": axis.maxValue})
                            if len(font["fvar"].axes) > 16:
                                face["axesTruncated"] = True
                        face.update(status="probed", asciiLetters=sum(point in points for point in
                                    range(65, 91)) + sum(point in points for point in range(97, 123)),
                                    asciiDigits=sum(point in points for point in range(48, 58)), axes=axes)
                    finally:
                        font.close()
                except Exception as error:  # malformed metadata must not lose other paths
                    face["reason"] = f"metadata-error:{type(error).__name__}:{error}"[:200]
            if count > STOCK_PROBE_FACE_LIMIT:
                result["facesTruncated"] = True
                result["probeReason"] = "metadata-face-count-limit"
            completed = sum(face["status"] == "probed" for face in result["faces"])
            result["probeStatus"] = "probed" if completed == count else "partial" if completed else "unavailable"
    except (OSError, ValueError, struct.error) as error:
        result["probeReason"] = f"metadata-error:{type(error).__name__}:{error}"[:200]
    return result


def _bounded_cmap(data: bytes) -> bool:
    """Reject malformed/huge cmap expansions before fontTools allocates maps."""
    try:
        count = struct.unpack_from(">H", data, 2)[0]
        if count > 128 or len(data) < 4 + count * 8:
            return False
        points = 0
        seen: set[int] = set()
        for index in range(count):
            platform, encoding, offset = struct.unpack_from(">HHI", data, 4 + index * 8)
            # fontTools decompiles all subtables, including non-Unicode ones.
            # Validate their expansions too before asking for Unicode coverage.
            if offset in seen:
                continue
            seen.add(offset)
            fmt = struct.unpack_from(">H", data, offset)[0]
            if fmt in {12, 13}:
                groups = struct.unpack_from(">I", data, offset + 12)[0]
                if groups > STOCK_PROBE_CMAP_POINT_LIMIT or offset + 16 + groups * 12 > len(data):
                    return False
                for group in range(groups):
                    start, end, _glyph = struct.unpack_from(">III", data, offset + 16 + group * 12)
                    if start > end or end > 0x10FFFF:
                        return False
                    points += end - start + 1
                    if points > STOCK_PROBE_CMAP_POINT_LIMIT:
                        return False
            elif fmt == 4:
                segments = struct.unpack_from(">H", data, offset + 6)[0] // 2
                if offset + 16 + segments * 8 > len(data):
                    return False
                for segment in range(segments):
                    end = struct.unpack_from(">H", data, offset + 14 + segment * 2)[0]
                    start = struct.unpack_from(">H", data, offset + 16 + segments * 2 + segment * 2)[0]
                    if start > end:
                        return False
                    points += end - start + 1
            elif fmt in {6, 10}:
                points += struct.unpack_from(">H" if fmt == 6 else ">I", data,
                                             offset + (8 if fmt == 6 else 16))[0]
            elif fmt == 0:
                points += 256
            elif fmt == 2:
                points += 65536  # legacy two-byte encoding has a finite domain
            elif fmt == 14:
                selectors = struct.unpack_from(">I", data, offset + 6)[0]
                if selectors > 256 or offset + 10 + selectors * 11 > len(data):
                    return False
                for selector in range(selectors):
                    record = offset + 10 + selector * 11
                    default, nondefault = struct.unpack_from(">II", data, record + 3)
                    if default:
                        ranges = struct.unpack_from(">I", data, offset + default)[0]
                        if ranges > STOCK_PROBE_CMAP_POINT_LIMIT or offset + default + 4 + ranges * 4 > len(data):
                            return False
                        for number_range in range(ranges):
                            location = offset + default + 4 + number_range * 4
                            start = int.from_bytes(data[location:location + 3], "big")
                            additional = data[location + 3]
                            if start + additional > 0x10FFFF:
                                return False
                            points += additional + 1
                            if points > STOCK_PROBE_CMAP_POINT_LIMIT:
                                return False
                    if nondefault:
                        mappings = struct.unpack_from(">I", data, offset + nondefault)[0]
                        if offset + nondefault + 4 + mappings * 5 > len(data):
                            return False
                        points += mappings
            else:
                return False  # unsupported Unicode formats remain explicitly unknown
            if points > STOCK_PROBE_CMAP_POINT_LIMIT:
                return False
        return True
    except (struct.error, IndexError):
        return False


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
    from fontTools.ttLib.tables.DefaultTable import DefaultTable
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
    # Hollow files are evidence/replay samples, never valid original bases for
    # partial replacement. Keep this marker inside every sfnt/TTC face so it
    # survives a rename, extraction, or loss of the diagnostic index.
    marker = DefaultTable(HOLLOW_MARKER_TAG)
    marker.data = HOLLOW_MARKER_DATA
    font[HOLLOW_MARKER_TAG] = marker


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
    wanted = _wanted_slots(config, full)
    coverage_audit = _stock_coverage_audit(config, wanted)
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
        "stockCoverageAudit": coverage_audit,
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
        fonts_seen: dict[str, Any] = {}
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
        original_text_total = 0
        probe_budget = {"bytes": 0, "deadline": time.monotonic() + STOCK_PROBE_TIME_LIMIT}
        for logical, audit in coverage_audit.items():
            if audit["probeStatus"] == "excluded":
                index["stockSkipped"].append({"path": logical, "reason": audit["skippedReason"]})
        observed_paths = {str(record.get("path") or "") for process in fonts_seen.get("processes") or []
                          for record in process.get("fonts") or []}
        # A maps observation only prioritizes source evidence collection; it
        # does not confirm which font rendered a particular string.
        wanted.sort(key=lambda item: (item[0] not in observed_paths,
                    0 if item[1] in KNOWN_TEXT_STOCK_ROLES else 1, item[0]))
        prepared_stocks: list[tuple[str, str, str, str, Path, int]] = []
        for logical, role, action in wanted:
            audit = coverage_audit[logical]
            try:
                found = _resolve_stock(logical, lower_root, live_ok)
            except OSError as error:
                reason = f"snapshot-unreadable:{_read_error(error)}"
                audit.update(probeStatus="unavailable", skippedReason=reason)
                index["stockSkipped"].append({"path": logical, "reason": reason})
                continue
            if found is None:
                audit.update(probeStatus="unavailable", skippedReason="no-stock-snapshot")
                index["stockSkipped"].append({"path": logical, "reason": "no-stock-snapshot"})
                continue
            origin, actual = found
            try:
                size = actual.stat().st_size
            except OSError as error:
                reason = f"snapshot-unreadable:{_read_error(error)}"
                audit.update(probeStatus="unavailable", skippedReason=reason)
                index["stockSkipped"].append({"path": logical, "reason": reason})
                continue
            audit.update(origin=origin, bytes=size)
            audit.update(_probe_stock_coverage(actual, probe_budget))
            prepared_stocks.append((logical, role, action, origin, actual, size))
        # Probe every source before hashing/compressing full originals, so a
        # large copy does not consume the bounded metadata inspection time.
        for logical, role, action, origin, actual, size in prepared_stocks:
            audit = coverage_audit[logical]
            original = action in {"partial-stock", "audit-stock", "preserve"}
            reason = _original_stock_skip_reason(audit, role, size, original_text_total) if not full and original else None
            if reason is not None:
                audit["skippedReason"] = reason
                index["stockSkipped"].append({"path": logical, "reason": reason, "bytes": size})
                continue
            if stock_total + size > STOCK_TOTAL_LIMIT:
                audit["skippedReason"] = "size-limit"
                index["stockSkipped"].append({"path": logical, "reason": "size-limit", "bytes": size})
                continue
            name = "stock" + logical
            try:
                # A partial output retains the stock's other glyphs and their
                # component dependencies. Hollowing its base would change the
                # merger's safety decisions and cannot faithfully replay it.
                hollow = _add_font(bundle, actual, name, None if original else scratch, keep_points)
                digest = _sha256(actual)
            except (OSError, ValueError) as error:  # one unreadable slot must not lose the bundle
                reason = f"error:{type(error).__name__}: {error}"[:200]
                audit["skippedReason"] = reason
                index["stockSkipped"].append({"path": logical, "reason": reason})
                continue
            stock_total += size
            if original and role in KNOWN_TEXT_STOCK_ROLES:
                original_text_total += size
            index["stock"][logical] = {
                "file": name, "origin": origin, "role": role, "action": action,
                "bytes": size, "sha256": digest, "hollow": hollow,
            }
            audit.update(selected=True, file=name, hollow=hollow)
        index["stockCoverageAuditSummary"] = {
            "pathCount": len(coverage_audit), "selectedCount": len(index["stock"]),
            "probedCount": sum(row["probeStatus"] == "probed" for row in coverage_audit.values()),
            "partialCount": sum(row["probeStatus"] == "partial" for row in coverage_audit.values()),
            "unknownCount": sum(row["probeStatus"] in {"unavailable", "not-probed"} for row in coverage_audit.values()),
            "excludedCount": sum(row["probeStatus"] == "excluded" for row in coverage_audit.values()),
            "metadataBytes": probe_budget["bytes"], "metadataByteLimit": STOCK_PROBE_BYTE_LIMIT,
            "metadataFaceLimit": STOCK_PROBE_FACE_LIMIT, "metadataTimeLimitSeconds": STOCK_PROBE_TIME_LIMIT,
            "originalTextBytes": original_text_total, "originalTextFileLimit": ORIGINAL_TEXT_FILE_LIMIT,
            "originalTextTotalLimit": ORIGINAL_TEXT_TOTAL_LIMIT, "originalTextLimitApplied": not full,
            "stockBytes": stock_total, "stockTotalLimit": STOCK_TOTAL_LIMIT,
            "capturePriority": "observed-system-maps-then-known-text-semantics",
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
