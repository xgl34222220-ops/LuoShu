#!/usr/bin/env python3
"""Experimental HyperOS seed-XML rewrite (default OFF).

HyperOS exposes ``/system/etc/fonts.xml`` and ``font_fallback.xml`` as symlinks
to ``/data/system/fonts/theme_webview/``. init copies those files from the
``/system_ext/etc/miui_*.xml`` seeds at post-fs-data and the framework later
switches between ``hyper_*`` and ``miui_*`` seeds. A per-file bind of the
logical XML therefore lands on a ``/data`` copy that init or the framework can
replace.

When ``config/hyperos_source_xml.conf`` contains ``enabled=1`` this step adds
per-slot rewritten copies of the system_ext seeds to LuoShu's staged overlay
tree, so the existing private self-mount overlays them like every other staged
XML. Only the file-name text of ``<font>`` nodes whose slot LuoShu already
replaced is changed; every other byte of the seed stays identical. Any parse,
alignment or validation problem makes the whole step a no-op.
"""
from __future__ import annotations

import html
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable

SCHEMA = "hyperos-source-xml-v1"
SEED_PATTERNS = (
    "hyper_fonts*.xml",
    "hyper_font_fallback*.xml",
    "miui_fonts*.xml",
    "miui_font_fallback*.xml",
)
LOGICAL_SEED_ETC = "/system_ext/etc"
LOGICAL_SYSTEM_XMLS = ("fonts.xml", "font_fallback.xml")
DATA_SEED_PREFIX = "/data/system/fonts/theme_webview/"
_LUOSHU_MARKER = re.compile(rb"LuoShu(?:Mono|Slot)?-")
_SAFE_GENERATED = re.compile(r"^LuoShu[A-Za-z0-9._-]*\.(?:ttf|otf)$")
_MASK_RE = re.compile(r"<!--.*?-->|<!\[CDATA\[.*?\]\]>|<\?.*?\?>|<!DOCTYPE[^>]*>", re.S)
_FONT_START = re.compile(r"<font(?=[\s/>])([^>]*?)(/?)>", re.S)
_FONT_END = re.compile(r"</font\s*>")
_ATTR = re.compile(r"([A-Za-z_][\w:.-]*)\s*=\s*(['\"])(.*?)\2", re.S)


class SourceXmlError(RuntimeError):
    pass


def _module_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def config_path() -> Path:
    raw = os.environ.get("LUOSHU_HYPEROS_SOURCE_XML_CONF", "").strip()
    return Path(raw) if raw else _module_dir() / "config" / "hyperos_source_xml.conf"


def enabled() -> bool:
    """Only an exact ``enabled=1`` line turns the experiment on.

    Same rule as ``grep -qx 'enabled=1'`` in device_font_cache.sh.
    """
    try:
        text = config_path().read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return any(line == "enabled=1" for line in text.split("\n"))


def _log(event: dict[str, Any]) -> None:
    raw = os.environ.get("LUOSHU_HYPEROS_SOURCE_XML_LOG", "").strip()
    path = Path(raw) if raw else _module_dir() / "logs" / "hyperos-source-xml.log"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{stamp}] {json.dumps(event, ensure_ascii=False, separators=(',', ':'))}\n")
    except OSError:
        pass


def _seed_actual_root() -> Path:
    raw = os.environ.get("LUOSHU_HYPEROS_SEED_ETC_ROOT", "").strip()
    return Path(raw) if raw else Path(LOGICAL_SEED_ETC)


def _system_etc_root() -> Path:
    raw = os.environ.get("LUOSHU_HYPEROS_SYSTEM_ETC_ROOT", "").strip()
    return Path(raw) if raw else Path("/system/etc")


def link_chain(path: Path, logical: str) -> dict[str, Any]:
    """Describe one XML path: symlink hop, final target and whether /data seeds it."""
    entry: dict[str, Any] = {"path": logical, "kind": "missing", "link": "", "resolved": ""}
    try:
        if path.is_symlink():
            entry["kind"] = "symlink"
            entry["link"] = os.readlink(path)
            entry["resolved"] = os.path.realpath(path)
        elif path.is_file():
            entry["kind"] = "file"
            entry["resolved"] = logical
    except OSError:
        entry["kind"] = "unreadable"
    target = str(entry.get("resolved") or entry.get("link") or "")
    entry["dataSeeded"] = target.startswith(DATA_SEED_PREFIX)
    return entry


