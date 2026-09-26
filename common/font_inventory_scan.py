#!/usr/bin/env python3
"""Canonical stock-font inventory scanner.

Revision 10 discovers physical text capabilities from trusted stock files and
XML contracts, without vendor properties or ROM-specific filename lists.
"""
from __future__ import annotations

import json
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable

import font_inventory as base
SCANNER_REVISION = 10
CANDIDATE_SCHEMA = "device-font-candidates-v1"
METRICS_REVISION = 5
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
XML_PATTERNS = (
    "fonts.xml",
    "font_fallback.xml",
    "system_fonts.xml",
    "fallback_fonts.xml",
    "fonts_customization.xml",
    "fonts*.xml",
    "font_fallback*.xml",
)


def _is_ui_family(name: str) -> bool:
    return base._is_ui_family(name)

def _discover_xml_sources(etc_roots: Iterable[tuple[str, Path, Path]]) -> list[tuple[str, Path, Path]]:
    discovered: dict[str, tuple[str, Path, Path]] = {}
    for partition, logical_root, actual_root in etc_roots:
        if not actual_root.is_dir():
            continue
        for pattern in XML_PATTERNS:
            for actual in actual_root.rglob(pattern):
                if not actual.is_file():
                    continue
                logical = logical_root / actual.relative_to(actual_root)
                discovered[str(logical)] = (partition, logical, actual)
    return [discovered[key] for key in sorted(discovered)]

def _merge_families(target: dict[str, list[str]], source: dict[str, list[str]]) -> None:
    for family, paths in source.items():
        bucket = target.setdefault(family, [])
        for path in paths:
            if path not in bucket:
                bucket.append(path)

def _merge_slots(target: dict[str, dict[str, Any]], source: dict[str, dict[str, Any]], xml_paths: list[str]) -> None:
    for logical, candidate in source.items():
        if logical not in target:
            target[logical] = {**candidate, "sourceXmls": list(xml_paths)}
            continue
        current = target[logical]
        for family in candidate.get("families", []):
            if family not in current.setdefault("families", []):
                current["families"].append(family)
        for xml_path in xml_paths:
            if xml_path not in current.setdefault("sourceXmls", []):
                current["sourceXmls"].append(xml_path)
        if current.get("source") != "xml" and candidate.get("source") == "xml":
            preserved_families = list(current.get("families", []))
            preserved_sources = list(current.get("sourceXmls", []))
            current.clear()
            current.update(candidate)
            current["families"] = preserved_families
            current["sourceXmls"] = preserved_sources

def _parse_partition_xml(
    xml_sources: list[tuple[str, Path, Path]],
    font_roots: list[base.FontRoot],
    protected_paths: set[str] | None = None,
) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]]]:
    roots_by_xml: dict[Path, list[base.FontRoot]] = {}
    logical_xmls: dict[Path, str] = {}
    for partition, logical_xml, actual_xml in xml_sources:
        preferred = [root for root in font_roots if root.partition == partition]
        roots_by_xml[actual_xml] = preferred + [root for root in font_roots if root.partition != partition]
        logical_xmls[actual_xml] = str(logical_xml)
    return base._parse_xml_mappings(
        [actual for _partition, _logical, actual in xml_sources], font_roots,
        roots_by_xml=roots_by_xml, logical_xmls=logical_xmls, protected_paths=protected_paths,
    )

def _count_xml_ui_faces(xml_sources: Iterable[tuple[str, Path, Path]]) -> int:
    faces: set[tuple[str, str, str, str]] = set()
    for _partition, logical_xml, actual_xml in xml_sources:
        try:
            root = ET.parse(actual_xml).getroot()
        except (OSError, ET.ParseError):
            continue
        for family in root.iter():
            if base._local_name(family.tag) != "family":
                continue
            family_name = (family.get("name") or "").strip()
            family_language = (family.get("lang") or "").strip()
            if family_language or not _is_ui_family(family_name):
                continue
            for font in family:
                if base._local_name(font.tag) != "font":
                    continue
                raw_name = (font.text or "").strip()
                if not raw_name:
                    continue
                faces.add(
                    (
                        str(logical_xml),
                        raw_name,
                        font.get("index") or "0",
                        (font.get("weight") or "400") + ":" + (font.get("style") or "normal"),
                    )
                )
    return len(faces)

