#!/usr/bin/env python3
"""LuoShu Phase 5 minimal Android font XML router.

Consumes universal-font-plan-v1 and stock XML snapshots. The router only plans
and validates exact font-reference substitutions. It never chooses replacement
slots, compiles fonts, writes Android partitions, touches /data/fonts, or mounts
anything.

Rendering is optional and only changes targeted <font> text references. Family
order, aliases, fallback ordering, family/font attributes, TTC index,
postScriptName and <axis> children must remain semantically identical.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import tempfile
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import universal_font_plan
from device_font_template_base import effective_family_context

SCHEMA = "minimal-xml-route-plan-v1"
ROUTE_REVISION = 3
FONT_PLAN_SCHEMA = "universal-font-plan-v1"
ROUTABLE_ACTIONS = {"replace", "compile", "compile-specialized"}
DYNAMIC_PREFIX = "/data/fonts/"
FONT_EXTENSIONS = {".ttf", ".otf", ".ttc", ".otc"}
SAFE_FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,126}$")


class RouterError(RuntimeError):
    pass


def _int(value: Any, default: int = 0) -> int:
    try:
        if isinstance(value, bool):
            return default
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _normalize(value: str) -> str:
    return re.sub(r"[\s_-]+", "-", value.strip().lower()).strip("-")


def _local(tag: Any) -> str:
    if not isinstance(tag, str):
        return "#comment"
    return tag.rsplit("}", 1)[-1]


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RouterError(f"无法读取 JSON：{path}") from error
    if not isinstance(value, dict):
        raise RouterError(f"JSON 根节点不是对象：{path}")
    return value


def _canonical_hash(value: Any) -> str:
    blob = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise RouterError(f"无法读取 XML：{path}") from error
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".tmp.{os.getpid()}")
    try:
        temp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _parse_xml(path: Path) -> ET.ElementTree:
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    try:
        return ET.parse(path, parser=parser)
    except (OSError, ET.ParseError) as error:
        raise RouterError(f"无法解析原厂字体 XML：{path}: {error}") from error


def _atomic_tree(path: Path, tree: ET.ElementTree) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(fd)
    temporary = Path(temporary_raw)
    try:
        ET.indent(tree, space="    ")
        tree.write(temporary, encoding="utf-8", xml_declaration=True)
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _effective_family_name(
    family: ET.Element,
    parents: dict[ET.Element, ET.Element],
) -> str:
    own = str(family.attrib.get("name") or "").strip()
    if own:
        return own
    current = parents.get(family)
    while current is not None:
        if _local(current.tag) == "family-list":
            inherited = str(current.attrib.get("name") or "").strip()
            if inherited:
                return inherited
        current = parents.get(current)
    return ""


def _font_postscript(font: ET.Element) -> str:
    return str(
        font.attrib.get("name")
        or font.attrib.get("postScriptName")
        or font.attrib.get("postscriptName")
        or ""
    ).strip()


def _axis_children(font: ET.Element) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for child in list(font):
        if _local(child.tag) != "axis":
            continue
        result.append({
            "tag": str(child.attrib.get("tag") or ""),
            "stylevalue": str(
                child.attrib.get("stylevalue")
                or child.attrib.get("styleValue")
                or child.attrib.get("value")
                or ""
            ),
            "attributes": dict(sorted((str(k), str(v)) for k, v in child.attrib.items())),
        })
    return result


def _family_attrs(family: ET.Element) -> dict[str, str]:
    return dict(sorted((str(k), str(v)) for k, v in family.attrib.items()))


def _font_attrs(font: ET.Element) -> dict[str, str]:
    return dict(sorted((str(k), str(v)) for k, v in font.attrib.items()))


def _node_record(
    source_xml: str,
    ordinal: int,
    family: ET.Element,
    family_name: str,
    font: ET.Element,
) -> dict[str, Any]:
    declared = (font.text or "").strip()
    return {
        "sourceXml": source_xml,
        "ordinal": ordinal,
        "family": family_name,
        "familyNormalized": _normalize(family_name),
        "familyAttributes": _family_attrs(family),
        "weight": _int(font.attrib.get("weight"), 400),
        "style": str(font.attrib.get("style") or "normal").lower(),
        "index": max(0, _int(font.attrib.get("index"), 0)),
        "declared": declared,
        "postScriptName": _font_postscript(font),
        "fontAttributes": _font_attrs(font),
        "axes": _axis_children(font),
    }


def _node_fingerprint(record: dict[str, Any]) -> str:
    material = {
        "sourceXml": record.get("sourceXml"),
        "family": record.get("family"),
        "familyNormalized": record.get("familyNormalized"),
        "familyAttributes": record.get("familyAttributes"),
        "weight": record.get("weight"),
        "style": record.get("style"),
        "index": record.get("index"),
        "declared": record.get("declared"),
        "postScriptName": record.get("postScriptName"),
        "fontAttributes": record.get("fontAttributes"),
        "axes": record.get("axes"),
    }
    return f"sha256:{_canonical_hash(material)}"


def _document_nodes(source_xml: str, tree: ET.ElementTree) -> list[dict[str, Any]]:
    root = tree.getroot()
    parents = {child: parent for parent in root.iter() for child in list(parent)}
    result: list[dict[str, Any]] = []
    ordinals = {node: i for i, node in enumerate(
        node for node in root.iter() if _local(node.tag) == "font")}
    for family in root.iter():
        if _local(family.tag) != "family":
            continue
        family_name, family_attrs = effective_family_context(family, parents)
        for font in list(family):
            if _local(font.tag) != "font":
                continue
            record = _node_record(source_xml, ordinals[font], family, family_name, font)
            record["familyAttributes"] = family_attrs
            record["fingerprint"] = _node_fingerprint(record)
            result.append(record)
    return result


def _logical_snapshot(source_xml: str, snapshot_root: Path) -> Path | None:
    source = Path(source_xml)
    parts = source.parts
    if len(parts) >= 4 and parts[0] == "/" and parts[2] == "etc":
        candidate = snapshot_root / parts[1] / Path(*parts[3:])
        if candidate.is_file():
            return candidate
    return None


def _xml_map(path: Path | None) -> dict[str, Path]:
    if path is None:
        return {}
    raw = _load(path)
    result: dict[str, Path] = {}
    for key, value in raw.items():
        source = str(key).strip()
        actual = str(value).strip()
        if source.startswith("/") and actual:
            result[source] = Path(actual)
    return result


def _resolve_xml(
    source_xml: str,
    explicit: dict[str, Path],
    snapshot_root: Path | None,
    allow_live: bool,
) -> Path | None:
    candidate = explicit.get(source_xml)
    if candidate is not None and candidate.is_file():
        return candidate
    if snapshot_root is not None:
        candidate = _logical_snapshot(source_xml, snapshot_root)
        if candidate is not None:
            return candidate
    if allow_live:
        live = Path(source_xml)
        if live.is_file():
            return live
    return None


def _ref_value(ref: dict[str, Any], *names: str) -> str:
    for name in names:
        value = ref.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _ref_locator(ref: dict[str, Any]) -> dict[str, Any]:
    family = _ref_value(ref, "family", "familyName")
    declared = _ref_value(ref, "declared", "file", "filename")
    postscript = _ref_value(ref, "postScriptName", "postscriptName")
    result = {
        "family": family,
        "familyNormalized": _normalize(family),
        "familyAttributes": dict(ref.get("familyAttributes") or {}) if isinstance(ref.get("familyAttributes"), dict) else {},
        "weight": _int(ref.get("weight"), 400),
        "style": str(ref.get("style") or "normal").lower(),
        "index": max(0, _int(ref.get("index"), 0)),
        "declared": declared,
        "postScriptName": postscript,
    }
    if "ordinal" in ref:
        result["ordinal"] = _int(ref["ordinal"], -1)
    if isinstance(ref.get("axes"), list):
        result["axes"] = ref["axes"]
    if isinstance(ref.get("fontAttributes"), dict):
        result["fontAttributes"] = ref["fontAttributes"]
    return result


def _match_score(locator: dict[str, Any], node: dict[str, Any]) -> tuple[int, list[str]] | None:
    reasons: list[str] = []
    score = 0
    for key in ("ordinal", "fontAttributes"):
        if key in locator and locator[key] != node.get(key):
            return None
    if "axes" in locator:
        expected_axes, actual_axes = locator["axes"], node.get("axes", [])
        if len(expected_axes) != len(actual_axes):
            return None
        for expected, actual in zip(expected_axes, actual_axes):
            if any(str(expected.get(key, "")) != str(actual.get(key, ""))
                   for key in ("tag", "stylevalue")):
                return None
            if "attributes" in expected and expected["attributes"] != actual.get("attributes"):
                return None

    family = str(locator.get("familyNormalized") or "")
    if family:
        if node.get("familyNormalized") != family:
            return None
        score += 100
        reasons.append("family")

    if int(node.get("weight") or 400) != int(locator.get("weight") or 400):
        return None
    score += 40
    reasons.append("weight")

    if str(node.get("style") or "normal") != str(locator.get("style") or "normal"):
        return None
    score += 30
    reasons.append("style")

    if int(node.get("index") or 0) != int(locator.get("index") or 0):
        return None
    score += 30
    reasons.append("index")

    declared = str(locator.get("declared") or "")
    if declared:
        if Path(str(node.get("declared") or "")).name != Path(declared).name:
            return None
        score += 100
        reasons.append("declared")

    postscript = str(locator.get("postScriptName") or "")
    if postscript:
        if str(node.get("postScriptName") or "") != postscript:
            return None
        score += 80
        reasons.append("postscript")

    attrs = locator.get("familyAttributes")
    if isinstance(attrs, dict) and attrs:
        node_attrs = node.get("familyAttributes") if isinstance(node.get("familyAttributes"), dict) else {}
        for key, value in attrs.items():
            if str(node_attrs.get(str(key), "")) != str(value):
                return None
        score += 10 * len(attrs)
        reasons.append("family-attributes")

    return score, reasons


def _find_unique_node(locator: dict[str, Any], nodes: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    ranked: list[tuple[int, int, dict[str, Any], list[str]]] = []
    for node in nodes:
        match = _match_score(locator, node)
        if match is None:
            continue
        score, reasons = match
        ranked.append((score, -int(node["ordinal"]), node, reasons))

    if not ranked:
        return None, {"status": "missing", "candidateCount": 0}
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    best_score = ranked[0][0]
    best = [item for item in ranked if item[0] == best_score]
    if len(best) != 1:
        return None, {
            "status": "ambiguous",
            "candidateCount": len(best),
            "candidateOrdinals": sorted(int(item[2]["ordinal"]) for item in best),
            "score": best_score,
        }
    node = best[0][2]
    return node, {
        "status": "unique",
        "candidateCount": 1,
        "score": best_score,
        "matchedBy": best[0][3],
    }


def _artifact_extension(target: dict[str, Any], node: dict[str, Any]) -> str:
    declared_suffix = Path(str(node.get("declared") or "")).suffix.lower()
    source = target.get("source") if isinstance(target.get("source"), dict) else {}
    target_contract = target.get("targetContract") if isinstance(target.get("targetContract"), dict) else {}
    target_format = str(target_contract.get("format") or "").upper()
    source_format = str(source.get("format") or "").upper()
    if declared_suffix == ".otc":
        return ".otc"
    if declared_suffix == ".ttc":
        return ".ttc"
    if int(node.get("index") or 0) > 0:
        return ".otc" if "OTF" in target_format or "CFF" in target_format else ".ttc"
    if target_format == "OTF" or "CFF" in target_format:
        return ".otf"
    if target_format == "TTC":
        return ".ttc"
    if target_format == "OTC":
        return ".otc"
    if "CFF" in source_format:
        return ".otf"
    return ".ttf"


def _artifact_contract(font_plan: dict[str, Any], target: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    semantic = {
        "fontPlanId": font_plan.get("planId"),
        "targetPath": target.get("path"),
        "role": target.get("role"),
        "compiler": target.get("compiler"),
        "requirements": target.get("requirements"),
        "selection": target.get("selection"),
        "risks": target.get("risks"),
        "source": target.get("source"),
        "targetContract": target.get("targetContract"),
        "xmlContract": {
            "weight": node.get("weight"),
            "style": node.get("style"),
            "index": node.get("index"),
            "postScriptName": node.get("postScriptName"),
            "axes": node.get("axes"),
        },
    }
    digest = _canonical_hash(semantic)
    extension = _artifact_extension(target, node)
    return {
        "artifactId": f"ufc:{digest[:32]}",
        "suggestedFileName": f"LuoShu-UF-{digest[:20]}{extension}",
        "container": "collection" if extension in {".ttc", ".otc"} else "sfnt",
        "requiredFaceIndex": int(node.get("index") or 0),
        "requiredPostScriptName": str(node.get("postScriptName") or ""),
        "requiredAxes": list(node.get("axes") or []),
        "requiredWeight": int(node.get("weight") or 400),
        "requiredStyle": str(node.get("style") or "normal"),
        "preserveXmlAttributes": True,
        "preserveAxisChildren": True,
    }


def _preserve_fixed_italic(target: dict[str, Any]) -> bool:
    hard_risks = set(target.get("risks") or []) & {
        "static-weight-fallback", "italic-style-mismatch", "source-weight-axis-out-of-range",
        "source-style-axis-missing", "source-style-axis-out-of-range",
    }
    return (universal_font_plan.is_fixed_composite_selection(target.get("source") or {})
            and target.get("targetContract", {}).get("italic") is True
            and bool(hard_risks)
            and hard_risks <= {"italic-style-mismatch", "source-style-axis-missing",
                               "source-style-axis-out-of-range"})


def _target_route_refs(target: dict[str, Any]) -> list[dict[str, Any]]:
    scoped = target.get("xmlScopedTarget")
    refs = (scoped if isinstance(scoped, dict) else target).get("xmlRefs")
    if not isinstance(refs, list):
        return []
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        source_xml = str(ref.get("sourceXml") or "").strip()
        if not source_xml or source_xml.startswith(DYNAMIC_PREFIX):
            continue
        key = json.dumps(ref, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(ref))
    return result


def _source_xmls(font_plan: dict[str, Any]) -> list[str]:
    values: set[str] = set()
    targets = font_plan.get("targets")
    if not isinstance(targets, dict):
        return []
    for target in targets.values():
        if not isinstance(target, dict):
            continue
        if str(target.get("action") or "") not in ROUTABLE_ACTIONS and not isinstance(target.get("xmlScopedTarget"), dict):
            continue
        for ref in _target_route_refs(target):
            source_xml = str(ref.get("sourceXml") or "")
            if source_xml:
                values.add(source_xml)
    return sorted(values)


def _semantic_tree(
    tree: ET.ElementTree,
    replacement_ordinals: set[int] | None = None,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    font_ordinal = 0
    for element in tree.getroot().iter():
        tag = _local(element.tag)
        if tag == "#comment":
            result.append({
                "kind": "comment",
                "text": str(element.text or ""),
            })
            continue

        record: dict[str, Any] = {
            "kind": tag,
            "attributes": dict(sorted((str(k), str(v)) for k, v in element.attrib.items())),
        }
        text_value = str(element.text or "")
        if tag == "font":
            record["ordinal"] = font_ordinal
            record["text"] = (
                "<ROUTED>"
                if replacement_ordinals is not None and font_ordinal in replacement_ordinals
                else text_value.strip()
            )
            font_ordinal += 1
        elif text_value.strip():
            record["text"] = text_value.strip()
        result.append(record)
    return result

def _validate_font_plan(font_plan: dict[str, Any]) -> None:
    if font_plan.get("schema") != FONT_PLAN_SCHEMA:
        raise RouterError("Universal FontPlan 未就绪")
    try:
        universal_font_plan.validate_plan(font_plan)
    except Exception as error:
        raise RouterError(f"Universal FontPlan 完整性校验失败：{error}") from error


def build_route_plan(
    font_plan: dict[str, Any],
    explicit_xml_map: dict[str, Path],
    snapshot_root: Path | None,
    allow_live: bool,
) -> dict[str, Any]:
    _validate_font_plan(font_plan)
    targets = font_plan.get("targets")
    if not isinstance(targets, dict):
        raise RouterError("Universal FontPlan 缺少 targets")

    source_xmls = _source_xmls(font_plan)
    documents: dict[str, dict[str, Any]] = {}
    document_nodes: dict[str, list[dict[str, Any]]] = {}
    missing_documents: list[str] = []

    for source_xml in source_xmls:
        actual = _resolve_xml(source_xml, explicit_xml_map, snapshot_root, allow_live)
        if actual is None:
            missing_documents.append(source_xml)
            documents[source_xml] = {
                "sourceXml": source_xml,
                "sourcePath": "",
                "sourceDigest": "",
                "status": "missing",
                "operations": [],
            }
            document_nodes[source_xml] = []
            continue
        tree = _parse_xml(actual)
        nodes = _document_nodes(source_xml, tree)
        documents[source_xml] = {
            "sourceXml": source_xml,
            "sourcePath": str(actual),
            "sourceDigest": f"sha256:{_file_sha256(actual)}",
            "status": "ready",
            "nodeCount": len(nodes),
            "operations": [],
        }
        document_nodes[source_xml] = nodes

    unresolved: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    physical_only: list[str] = []
    deferred_dynamic: list[str] = []
    preserved_routes: list[dict[str, Any]] = []
    node_artifacts: dict[tuple[str, int], str] = {}

    for target_path in sorted(targets):
        target = targets[target_path]
        if not isinstance(target, dict):
            continue
        action = str(target.get("action") or "")
        if action not in ROUTABLE_ACTIONS and not isinstance(target.get("xmlScopedTarget"), dict):
            continue

        all_refs = target.get("xmlRefs")
        has_dynamic_ref = isinstance(all_refs, list) and any(
            isinstance(ref, dict)
            and str(ref.get("sourceXml") or "").startswith(DYNAMIC_PREFIX)
            for ref in all_refs
        )
        if has_dynamic_ref:
            deferred_dynamic.append(target_path)

        refs = _target_route_refs(target)
        if not refs:
            if not has_dynamic_ref:
                physical_only.append(target_path)
            continue

        for ref in refs:
            source_xml = str(ref.get("sourceXml") or "")
            document = documents.get(source_xml)
            if document is None or document.get("status") != "ready":
                unresolved.append({
                    "targetPath": target_path,
                    "sourceXml": source_xml,
                    "reason": "stock-xml-snapshot-missing",
                    "locator": _ref_locator(ref),
                })
                continue

            locator = _ref_locator(ref)
            node, match = _find_unique_node(locator, document_nodes[source_xml])
            if node is None:
                unresolved.append({
                    "targetPath": target_path,
                    "sourceXml": source_xml,
                    "reason": f"xml-node-{match.get('status', 'unresolved')}",
                    "locator": locator,
                    "match": match,
                })
                continue

            route_target = universal_font_plan.route_target(target, node)
            if route_target.get("action") not in ROUTABLE_ACTIONS:
                raise RouterError("XML route escaped its scoped replacement contract")
            artifact = _artifact_contract(font_plan, route_target, node)
            key = (source_xml, int(node["ordinal"]))
            previous = node_artifacts.get(key)
            if previous is not None:
                if previous != artifact["artifactId"]:
                    conflicts.append({
                        "sourceXml": source_xml,
                        "ordinal": int(node["ordinal"]),
                        "firstArtifactId": previous,
                        "secondArtifactId": artifact["artifactId"],
                        "targetPath": target_path,
                    })
                # Duplicate XML graph evidence for the same target/node/artifact is
                # not a second mutation.
                continue
            node_artifacts[key] = artifact["artifactId"]

            if _preserve_fixed_italic(route_target):
                preserved_routes.append({
                    "sourceXml": source_xml,
                    "targetPath": target_path,
                    "role": str(target.get("role") or ""),
                    "reason": "fixed-composite-italic-preserved",
                    "node": copy.deepcopy(node),
                    "nodeFingerprint": node["fingerprint"],
                    "artifact": artifact,
                    "risks": list(route_target.get("risks") or []),
                })
                continue

            operation = {
                "operation": "replace-font-reference",
                "targetPath": target_path,
                "role": str(route_target.get("role") or ""),
                "targetStatus": str(route_target.get("status") or ""),
                "compiler": str(route_target.get("compiler") or ""),
                "requirements": list(route_target.get("requirements") or []),
                "risks": list(route_target.get("risks") or []),
                "routeTarget": route_target,
                "locator": locator,
                "match": match,
                "node": node,
                "nodeFingerprint": node["fingerprint"],
                "artifact": artifact,
                "mutation": {
                    "field": "font.text",
                    "from": str(node.get("declared") or ""),
                    "toArtifactId": artifact["artifactId"],
                    "preserveFamilyOrder": True,
                    "preserveFallbackOrder": True,
                    "preserveFamilyAttributes": True,
                    "preserveFontAttributes": True,
                    "preserveAxisChildren": True,
                },
            }
            document["operations"].append(operation)

    for source_xml, document in documents.items():
        operations = document.get("operations")
        if not isinstance(operations, list):
            continue
        operations.sort(key=lambda item: int(item["node"]["ordinal"]))
        document["operationCount"] = len(operations)
        document["artifactIds"] = sorted({
            str(item["artifact"]["artifactId"])
            for item in operations
            if isinstance(item, dict)
        })

    plan_constraints = font_plan.get("constraints") if isinstance(font_plan.get("constraints"), dict) else {}
    review_reasons: list[str] = []
    if unresolved:
        review_reasons.append("unresolved-target-xml-nodes")
    if conflicts:
        review_reasons.append("conflicting-target-xml-nodes")
    if missing_documents:
        review_reasons.append("missing-stock-xml-snapshots")
    if plan_constraints.get("unresolvedXmlRefCount"):
        review_reasons.append("font-plan-has-unresolved-xml-routes")
    if plan_constraints.get("dataFontFileCount") or plan_constraints.get("dataFontConfigReferenceCount"):
        review_reasons.append("data-font-layer-deferred")
    if preserved_routes:
        review_reasons.append("fixed-composite-italic-preserved")

    preserved_routes.sort(key=lambda item: (item["sourceXml"], item["node"]["ordinal"], item["targetPath"]))

    route_semantic = {
        "fontPlanId": font_plan["planId"],
        "documents": _route_semantic_documents(documents),
        "unresolved": unresolved,
        "conflicts": conflicts,
        "physicalOnlyTargets": physical_only,
        "deferredDynamicTargets": deferred_dynamic,
        "reviewReasons": sorted(set(review_reasons)),
        "preservedRoutes": preserved_routes,
    }
    route_id = f"sha256:{_canonical_hash(route_semantic)}"
    operation_count = sum(
        int(document.get("operationCount") or 0)
        for document in documents.values()
    )
    payload = {
        "schema": SCHEMA,
        "routeRevision": ROUTE_REVISION,
        "state": "planned",
        "mutatesSystem": False,
        "generatedAt": int(time.time()),
        "routeId": route_id,
        "fontPlanId": font_plan["planId"],
        "fontPlanInputs": copy.deepcopy(font_plan.get("inputs") or {}),
        "summary": {
            "documentCount": len(documents),
            "operationCount": operation_count,
            "unresolvedCount": len(unresolved),
            "conflictCount": len(conflicts),
            "missingDocumentCount": len(missing_documents),
            "physicalOnlyTargetCount": len(physical_only),
            "deferredDynamicTargetCount": len(deferred_dynamic),
            "preservedRouteCount": len(preserved_routes),
            "routingComplete": not unresolved and not conflicts and not missing_documents,
            "executableNow": False,
        },
        "reviewReasons": sorted(set(review_reasons)),
        "missingDocuments": sorted(missing_documents),
        "physicalOnlyTargets": sorted(set(physical_only)),
        "deferredDynamicTargets": sorted(set(deferred_dynamic)),
        "preservedRoutes": preserved_routes,
        "unresolved": unresolved,
        "conflicts": conflicts,
        "documents": documents,
    }
    validate_route_plan(payload, font_plan=font_plan)
    return payload


def _route_semantic_documents(documents: Any) -> dict[str, Any]:
    if not isinstance(documents, dict):
        return {}
    result: dict[str, Any] = {}
    for source_xml, document in documents.items():
        if not isinstance(document, dict):
            continue
        result[str(source_xml)] = {
            key: copy.deepcopy(value)
            for key, value in document.items()
            if key != "sourcePath"
        }
    return result


def _recompute_route_id(plan: dict[str, Any]) -> str:
    semantic = {
        "fontPlanId": plan.get("fontPlanId"),
        "documents": _route_semantic_documents(plan.get("documents")),
        "unresolved": plan.get("unresolved"),
        "conflicts": plan.get("conflicts"),
        "physicalOnlyTargets": plan.get("physicalOnlyTargets"),
        "deferredDynamicTargets": plan.get("deferredDynamicTargets"),
        "reviewReasons": plan.get("reviewReasons"),
        "preservedRoutes": plan.get("preservedRoutes"),
    }
    return f"sha256:{_canonical_hash(semantic)}"


def validate_route_plan(
    plan: dict[str, Any],
    font_plan: dict[str, Any] | None = None,
) -> None:
    if plan.get("schema") != SCHEMA or plan.get("state") != "planned":
        raise RouterError("Minimal XML Route Plan 格式无效")
    if _int(plan.get("routeRevision"), 0) != ROUTE_REVISION:
        raise RouterError("Minimal XML Route Plan 版本无效")
    if plan.get("mutatesSystem") is not False:
        raise RouterError("Phase 5 Route Plan 不得修改系统")
    summary = plan.get("summary")
    if not isinstance(summary, dict) or summary.get("executableNow") is not False:
        raise RouterError("Phase 5 Route Plan 不得声明可直接执行")
    if font_plan is not None:
        _validate_font_plan(font_plan)
        if plan.get("fontPlanId") != font_plan.get("planId"):
            raise RouterError("Route Plan 与 Universal FontPlan 不一致")
        if plan.get("fontPlanInputs") != (font_plan.get("inputs") or {}):
            raise RouterError("Route Plan 与 Universal FontPlan 输入摘要不一致")

    documents = plan.get("documents")
    if not isinstance(documents, dict):
        raise RouterError("Route Plan 缺少 documents")
    operations = 0
    seen_nodes: dict[tuple[str, int], str] = {}
    for source_xml, document in documents.items():
        if not isinstance(document, dict):
            raise RouterError(f"Route Plan 文档无效：{source_xml}")
        if str(document.get("sourceXml") or "") != str(source_xml):
            raise RouterError(f"Route Plan 文档键不一致：{source_xml}")
        raw_ops = document.get("operations")
        if not isinstance(raw_ops, list):
            raise RouterError(f"Route Plan 文档缺少 operations：{source_xml}")
        for operation in raw_ops:
            if not isinstance(operation, dict) or operation.get("operation") != "replace-font-reference":
                raise RouterError(f"Route Plan XML 操作无效：{source_xml}")
            node = operation.get("node")
            artifact = operation.get("artifact")
            mutation = operation.get("mutation")
            if not isinstance(node, dict) or not isinstance(artifact, dict) or not isinstance(mutation, dict):
                raise RouterError(f"Route Plan XML 操作契约不完整：{source_xml}")
            if mutation.get("field") != "font.text":
                raise RouterError(f"Phase 5 只能修改 font.text：{source_xml}")
            for key in (
                "preserveFamilyOrder",
                "preserveFallbackOrder",
                "preserveFamilyAttributes",
                "preserveFontAttributes",
                "preserveAxisChildren",
            ):
                if mutation.get(key) is not True:
                    raise RouterError(f"Phase 5 不得放宽 XML 保留策略：{source_xml}")
            if operation.get("nodeFingerprint") != _node_fingerprint(node):
                raise RouterError(f"Route Plan 节点指纹无效：{source_xml}")
            if font_plan is not None:
                target = font_plan["targets"].get(str(operation.get("targetPath") or ""))
                if not isinstance(target, dict):
                    raise RouterError(f"Route Plan 目标不在 FontPlan 中：{source_xml}")
                resolved = universal_font_plan.route_target(target, node)
                if resolved.get("action") not in ROUTABLE_ACTIONS:
                    raise RouterError("XML operation has no scoped replacement permission")
                if operation.get("routeTarget") != resolved or artifact != _artifact_contract(font_plan, resolved, node):
                    raise RouterError(f"Route Plan 源 face/编译契约与 XML route 不一致：{source_xml}")
                for key in ("role", "compiler", "requirements", "risks"):
                    if operation.get(key) != resolved.get(key):
                        raise RouterError(f"Route Plan route {key} 不一致：{source_xml}")
            artifact_id = str(artifact.get("artifactId") or "")
            if not artifact_id.startswith("ufc:"):
                raise RouterError(f"Route Plan 缺少编译 artifactId：{source_xml}")
            filename = str(artifact.get("suggestedFileName") or "")
            if not SAFE_FILE_RE.fullmatch(filename) or Path(filename).suffix.lower() not in FONT_EXTENSIONS:
                raise RouterError(f"Route Plan 生成文件名无效：{source_xml}")
            key = (source_xml, int(node.get("ordinal") or 0))
            previous = seen_nodes.get(key)
            if previous is not None and previous != artifact_id:
                raise RouterError(f"同一 XML 节点被路由到不同 artifact：{source_xml}")
            seen_nodes[key] = artifact_id
            operations += 1

    unresolved = plan.get("unresolved")
    conflicts = plan.get("conflicts")
    missing = plan.get("missingDocuments")
    physical = plan.get("physicalOnlyTargets")
    dynamic = plan.get("deferredDynamicTargets")
    review = plan.get("reviewReasons")
    preserved = plan.get("preservedRoutes")
    if not all(isinstance(value, list) for value in (unresolved, conflicts, missing, physical, dynamic, review, preserved)):
        raise RouterError("Route Plan 摘要集合无效")
    for route in preserved:
        if not isinstance(route, dict) or route.get("reason") != "fixed-composite-italic-preserved":
            raise RouterError("Route Plan 保留路由原因无效")
        node = route.get("node")
        source_xml = str(route.get("sourceXml") or "")
        if not isinstance(node, dict) or route.get("nodeFingerprint") != _node_fingerprint(node):
            raise RouterError("Route Plan 保留路由指纹无效")
        if source_xml not in documents or node.get("sourceXml") != source_xml:
            raise RouterError("Route Plan 保留路由文档无效")
        key = (source_xml, int(node.get("ordinal") or 0))
        if key in seen_nodes:
            raise RouterError("Route Plan 保留路由与替换路由冲突")
        seen_nodes[key] = "preserved"
        if font_plan is not None:
            target = font_plan["targets"].get(str(route.get("targetPath") or ""))
            if not isinstance(target, dict):
                raise RouterError("Route Plan 保留目标不在 FontPlan 中")
            resolved = universal_font_plan.route_target(target, node)
            if (not _preserve_fixed_italic(resolved)
                    or route.get("artifact") != _artifact_contract(font_plan, resolved, node)
                    or route.get("risks") != resolved.get("risks")):
                raise RouterError("Route Plan 不允许保留此 fixed-composite 路由")
    if bool(preserved) != ("fixed-composite-italic-preserved" in review):
        raise RouterError("Route Plan 缺少保留路由覆盖范围说明")

    if font_plan is not None and summary.get("routingComplete") is True:
        handled = [(op.get("targetPath"), op.get("node") or {})
                   for doc in documents.values() for op in doc.get("operations", [])]
        handled += [(op.get("targetPath"), op.get("node") or {}) for op in preserved]
        for path, target in font_plan["targets"].items():
            scoped = target.get("xmlScopedTarget")
            if not isinstance(scoped, dict):
                continue
            if path in physical:
                raise RouterError("XML-scoped target cannot replace its protected physical container")
            for ref in scoped["xmlRefs"]:
                if not any(path == actual_path and universal_font_plan._scoped_reference_key(ref) ==
                           universal_font_plan._scoped_reference_key(node) for actual_path, node in handled):
                    raise RouterError("XML-scoped target has an unaccounted reference")

    expected_summary = {
        "documentCount": len(documents),
        "operationCount": operations,
        "unresolvedCount": len(unresolved),
        "conflictCount": len(conflicts),
        "missingDocumentCount": len(missing),
        "physicalOnlyTargetCount": len(physical),
        "deferredDynamicTargetCount": len(dynamic),
        "preservedRouteCount": len(preserved),
        "routingComplete": not unresolved and not conflicts and not missing,
        "executableNow": False,
    }
    if summary != expected_summary:
        raise RouterError("Route Plan summary 与操作不一致")
    if plan.get("routeId") != _recompute_route_id(plan):
        raise RouterError("Route Plan routeId 完整性校验失败")


def _artifact_map(path: Path) -> dict[str, str]:
    raw = _load(path)
    result: dict[str, str] = {}
    for artifact_id, filename_value in raw.items():
        artifact = str(artifact_id).strip()
        filename = str(filename_value).strip()
        if not artifact.startswith("ufc:"):
            raise RouterError(f"artifact map ID 无效：{artifact}")
        if not SAFE_FILE_RE.fullmatch(filename):
            raise RouterError(f"artifact map 文件名无效：{filename}")
        if Path(filename).suffix.lower() not in FONT_EXTENSIONS:
            raise RouterError(f"artifact map 字体扩展名无效：{filename}")
        result[artifact] = filename
    return result


def _font_elements(tree: ET.ElementTree) -> list[ET.Element]:
    return [
        element
        for element in tree.getroot().iter()
        if _local(element.tag) == "font"
    ]


def render_document(
    route_plan: dict[str, Any],
    source_xml: str,
    artifact_map: dict[str, str],
    output: Path,
) -> dict[str, Any]:
    validate_route_plan(route_plan)
    documents = route_plan["documents"]
    document = documents.get(source_xml)
    if not isinstance(document, dict) or document.get("status") != "ready":
        raise RouterError(f"Route Plan 中没有可渲染 XML：{source_xml}")
    source_path = Path(str(document.get("sourcePath") or ""))
    if not source_path.is_file():
        raise RouterError(f"原厂 XML 快照不存在：{source_path}")
    digest = f"sha256:{_file_sha256(source_path)}"
    if digest != document.get("sourceDigest"):
        raise RouterError(f"原厂 XML 快照已经变化：{source_xml}")

    tree = _parse_xml(source_path)
    before_tree = copy.deepcopy(tree)
    elements = _font_elements(tree)
    operations = document.get("operations") or []
    ordinals: set[int] = set()

    for operation in operations:
        node = operation["node"]
        ordinal = int(node["ordinal"])
        if ordinal < 0 or ordinal >= len(elements):
            raise RouterError(f"XML 节点 ordinal 越界：{source_xml}#{ordinal}")
        current_nodes = _document_nodes(source_xml, tree)
        current = current_nodes[ordinal]
        if current["fingerprint"] != operation["nodeFingerprint"]:
            raise RouterError(f"XML 节点已变化，拒绝应用：{source_xml}#{ordinal}")
        artifact_id = str(operation["artifact"]["artifactId"])
        filename = artifact_map.get(artifact_id)
        if not filename:
            raise RouterError(f"缺少已编译 artifact：{artifact_id}")
        expected_suffix = Path(str(operation["artifact"]["suggestedFileName"])).suffix.lower()
        if Path(filename).suffix.lower() != expected_suffix:
            raise RouterError(f"artifact 容器类型与 XML 合约不一致：{artifact_id}")
        elements[ordinal].text = filename
        ordinals.add(ordinal)

    before_semantic = _semantic_tree(before_tree, replacement_ordinals=ordinals)
    after_semantic = _semantic_tree(tree, replacement_ordinals=ordinals)
    if before_semantic != after_semantic:
        raise RouterError(f"XML 最小修改验证失败：{source_xml}")

    _atomic_tree(output, tree)
    return {
        "sourceXml": source_xml,
        "output": str(output),
        "changedFonts": len(ordinals),
        "sourceDigest": digest,
    }


def render_all(
    route_plan: dict[str, Any],
    artifact_map: dict[str, str],
    output_root: Path,
) -> dict[str, Any]:
    validate_route_plan(route_plan)
    if route_plan.get("summary", {}).get("routingComplete") is not True:
        raise RouterError("XML 路由尚不完整，拒绝生成部分覆盖")
    rendered: list[dict[str, Any]] = []
    for source_xml in sorted(route_plan["documents"]):
        document = route_plan["documents"][source_xml]
        if document.get("status") != "ready" or not document.get("operations"):
            continue
        parts = Path(source_xml).parts
        if len(parts) < 4 or parts[0] != "/" or parts[2] != "etc":
            raise RouterError(f"不支持的字体 XML 路径：{source_xml}")
        output = output_root / parts[1] / "etc" / Path(*parts[3:])
        rendered.append(render_document(route_plan, source_xml, artifact_map, output))
    return {
        "renderedDocuments": len(rendered),
        "changedFonts": sum(int(item["changedFonts"]) for item in rendered),
        "documents": rendered,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--font-plan", required=True, type=Path)
    parser.add_argument("--xml-map", type=Path)
    parser.add_argument("--snapshot-root", type=Path)
    parser.add_argument("--allow-live", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate", type=Path)
    parser.add_argument("--render-plan", type=Path)
    parser.add_argument("--artifact-map", type=Path)
    parser.add_argument("--output-tree", type=Path)
    args = parser.parse_args()

    try:
        font_plan = _load(args.font_plan)
        if args.render_plan is not None:
            route_plan = _load(args.render_plan)
            validate_route_plan(route_plan, font_plan=font_plan)
            if args.artifact_map is None or args.output_tree is None:
                raise RouterError("--render-plan 需要 --artifact-map 与 --output-tree")
            report = render_all(route_plan, _artifact_map(args.artifact_map), args.output_tree)
            print(json.dumps({"status": "ok", **report}, ensure_ascii=False, separators=(",", ":")))
            return 0

        if args.validate is not None:
            route_plan = _load(args.validate)
            validate_route_plan(route_plan, font_plan=font_plan)
            print(json.dumps({
                "status": "ok",
                "schema": route_plan["schema"],
                "routeId": route_plan["routeId"],
                **route_plan["summary"],
            }, ensure_ascii=False, separators=(",", ":")))
            return 0

        route_plan = build_route_plan(
            font_plan,
            _xml_map(args.xml_map),
            args.snapshot_root,
            args.allow_live,
        )
        if args.output is not None:
            _atomic_json(args.output, route_plan)
        print(json.dumps({
            "status": "ok",
            "schema": route_plan["schema"],
            "routeId": route_plan["routeId"],
            **route_plan["summary"],
        }, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (RouterError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "error", "message": str(error)}, ensure_ascii=False, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
