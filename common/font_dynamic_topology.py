#!/usr/bin/env python3
"""Resolve authoritative Android updated-font references without changing them.

Only config-declared paths/directories may become targets. A directory listing or
FontManager substring by itself is diagnostics, never replacement authority.
Unresolved generations remain explicit blockers rather than disappearing.
"""
from __future__ import annotations

import copy
import hashlib
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import device_font_template_base as template
import font_inventory as inventory_engine
from fontTools.ttLib import TTCollection, TTFont

CONFIG_LOGICAL = "/data/fonts/config/config.xml"
FILES_LOGICAL = Path("/data/fonts/files")
EXTENSIONS = {".ttf", ".otf", ".ttc", ".otc"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_actual(logical: str, root: Path) -> Path:
    path = Path(logical)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("dynamic-path-outside-font-files")
    rel = path.relative_to(FILES_LOGICAL)
    if not rel.parts or root.is_symlink():
        raise ValueError("dynamic-path-not-regular")
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("dynamic-symlink-not-supported")
    if not current.is_file() or current.suffix.lower() not in EXTENSIONS:
        raise ValueError("dynamic-font-file-missing")
    return current


def _names(path: Path) -> list[str]:
    # Android's update registry uses the PostScript name, never family/full names.
    with path.open("rb") as stream:
        collection = stream.read(4) == b"ttcf"
    count = 1
    if collection:
        with TTCollection(str(path), lazy=True) as fonts:
            count = len(fonts.fonts)
    result = []
    for index in range(count):
        kwargs = {"fontNumber": index} if collection else {}
        with TTFont(str(path), lazy=True, recalcTimestamp=False, **kwargs) as font:
            values = {entry.toUnicode().strip() for entry in font["name"].names if entry.nameID == 6}
            values.discard("")
            if len(values) != 1:
                raise ValueError("dynamic-postscript-name-ambiguous")
            result.append(next(iter(values)))
    return result


def _axes(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        result = copy.deepcopy(raw)
        tags = set()
        for axis in result:
            tag = str(axis.get("tag") or "")
            value = axis.get("stylevalue", axis.get("value", ""))
            if not re.fullmatch(r"[A-Za-z0-9]{4}", tag) or tag in tags or not math.isfinite(float(value)):
                raise ValueError("dynamic-variation-settings-invalid")
            tags.add(tag)
        return result
    value = str(raw or "").strip()
    if not value:
        return []
    # FontUpdateRequest stores Android font-variation-settings, not XML children.
    pattern = re.compile(r"\s*['\"]([A-Za-z0-9]{4})['\"]\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*,?\s*")
    result = []
    while value:
        match = pattern.match(value)
        if match is None:
            raise ValueError("dynamic-variation-settings-unparsed")
        result.append({"tag": match[1], "stylevalue": match[2], "attributes": {"tag": match[1], "stylevalue": match[2]}})
        value = value[match.end():]
    return _axes(result)


def discover(config: Path | None, files_root: Path | None,
             inventory: dict[str, Any], reported: list[str],
             observed_files: list[dict[str, Any]], mounted_targets: set[str] | None = None) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    mounted_targets = mounted_targets or set()
    slots: dict[str, dict[str, Any]] = {}
    issues: list[dict[str, Any]] = []
    evidence: dict[str, Any] = {"schema": "dynamic-font-discovery-v1", "complete": True,
                              "configPath": CONFIG_LOGICAL, "configSha256": "", "activeFileCount": 0,
                              "resolvedTargetCount": 0, "unresolved": issues}

    def issue(reason: str, **details: Any) -> None:
        item = {"reason": reason, **details}
        if item not in issues:
            issues.append(item)

    if CONFIG_LOGICAL in mounted_targets:
        issue("dynamic-active-overlay-stock-unavailable", path=CONFIG_LOGICAL)
        evidence["complete"] = False
        return slots, evidence
    if config is not None and config.is_symlink():
        issue("dynamic-config-symlink-not-supported")
        evidence["complete"] = False
        return slots, evidence
    if config is None or not config.is_file():
        if reported or observed_files:
            issue("dynamic-config-missing")
        evidence["complete"] = not issues
        return slots, evidence
    try:
        config_hash = sha256(config)
        evidence["configSha256"] = config_hash
        tree = ET.parse(config)
        root = tree.getroot()
        if template.local_name(root.tag) not in {"fontConfig", "familyset", "fonts-modification"}:
            raise ValueError("dynamic-config-schema-unsupported")
        refs = template.parse_xml(config)
        if len(refs) != sum(template.local_name(node.tag) == "font" for node in root.iter()):
            issue("dynamic-font-reference-empty")
    except (OSError, ValueError, ET.ParseError) as error:
        issue("dynamic-config-unreadable", detail=str(error))
        evidence["complete"] = False
        return slots, evidence
    if files_root is None or not files_root.is_dir():
        if refs or reported or any(template.local_name(n.tag) == "updatedFontDir" for n in root.iter()):
            issue("dynamic-files-root-missing")
        evidence["complete"] = not issues
        return slots, evidence

    active: dict[str, Path] = {}
    for node in root:
        tag = template.local_name(node.tag)
        if tag not in {"lastModifiedDate", "updatedFontDir", "family", "family-list", "alias"}:
            issue("dynamic-config-element-unsupported", element=tag)
        if tag != "updatedFontDir":
            continue
        name = str(node.get("value") or "").strip()
        if not name or Path(name).name != name or name in {".", ".."}:
            issue("dynamic-updated-directory-invalid", directory=name)
            continue
        directory = files_root / name
        if directory.is_symlink() or not directory.is_dir():
            issue("dynamic-updated-directory-missing", directory=name)
            continue
        fonts = sorted(p for p in directory.iterdir() if p.suffix.lower() in EXTENSIONS)
        if not fonts:
            issue("dynamic-updated-directory-empty", directory=name)
        for path in fonts:
            logical = str(FILES_LOGICAL / name / path.name)
            try:
                active[logical] = _safe_actual(logical, files_root)
            except ValueError as error:
                issue(str(error), path=logical)

    # File references are scoped to the authorized files root. An absolute path
    # outside it, a traversal, or an unlisted PS name is never guessed by basename.
    for ref in refs:
        if not ref.declared:
            continue
        logical = ref.declared if Path(ref.declared).is_absolute() else str(FILES_LOGICAL / ref.declared)
        try:
            active[logical] = _safe_actual(logical, files_root)
        except (OSError, ValueError) as error:
            issue(str(error), path=logical)

    indexed: dict[str, list[tuple[str, int]]] = {}
    names: dict[str, list[str]] = {}
    hashes: dict[str, str] = {}
    for logical, actual in active.items():
        if logical in mounted_targets:
            issue("dynamic-active-overlay-stock-unavailable", path=logical)
            continue
        try:
            before = sha256(actual)
            names[logical] = _names(actual)
            if sha256(actual) != before:
                raise ValueError("dynamic-font-changed-during-discovery")
            hashes[logical] = before
            for index, name in enumerate(names[logical]):
                indexed.setdefault(name, []).append((logical, index))
        except Exception as error:
            issue("dynamic-font-inspection-failed", path=logical, detail=str(error))
    evidence["activeFileCount"] = len(active)
    resolved_refs: dict[str, list[dict[str, Any]]] = {}

    def add_ref(ref: Any, *, origin: dict[str, Any] | None = None) -> None:
        try:
            if "index" in ref.font_attrs and (int(ref.font_attrs["index"]) < 0 or int(ref.font_attrs["index"]) != ref.index):
                raise ValueError("dynamic-face-index-invalid")
            if "weight" in ref.font_attrs and not 1 <= int(ref.font_attrs["weight"]) <= 1000:
                raise ValueError("dynamic-weight-invalid")
        except ValueError:
            issue("dynamic-reference-numeric-attribute-invalid", ordinal=ref.ordinal)
            return
        declared = ref.declared
        if declared:
            logical = declared if Path(declared).is_absolute() else str(FILES_LOGICAL / declared)
            choices = [(logical, ref.index)] if logical in names and ref.index < len(names[logical]) else []
            if choices and ref.postscript_name and names[logical][ref.index] != ref.postscript_name:
                choices = []
        else:
            choices = [item for item in indexed.get(ref.postscript_name, []) if item[1] == ref.index]
        if len(choices) != 1:
            issue("dynamic-reference-unresolved" if not choices else "dynamic-reference-ambiguous",
                  declared=declared, postScriptName=ref.postscript_name, index=ref.index)
            return
        logical, index = choices[0]
        try:
            axes = _axes(ref.axes)
            style = ref.style
            if "slant" in ref.font_attrs:
                if ref.font_attrs["slant"] not in {"0", "1"}:
                    raise ValueError("dynamic-slant-invalid")
                style = "italic" if ref.font_attrs["slant"] == "1" else "normal"
        except ValueError as error:
            issue(str(error), path=logical)
            return
        record = {"sourceXml": CONFIG_LOGICAL, "sourcePartition": "data", "ordinal": ref.ordinal,
                  "family": ref.family, "familyNormalized": template.normalize(ref.family),
                  "familyAttributes": dict(ref.family_attrs), "fontAttributes": dict(ref.font_attrs),
                  "declared": declared, "postScriptName": names[logical][index],
                  "weight": ref.weight, "style": style, "index": index, "axes": axes,
                  "resolvedPath": logical}
        if origin:
            record["originalStockReference"] = {"sourceXml": origin.get("sourceXml"), "ordinal": origin.get("ordinal")}
        if record not in resolved_refs.setdefault(logical, []):
            resolved_refs[logical].append(record)

    for ref in refs:
        add_ref(ref)

    # Updated files can override stock XML by PostScript name without a new
    # dynamic family. Resolve the exact stock face name from trusted stock bytes
    # when the XML does not declare it; filenames are not identity evidence.
    roots = []
    for source in [*(inventory.get("sourceRoots") or []), *(inventory.get("auxiliaryRoots") or [])]:
        if isinstance(source, dict) and all(source.get(k) for k in ("partition", "logical", "actual")):
            roots.append(inventory_engine.FontRoot(str(source["partition"]), Path(source["logical"]), Path(source["actual"])))
    stock_name_cache: dict[str, list[str]] = {}
    for raw in (inventory.get("xmlGraph") or {}).get("refs", []) if indexed else []:
        name = str(raw.get("postScriptName") or "")
        index = int(raw.get("index") or 0)
        if not name:
            resolved = inventory_engine._resolve_file(str(raw.get("resolvedPath") or raw.get("declared") or ""), roots)
            if resolved:
                try:
                    stock = inventory_engine._stock_font_path(resolved[0], resolved[1], roots)
                    if str(stock) not in stock_name_cache:
                        stock_name_cache[str(stock)] = _names(stock)
                    stock_names = stock_name_cache[str(stock)]
                    if index < len(stock_names):
                        name = stock_names[index]
                except Exception:
                    pass
        if name not in indexed:
            continue
        ref = template.FontRef(str(raw.get("family") or ""), dict(raw.get("familyAttributes") or {}), "", name,
                               int(raw.get("weight") or 400), str(raw.get("style") or "normal"), index,
                               raw.get("axes") or [], config, True, int(raw.get("ordinal") or 0),
                               dict(raw.get("fontAttributes") or {}))
        add_ref(ref, origin=raw)

    for logical in reported:
        if logical not in active:
            issue("runtime-dynamic-font-not-in-config", path=logical)
    for logical, actual in active.items():
        entries = resolved_refs.get(logical, [])
        if not entries:
            issue("dynamic-file-role-unresolved", path=logical)
            continue
        indices = {entry["index"] for entry in entries}
        if len(indices) != 1:
            issue("dynamic-multiple-face-contracts-unsupported", path=logical, indices=sorted(indices))
            continue
        index = next(iter(indices))
        try:
            fmt, metrics = inventory_engine._read_metrics(actual, index)
            if sha256(actual) != hashes[logical]:
                raise ValueError("dynamic-font-changed-during-discovery")
        except Exception as error:
            issue("dynamic-metrics-unavailable", path=logical, detail=str(error))
            continue
        slots[logical] = {"path": logical, "actualPath": str(actual), "slotName": Path(logical).name,
                          "partition": "data", "source": "dynamic-config", "sourceXmls": [CONFIG_LOGICAL],
                          "families": sorted({entry["family"] for entry in entries if entry["family"]}),
                          "format": fmt, "faceIndex": index, "weight": metrics["weightClass"],
                          "metrics": metrics, "xmlRefs": entries,
                          "dynamicIdentity": {"configPath": CONFIG_LOGICAL, "configSha256": config_hash,
                                              "fontPath": logical, "fontSha256": hashes[logical],
                                              "faceIndex": index, "postScriptName": names[logical][index]}}
    try:
        if sha256(config) != config_hash:
            slots.clear()
            issue("dynamic-config-changed-during-discovery")
    except OSError:
        slots.clear()
        issue("dynamic-config-changed-during-discovery")
    evidence.update(complete=not issues, resolvedTargetCount=len(slots))
    return slots, evidence