def _slot_partition_counts(slots: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in slots.values():
        partition = str(entry.get("partition", "unknown"))
        counts[partition] = counts.get(partition, 0) + 1
    return counts

def _summary(slots: dict[str, dict[str, Any]], stock_total: int, stock_parts: dict[str, int], xml_source_count: int, xml_face_count: int) -> dict[str, Any]:
    xml_slots = sum(1 for entry in slots.values() if entry.get("source") == "xml")
    heuristic_slots = len(slots) - xml_slots
    return {
        "stockFontFileCount": stock_total,
        "partitionFontFileCounts": stock_parts,
        "uiFileCount": len(slots),
        "uiXmlFaceCount": xml_face_count,
        "xmlUiFileCount": xml_slots,
        "heuristicUiFileCount": heuristic_slots,
        "xmlSourceCount": xml_source_count,
        "partitionUiFileCounts": _slot_partition_counts(slots),
    }


KNOWN_PARTITIONS = {
    partition for partition, *_rest in (*PRIMARY_FONT_SPECS, *AUX_FONT_SPECS)
}
DYNAMIC_PARTITION_DENY = {
    "acct", "apex", "cache", "config", "data", "data_mirror", "debug_ramdisk",
    "dev", "linkerconfig", "lost+found", "metadata", "mnt", "proc", "sdcard",
    "storage", "sys", "tmp", "vendor_dlkm", "odm_dlkm", "system_dlkm",
}
DYNAMIC_PARTITION_LIMIT = 16
DYNAMIC_PARTITION_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_]{0,63}$")
NESTED_FONT_ROOT_SCHEMA = "device-font-roots-v1"
NESTED_ROOT_COMPONENT = re.compile(r"^[A-Za-z0-9._+-]{1,96}$")
NESTED_ROOT_DENY_COMPONENTS = {
    "app", "priv-app", "overlay", "framework", "lib", "lib64", "bin", "xbin",
    "media", "lost+found",
}
_LIVE_FONT_CENSUS: list[tuple[str, Path, Path]] | None = None
# Install wrapper may replace this with a stock-partition resolver. Returning
# None means no trustworthy whole-partition view is available for census.
PARTITION_CENSUS_ROOT_RESOLVER = None


def _dynamic_partition_search_bases() -> tuple[Path, ...]:
    override = os.environ.get("LUOSHU_DYNAMIC_PARTITION_SCAN_ROOTS", "").strip()
    if override:
        return tuple(Path(item) for item in override.split(os.pathsep) if item)
    return (Path("/"), Path("/system"))


def _safe_dynamic_partition_name(name: str) -> bool:
    return bool(DYNAMIC_PARTITION_NAME.fullmatch(name)
                and name not in KNOWN_PARTITIONS
                and name.lower() not in DYNAMIC_PARTITION_DENY)


def _dynamic_partition_specs() -> list[tuple[str, Path, tuple[Path, ...], Path, tuple[Path, ...]]]:
    """Discover unknown root-level OEM partitions that actually contain fonts.

    Only direct children of / and /system are considered, and runtime/data/theme
    trees are denied. A discovered partition is canonicalized to /<name>/fonts;
    /system/<name>/fonts is treated as an alias for ROMs that expose logical
    partitions under /system. Results are capped so a malformed filesystem cannot
    explode scan or mount work.
    """
    found: dict[str, dict[str, Path]] = {}
    for base_dir in _dynamic_partition_search_bases():
        try:
            children = sorted(base_dir.iterdir(), key=lambda path: path.name.lower())
        except OSError:
            continue
        for child in children:
            name = child.name
            if not _safe_dynamic_partition_name(name):
                continue
            font_dir = child / "fonts"
            try:
                font_dir_ready = font_dir.is_dir()
            except OSError:
                continue
            if font_dir_ready:
                if not _contains_font_capped(font_dir, limit=1024):
                    continue
            else:
                # Unknown mounted partitions can expose only nested font assets.
                # Explicit roots are used by offline scans/tests; ordinary host
                # directories must not be mistaken for Android partitions.
                eligible_partition = (bool(os.environ.get("LUOSHU_DYNAMIC_PARTITION_SCAN_ROOTS"))
                                      or os.path.ismount(child) or base_dir == Path("/system"))
                if (not eligible_partition or name.lower() in NESTED_ROOT_DENY_COMPONENTS
                        or not _contains_font_capped(child)):
                    continue
            entry = found.setdefault(name, {})
            # Prefer the direct /partition view over a /system/partition alias.
            key = "direct" if base_dir == Path("/") else "alias"
            entry[key] = font_dir
            etc_dir = child / "etc"
            try:
                etc_ready = etc_dir.is_dir()
            except OSError:
                etc_ready = False
            if etc_ready:
                entry[key + "_etc"] = etc_dir
            if len(found) >= DYNAMIC_PARTITION_LIMIT:
                break
        if len(found) >= DYNAMIC_PARTITION_LIMIT:
            break

    specs: list[tuple[str, Path, tuple[Path, ...], Path, tuple[Path, ...]]] = []
    for name in sorted(found):
        entry = found[name]
        logical_fonts = Path("/") / name / "fonts"
        font_aliases = tuple(
            path for path in (entry.get("direct"), entry.get("alias"))
            if path is not None and path != logical_fonts
        )
        logical_etc = Path("/") / name / "etc"
        etc_aliases = tuple(
            path for path in (entry.get("direct_etc"), entry.get("alias_etc"))
            if path is not None and path != logical_etc
        )
        specs.append((name, logical_fonts, font_aliases, logical_etc, etc_aliases))
    return specs


