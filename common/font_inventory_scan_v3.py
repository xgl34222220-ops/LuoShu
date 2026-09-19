#!/usr/bin/env python3
"""Extended stock-font inventory scanner.

Revision 4 keeps replaceable slots restricted to the partitions supported by the
runtime, adds a vendor-independent verified text scan, and persists an install-time
path probe even when the current boot still has an older font overlay mounted.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Iterable

import font_inventory as base
import font_inventory_scan as v2
from hyperos_physical_policy import (PARTITIONS as HYPEROS_PARTITIONS, safe_physical_font_name,
                                    DYNAMIC_OVERLAY_PATH, DYNAMIC_OVERLAY_TARGET)

SCANNER_REVISION = 4
CANDIDATE_SCHEMA = "device-font-candidates-v1"
METRICS_REVISION = 3
# Re-scan trusted stock metrics for Latin UI families restored after v4.3.0.
HYPEROS_COVERAGE_REVISION = 4
PRIMARY_FONT_SPECS = (
    ("system", Path("/system/fonts"), "system_fonts", (Path("/system/font"),)),
    ("system_ext", Path("/system_ext/fonts"), "system_ext_fonts", (Path("/system/system_ext/fonts"),)),
    ("product", Path("/product/fonts"), "product_fonts", (Path("/system/product/fonts"),)),
    ("my_product", Path("/my_product/fonts"), "my_product_fonts", (Path("/system/my_product/fonts"),)),
    ("vendor", Path("/vendor/fonts"), "vendor_fonts", (Path("/system/vendor/fonts"),)),
)
PRIMARY_ETC_SPECS = (
    ("system", Path("/system/etc"), "system_etc", ()),
    ("system_ext", Path("/system_ext/etc"), "system_ext_etc", (Path("/system/system_ext/etc"),)),
    ("product", Path("/product/etc"), "product_etc", (Path("/system/product/etc"),)),
    ("my_product", Path("/my_product/etc"), "my_product_etc", (Path("/system/my_product/etc"),)),
    ("vendor", Path("/vendor/etc"), "vendor_etc", (Path("/system/vendor/etc"),)),
)
AUX_FONT_SPECS = (
    ("odm", Path("/odm/fonts"), "odm_fonts"),
    ("oem", Path("/oem/fonts"), "oem_fonts"),
    ("my_engineering", Path("/my_engineering/fonts"), "my_engineering_fonts"),
    ("my_company", Path("/my_company/fonts"), "my_company_fonts"),
    ("my_preload", Path("/my_preload/fonts"), "my_preload_fonts"),
    ("my_region", Path("/my_region/fonts"), "my_region_fonts"),
    ("my_stock", Path("/my_stock/fonts"), "my_stock_fonts"),
    ("oplus_product", Path("/oplus_product/fonts"), "oplus_product_fonts"),
    ("oplus_engineering", Path("/oplus_engineering/fonts"), "oplus_engineering_fonts"),
    ("oplus_version", Path("/oplus_version/fonts"), "oplus_version_fonts"),
    ("oplus_region", Path("/oplus_region/fonts"), "oplus_region_fonts"),
    ("mi_ext", Path("/mi_ext/fonts"), "mi_ext_fonts"),
    ("cust", Path("/cust/fonts"), "cust_fonts"),
    ("hw_product", Path("/hw_product/fonts"), "hw_product_fonts"),
)
AUX_ETC_SPECS = (
    ("odm", Path("/odm/etc"), "odm_etc"),
    ("oem", Path("/oem/etc"), "oem_etc"),
    ("my_engineering", Path("/my_engineering/etc"), "my_engineering_etc"),
    ("my_company", Path("/my_company/etc"), "my_company_etc"),
    ("my_preload", Path("/my_preload/etc"), "my_preload_etc"),
    ("my_region", Path("/my_region/etc"), "my_region_etc"),
    ("my_stock", Path("/my_stock/etc"), "my_stock_etc"),
    ("oplus_product", Path("/oplus_product/etc"), "oplus_product_etc"),
    ("oplus_engineering", Path("/oplus_engineering/etc"), "oplus_engineering_etc"),
    ("oplus_version", Path("/oplus_version/etc"), "oplus_version_etc"),
    ("oplus_region", Path("/oplus_region/etc"), "oplus_region_etc"),
    ("mi_ext", Path("/mi_ext/etc"), "mi_ext_etc"),
    ("cust", Path("/cust/etc"), "cust_etc"),
    ("hw_product", Path("/hw_product/etc"), "hw_product_etc"),
)
THEME_FONT_ROOTS = (
    Path("/data/system/theme/fonts"),
    Path("/data/system/theme_magic/fonts"),
    Path("/data/themes"),
    Path("/data/theme/fonts"),
    Path("/data/fonts/files"),
    Path("/data/bbkcore/theme"),
    Path("/data/oplus/uxres/theme"),
    Path("/data/skin/fonts"),
)
ROM_FONT_MARKERS = {
    "hyperos": ("MiSansVF.ttf", "MiSansVF_Overlay.ttf", "MiLanProVF.ttf", "MiSans-Regular.ttf", "XiaomiSansVF.ttf"),
    "coloros": ("SysSans-Hans-Regular.ttf", "SysFont-Hans-Regular.ttf", "OPlusSans3.0.ttf", "ColorOSUI-Regular.ttf"),
    "originos": ("VivoFont.ttf", "DroidSansFallbackBBK.ttf"),
    "oneui": ("SamsungOneUI-Regular.ttf", "SECRobotoLight-Regular.ttf"),
    "flyme": ("FlymeSans-Regular.ttf",),
    "harmonyos": ("HarmonyOS_Sans_SC_Regular.ttf", "HwChinese-Medium.ttf"),
    "magicos": ("HONORSansVF.ttf",),
    "aosp": ("Roboto-Regular.ttf", "NotoSansCJK-Regular.ttc", "NotoSansSC-VF.otf"),
}


def _probe_font_roots(args: Any) -> list[base.FontRoot]:
    """Pick the live/explicit font directories without requiring stock trust.

    This pass records paths only. It intentionally does not call _read_metrics(),
    so an already-mounted old LuoShu payload cannot poison stock metric contracts.
    """
    roots: list[base.FontRoot] = []
    for partition, logical, argument, aliases in PRIMARY_FONT_SPECS:
        explicit = getattr(args, argument)
        if explicit is not None:
            actual = explicit
        else:
            actual = next((candidate for candidate in (logical, *aliases) if candidate.is_dir()), logical)
        roots.append(base.FontRoot(partition, logical, actual))
    for partition, logical, argument in AUX_FONT_SPECS:
        explicit = getattr(args, argument)
        roots.append(base.FontRoot(partition, logical, explicit if explicit is not None else logical))
    return roots


def _write_live_candidate_probe(args: Any, output: Path) -> dict[str, Any]:
    """Persist every visible font path before trusted stock metric resolution.

    A Root manager's merged view still exposes the device's physical filenames even
    while some files are replaced. This gives installation a device-specific slot
    map on every phone; the trusted scanner later decides which candidates are safe
    UI text slots and attaches stock metrics.
    """
    entries: dict[str, dict[str, Any]] = {}
    for root in _probe_font_roots(args):
        if not root.actual.is_dir():
            continue
        try:
            paths = sorted(root.actual.rglob("*"), key=lambda item: str(item).lower())
        except OSError:
            continue
        for actual in paths:
            if actual.suffix.lower() not in base.FONT_EXTENSIONS:
                continue
            try:
                if not (actual.is_file() or actual.is_symlink()):
                    continue
                relative = actual.relative_to(root.actual)
            except (OSError, ValueError):
                continue
            logical = str(root.logical / relative)
            lowered = actual.name.lower()
            denied = any(token in lowered for token in base.GENERIC_DENY_FILE_TOKENS)
            denied = denied or any(token in lowered for token in base.GENERIC_DENY_STYLE_TOKENS)
            entries[logical] = {
                "path": logical,
                "partition": root.partition,
                "slotName": actual.name,
                "candidate": not denied,
                "reason": "specialized-name" if denied else "visible-font-path",
            }
    payload = {
        "schema": CANDIDATE_SCHEMA,
        "generatedAt": int(time.time()),
        "fontFileCount": len(entries),
        "candidateCount": sum(1 for entry in entries.values() if entry["candidate"]),
        "paths": [entries[path] for path in sorted(entries)],
    }
    base._atomic_write(output, payload)
    return payload


def _resolve_actual(logical: Path, explicit: Path | None, aliases: Iterable[Path], overlay_risk: bool) -> Path:
    if explicit is not None:
        return explicit
    candidates = (logical, *tuple(aliases))
    if overlay_risk:
        existing = False
        last_error: Exception | None = None
        for candidate in candidates:
            existing = existing or candidate.exists()
            try:
                resolved = base._pick_actual_root(candidate, None, True)
            except base.InventoryError as error:
                last_error = error
                continue
            if resolved.is_dir():
                return resolved
        if not existing:
            return logical
        if last_error is not None:
            raise last_error
        raise base.InventoryError(f"字体覆盖仍在活动，无法安全读取原厂目录：{logical}")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return logical


def _resolve_primary_font_roots(args: Any, overlay_risk: bool) -> list[base.FontRoot]:
    return [
        base.FontRoot(partition, logical, _resolve_actual(logical, getattr(args, argument), aliases, overlay_risk))
        for partition, logical, argument, aliases in PRIMARY_FONT_SPECS
    ]


def _resolve_aux_font_roots(args: Any, overlay_risk: bool) -> list[base.FontRoot]:
    return [
        base.FontRoot(partition, logical, _resolve_actual(logical, getattr(args, argument), (), overlay_risk))
        for partition, logical, argument in AUX_FONT_SPECS
    ]


def _resolve_etc_roots(args: Any, overlay_risk: bool) -> list[tuple[str, Path, Path]]:
    roots: list[tuple[str, Path, Path]] = []
    for partition, logical, argument, aliases in PRIMARY_ETC_SPECS:
        roots.append((partition, logical, _resolve_actual(logical, getattr(args, argument), aliases, overlay_risk)))
    for partition, logical, argument in AUX_ETC_SPECS:
        roots.append((partition, logical, _resolve_actual(logical, getattr(args, argument), (), overlay_risk)))
    return roots


def _font_identity(path: Path) -> tuple[str, int, int] | tuple[str, str]:
    try:
        stat = path.stat()
        return ("inode", int(stat.st_dev), int(stat.st_ino))
    except OSError:
        try:
            return ("path", str(path.resolve()))
        except OSError:
            return ("path", str(path))


def _stock_file_counts(font_roots: Iterable[base.FontRoot]) -> tuple[int, int, dict[str, int], dict[str, int], set[str]]:
    path_total = 0
    unique_total = 0
    path_counts: dict[str, int] = {}
    unique_counts: dict[str, int] = {}
    identities: set[tuple[Any, ...]] = set()
    names: set[str] = set()
    for root in font_roots:
        partition_paths = 0
        partition_unique = 0
        if root.actual.is_dir():
            for path in root.actual.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in base.FONT_EXTENSIONS:
                    continue
                partition_paths += 1
                path_total += 1
                names.add(path.name)
                identity = _font_identity(path)
                if identity in identities:
                    continue
                identities.add(identity)
                partition_unique += 1
                unique_total += 1
        path_counts[root.partition] = partition_paths
        unique_counts[root.partition] = partition_unique
    return path_total, unique_total, path_counts, unique_counts, names


def _contains_font_capped(root: Path, limit: int = 4096) -> bool:
    seen = 0
    try:
        for _directory, _subdirs, files in os.walk(root):
            for name in files:
                seen += 1
                if Path(name).suffix.lower() in base.FONT_EXTENSIONS:
                    return True
                if seen >= limit:
                    return False
    except OSError:
        return False
    return False


def _theme_override_roots() -> list[str]:
    found: list[str] = []
    for root in THEME_FONT_ROOTS:
        if root.is_dir() and _contains_font_capped(root):
            found.append(str(root))
    return found


def _font_mount_targets() -> list[str]:
    targets: set[str] = set()
    try:
        lines = Path("/proc/mounts").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for line in lines:
        fields = line.split()
        if len(fields) < 2:
            continue
        target = fields[1].replace("\\040", " ")
        lowered = target.lower()
        if "/fonts" in lowered or lowered.startswith("/data/fonts"):
            targets.add(target)
    return sorted(targets)


def _rom_markers(names: set[str]) -> dict[str, list[str]]:
    lowered = {name.lower(): name for name in names}
    result: dict[str, list[str]] = {}
    for rom, markers in ROM_FONT_MARKERS.items():
        matches = [lowered[marker.lower()] for marker in markers if marker.lower() in lowered]
        if matches:
            result[rom] = matches
    return result


def _is_hyperos_inventory(existing: dict[str, Any]) -> bool:
    # A ColorOS ROM can contain an unused Xiaomi-named file. Its already-selected
    # OEM main family takes precedence over those optional physical signatures.
    if existing.get("romKind") == "coloros":
        return False
    summary = existing.get("scanSummary")
    signatures = summary.get("fontSignatures") if isinstance(summary, dict) else None
    return (existing.get("romKind") == "hyperos"
            or isinstance(signatures, dict) and bool(signatures.get("hyperos")))


def _has_current_hyperos_coverage(existing: dict[str, Any]) -> bool:
    return (not _is_hyperos_inventory(existing)
            or existing.get("hyperosCoverageRevision") == HYPEROS_COVERAGE_REVISION)


def _add_hyperos_physical_slots(slots: dict[str, dict[str, Any]], roots: list[base.FontRoot]) -> dict:
    """Capture stock contracts for files the HyperOS mapper actually replaces.

    Named UI-family discovery intentionally omits lang=zh-Hans/zh-Hant fallback
    families. Capture only the explicit CJK and UI files selected by the physical
    mapper, including their real stock metrics. Unrelated language/symbol fonts
    remain stock; this does not widen the generic/ColorOS replacement heuristic.
    """
    additional: dict[str, dict[str, Any]] = {}
    dynamic_aliases: dict[str, dict[str, str]] = {}
    for root in roots:
        if root.partition not in HYPEROS_PARTITIONS or not root.actual.is_dir():
            continue
        for actual in sorted(root.actual.iterdir(), key=lambda item: item.name.lower()):
            if not safe_physical_font_name(actual.name):
                continue
            logical = base._logical_path(root, actual)
            if (logical == DYNAMIC_OVERLAY_PATH and actual.is_symlink()
                    and os.readlink(actual) == DYNAMIC_OVERLAY_TARGET):
                # init only seeds this path with Roboto. SymlinkUtils replaces
                # it with the locale-selected MiSans/Roboto or theme font later.
                # Preserve that framework route rather than freezing the seed
                # as an independently normalized Latin font. Never read /data.
                dynamic_aliases[logical] = {"source": "hyperos-framework-symlink",
                                            "target": DYNAMIC_OVERLAY_TARGET}
                slots.pop(logical, None)
                continue
            if logical in slots:
                continue
            try:
                # Absolute links in a stock lower directory must resolve through
                # the corresponding stock partition, never through a live mount.
                safe = base._stock_font_path(root, actual, roots)
                fmt = base._font_format(safe)
            except (base.InventoryError, OSError):
                continue
            # A .ttf/.otf filename can conceal a collection. The physical mapper
            # does not preserve a collection's face/index contract.
            if fmt not in {"TTF", "OTF"}:
                continue
            additional[logical] = {
                "slotName": actual.name, "path": logical, "partition": root.partition,
                "actualPath": str(safe), "source": "hyperos-physical", "families": [],
                "weight": base._infer_weight(actual.name), "style": "normal", "faceIndex": 0,
                "validatedBy": "fontTools-stock-metrics", "validatedFormat": fmt,
            }
    base._populate_metrics(additional)
    slots.update(additional)
    return dynamic_aliases


def _can_reuse(existing: dict[str, Any], build_key: str) -> bool:
    try:
        base.validate_inventory(existing, build_key)
    except base.InventoryError:
        return False
    summary = existing.get("scanSummary")
    return (
        int(existing.get("scannerRevision", 0) or 0) == SCANNER_REVISION
        and _has_current_metrics(existing)
        and _has_current_hyperos_coverage(existing)
        and isinstance(summary, dict)
        and "stockFontUniqueFileCount" in summary
        and "themeOverrideRoots" in summary
    )


def _has_current_metrics(existing: dict[str, Any]) -> bool:
    return (existing.get("metricsRevision") == METRICS_REVISION
            and all(isinstance(entry.get("metrics", {}).get("head"), dict)
                    and base.valid_coverage(entry.get("metrics", {}).get("coverage"))
                    for entry in existing.get("slots", {}).values())
            and isinstance(existing.get("mainSlot", {}).get("metrics", {}).get("head"), dict)
            and base.valid_coverage(existing.get("mainSlot", {}).get("metrics", {}).get("coverage")))


def _verify_upgrade_roots(font_roots: list[base.FontRoot], etc_roots: list[tuple[str, Path, Path]]) -> None:
    """A metrics-only refresh must not promote live replacement fonts to stock.

    Resolve each present root again through the existing lower/mirror safety
    resolver, including explicit directory arguments. The private-payload wrapper
    can also prove a partition is untouched; the pre-mount hook bypasses this
    check only via its existing LUOSHU_STOCK_VIEW_VERIFIED contract.
    """
    aliases_by_root = {logical: aliases for _partition, logical, _argument, aliases
                       in (*PRIMARY_FONT_SPECS, *PRIMARY_ETC_SPECS)}
    sources = [(root.logical, root.actual) for root in font_roots]
    sources.extend((logical, actual) for _partition, logical, actual in etc_roots)
    for logical, actual in sources:
        if not actual.is_dir():
            continue
        verified = _resolve_actual(logical, None, aliases_by_root.get(logical, ()), True)
        if not verified.is_dir() or verified.resolve() != actual.resolve():
            raise base.InventoryError(f"补充原厂字体度量需要可验证的 stock lower/mirror：{logical}")


def _stock_logical_entry_exists(logical: str, roots: list[base.FontRoot]) -> bool:
    """Return True when a directory entry exists in the verified stock views.

    This intentionally uses lexists semantics rather than font parsing. During an
    inventory upgrade, an old slot may have come from LuoShu's generated payload.
    If the exact logical filename is absent from every verified stock root, that
    stale slot can be retired safely. If the entry still exists (even as a broken
    symlink or malformed font), keep failing closed so a real ROM slot is never
    silently dropped.
    """
    candidate = Path(logical)
    if not candidate.is_absolute():
        return False
    for root in roots:
        for logical_root in base._font_root_names(root):
            try:
                relative = candidate.relative_to(logical_root)
            except ValueError:
                continue
            return os.path.lexists(root.actual / relative)
    return False


def _refresh_known_slots(slots: dict[str, dict[str, Any]], families: dict[str, list[str]],
                         existing: dict[str, Any], roots: list[base.FontRoot],
                         preserved_paths: set[str]) -> None:
    """Refresh previously discovered UI slots from the same verified stock path.

    A metrics upgrade must not depend on rediscovering every OEM family through
    the current XML/filename rules. Keep its established face contract, but read
    all metrics again through the selected stock views. Missing, corrupt, or
    theme-linked files still fail the preservation check below.
    """
    for logical in sorted(set(existing["slots"]) - set(slots) - preserved_paths):
        resolved = base._resolve_file(logical, roots)
        if resolved is None:
            continue
        root, actual = resolved
        if base._logical_path(root, actual) != logical:
            continue
        old = existing["slots"][logical]
        try:
            stock_file = base._stock_font_path(root, actual, roots)
            fmt, metrics = base._read_metrics(stock_file, int(old.get("faceIndex", 0)))
        except (base.InventoryError, OSError, ValueError):
            continue
        entry = {**old, "format": fmt, "metrics": metrics,
                 "partition": root.partition, "validatedBy": "fontTools-stock-metrics"}
        entry.pop("actualPath", None)
        slots[logical] = entry
        for name in entry.get("families", []):
            paths = families.setdefault(name, [])
            if logical not in paths:
                paths.append(logical)


def scan(args: Any) -> int:
    output: Path = args.output
    candidate_output = output.with_name("device_font_candidates.json")
    probe = _write_live_candidate_probe(args, candidate_output)
    build_key, fingerprint, display_id = base.current_build_key(args.build_key)
    existing = base._load_json(output)
    if not args.force and existing is not None and _can_reuse(existing, build_key):
        summary = existing["scanSummary"]
        print(json.dumps({
            "status": "reused",
            "buildKey": build_key,
            "slotCount": len(existing["slots"]),
            "stockFontFileCount": int(summary.get("stockFontFileCount", 0)),
            "stockFontUniqueFileCount": int(summary.get("stockFontUniqueFileCount", 0)),
            "xmlSlotCount": int(summary.get("xmlUiFileCount", 0)),
            "heuristicSlotCount": int(summary.get("heuristicUiFileCount", 0)),
            "genericSlotCount": int(summary.get("verifiedScanUiFileCount", 0)),
            "candidatePathCount": int(probe.get("candidateCount", 0)),
            "themeOverrideCount": len(summary.get("themeOverrideRoots", [])),
            "romKind": existing.get("romKind", "generic"),
        }, ensure_ascii=False))
        return 0
    valid_existing = None
    if existing is not None:
        try:
            base.validate_inventory(existing, build_key)
        except base.InventoryError:
            output.unlink(missing_ok=True)
        else:
            valid_existing = existing
    upgrade = valid_existing is not None and (
        not _has_current_metrics(valid_existing) or not _has_current_hyperos_coverage(valid_existing)
    )
    try:
        return _scan_current_roots(args, build_key, fingerprint, display_id, valid_existing, upgrade, probe)
    except Exception as error:
        if not upgrade:
            raise
        # The former valid inventory remains readable. Return failure so the
        # existing pending marker survives and the next pre-mount boot can retry.
        print(json.dumps({
            "status": "error", "retainedInventory": True, "metricsRefreshPending": True,
            "candidatePathCount": int(probe.get("candidateCount", 0)),
            "message": f"原厂字体度量补充未完成，保留原有清单：{error}",
        }, ensure_ascii=False), file=os.sys.stderr)
        return 2


def _scan_current_roots(args: Any, build_key: str, fingerprint: str, display_id: str,
                        existing: dict[str, Any] | None, upgrade: bool,
                        probe: dict[str, Any]) -> int:
    output: Path = args.output
    risk = base._overlay_risk(args.overlay_module)
    require_verified = upgrade and os.environ.get("LUOSHU_STOCK_VIEW_VERIFIED", "").strip() != "1"
    risk = risk or require_verified
    primary_roots = _resolve_primary_font_roots(args, risk)
    auxiliary_roots = _resolve_aux_font_roots(args, risk)
    etc_roots = _resolve_etc_roots(args, risk)
    if require_verified:
        _verify_upgrade_roots([*primary_roots, *auxiliary_roots], etc_roots)
    xml_sources = v2._discover_xml_sources(etc_roots)

    base._is_ui_family = v2._is_ui_family
    replaceable_roots = [*primary_roots, *auxiliary_roots]
    families, slots = v2._parse_partition_xml(xml_sources, replaceable_roots)
    base._add_heuristic_slots(slots, replaceable_roots, args.font_check)
    # Vendor-agnostic final pass: enumerate stock font files and classify real
    # text faces by cmap/metrics instead of waiting for a hard-coded OEM name.
    base._add_verified_text_slots(slots, replaceable_roots)
    base._populate_metrics(slots)
    path_total, unique_total, path_counts, unique_counts, names = _stock_file_counts(replaceable_roots)
    try:
        _initial_path, _initial_entry, initial_rom = base._pick_main_slot(slots, families)
    except base.InventoryError:
        initial_rom = "generic"
    # Use validated stock core slots, not only _pick_main_slot's filename order:
    # a ColorOS ROM can retain a MiSansVF file which that older selector ranks
    # first. An existing valid ColorOS inventory also keeps this pass ROM-local.
    coloros_cores = {*ROM_FONT_MARKERS["coloros"], "SysFont-Regular.ttf", "SysSans-En-Regular.ttf"}
    coloros = (existing is not None and existing.get("romKind") == "coloros") or any(
        entry.get("slotName") in coloros_cores for entry in slots.values()
    )
    hyperos = not coloros and (initial_rom == "hyperos" or bool(_rom_markers(names).get("hyperos")))
    dynamic_aliases = _add_hyperos_physical_slots(slots, replaceable_roots) if hyperos else {}
    retired_physical_slots = {
        path for path, entry in (existing or {}).get("slots", {}).items()
        if hyperos and entry.get("source") == "hyperos-physical"
        and path not in slots and not safe_physical_font_name(Path(path).name)
    }
    preserved_paths = set(dynamic_aliases) | retired_physical_slots
    retired_absent_upgrade_slots: set[str] = set()
    if upgrade and existing is not None:
        _refresh_known_slots(slots, families, existing, replaceable_roots, preserved_paths)
        # Older LuoShu builds could pollute the saved inventory with aliases that
        # existed only in LuoShu's generated payload (ColorOS alias_core is the
        # common example). Once this scan is reading verified stock roots, an old
        # logical path that is completely absent from stock is safe to retire.
        # Existing-but-unparseable paths are NOT retired and still fail closed.
        for logical in set(existing["slots"]) - set(slots) - preserved_paths:
            if not _stock_logical_entry_exists(logical, replaceable_roots):
                retired_absent_upgrade_slots.add(logical)
    if coloros:
        # The generic selector prefers MiSans by filename. An unused MiSans on
        # ColorOS must not become the main metric contract or change the ROM kind.
        native_slots = {path: entry for path, entry in slots.items()
                        if entry.get("slotName") in coloros_cores}
        main_path, main_entry, _rom = base._pick_main_slot(native_slots or slots, families)
        rom = "coloros"
    else:
        main_path, main_entry, rom = base._pick_main_slot(slots, families)
    if hyperos:
        rom = "hyperos"

    theme_roots = _theme_override_roots()
    mount_targets = _font_mount_targets()
    scan_summary = v2._summary(slots, path_total, path_counts, len(xml_sources), v2._count_xml_ui_faces(xml_sources))
    scan_summary["heuristicUiFileCount"] = sum(
        1 for entry in slots.values() if entry.get("source") == "heuristic"
    )
    scan_summary["verifiedScanUiFileCount"] = sum(
        1 for entry in slots.values() if entry.get("source") == "verified-scan"
    )
    scan_summary.update({
        "stockFontUniqueFileCount": unique_total,
        "partitionUniqueFontFileCounts": unique_counts,
        "themeOverrideRoots": theme_roots,
        "fontMountTargets": mount_targets,
        "fontSignatures": _rom_markers(names),
        "stockCountSemantics": "font paths from canonical-or-alias partition roots; theme fonts excluded",
        "installCandidatePathCount": int(probe.get("candidateCount", 0)),
    })
    inventory = {
        "schema": base.SCHEMA,
        "inventoryRevision": base.INVENTORY_REVISION,
        "scannerRevision": SCANNER_REVISION,
        "metricsRevision": METRICS_REVISION,
        # Successful scans have checked applicability as well as coverage. This
        # avoids repeated refreshes when an old main-family selector labels a
        # ColorOS inventory "hyperos" because an unused MiSans file is present.
        "hyperosCoverageRevision": HYPEROS_COVERAGE_REVISION,
        "preservedDynamicAliases": dynamic_aliases,
        "retiredPhysicalSlots": sorted(retired_physical_slots),
        "retiredAbsentUpgradeSlots": sorted(retired_absent_upgrade_slots),
        "state": "ready",
        "buildKey": build_key,
        "buildFingerprint": fingerprint,
        "buildDisplayId": display_id,
        "generatedAt": int(time.time()),
        "romKind": rom,
        "sourceRoots": [
            {"partition": root.partition, "logical": str(root.logical), "actual": str(root.actual)}
            for root in primary_roots if root.actual.is_dir()
        ],
        "auxiliaryRoots": [
            {"partition": root.partition, "logical": str(root.logical), "actual": str(root.actual)}
            for root in auxiliary_roots if root.actual.is_dir()
        ],
        "etcRoots": [
            {"partition": partition, "logical": str(logical), "actual": str(actual)}
            for partition, logical, actual in etc_roots if actual.is_dir()
        ],
        "xmlSources": [str(logical) for _partition, logical, _actual in xml_sources],
        "families": {name: paths for name, paths in sorted(families.items()) if name and paths},
        "slots": {logical: slots[logical] for logical in sorted(slots)},
        "slotCount": len(slots),
        "scanSummary": scan_summary,
        "mainSlotPath": main_path,
        "mainSlot": {**main_entry, "path": main_path},
    }
    base.validate_inventory(inventory, build_key)
    if upgrade and existing is not None:
        missing = sorted(
            set(existing["slots"]) - set(slots) - preserved_paths - retired_absent_upgrade_slots
        )
        if missing:
            names = "、".join(Path(path).name for path in missing[:5])
            raise base.InventoryError(f"原厂字体重扫未完整保留已有槽位（{len(missing)} 个：{names}）")
    base._atomic_write(output, inventory)
    print(json.dumps({
        "status": "ok",
        "buildKey": build_key,
        "slotCount": len(slots),
        "stockFontFileCount": path_total,
        "stockFontUniqueFileCount": unique_total,
        "xmlSlotCount": scan_summary["xmlUiFileCount"],
        "heuristicSlotCount": scan_summary["heuristicUiFileCount"],
        "genericSlotCount": scan_summary["verifiedScanUiFileCount"],
        "physicalSlotCount": sum(1 for entry in slots.values() if entry.get("source") == "hyperos-physical"),
        "retiredAbsentUpgradeSlotCount": len(retired_absent_upgrade_slots),
        "candidatePathCount": int(probe.get("candidateCount", 0)),
        "xmlSourceCount": scan_summary["xmlSourceCount"],
        "themeOverrideCount": len(theme_roots),
        "fontMountCount": len(mount_targets),
        "mainSlot": main_entry["slotName"],
        "romKind": rom,
    }, ensure_ascii=False))
    return 0


def build_parser() -> Any:
    parser = v2.build_parser()
    parser.add_argument("--odm-fonts", type=Path)
    parser.add_argument("--oem-fonts", type=Path)
    parser.add_argument("--my-engineering-fonts", type=Path)
    parser.add_argument("--my-company-fonts", type=Path)
    parser.add_argument("--my-preload-fonts", type=Path)
    parser.add_argument("--my-region-fonts", type=Path)
    parser.add_argument("--my-stock-fonts", type=Path)
    parser.add_argument("--oplus-product-fonts", type=Path)
    parser.add_argument("--oplus-engineering-fonts", type=Path)
    parser.add_argument("--oplus-version-fonts", type=Path)
    parser.add_argument("--oplus-region-fonts", type=Path)
    parser.add_argument("--mi-ext-fonts", type=Path)
    parser.add_argument("--cust-fonts", type=Path)
    parser.add_argument("--hw-product-fonts", type=Path)
    parser.add_argument("--odm-etc", type=Path)
    parser.add_argument("--oem-etc", type=Path)
    parser.add_argument("--my-engineering-etc", type=Path)
    parser.add_argument("--my-company-etc", type=Path)
    parser.add_argument("--my-preload-etc", type=Path)
    parser.add_argument("--my-region-etc", type=Path)
    parser.add_argument("--my-stock-etc", type=Path)
    parser.add_argument("--oplus-product-etc", type=Path)
    parser.add_argument("--oplus-engineering-etc", type=Path)
    parser.add_argument("--oplus-version-etc", type=Path)
    parser.add_argument("--oplus-region-etc", type=Path)
    parser.add_argument("--mi-ext-etc", type=Path)
    parser.add_argument("--cust-etc", type=Path)
    parser.add_argument("--hw-product-etc", type=Path)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.list:
            return base.list_slots(args)
        if args.validate:
            return base.validate_command(args)
        return scan(args)
    except Exception as error:
        print(json.dumps({"status": "error", "message": str(error) or error.__class__.__name__}, ensure_ascii=False), file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