def discover_seeds(actual_root: Path | None = None) -> list[tuple[str, Path]]:
    root = actual_root or _seed_actual_root()
    found: dict[str, Path] = {}
    if not root.is_dir():
        return []
    for pattern in SEED_PATTERNS:
        for actual in root.glob(pattern):
            if actual.is_file():
                found[f"{LOGICAL_SEED_ETC}/{actual.name}"] = actual
    return sorted(found.items())


def stock_seed_input(template: dict[str, Any], logical: str, live: Path) -> tuple[Path, str]:
    snapshot_root = str(template.get("xmlSourceRoot") or "").strip()
    if snapshot_root:
        snapshot = Path(snapshot_root) / logical.lstrip("/")
        if snapshot.is_file():
            return snapshot, "template-snapshot"
    state_root = Path(os.environ.get("LUOSHU_SELF_MOUNT_STATE_ROOT", "/data/adb/luoshu/self-mount"))
    lower = state_root / "lower" / "system_ext-etc" / Path(logical).name
    if lower.is_file():
        return lower, "self-mount-lower"
    return live, "live"


def _local(tag: Any) -> str:
    return str(tag).rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _normalize(value: str) -> str:
    # Same normalisation as device_font_template_base.normalize (slot keys).
    return re.sub(r"[\s_-]+", "-", str(value or "").strip().lower()).strip("-")


def _weight(raw: Any) -> int:
    # Same nearest-weight rule as device_font_template_base.nearest_weight.
    try:
        requested = int(str(raw or "400").strip() or "400")
    except ValueError:
        requested = 400
    requested = max(1, min(1000, requested))
    return min(range(100, 1000, 100), key=lambda value: abs(value - requested))


def _postscript(attrs: dict[str, str]) -> str:
    return (attrs.get("name", "") or attrs.get("postScriptName", "") or attrs.get("postscriptName", "")).strip()


def _index(attrs: dict[str, str]) -> int:
    try:
        return max(0, int(attrs.get("index", "0") or "0"))
    except ValueError:
        return -1


def _font_nodes(root: ET.Element) -> list[tuple[ET.Element, str]]:
    parents = {child: parent for parent in root.iter() for child in list(parent)}
    result: list[tuple[ET.Element, str]] = []
    for node in root.iter():
        if _local(node.tag) != "font":
            continue
        family = parents.get(node)
        name = ""
        current = family
        while current is not None:
            tag = _local(current.tag)
            if tag in ("family", "family-list"):
                name = current.attrib.get("name", "").strip()
                if name:
                    break
            current = parents.get(current)
        result.append((node, name))
    return result


def _slot_index(slots: list[dict[str, Any]]) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    index: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for slot in slots:
        generated = str(slot.get("generatedFile") or "")
        source = str(slot.get("sourceXml") or "").replace("\\", "/")
        if not generated or "/data/fonts/" in source:
            continue
        key = (
            _normalize(str(slot.get("familyNormalized") or slot.get("family") or "")),
            _weight(slot.get("weight", "400")),
            str(slot.get("style", "normal")).lower(),
            int(slot.get("index") or 0),
            str(slot.get("declared", "")).strip(),
            str(slot.get("postScriptName", "")).strip(),
        )
        index.setdefault(key, []).append(slot)
    return index


def _pair_name(seed_name: str) -> str:
    return "font_fallback.xml" if "fallback" in seed_name else "fonts.xml"


def plan_mapping(
    root: ET.Element,
    slots: list[dict[str, Any]],
    seed_name: str,
) -> tuple[dict[int, str], list[str]]:
    """Return font-node ordinal -> generated filename, plus ambiguity notes."""
    index = _slot_index(slots)
    pair = _pair_name(seed_name)
    mapping: dict[int, str] = {}
    notes: list[str] = []
    for ordinal, (node, family) in enumerate(_font_nodes(root)):
        attrs = dict(node.attrib)
        key = (
            _normalize(family),
            _weight(attrs.get("weight")),
            attrs.get("style", "normal").lower(),
            _index(attrs),
            (node.text or "").strip(),
            _postscript(attrs),
        )
        candidates = index.get(key, [])
        if not candidates:
            continue
        paired = [s for s in candidates if Path(str(s.get("sourceXml", ""))).name == pair]
        chosen = paired or candidates
        names = sorted({str(s["generatedFile"]) for s in chosen})
        if len(names) != 1:
            notes.append(f"ambiguous:{family}:{key[1]}:{key[4]}")
            continue
        mapping[ordinal] = names[0]
    return mapping, notes