def _write_dynamic_partition_manifest(output: Path, partitions: Iterable[str]) -> None:
    manifest = output.parent / "device_font_partitions.conf"
    values = sorted({part for part in partitions if _safe_dynamic_partition_name(part)})
    temp = manifest.with_name(manifest.name + f".tmp.{os.getpid()}")
    temp.parent.mkdir(parents=True, exist_ok=True)
    temp.write_text("".join(f"{part}\n" for part in values), encoding="utf-8")
    os.replace(temp, manifest)



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
    for partition, logical, aliases, _etc_logical, _etc_aliases in _dynamic_partition_specs():
        actual = next((candidate for candidate in (logical, *aliases) if candidate.is_dir() or candidate.parent.is_dir()), logical)
        roots.append(base.FontRoot(partition, logical, actual))
    return roots


def _partition_scan_bases(font_roots: Iterable[base.FontRoot]) -> list[tuple[str, Path, Path]]:
    """Return one logical/actual partition base for every configured font root.

    The canonical root is normally /<partition>/fonts. Explicit test roots and
    /system/<partition>/fonts aliases are supported by removing the same logical
    suffix from the actual path. This lets the census see standalone font files
    anywhere inside the trusted system/OEM partition instead of assuming every
    vendor stores them directly under /fonts.
    """
    found: dict[tuple[str, str], tuple[str, Path, Path]] = {}
    for root in font_roots:
        logical_partition = Path("/") / root.partition
        try:
            suffix = root.logical.relative_to(logical_partition)
        except ValueError:
            continue
        actual_partition = root.actual
        for _part in suffix.parts:
            actual_partition = actual_partition.parent
        resolver = PARTITION_CENSUS_ROOT_RESOLVER
        if callable(resolver):
            actual_partition = resolver(root.partition, logical_partition, actual_partition)
            if actual_partition is None:
                continue
        key = (root.partition, str(actual_partition))
        found.setdefault(key, (root.partition, logical_partition, actual_partition))
    return sorted(found.values(), key=lambda item: (item[0], str(item[2])))


def _partition_font_census(font_roots: Iterable[base.FontRoot]) -> list[tuple[str, Path, Path]]:
    """Enumerate every standalone TTF/OTF/TTC/OTC under trusted ROM partitions.

    This is the broad census layer. It intentionally records specialized fonts
    too; promotion into the replaceable inventory is a later, stricter decision.
    os.walk never follows directory symlinks, and nested aliases that are already
    represented by another partition base are pruned to avoid /system/product
    being misclassified as part of /system.
    """
    bases = _partition_scan_bases(font_roots)
    base_paths = [(partition, actual) for partition, _logical, actual in bases]
    entries: dict[str, tuple[str, Path, Path]] = {}
    for partition, logical_base, actual_base in bases:
        if not actual_base.is_dir():
            continue
        other_bases = {
            str(path)
            for other_partition, path in base_paths
            if other_partition != partition and path != actual_base
        }
        candidates = sorted(
            (root for root in font_roots if root.partition == partition and root.actual.is_dir()),
            key=lambda root: len(root.actual.parts), reverse=True,
        )
        try:
            walker = os.walk(actual_base, topdown=True, followlinks=False)
            for current_raw, dirs, files in walker:
                current = Path(current_raw)
                pruned: list[str] = []
                for name in dirs:
                    child = current / name
                    try:
                        if child.is_symlink():
                            continue
                    except OSError:
                        continue
                    if str(child) in other_bases:
                        continue
                    pruned.append(name)
                dirs[:] = pruned
                for name in files:
                    actual = current / name
                    if actual.suffix.lower() not in base.FONT_EXTENSIONS:
                        continue
                    try:
                        if not (actual.is_file() or actual.is_symlink()):
                            continue
                        relative = actual.relative_to(actual_base)
                    except (OSError, ValueError):
                        continue
                    logical = logical_base / relative
                    # Canonical font roots may use a physical alias such as
                    # /system/product/fonts or /system/font. If this file already
                    # belongs to one of those configured roots, keep the scanner's
                    # canonical logical namespace instead of inventing a nested
                    # path from the physical partition walk.
                    for root in candidates:
                        try:
                            root_relative = actual.relative_to(root.actual)
                        except ValueError:
                            continue
                        logical = root.logical / root_relative
                        break
                    entries.setdefault(str(logical), (partition, logical, actual))
        except OSError:
            continue
    return [entries[key] for key in sorted(entries)]


def _nested_root_for_directory(logical_dir: Path, partition: str) -> Path | None:
    """Return the unique shallow font-root ancestor for one nested font path.

    If a vendor stores fonts below /product/vivo/fonts/subdir/..., the mount root
    is /product/vivo/fonts, never both that directory and its descendants.
    """
    try:
        relative = logical_dir.relative_to(Path("/") / partition)
    except ValueError:
        return None
    if not relative.parts or relative.parts == ("etc",) or relative.parts[0].lower() in {"font", "fonts"}:
        # Canonical /partition/fonts is already recursive.
        return None

    lowered = [part.lower() for part in relative.parts]
    if any(part in NESTED_ROOT_DENY_COMPONENTS for part in lowered):
        return None
    if any(not NESTED_ROOT_COMPONENT.fullmatch(part) for part in relative.parts):
        return None

    for index, part in enumerate(lowered):
        if "font" not in part:
            continue
        root_relative = Path(*relative.parts[: index + 1])
        return Path("/") / partition / root_relative
    # A font extension and a verified stock parent establish the root even
    # when the OEM calls it assets/typefaces rather than fonts.
    return logical_dir


