#!/usr/bin/env python3
"""HyperOS seed-XML rewrite (default ON for HyperOS, ``enabled=0`` turns it off).

HyperOS exposes ``/system/etc/fonts.xml`` and ``font_fallback.xml`` as symlinks
to ``/data/system/fonts/theme_webview/``. init copies those files from the
``/system_ext/etc/miui_*.xml`` seeds at post-fs-data and the framework later
switches between ``hyper_*`` and ``miui_*`` seeds. A per-file bind of the
logical XML therefore lands on a ``/data`` copy that init or the framework can
replace.

Unless ``config/hyperos_source_xml.conf`` contains an exact ``enabled=0`` line,
this step adds per-slot rewritten copies of the system_ext seeds to LuoShu's
staged overlay tree, so the existing private self-mount overlays them like every
other staged XML. It runs only where seed XML exists (HyperOS/MIUI), so other
ROMs are unaffected. The same rewrite covers ``/product/etc/fonts_customization.xml``
(AOSP OEM customization) and ``/system/etc/{fonts,font_fallback}.xml`` when they
are regular files the main renderer did not stage; on HyperOS 2+ those two are
symlinks to ``/data/system/fonts/theme_webview/`` that init fills from the
rewritten seeds, so they are reported and left alone.

Only the file-name text of ``<font>`` nodes whose slot LuoShu already replaced
is changed. Every other byte stays identical. Files the physical policy keeps
stock (clock/tabular Mono, MiSansL3, disabled optional groups) are never pointed
at a proportional build.

The main ``sans-serif`` family and ``lang="zh-*"`` families are never renamed:
they keep their stock file names and the physical route replaces the content of
those same-name slots (the pre-v4.3 / 1bf06137 behaviour). Chromium's
``SkFontMgr_android_ndk`` re-opens every font by path inside the WebView
renderer; a new ``LuoShu*.ttf`` name that the renderer cannot open (or that no
longer matches Skia's own fonts.xml parse) drops the whole family, so web pages
fell back to stock fonts and mixed weights for Simplified-only Han.

After rendering, every output is re-parsed and checked: structure and
attributes unchanged, every family still complete with non-empty file names,
every rewritten name present in the staged tree, and no stock reference that
resolved before now unresolved. Any parse, alignment or validation problem
makes the whole step a no-op, so the ROM XML is used unchanged.
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

try:
    import hyperos_physical_policy as physical_policy
except ImportError:  # pragma: no cover - module layout always ships it
    physical_policy = None

SCHEMA = "hyperos-source-xml-v3"
SEED_PATTERNS = (
    "hyper_fonts*.xml",
    "hyper_font_fallback*.xml",
    "miui_fonts*.xml",
    "miui_font_fallback*.xml",
)
LOGICAL_SEED_ETC = "/system_ext/etc"
LOGICAL_SYSTEM_XMLS = ("fonts.xml", "font_fallback.xml")
LOGICAL_PRODUCT_CUSTOMIZATION = "/product/etc/fonts_customization.xml"
DATA_SEED_PREFIX = "/data/system/fonts/theme_webview/"
# Families whose <font> file names stay stock; their same-name slots carry the
# user font through the physical route (normalized family names).
STOCK_NAME_FAMILIES = frozenset({"sans-serif"})
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
    """On by default; only an exact ``enabled=0`` line turns it off.

    Same rule as ``grep -qx 'enabled=0'`` in device_font_cache.sh. The step is a
    no-op wherever no HyperOS/MIUI seed XML exists.
    """
    try:
        text = config_path().read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True
    return not any(line == "enabled=0" for line in text.split("\n"))


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


def _product_etc_root() -> Path:
    raw = os.environ.get("LUOSHU_HYPEROS_PRODUCT_ETC_ROOT", "").strip()
    return Path(raw) if raw else Path("/product/etc")


def _font_root(partition: str) -> Path:
    """Stock font directory an XML in ``partition`` resolves file names against."""
    raw = os.environ.get(f"LUOSHU_{partition.upper()}_FONTS_ROOT", "").strip()
    return Path(raw) if raw else Path(f"/{partition}/fonts")


def discover_extra_sources() -> list[tuple[str, Path, str]]:
    """Regular (non-seeded) system XML and the product OEM customization XML."""
    found: list[tuple[str, Path, str]] = []
    system_etc = _system_etc_root()
    for name in LOGICAL_SYSTEM_XMLS:
        path = system_etc / name
        if path.is_file() and not path.is_symlink():
            found.append((f"/system/etc/{name}", path, "system"))
    product = _product_etc_root() / Path(LOGICAL_PRODUCT_CUSTOMIZATION).name
    if product.is_file() and not product.is_symlink():
        found.append((LOGICAL_PRODUCT_CUSTOMIZATION, product, "product"))
    return found


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
    partition = logical.strip("/").split("/", 1)[0]
    lower = state_root / "lower" / f"{partition}-etc" / Path(logical).name
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


def _family_attrs(root: ET.Element) -> dict[int, dict[str, str]]:
    """font ordinal -> attributes of its nearest enclosing <family>."""
    parents = {child: parent for parent in root.iter() for child in list(parent)}
    result: dict[int, dict[str, str]] = {}
    for ordinal, (node, _name) in enumerate(_font_nodes(root)):
        current = parents.get(node)
        while current is not None and _local(current.tag) != "family":
            current = parents.get(current)
        result[ordinal] = dict(current.attrib) if current is not None else {}
    return result


def _policy_allows(declared: str, generated: str, monospace_build: bool = False) -> bool:
    if physical_policy is None:
        return True
    return physical_policy.xml_file_allowed(declared, generated, monospace_build=monospace_build)


def _monospace_build(slots: list[dict[str, Any]]) -> bool:
    """Per-slot builds with a mono/clock role keep stock advances exactly."""
    return bool(slots) and all(
        isinstance(slot.get("roles"), list) and {"mono", "clock"} & set(slot["roles"])
        for slot in slots)


def is_zh_family(attrs: dict[str, str]) -> bool:
    """Any family declaring a zh lang tag (zh-Hans, "zh-Hant zh-Bopo", "zh-Hans ja", ...)."""
    tags = re.split(r"[\s,]+", attrs.get("lang", "").strip())
    return any(tag == "zh" or tag.startswith("zh-") for tag in tags if tag)


def plan_mapping(
    root: ET.Element,
    slots: list[dict[str, Any]],
    seed_name: str,
) -> tuple[dict[int, str], list[str]]:
    """Return font-node ordinal -> generated filename, plus notes."""
    index = _slot_index(slots)
    pair = _pair_name(seed_name)
    mapping: dict[int, str] = {}
    notes: list[str] = []
    families = _family_attrs(root)
    for ordinal, (node, family) in enumerate(_font_nodes(root)):
        attrs = dict(node.attrib)
        declared = (node.text or "").strip()
        family_attrs = families.get(ordinal, {})
        # Main sans-serif and zh families keep stock file names; the physical
        # route swaps the content of those same-name slots.
        if _normalize(family) in STOCK_NAME_FAMILIES or is_zh_family(family_attrs):
            if declared:
                notes.append(f"stock-name-kept:{declared}")
            continue
        key = (
            _normalize(family),
            _weight(attrs.get("weight")),
            attrs.get("style", "normal").lower(),
            _index(attrs),
            declared,
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
        if not _policy_allows(declared, names[0], _monospace_build(chosen)):
            notes.append(f"policy-kept:{declared}")
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


def _font_texts(root: ET.Element) -> list[str]:
    return [(node.text or "").strip() for node, _family in _font_nodes(root)]


def validate_references(
    original: bytes,
    rewritten: bytes,
    stage: Path,
    partition: str,
    stock_fonts: Path,
) -> None:
    """Strict post-render check: families complete, every reference resolvable.

    A rewritten name must exist in the staged ``<partition>/fonts``. A stock name
    must resolve as before; names that were already unresolved on this ROM are
    tolerated (OEM lists sometimes name optional files) but never newly created.
    """
    old_root = _parse_bytes(original)
    new_root = _parse_bytes(rewritten)
    old_families = [f for f in old_root.iter() if _local(f.tag) == "family"]
    new_families = [f for f in new_root.iter() if _local(f.tag) == "family"]
    if len(old_families) != len(new_families):
        raise SourceXmlError("family count changed")
    for old, new in zip(old_families, new_families):
        old_fonts = [n for n in old.iter() if _local(n.tag) == "font"]
        new_fonts = [n for n in new.iter() if _local(n.tag) == "font"]
        if len(old_fonts) != len(new_fonts):
            raise SourceXmlError(f"family {old.attrib.get('name', '')!r} lost fonts")
        if any(not (n.text or "").strip() for n, o in zip(new_fonts, old_fonts) if (o.text or "").strip()):
            raise SourceXmlError(f"family {old.attrib.get('name', '')!r} has an empty font")
    staged_fonts = stage / partition / "fonts"

    def resolves(name: str) -> bool:
        if not name or "/" in name or name in (".", ".."):
            return False
        return (staged_fonts / name).is_file() or (stock_fonts / name).exists()

    before = {name for name in _font_texts(old_root) if not resolves(name)}
    for old_name, new_name in zip(_font_texts(old_root), _font_texts(new_root)):
        if old_name == new_name:
            if not resolves(new_name) and new_name not in before:
                raise SourceXmlError(f"stock reference {new_name} no longer resolves")
            continue
        if not _SAFE_GENERATED.match(new_name) or not (staged_fonts / new_name).is_file():
            raise SourceXmlError(f"rewritten reference {new_name} missing from staged {partition}/fonts")


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
        "extra": [],
    }
    written: list[Path] = []
    added_fonts: list[tuple[str, str]] = []
    try:
        seeds = discover_seeds()
        if not seeds:
            report["reason"] = "no-seed-xml"
            _log(report)
            return report
        sources: list[tuple[str, Path, str, bool]] = [
            (logical, live, "system", True) for logical, live in seeds]
        sources += [(logical, live, partition, False)
                    for logical, live, partition in discover_extra_sources()]
        planned: list[tuple[str, bytes, bytes, dict[int, str], str, str]] = []
        for logical, live, partition, is_seed in sources:
            output = stage / logical.lstrip("/")
            entry: dict[str, Any] = {"source": logical, "link": link_chain(live, logical)}
            (report["seeds"] if is_seed else report["extra"]).append(entry)
            if output.exists():
                if is_seed:
                    raise SourceXmlError(f"{logical} already staged by the main renderer")
                entry["skipped"] = "staged-by-main-renderer"
                continue
            source, origin = stock_seed_input(template, logical, live)
            entry["input"] = origin
            raw = source.read_bytes()
            if _LUOSHU_MARKER.search(raw):
                raise SourceXmlError(f"{logical} is not a stock view ({origin})")
            root = _parse_bytes(raw)
            mapping, notes = plan_mapping(root, slots, Path(logical).name)
            entry["changedFonts"] = len(mapping)
            entry["notes"] = notes
            if not mapping:
                continue
            rewritten = rewrite_text(raw, root, mapping)
            validate_rewrite(raw, rewritten, mapping)
            planned.append((logical, raw, rewritten, mapping, str(output), partition))
        if not planned:
            report["reason"] = "no-mapped-slots"
            _log(report)
            return report
        for _logical, _raw, _rewritten, mapping, _output, partition in planned:
            for name in sorted(set(mapping.values())):
                key = (partition, name)
                if key not in copied:
                    copy_generated(payload_root, stage, partition, name, copied)
                    added_fonts.append(key)
        for logical, raw, rewritten, _mapping, _output, partition in planned:
            validate_references(raw, rewritten, stage, partition, _font_root(partition))
        for _logical, _raw, rewritten, _mapping, output_raw, _partition in planned:
            output = Path(output_raw)
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary = output.with_name(f".{output.name}.tmp.{os.getpid()}")
            temporary.write_bytes(rewritten)
            os.chmod(temporary, 0o644)
            os.replace(temporary, output)
            written.append(output)
            if output.read_bytes() != rewritten:
                raise SourceXmlError(f"{output} verification failed")
            # Final gate: what is on disk must parse.
            _parse_bytes(output.read_bytes())
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