def _masked(text: str) -> str:
    def blank(match: re.Match[str]) -> str:
        return "".join("\n" if ch == "\n" else " " for ch in match.group(0))
    return _MASK_RE.sub(blank, text)


def _start_attrs(raw: str) -> dict[str, str]:
    return {key: html.unescape(value) for key, _quote, value in _ATTR.findall(raw)}


def rewrite_text(raw: bytes, root: ET.Element, mapping: dict[int, str]) -> bytes:
    """Replace only the file-name text of mapped <font> nodes, byte-for-byte elsewhere."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SourceXmlError("seed XML is not UTF-8") from error
    masked = _masked(text)
    nodes = _font_nodes(root)
    spans: list[tuple[int, int, str]] = []
    position = 0
    ordinal = 0
    while True:
        start = _FONT_START.search(masked, position)
        if start is None:
            break
        if ordinal >= len(nodes):
            raise SourceXmlError("more <font> tags than parsed nodes")
        node = nodes[ordinal][0]
        tag_attrs = _start_attrs(start.group(1))
        node_attrs = {k: v for k, v in node.attrib.items() if not k.startswith("{")}
        if tag_attrs != node_attrs:
            raise SourceXmlError(f"<font> #{ordinal} attributes do not align")
        if start.group(2) == "/":
            if ordinal in mapping:
                raise SourceXmlError(f"<font> #{ordinal} has no file text")
            position = start.end()
            ordinal += 1
            continue
        end = _FONT_END.search(masked, start.end())
        if end is None:
            raise SourceXmlError(f"<font> #{ordinal} is not closed")
        content_end = masked.find("<", start.end(), end.start())
        if content_end < 0:
            content_end = end.start()
        segment = text[start.end():content_end]
        expected = (node.text or "").strip()
        if segment.strip() != expected and ordinal in mapping:
            raise SourceXmlError(f"<font> #{ordinal} text does not align")
        if ordinal in mapping:
            new_name = mapping[ordinal]
            if not _SAFE_GENERATED.match(new_name) or not expected or "&" in segment:
                raise SourceXmlError(f"<font> #{ordinal} cannot be rewritten safely")
            if _index(dict(node.attrib)) != 0:
                raise SourceXmlError(f"<font> #{ordinal} uses a collection index")
            lead = len(segment) - len(segment.lstrip())
            name_start = start.end() + lead
            spans.append((name_start, name_start + len(expected), new_name))
        position = end.end()
        ordinal += 1
    if ordinal != len(nodes):
        raise SourceXmlError("parsed <font> nodes are missing from the text scan")
    result = text
    for begin, finish, replacement in sorted(spans, reverse=True):
        if result[begin:finish] != text[begin:finish]:
            raise SourceXmlError("overlapping rewrite spans")
        result = result[:begin] + replacement + result[finish:]
    return result.encode("utf-8")


def _parse_bytes(raw: bytes) -> ET.Element:
    try:
        return ET.fromstring(raw)
    except ET.ParseError as error:
        raise SourceXmlError(f"XML parse failed: {error}") from error


def validate_rewrite(original: bytes, rewritten: bytes, mapping: dict[int, str]) -> None:
    old_root = _parse_bytes(original)
    new_root = _parse_bytes(rewritten)
    if _local(new_root.tag) != _local(old_root.tag):
        raise SourceXmlError("root element changed")
    old_all = list(old_root.iter())
    new_all = list(new_root.iter())
    if [_local(n.tag) for n in old_all] != [_local(n.tag) for n in new_all]:
        raise SourceXmlError("element structure changed")
    for old, new in zip(old_all, new_all):
        if old.attrib != new.attrib:
            raise SourceXmlError("attributes changed")
    old_fonts = _font_nodes(old_root)
    new_fonts = _font_nodes(new_root)
    for ordinal, ((old, _), (new, _)) in enumerate(zip(old_fonts, new_fonts)):
        want = mapping.get(ordinal, (old.text or "").strip())
        if (new.text or "").strip() != want:
            raise SourceXmlError(f"<font> #{ordinal} text mismatch after rewrite")
    # Independent byte check: every line is identical except for one stock file
    # name swapped for its LuoShu generated name.
    pairs: dict[bytes, set[bytes]] = {}
    for ordinal, (old, _) in enumerate(old_fonts):
        if ordinal in mapping:
            pairs.setdefault((old.text or "").strip().encode("utf-8"), set()).add(
                mapping[ordinal].encode("utf-8"))
    old_lines = original.splitlines(keepends=True)
    new_lines = rewritten.splitlines(keepends=True)
    if len(old_lines) != len(new_lines):
        raise SourceXmlError("line structure changed")
    changed_lines = 0
    for old_line, new_line in zip(old_lines, new_lines):
        if old_line == new_line:
            continue
        if not _line_swap_only(old_line, new_line, pairs):
            raise SourceXmlError("unexpected byte changes outside rewritten names")
        changed_lines += 1
    if mapping and not changed_lines:
        raise SourceXmlError("mapped rewrite produced no change")


def _line_swap_only(old: bytes, new: bytes, pairs: dict[bytes, set[bytes]], depth: int = 0) -> bool:
    """True when ``new`` equals ``old`` with some stock names swapped for their generated names."""
    if old == new:
        return True
    if depth > 8:
        return False
    for stock, generated_names in pairs.items():
        at = old.find(stock)
        while at >= 0:
            if new[:at] == old[:at]:
                for generated in generated_names:
                    if new[at:at + len(generated)] == generated and _line_swap_only(
                        old[at + len(stock):], new[at + len(generated):], pairs, depth + 1
                    ):
                        return True
            at = old.find(stock, at + 1)
    return False


def apply(
    template: dict[str, Any],
    slots: list[dict[str, Any]],
    payload_root: Path,
    stage: Path,
    copied: dict[tuple[str, str], Path],
    copy_generated: Callable[..., Path],
) -> dict[str, Any]:
    """Stage rewritten seeds. Never raises; on any failure nothing is left behind."""
    system_etc = _system_etc_root()
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "skipped",
        "links": [link_chain(system_etc / name, f"/system/etc/{name}") for name in LOGICAL_SYSTEM_XMLS],
        "seeds": [],
    }
    written: list[Path] = []
    added_fonts: list[tuple[str, str]] = []
    try:
        seeds = discover_seeds()
        if not seeds:
            report["reason"] = "no-seed-xml"
            _log(report)
            return report
        planned: list[tuple[str, bytes, dict[int, str], str]] = []
        for logical, live in seeds:
            source, origin = stock_seed_input(template, logical, live)
            raw = source.read_bytes()
            if _LUOSHU_MARKER.search(raw):
                raise SourceXmlError(f"{logical} is not a stock view ({origin})")
            root = _parse_bytes(raw)
            mapping, notes = plan_mapping(root, slots, Path(logical).name)
            entry: dict[str, Any] = {
                "source": logical,
                "input": origin,
                "changedFonts": len(mapping),
                "notes": notes,
                "link": link_chain(live, logical),
            }
            report["seeds"].append(entry)
            if not mapping:
                continue
            rewritten = rewrite_text(raw, root, mapping)
            validate_rewrite(raw, rewritten, mapping)
            output = stage / logical.lstrip("/")
            if output.exists():
                raise SourceXmlError(f"{logical} already staged by the main renderer")
            planned.append((logical, rewritten, mapping, str(output)))
        if not planned:
            report["reason"] = "no-mapped-slots"
            _log(report)
            return report
        for _logical, _rewritten, mapping, _output in planned:
            for name in sorted(set(mapping.values())):
                key = ("system", name)
                if key not in copied:
                    copy_generated(payload_root, stage, "system", name, copied)
                    added_fonts.append(key)
        for _logical, rewritten, _mapping, output_raw in planned:
            output = Path(output_raw)
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary = output.with_name(f".{output.name}.tmp.{os.getpid()}")
            temporary.write_bytes(rewritten)
            os.chmod(temporary, 0o644)
            os.replace(temporary, output)
            written.append(output)
            if output.read_bytes() != rewritten:
                raise SourceXmlError(f"{output} verification failed")
        report["status"] = "applied"
        report["stagedXml"] = [str(path.relative_to(stage)) for path in written]
        _log(report)
        return report
    except Exception as error:  # fail closed: undo our own staged files only
        for path in written:
            try:
                path.unlink()
            except OSError:
                pass
        for key in added_fonts:
            path = copied.pop(key, None)
            if path is not None:
                try:
                    path.unlink()
                except OSError:
                    pass
        report["status"] = "error"
        report["reason"] = str(error) or error.__class__.__name__
        report.pop("stagedXml", None)
        _log(report)
        return report