def _safe_nested_root(logical_dir: Path, partition: str) -> bool:
    return _nested_root_for_directory(logical_dir, partition) == logical_dir


def _nested_mount_key(partition: str, relative_dir: Path) -> str:
    digest = __import__("hashlib").sha256(
        f"{partition}/{relative_dir.as_posix()}".encode("utf-8")
    ).hexdigest()[:16]
    return f"{partition}-nested-{digest}"


def _module_owns_nested_root(module: Path | None, partition: str, relative: Path) -> bool:
    if module is None:
        return False
    return (
        (module / partition / relative).exists()
        or (module / ".luoshu-payload" / partition / relative).exists()
    )


def _trusted_nested_dir(
    logical_dir: Path,
    partition: str,
    live_dir: Path,
    overlay_module: Path | None,
    overlay_risk: bool,
) -> Path | None:
    relative = logical_dir.relative_to(Path("/") / partition)
    key = _nested_mount_key(partition, relative)
    state_root = Path(os.environ.get("LUOSHU_SELF_MOUNT_STATE_ROOT", "/data/adb/luoshu/self-mount"))
    lower = state_root / "lower" / key
    if lower.is_dir():
        return lower
    for prefix in base.MIRROR_PREFIXES:
        candidate = prefix / logical_dir.relative_to("/")
        if candidate.is_dir():
            return candidate
    if overlay_risk and _module_owns_nested_root(overlay_module, partition, relative):
        return None
    return live_dir if live_dir.is_dir() else None


def _discover_nested_font_roots(
    args: Any,
    overlay_risk: bool,
    live_probe_roots: list[base.FontRoot],
) -> list[base.FontRoot]:
    """Promote safe nested font directories discovered by the broad census.

    Example: /product/vivo/fonts becomes its own FontRoot without any Vivo/OEM
    name in the scanner. Files remain subject to the same fontTools coverage and
    protected-family gates as canonical /partition/fonts entries.
    """
    grouped: dict[tuple[str, str], Path] = {}
    census = _LIVE_FONT_CENSUS
    if census is None:
        census = _partition_font_census(live_probe_roots)
    for partition, logical, actual in census:
        logical_dir = logical.parent
        logical_root = _nested_root_for_directory(logical_dir, partition)
        if logical_root is None:
            continue
        try:
            trailing = logical_dir.relative_to(logical_root)
        except ValueError:
            continue
        actual_root = actual.parent
        for _part in trailing.parts:
            actual_root = actual_root.parent
        grouped.setdefault((partition, str(logical_root)), actual_root)

    roots: list[base.FontRoot] = []
    overlay_module = getattr(args, "overlay_module", None)
    for (partition, logical_raw), live_dir in sorted(grouped.items()):
        logical_dir = Path(logical_raw)
        if any(root.partition == partition and logical_dir.is_relative_to(root.logical) for root in roots):
            continue
        actual = _trusted_nested_dir(
            logical_dir, partition, live_dir, overlay_module, overlay_risk
        )
        if actual is None:
            continue
        roots.append(base.FontRoot(partition, logical_dir, actual))
    return roots


def _discover_xml_reference_roots(
    args: Any, overlay_risk: bool, xml_sources: list[tuple[str, Path, Path]],
    known_roots: list[base.FontRoot],
) -> list[base.FontRoot]:
    """Discover explicitly referenced sfnt files outside extension-based census.

    A trusted XML can reference /product/assets/typefaces/blob.bin. The filename
    suffix is irrelevant, but the physical parent must still resolve through the
    same stock partition/lower/mirror rules as an ordinary .ttf font root.
    """
    partition_views = {part: actual for part, _logical, actual in _partition_scan_bases(known_roots)
                       if actual.is_dir()}
    discovered: dict[tuple[str, str], base.FontRoot] = {}
    for xml_partition, _logical_xml, actual_xml in xml_sources:
        try:
            document = ET.parse(actual_xml)
        except (OSError, ET.ParseError):
            continue
        for node in document.getroot().iter():
            if base._local_name(node.tag) not in {"font", "file"}:
                continue
            reference = (node.text or "").strip()
            if not reference:
                continue
            candidate = Path(reference)
            if not candidate.is_absolute():
                candidate = Path("/") / xml_partition / "fonts" / candidate
            candidate = Path(os.path.abspath(os.path.normpath(str(candidate))))
            if len(candidate.parts) < 4:
                continue
            partition = candidate.parts[1]
            if any(candidate.is_relative_to(root.logical) for root in known_roots):
                continue
            partition_view = partition_views.get(partition)
            if partition_view is None and _safe_dynamic_partition_name(partition):
                for search_base in _dynamic_partition_search_bases():
                    proposed = search_base / partition
                    if (not proposed.is_dir() or not (os.environ.get("LUOSHU_DYNAMIC_PARTITION_SCAN_ROOTS")
                            or search_base == Path("/system") or os.path.ismount(proposed))):
                        continue
                    resolver = PARTITION_CENSUS_ROOT_RESOLVER
                    partition_view = resolver(partition, Path("/") / partition, proposed) if callable(resolver) else proposed
                    if partition_view is not None:
                        partition_views[partition] = partition_view
                        break
            if partition_view is None:
                continue
            logical_root = _nested_root_for_directory(candidate.parent, partition)
            if logical_root is None:
                continue
            live_parent = partition_view / logical_root.relative_to(Path("/") / partition)
            actual_root = _trusted_nested_dir(logical_root, partition, live_parent,
                getattr(args, "overlay_module", None), overlay_risk)
            if actual_root is None or not actual_root.is_dir():
                continue
            actual_font = actual_root / candidate.relative_to(logical_root)
            if not (actual_font.is_file() or actual_font.is_symlink()):
                continue
            discovered[(partition, str(logical_root))] = base.FontRoot(partition, logical_root, actual_root)
    roots: list[base.FontRoot] = []
    for (_partition, _logical), root in sorted(discovered.items()):
        if not any(root.partition == old.partition and root.logical.is_relative_to(old.logical)
                   for old in (*known_roots, *roots)):
            roots.append(root)
    return roots


