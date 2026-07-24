#!/usr/bin/env python3
"""Render a v2.2 per-device font payload into a staged module tree.

System and OEM XML files are rewritten slot-by-slot. Android updatable-font
families are handled without changing signed /data/fonts/files payloads: only
fully mapped named UI families are removed from a private config.xml view and
injected into both primary and legacy system font XML views.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Iterable

import device_font_template as template_engine

SCHEMA = "device-font-overlay-v1"
PAYLOAD_SCHEMA = "device-font-payload-v1"
DYNAMIC_PREFIX = "/data/fonts/"
PRIMARY_SYSTEM_XMLS = (
    "/system/etc/font_fallback.xml",
    "/system/etc/fonts.xml",
)


class OverlayError(RuntimeError):
    pass


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def normalize(value: str) -> str:
    return template_engine.normalize(value)


def nearest_weight(raw: str | None) -> int:
    return template_engine.nearest_weight(raw)


def is_dynamic_path(path: str) -> bool:
    return path.replace("\\", "/").startswith(DYNAMIC_PREFIX)


def namespace(root: ET.Element) -> str:
    if root.tag.startswith("{") and "}" in root.tag:
        return root.tag.split("}", 1)[0] + "}"
    return ""


def parse(path: Path) -> ET.ElementTree:
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    return ET.parse(path, parser=parser)


def atomic_tree_write(tree: ET.ElementTree, output: Path, mode: int = 0o644) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(tree, space="    ")
    fd, temporary_raw = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    os.close(fd)
    temporary = Path(temporary_raw)
    try:
        tree.write(temporary, encoding="utf-8", xml_declaration=True)
        os.chmod(temporary, mode)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(payload: dict[str, Any], output: Path, mode: int = 0o600) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_raw = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    os.close(fd)
    temporary = Path(temporary_raw)
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        os.chmod(temporary, mode)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def font_postscript(element: ET.Element) -> str:
    return (
        element.attrib.get("name", "")
        or element.attrib.get("postScriptName", "")
        or element.attrib.get("postscriptName", "")
    ).strip()


def font_key(source_xml: str, family_name: str, font: ET.Element) -> tuple[Any, ...]:
    try:
        index = int(font.attrib.get("index", "0") or "0")
    except ValueError:
        index = 0
    return (
        source_xml,
        normalize(family_name),
        nearest_weight(font.attrib.get("weight")),
        font.attrib.get("style", "normal").lower(),
        max(0, index),
        (font.text or "").strip(),
        font_postscript(font),
    )


def slot_key(slot: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(slot.get("sourceXml", "")),
        normalize(str(slot.get("familyNormalized") or slot.get("family") or "")),
        nearest_weight(str(slot.get("weight", "400"))),
        str(slot.get("style", "normal")).lower(),
        int(slot.get("index") or 0),
        str(slot.get("declared", "")).strip(),
        str(slot.get("postScriptName", "")).strip(),
    )


def mapped_queues(slots: Iterable[dict[str, Any]]) -> dict[tuple[Any, ...], deque[dict[str, Any]]]:
    result: dict[tuple[Any, ...], deque[dict[str, Any]]] = defaultdict(deque)
    for slot in slots:
        if slot.get("generatedFile"):
            result[slot_key(slot)].append(slot)
    return result


def fallback_match(
    queues: dict[tuple[Any, ...], deque[dict[str, Any]]],
    source_xml: str,
    family: str,
    font: ET.Element,
) -> dict[str, Any] | None:
    exact = font_key(source_xml, family, font)
    if queues.get(exact):
        return queues[exact].popleft()
    prefix = exact[:5]
    candidates = [key for key, values in queues.items() if values and key[:5] == prefix]
    if len(candidates) == 1:
        return queues[candidates[0]].popleft()
    return None


def clean_font_node(font: ET.Element, filename: str) -> None:
    font.text = filename
    for key in ("index", "name", "postScriptName", "postscriptName"):
        font.attrib.pop(key, None)
    for child in list(font):
        if local(child.tag) == "axis":
            font.remove(child)


def partition_for_xml(source_xml: str) -> str:
    parts = Path(source_xml).parts
    if len(parts) < 2 or parts[0] != "/":
        raise OverlayError(f"字体 XML 不是绝对路径：{source_xml}")
    partition = parts[1]
    if not re.fullmatch(r"[A-Za-z0-9_]+", partition):
        raise OverlayError(f"无法识别字体 XML 分区：{source_xml}")
    return partition


def copy_generated(
    payload_root: Path,
    stage: Path,
    partition: str,
    filename: str,
    copied: dict[tuple[str, str], Path],
) -> Path:
    key = (partition, filename)
    existing = copied.get(key)
    if existing is not None:
        return existing
    source = payload_root / "fonts" / filename
    if not source.is_file() or source.stat().st_size < 1024:
        raise OverlayError(f"生成字体不存在或过小：{source}")
    destination = stage / partition / "fonts" / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
    except OSError:
        shutil.copyfile(source, destination)
    os.chmod(destination, 0o644)
    copied[key] = destination
    return destination


def rewrite_regular_xml(
    source_xml: str,
    input_path: Path,
    output_path: Path,
    slots: list[dict[str, Any]],
    payload_root: Path,
    stage: Path,
    copied: dict[tuple[str, str], Path],
) -> dict[str, Any]:
    tree = parse(input_path)
    queues = mapped_queues(slots)
    partition = partition_for_xml(source_xml)
    changed = 0
    families: set[str] = set()
    for family in tree.getroot().iter():
        if local(family.tag) != "family":
            continue
        family_name = family.attrib.get("name", "")
        for font in list(family):
            if local(font.tag) != "font":
                continue
            mapped = fallback_match(queues, source_xml, family_name, font)
            if mapped is None:
                continue
            filename = str(mapped["generatedFile"])
            copy_generated(payload_root, stage, partition, filename, copied)
            clean_font_node(font, filename)
            family.attrib.pop("supportedAxes", None)
            changed += 1
            families.add(family_name)
    remaining = sum(len(values) for values in queues.values())
    if remaining:
        raise OverlayError(f"{source_xml} 有 {remaining} 个已生成槽位无法定位到原 XML 节点")
    if changed:
        atomic_tree_write(tree, output_path)
    return {
        "source": source_xml,
        "output": str(output_path),
        "changedFonts": changed,
        "changedFamilies": sorted(families),
    }


def dynamic_family_groups(slots: list[dict[str, Any]]) -> tuple[dict[str, list[dict[str, Any]]], set[str]]:
    all_by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for slot in slots:
        all_by_family[normalize(str(slot.get("familyNormalized") or slot.get("family") or ""))].append(slot)
    eligible: dict[str, list[dict[str, Any]]] = {}
    incomplete: set[str] = set()
    for family, family_slots in all_by_family.items():
        replaceable = [
            slot
            for slot in family_slots
            if slot.get("replaceable") and str(slot.get("style", "normal")).lower() not in ("italic", "oblique")
        ]
        if replaceable and all(slot.get("generatedFile") for slot in replaceable):
            eligible[family] = replaceable
        elif replaceable:
            incomplete.add(family)
    return eligible, incomplete


def sanitize_dynamic_xml(
    source_xml: str,
    input_path: Path,
    output_path: Path,
    eligible: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    tree = parse(input_path)
    removed: list[str] = []
    root = tree.getroot()
    for parent in root.iter():
        for child in list(parent):
            if local(child.tag) != "family":
                continue
            family = normalize(child.attrib.get("name", ""))
            if family and family in eligible:
                removed.append(child.attrib.get("name", family))
                parent.remove(child)
    if set(map(normalize, removed)) != set(eligible):
        missing = sorted(set(eligible) - set(map(normalize, removed)))
        raise OverlayError(f"动态字体配置中找不到完整 family：{', '.join(missing)}")
    atomic_tree_write(tree, output_path, 0o600)
    return {
        "source": source_xml,
        "output": str(output_path),
        "removedFamilies": sorted(removed),
    }


def remove_existing_family(root: ET.Element, family_name: str) -> None:
    target = normalize(family_name)
    for parent in root.iter():
        for child in list(parent):
            if local(child.tag) == "family" and normalize(child.attrib.get("name", "")) == target:
                parent.remove(child)


def inject_dynamic_families(
    tree: ET.ElementTree,
    eligible: dict[str, list[dict[str, Any]]],
) -> int:
    root = tree.getroot()
    ns = namespace(root)
    injected = 0
    for normalized_family, slots in sorted(eligible.items()):
        original_name = str(slots[0].get("family") or normalized_family)
        remove_existing_family(root, original_name)
        family = ET.SubElement(root, ns + "family", {"name": original_name})
        seen: set[tuple[int, str, str]] = set()
        for slot in sorted(slots, key=lambda item: (int(item.get("weight") or 400), str(item.get("style", "normal")))):
            weight = int(slot.get("weight") or 400)
            style = str(slot.get("style", "normal")).lower()
            filename = str(slot["generatedFile"])
            key = (weight, style, filename)
            if key in seen:
                continue
            seen.add(key)
            font = ET.SubElement(
                family,
                ns + "font",
                {"weight": str(weight), "style": style if style in ("normal", "italic") else "normal"},
            )
            font.text = filename
            injected += 1
    return injected


def commit_directory(stage: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    backup = output.with_name(f".{output.name}.previous.{os.getpid()}")
    shutil.rmtree(backup, ignore_errors=True)
    moved = False
    try:
        if output.exists():
            os.replace(output, backup)
            moved = True
        os.replace(stage, output)
        if moved:
            shutil.rmtree(backup, ignore_errors=True)
    except Exception:
        if not output.exists() and moved and backup.exists():
            os.replace(backup, output)
        raise


def render_overlay(
    template: dict[str, Any],
    payload: dict[str, Any],
    payload_root: Path,
    output_tree: Path,
) -> dict[str, Any]:
    if template.get("schema") != "device-font-template-v1":
        raise OverlayError(f"不支持的设备模板：{template.get('schema')!r}")
    if payload.get("schema") != PAYLOAD_SCHEMA:
        raise OverlayError(f"不支持的设备负载：{payload.get('schema')!r}")
    slots = payload.get("slots") if isinstance(payload.get("slots"), list) else []
    template_xmls = [str(item) for item in template.get("xml", [])]
    if not slots or not template_xmls:
        raise OverlayError("设备模板或负载没有可映射内容")

    stage = output_tree.with_name(f".{output_tree.name}.stage.{os.getpid()}")
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True, exist_ok=True)
    copied: dict[tuple[str, str], Path] = {}
    xml_reports: list[dict[str, Any]] = []
    dynamic_reports: list[dict[str, Any]] = []
    dynamic_slots = [slot for slot in slots if is_dynamic_path(str(slot.get("sourceXml", "")))]
    eligible_dynamic, incomplete_dynamic = dynamic_family_groups(dynamic_slots)

    try:
        by_xml: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for slot in slots:
            by_xml[str(slot.get("sourceXml", ""))].append(slot)

        system_trees: dict[str, ET.ElementTree] = {}
        system_inputs: dict[str, Path] = {}
        for source_xml in template_xmls:
            input_path = Path(source_xml)
            if not input_path.is_file():
                continue
            if is_dynamic_path(source_xml):
                if eligible_dynamic:
                    dynamic_output = stage / "dynamic" / "data-fonts-config.xml"
                    dynamic_reports.append(
                        sanitize_dynamic_xml(source_xml, input_path, dynamic_output, eligible_dynamic)
                    )
                continue
            output_path = stage / source_xml.lstrip("/")
            report = rewrite_regular_xml(
                source_xml,
                input_path,
                output_path,
                by_xml.get(source_xml, []),
                payload_root,
                stage,
                copied,
            )
            xml_reports.append(report)
            if source_xml in PRIMARY_SYSTEM_XMLS:
                tree = parse(output_path if output_path.is_file() else input_path)
                system_trees[source_xml] = tree
                system_inputs[source_xml] = input_path

        if eligible_dynamic:
            if not system_trees:
                raise OverlayError("存在动态命名字体，但设备没有可注入的系统主字体 XML")
            for family_slots in eligible_dynamic.values():
                for slot in family_slots:
                    copy_generated(payload_root, stage, "system", str(slot["generatedFile"]), copied)
            for source_xml, tree in system_trees.items():
                injected = inject_dynamic_families(tree, eligible_dynamic)
                output_path = stage / source_xml.lstrip("/")
                atomic_tree_write(tree, output_path)
                for report in xml_reports:
                    if report["source"] == source_xml:
                        report["dynamicInjectedFonts"] = injected
                        report["output"] = str(output_path)
                        break

        mapped = sum(1 for slot in slots if slot.get("generatedFile"))
        rewritten = sum(int(report.get("changedFonts", 0)) for report in xml_reports)
        injected = sum(int(report.get("dynamicInjectedFonts", 0)) for report in xml_reports)
        dynamic_mapped = sum(len(items) for items in eligible_dynamic.values())
        if rewritten + dynamic_mapped != mapped:
            raise OverlayError(
                f"槽位映射不完整：mapped={mapped} rewritten={rewritten} dynamic={dynamic_mapped}"
            )

        report = {
            "schema": SCHEMA,
            "deviceFingerprint": template.get("fingerprint", ""),
            "payloadSchema": payload.get("schema", ""),
            "summary": {
                "mappedSlots": mapped,
                "rewrittenSlots": rewritten,
                "dynamicSlots": dynamic_mapped,
                "dynamicInjectedFonts": injected,
                "uniqueCopiedFonts": len(copied),
                "xmlOutputs": sum(1 for item in xml_reports if int(item.get("changedFonts", 0)) or int(item.get("dynamicInjectedFonts", 0))),
                "incompleteDynamicFamilies": len(incomplete_dynamic),
            },
            "xml": xml_reports,
            "dynamic": dynamic_reports,
            "incompleteDynamicFamilies": sorted(incomplete_dynamic),
            "copiedFonts": [
                {
                    "partition": partition,
                    "filename": filename,
                    "path": str(path.relative_to(stage)),
                    "bytes": path.stat().st_size,
                }
                for (partition, filename), path in sorted(copied.items())
            ],
            "dynamicMounts": [
                {
                    "source": "dynamic/data-fonts-config.xml",
                    "target": report["source"],
                }
                for report in dynamic_reports
            ],
        }
        atomic_json(report, stage / "overlay-manifest.json")
        commit_directory(stage, output_tree)
        return report
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--payload", required=True, type=Path)
    parser.add_argument("--payload-root", required=True, type=Path)
    parser.add_argument("--output-tree", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        template = json.loads(args.template.read_text(encoding="utf-8"))
        payload = json.loads(args.payload.read_text(encoding="utf-8"))
        report = render_overlay(template, payload, args.payload_root, args.output_tree)
        print(
            json.dumps(
                {"status": "ok", **report["summary"], "output": str(args.output_tree)},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {"status": "error", "message": str(exc) or exc.__class__.__name__},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