def _font_root_records(roots: Iterable[base.FontRoot]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for root in roots:
        try:
            relative = root.logical.relative_to(Path("/") / root.partition)
        except ValueError:
            continue
        if relative == Path("fonts") or not _safe_nested_root(root.logical, root.partition):
            continue
        records.append({
            "partition": root.partition,
            "logical": str(root.logical),
            "actual": str(root.actual),
            "relative": relative.as_posix(),
            "mountKey": _nested_mount_key(root.partition, relative),
        })
    return sorted(records, key=lambda item: (item["partition"], item["relative"]))


def _write_font_root_manifest(output: Path, records: Iterable[dict[str, str]]) -> None:
    manifest = output.parent / "device_font_roots.conf"
    temp = manifest.with_name(manifest.name + f".tmp.{os.getpid()}")
    temp.parent.mkdir(parents=True, exist_ok=True)
    with temp.open("w", encoding="utf-8") as stream:
        for item in records:
            partition = item.get("partition", "")
            relative = item.get("relative", "")
            key = item.get("mountKey", "")
            if not partition or not relative or not key:
                continue
            stream.write(f"{partition}|{relative}|{key}\n")
    os.replace(temp, manifest)


def _stock_file_counts_from_census(
    census: Iterable[tuple[str, Path, Path]],
) -> tuple[int, int, dict[str, int], dict[str, int], set[str]]:
    path_total = 0
    unique_total = 0
    path_counts: dict[str, int] = {}
    unique_counts: dict[str, int] = {}
    identities: set[tuple[Any, ...]] = set()
    names: set[str] = set()
    for partition, _logical, actual in census:
        path_total += 1
        path_counts[partition] = path_counts.get(partition, 0) + 1
        names.add(actual.name)
        identity = _font_identity(actual)
        if identity in identities:
            continue
        identities.add(identity)
        unique_total += 1
        unique_counts[partition] = unique_counts.get(partition, 0) + 1
    return path_total, unique_total, path_counts, unique_counts, names


def _write_live_candidate_probe(args: Any, output: Path) -> dict[str, Any]:
    """Persist every visible standalone font path before trusted stock resolution.

    This is deliberately broader than the replaceable inventory: every
    TTF/OTF/TTC/OTC under trusted system/OEM partition bases is recorded,
    including specialized/script fonts and unusual nested vendor directories.
    The later stock scan decides what can safely be replaced.
    """
    global _LIVE_FONT_CENSUS
    entries: dict[str, dict[str, Any]] = {}
    roots = _probe_font_roots(args)
    census = _partition_font_census(roots)
    _LIVE_FONT_CENSUS = census
    for partition, logical_path, actual in census:
        denied = False  # The measured stock pass classifies content, never filenames.
        logical_dir = logical_path.parent
        nested = logical_dir != (Path("/") / partition / "fonts")
        entries[str(logical_path)] = {
            "path": str(logical_path),
            "partition": partition,
            "slotName": actual.name,
            "candidate": not denied,
            "nested": nested,
            "replaceableRootCandidate": (
                not denied
                and (
                    not nested
                    or _nested_root_for_directory(logical_dir, partition) is not None
                )
            ),
            "reason": "specialized-name" if denied else "visible-font-path",
        }
    payload = {
        "schema": CANDIDATE_SCHEMA,
        "generatedAt": int(time.time()),
        "fontFileCount": len(entries),
        "candidateCount": sum(1 for entry in entries.values() if entry["candidate"]),
        "nestedFontFileCount": sum(1 for entry in entries.values() if entry["nested"]),
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
    roots = [
        base.FontRoot(partition, logical, _resolve_actual(logical, getattr(args, argument), (), overlay_risk))
        for partition, logical, argument in AUX_FONT_SPECS
    ]
    for partition, logical, aliases, _etc_logical, _etc_aliases in _dynamic_partition_specs():
        roots.append(base.FontRoot(partition, logical, _resolve_actual(logical, None, aliases, overlay_risk)))
    return roots


def _resolve_etc_roots(args: Any, overlay_risk: bool) -> list[tuple[str, Path, Path]]:
    roots: list[tuple[str, Path, Path]] = []
    for partition, logical, argument, aliases in PRIMARY_ETC_SPECS:
        roots.append((partition, logical, _resolve_actual(logical, getattr(args, argument), aliases, overlay_risk)))
    for partition, logical, argument in AUX_ETC_SPECS:
        roots.append((partition, logical, _resolve_actual(logical, getattr(args, argument), (), overlay_risk)))
    for partition, _font_logical, _font_aliases, logical, aliases in _dynamic_partition_specs():
        roots.append((partition, logical, _resolve_actual(logical, None, aliases, overlay_risk)))
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


def _stock_file_counts(font_roots: Iterable[base.FontRoot], slots: dict[str, dict[str, Any]] | None = None) -> tuple[int, int, dict[str, int], dict[str, int], set[str]]:
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
            candidates = {path for path in root.actual.rglob("*")
                          if path.is_file() and path.suffix.lower() in base.FONT_EXTENSIONS}
            for logical in slots or {}:
                if Path(logical).is_relative_to(root.logical):
                    actual = root.actual / Path(logical).relative_to(root.logical)
                    if actual.is_file():
                        candidates.add(actual)
            for path in candidates:
                partition_paths += 1
                path_total += 1
                names.add(path.name)
                identity = _font_identity(path)
                if identity in identities:
                    continue
                identities.add(identity)
                partition_unique += 1
                unique_total += 1
        path_counts[root.partition] = path_counts.get(root.partition, 0) + partition_paths
        unique_counts[root.partition] = unique_counts.get(root.partition, 0) + partition_unique
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


def _dynamic_font_aliases(roots: list[base.FontRoot]) -> dict[str, dict[str, str]]:
    """Identify mutable aliases from link targets without reading their contents."""
    result = {}
    views = sorted(((name, root) for root in roots for name in base._font_root_names(root)),
                   key=lambda value: len(value[0].parts), reverse=True)
    mutable = {"data", "data_mirror", "storage", "sdcard", "mnt", "cache"}
    for root in roots:
        if not root.actual.is_dir():
            continue
        for actual in root.actual.rglob("*"):
            if actual.suffix.lower() not in base.FONT_EXTENSIONS or not actual.is_symlink():
                continue
            origin = base._logical_path(root, actual)
            logical = Path(origin)
            seen = set()
            for _hop in range(41):
                if logical in seen:
                    break
                seen.add(logical)
                if len(logical.parts) > 1 and logical.parts[1] in mutable:
                    result[origin] = {"source": "dynamic-font-alias", "reason": "dynamic-font-alias",
                                      "target": str(logical)}
                    break
                selected = next(((prefix, view) for prefix, view in views if logical.is_relative_to(prefix)), None)
                if selected is None:
                    break
                prefix, view = selected
                parts = logical.relative_to(prefix).parts
                physical = view.actual
                linked = False
                for index, part in enumerate(parts):
                    physical = physical / part
                    if physical.is_symlink():
                        try:
                            target = Path(os.readlink(physical))
                        except OSError:
                            break
                        parent = prefix.joinpath(*parts[:index])
                        logical = Path(os.path.abspath(os.path.normpath(str(
                            (target if target.is_absolute() else parent / target).joinpath(*parts[index + 1:])))))
                        linked = True
                        break
                if not linked:
                    break
    return result


def _can_reuse(existing: dict[str, Any], build_key: str) -> bool:
    try:
        base.validate_inventory(existing, build_key)
    except base.InventoryError:
        return False
    summary = existing.get("scanSummary")
    return (
        int(existing.get("scannerRevision", 0) or 0) == SCANNER_REVISION
        and _has_current_metrics(existing)
        and existing.get("detectionPolicy") == "measured-font-capabilities-v1"
        and isinstance(summary, dict)
        and "stockFontUniqueFileCount" in summary
        and "themeOverrideRoots" in summary
        and isinstance(existing.get("discoveredPartitions"), list)
        and isinstance(existing.get("discoveredFontRoots"), list)
    )


def _has_current_metrics(existing: dict[str, Any]) -> bool:
    return (existing.get("metricsRevision") == METRICS_REVISION
            and all(isinstance(entry.get("metrics", {}).get("head"), dict)
                    and base.valid_coverage(entry.get("metrics", {}).get("coverage"))
                    for entry in existing.get("slots", {}).values())
            and all(isinstance(entry.get("faces"), list) and bool(entry["faces"])
                    and all(isinstance(face.get("metrics", {}).get("head"), dict)
                            and base.valid_coverage(face.get("metrics", {}).get("coverage"))
                            for face in entry["faces"])
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
    """Return True when a directory entry exists in the verified stock views."""
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


def scan(args: Any) -> int:
    output: Path = args.output
    candidate_output = output.with_name("device_font_candidates.json")
    build_key, fingerprint, display_id = base.current_build_key(args.build_key)
    existing = base._load_json(output)
    fresh_scan = os.environ.get("LUOSHU_FRESH_STOCK_SCAN", "").strip() == "1"
    if fresh_scan:
        # Installation and pre-mount recovery must rebuild the device inventory
        # from verified stock only. The previous inventory remains on disk as an
        # atomic fallback until a new scan succeeds, but it must not constrain the
        # new slot set or contaminate ROM classification.
        existing_for_scan = None
    else:
        existing_for_scan = existing
    if not fresh_scan and not args.force and existing_for_scan is not None and _can_reuse(existing_for_scan, build_key):
        summary = existing_for_scan["scanSummary"]
        # A validated inventory describes immutable stock for this exact ROM
        # build. Walking live partitions on a cache hit is both slow and liable
        # to count the current module's own overlay as new stock candidates.
        probe = {
            "fontFileCount": summary.get("installFontPathCount", 0),
            "nestedFontFileCount": summary.get("installNestedFontPathCount", 0),
            "candidateCount": summary.get("installCandidatePathCount", 0),
        }
        _write_dynamic_partition_manifest(output, existing_for_scan.get("discoveredPartitions", []))
        _write_font_root_manifest(output, existing_for_scan.get("discoveredFontRoots", []))
        print(json.dumps({
            "status": "reused",
            "buildKey": build_key,
            "slotCount": len(existing_for_scan["slots"]),
            "stockFontFileCount": int(summary.get("stockFontFileCount", 0)),
            "stockFontUniqueFileCount": int(summary.get("stockFontUniqueFileCount", 0)),
            "xmlSlotCount": int(summary.get("xmlUiFileCount", 0)),
            "heuristicSlotCount": int(summary.get("heuristicUiFileCount", 0)),
            "genericSlotCount": int(summary.get("verifiedScanUiFileCount", 0)),
            "fontPathCount": int(probe.get("fontFileCount", 0)),
            "nestedFontPathCount": int(probe.get("nestedFontFileCount", 0)),
            "nestedFontRootCount": len(existing_for_scan.get("discoveredFontRoots", [])),
            "candidatePathCount": int(probe.get("candidateCount", 0)),
            "themeOverrideCount": len(summary.get("themeOverrideRoots", [])),
            "romKind": existing_for_scan.get("romKind", "generic"),
        }, ensure_ascii=False))
        return 0
    # Establish the install wrapper's overlay context before the broad census.
    # Whole-partition stock views must be resolved before nested-root discovery.
    base._overlay_risk(args.overlay_module)
    probe = _write_live_candidate_probe(args, candidate_output)
    valid_existing = None
    if existing_for_scan is not None:
        try:
            base.validate_inventory(existing_for_scan, build_key)
        except base.InventoryError:
            if not fresh_scan:
                output.unlink(missing_ok=True)
        else:
            valid_existing = existing_for_scan
    upgrade = valid_existing is not None and (
        not _has_current_metrics(valid_existing)
        or valid_existing.get("scannerRevision") != SCANNER_REVISION
    )
    try:
        with base._scan_metrics_cache():
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

    live_probe_roots = _probe_font_roots(args)
    nested_roots = _discover_nested_font_roots(args, risk, live_probe_roots)
    xml_sources = _discover_xml_sources(etc_roots)
    nested_roots.extend(_discover_xml_reference_roots(args, risk, xml_sources,
                        [*primary_roots, *auxiliary_roots, *nested_roots]))

    replaceable_roots = [*primary_roots, *auxiliary_roots, *nested_roots]
    protected_xml_paths: set[str] = set()
    families, slots = _parse_partition_xml(xml_sources, replaceable_roots, protected_xml_paths)
    dynamic_aliases = _dynamic_font_aliases(replaceable_roots)
    preserved_fonts: dict[str, dict[str, Any]] = dict(dynamic_aliases)
    protected_paths = protected_xml_paths | set(dynamic_aliases)
    # Restore prior XML face evidence before measurement. Every file is still
    # parsed and measured anew; old filename/ROM labels cannot grant eligibility.
    if upgrade and existing is not None:
        for logical, old in existing["slots"].items():
            if logical in slots or logical in protected_paths:
                continue
            if not _stock_logical_entry_exists(logical, replaceable_roots):
                continue
            if old.get("source") == "xml":
                contract = {key: old[key] for key in ("faceIndex", "weight", "style", "families",
                    "familyLanguages", "xmlFallback", "fallbackFor", "sourceXmls",
                    "supportedAxes", "axes", "xmlReferences") if key in old}
                slots[logical] = {**old, "xmlFaces": {str(old.get("faceIndex", 0)): contract}}
                for name in old.get("families", []):
                    paths = families.setdefault(name, [])
                    if logical not in paths:
                        paths.append(logical)
    base._add_verified_text_slots(slots, replaceable_roots, protected_paths, preserved_fonts)
    preserved_fonts.update(dynamic_aliases)
    base._populate_metrics(slots)
    path_total, unique_total, path_counts, unique_counts, _names = _stock_file_counts(replaceable_roots, slots)
    preserved_paths = {path for path, entry in preserved_fonts.items()
                       if entry.get("reason") != "unreadable-stock-font"}
    # An old generated alias may only disappear after its absence is proven in
    # a verified stock directory; a missing scan root is never such proof.
    retired_absent_upgrade_slots: set[str] = set()
    if upgrade and existing is not None:
        for logical in set(existing["slots"]) - set(slots) - preserved_paths:
            selected_roots = [root for root in replaceable_roots
                              if Path(logical).is_relative_to(root.logical) and root.actual.is_dir()]
            if (existing["slots"][logical].get("source") == "heuristic"
                    and selected_roots and not _stock_logical_entry_exists(logical, selected_roots)):
                retired_absent_upgrade_slots.add(logical)
    main_path, main_entry, rom = base._pick_main_slot(slots, families)
    probed_paths = {entry["path"] for entry in probe.get("paths", [])}
    for path, slot in slots.items():
        if path not in probed_paths:
            probe.setdefault("paths", []).append({"path": path, "partition": slot["partition"],
                "slotName": slot["slotName"], "nested": not Path(path).parent == Path("/") / slot["partition"] / "fonts"})
    probe["paths"] = sorted(probe.get("paths", []), key=lambda entry: entry["path"])
    probe["fontFileCount"] = len(probe["paths"])
    probe["nestedFontFileCount"] = sum(bool(entry.get("nested")) for entry in probe["paths"])
    for entry in probe.get("paths", []):
        path = entry["path"]
        measured = path in slots
        preserved = preserved_fonts.get(path)
        entry.update(candidate=measured, replaceableRootCandidate=measured,
                     reason="verified-text-font" if measured else (preserved or {}).get("reason", "untrusted-stock-root"))
    probe["candidateCount"] = len(slots)
    base._atomic_write(output.with_name("device_font_candidates.json"), probe)

    theme_roots = _theme_override_roots()
    mount_targets = _font_mount_targets()
    scan_summary = _summary(slots, path_total, path_counts, len(xml_sources), _count_xml_ui_faces(xml_sources))
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
        "stockCountSemantics": "font paths from canonical-or-alias partition roots; theme fonts excluded",
        "installCandidatePathCount": int(probe.get("candidateCount", 0)),
        "installFontPathCount": int(probe.get("fontFileCount", 0)),
        "installNestedFontPathCount": int(probe.get("nestedFontFileCount", 0)),
        "nestedReplaceableRootCount": len(nested_roots),
    })
    inventory = {
        "schema": base.SCHEMA,
        "inventoryRevision": base.INVENTORY_REVISION,
        "scannerRevision": SCANNER_REVISION,
        "metricsRevision": METRICS_REVISION,
        "detectionPolicy": "measured-font-capabilities-v1",
        "preservedDynamicAliases": dynamic_aliases,
        "preservedFonts": preserved_fonts,
        "dynamicFontRoutes": [{"alias": path, **entry, "status": "preserved"}
                              for path, entry in sorted(dynamic_aliases.items())],
        "preservedXmlPaths": sorted(protected_xml_paths - slots.keys()),
        "retiredAbsentUpgradeSlots": sorted(retired_absent_upgrade_slots),
        "discoveredPartitions": sorted({
            root.partition for root in replaceable_roots if root.partition not in KNOWN_PARTITIONS
        }),
        "discoveredFontRoots": _font_root_records(nested_roots),
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
    _write_dynamic_partition_manifest(output, inventory.get("discoveredPartitions", []))
    _write_font_root_manifest(output, inventory.get("discoveredFontRoots", []))
    print(json.dumps({
        "status": "ok",
        "buildKey": build_key,
        "slotCount": len(slots),
        "stockFontFileCount": path_total,
        "stockFontUniqueFileCount": unique_total,
        "xmlSlotCount": scan_summary["xmlUiFileCount"],
        "heuristicSlotCount": scan_summary["heuristicUiFileCount"],
        "genericSlotCount": scan_summary["verifiedScanUiFileCount"],
        "physicalSlotCount": len(slots),
        "retiredAbsentUpgradeSlotCount": len(retired_absent_upgrade_slots),
        "dynamicPartitionCount": len(inventory.get("discoveredPartitions", [])),
        "nestedFontRootCount": len(inventory.get("discoveredFontRoots", [])),
        "fontPathCount": int(probe.get("fontFileCount", 0)),
        "candidatePathCount": int(probe.get("candidateCount", 0)),
        "xmlSourceCount": scan_summary["xmlSourceCount"],
        "themeOverrideCount": len(theme_roots),
        "fontMountCount": len(mount_targets),
        "mainSlot": main_entry["slotName"],
        "romKind": rom,
    }, ensure_ascii=False))
    return 0


def build_parser() -> Any:
    parser = base.build_parser()
    parser.add_argument("--system-ext-etc", type=Path)
    parser.add_argument("--product-etc", type=Path)
    parser.add_argument("--my-product-etc", type=Path)
    parser.add_argument("--vendor-etc", type=Path)
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
            build_key, _fingerprint, _display = base.current_build_key(args.build_key)
            current = base.load_inventory(args.output, build_key)
            if not _can_reuse(current, build_key):
                raise base.InventoryError("设备字体清单需要按当前通用检测规则重新扫描")
            return base.validate_command(args)
        return scan(args)
    except Exception as error:
        print(json.dumps({"status": "error", "message": str(error) or error.__class__.__name__}, ensure_ascii=False), file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
