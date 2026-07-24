#!/usr/bin/env python3
"""Capture Android/OEM stock font slots and script-specific visual contracts.

The scanner is read-only. A shell guard is responsible for invoking it only on a
clean default-font boot. The JSON keeps the historical template schema for payload
compatibility and carries captureRevision=2 to reject templates made from a mounted
LuoShu payload.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import statistics
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTCollection, TTFont

SCHEMA = "device-font-template-v1"
CAPTURE_REVISION = 2
PROBE_SCHEMA = "script-anchors-v2"
FONT_SUFFIXES = (".ttf", ".otf", ".ttc", ".otc")
WEIGHTS = (100, 200, 300, 400, 500, 600, 700, 800, 900)

GLOBAL_EXACT = {
    "sans", "sans-serif", "sans-serif-condensed", "default", "default-sans",
    "system-ui", "ui-sans-serif", "roboto", "roboto-flex", "roboto-static",
    "google-sans", "google-sans-text", "google-sans-flex", "google-sans-display",
    "source-sans", "source-sans-pro", "noto-sans", "noto-sans-cjk", "miui",
    "mipro", "misans", "mi-sans", "sysfont", "sys-font", "sys-sans", "sys-sans-en",
    "op-sans", "op-sans-en", "oplus-sans", "oppo-sans", "opposans", "oplus-os-ui",
    "oplusosui", "coloros-sans", "oneplus-sans", "realme-sans", "vivo-sans",
    "vivosans", "vivo-sans-vf", "origin", "originos", "origin-sans",
    "originos-sans", "iqoo-sans", "iqoosans", "flyme", "flyme-sans", "flyme-ui",
    "flymesans", "flymefont", "meizu", "meizu-sans", "meizusans", "mflyme",
    "mflyme-sans", "honor-sans", "harmonyos-sans",
}
GLOBAL_PREFIXES = (
    "sans-serif-", "roboto-", "google-sans-", "source-sans-", "noto-sans-",
    "miui-", "mipro-", "misans-", "mi-sans-", "sysfont-", "sys-font-",
    "sys-sans-", "op-sans-", "oplus-sans-", "oppo-sans-", "opposans-",
    "oplus-os-ui-", "oplusosui-", "coloros-sans-", "oneplus-sans-",
    "realme-sans-", "vivo-sans-", "vivosans-", "origin-sans-", "originos-sans-",
    "iqoo-sans-", "iqoosans-", "flyme-sans-", "flymesans-", "flymefont-",
    "meizu-sans-", "meizusans-", "mflyme-", "honor-sans-", "harmonyos-sans-",
)
PROTECTED_TOKENS = (
    "emoji", "symbol", "icon", "material", "dingbat", "math", "music",
    "braille", "barcode", "qrcode", "fallback", "legacy",
)
MONO_TOKENS = ("mono", "monospace", "code")
CLOCK_TOKENS = ("clock", "clockopia", "digit", "number", "numeric")
DISPLAY_TOKENS = ("display", "headline", "title", "mitype")

# Each group has one visual job. Separating punctuation is important: a full-width
# Chinese comma, a baseline period and a centered plus sign do not share a baseline.
PROBE_GROUPS: dict[str, tuple[int, ...]] = {
    "latinCap": tuple(map(ord, "AHIOXEFMNSTUVWYZBCDGLPQRJK")),
    "latinX": tuple(map(ord, "xnoeacmursvkwz")),
    "latinDescender": tuple(map(ord, "gjpqy")),
    "digits": tuple(map(ord, "0123456789")),
    "cjk": tuple(map(ord, "永国中日田目口回晶品林森木本未末上下左右天地人大小字体系统默认洛书高低正方圆")),
    "punctuationBaseline": tuple(map(ord, ".,;:_!?")),
    "punctuationCenter": tuple(map(ord, "()[]{}+-=/%<>")),
    "punctuationFullwidth": tuple(map(ord, "，。！？；：（）【】《》、—…")),
}
# Compatibility aggregate for old fixtures and diagnostics.
PROBE_GROUPS["punctuation"] = tuple(dict.fromkeys(
    PROBE_GROUPS["punctuationBaseline"]
    + PROBE_GROUPS["punctuationCenter"]
    + PROBE_GROUPS["punctuationFullwidth"]
))


class TemplateError(RuntimeError):
    pass


@dataclass(frozen=True)
class FontRef:
    family: str
    family_attrs: dict[str, str]
    declared: str
    postscript_name: str
    weight: int
    style: str
    index: int
    axes: str
    source_xml: Path
    dynamic: bool


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def normalize(value: str) -> str:
    return re.sub(r"[\s_-]+", "-", str(value or "").strip().lower()).strip("-")


def nearest_weight(raw: str | None) -> int:
    try:
        requested = int(raw or "400")
    except ValueError:
        requested = 400
    requested = max(1, min(1000, requested))
    return min(WEIGHTS, key=lambda value: abs(value - requested))


def classify_roles(ref: FontRef, resolved: Path | None) -> list[str]:
    family = normalize(ref.family)
    filename = normalize(resolved.name if resolved else ref.declared or ref.postscript_name)
    haystack = f"{family} {filename}"
    roles: list[str] = []
    if ref.dynamic:
        roles.append("dynamic")
    if any(ref.family_attrs.get(key) for key in ("lang", "variant", "fallbackFor", "fallbackfor")):
        roles.append("fallback")
    if any(token in haystack for token in PROTECTED_TOKENS):
        roles.append("protected")
    if any(token in haystack for token in MONO_TOKENS):
        roles.append("mono")
    if any(token in haystack for token in CLOCK_TOKENS):
        roles.append("clock")
    if any(token in haystack for token in DISPLAY_TOKENS):
        roles.append("display")
    if family and (family in GLOBAL_EXACT or family.startswith(GLOBAL_PREFIXES)):
        roles.append("global-ui")
    if not roles:
        roles.append("other")
    return list(dict.fromkeys(roles))


def partition_root_for_xml(xml_path: Path) -> Path | None:
    parts = xml_path.parts
    try:
        etc_index = parts.index("etc")
    except ValueError:
        return None
    if etc_index <= 0:
        return None
    prefix = Path(*parts[:etc_index])
    return prefix if str(prefix) else Path("/")


def iter_font_files(roots: Sequence[Path]) -> Iterator[Path]:
    seen: set[tuple[int, int]] = set()
    for root in roots:
        if not root.is_dir():
            continue
        try:
            iterator = root.rglob("*")
        except OSError:
            continue
        for path in iterator:
            try:
                if not path.is_file() or path.suffix.lower() not in FONT_SUFFIXES:
                    continue
                stat = path.stat()
            except OSError:
                continue
            key = (int(stat.st_dev), int(stat.st_ino))
            if key in seen:
                continue
            seen.add(key)
            yield path


def font_names(font: TTFont) -> set[str]:
    result: set[str] = set()
    if "name" not in font:
        return result
    for record in font["name"].names:
        if record.nameID not in (1, 2, 4, 6, 16, 17):
            continue
        try:
            value = record.toUnicode().strip()
        except Exception:
            continue
        if value:
            result.add(value)
    return result


def build_postscript_index(roots: Sequence[Path]) -> dict[str, tuple[Path, int]]:
    index: dict[str, tuple[Path, int]] = {}
    for path in iter_font_files(roots):
        try:
            with path.open("rb") as stream:
                is_collection = stream.read(4) == b"ttcf"
        except OSError:
            continue
        face_count = 1
        if is_collection:
            try:
                collection = TTCollection(str(path), lazy=True)
                face_count = len(collection.fonts)
                collection.close()
            except Exception:
                continue
        for face in range(face_count):
            try:
                kwargs: dict[str, object] = {"lazy": True, "recalcTimestamp": False}
                if is_collection:
                    kwargs["fontNumber"] = face
                font = TTFont(str(path), **kwargs)
                names = font_names(font)
                font.close()
            except Exception:
                continue
            for name in names:
                index.setdefault(normalize(name), (path, face if is_collection else -1))
    return index


def parse_xml(path: Path) -> list[FontRef]:
    tree = ET.parse(path)
    dynamic = "/data/fonts/" in str(path).replace("\\", "/")
    refs: list[FontRef] = []
    for family in tree.getroot().iter():
        if local_name(family.tag) != "family":
            continue
        family_name = family.attrib.get("name", "")
        family_attrs = {key: value for key, value in family.attrib.items() if value}
        for child in list(family):
            if local_name(child.tag) != "font":
                continue
            declared = (child.text or "").strip()
            postscript_name = child.attrib.get("name", "").strip()
            if not declared and not postscript_name:
                continue
            try:
                index = int(child.attrib.get("index", "0") or "0")
            except ValueError:
                index = 0
            refs.append(FontRef(
                family=family_name,
                family_attrs=family_attrs,
                declared=declared,
                postscript_name=postscript_name,
                weight=nearest_weight(child.attrib.get("weight")),
                style=child.attrib.get("style", "normal").lower(),
                index=max(0, index),
                axes=child.attrib.get("axis", child.attrib.get("axes", "")),
                source_xml=path,
                dynamic=dynamic,
            ))
    return refs


def resolve_ref(ref: FontRef, postscript_index: dict[str, tuple[Path, int]]) -> tuple[Path | None, int]:
    if ref.declared:
        declared = Path(ref.declared)
        if declared.is_absolute() and declared.is_file():
            return declared, ref.index
        root = partition_root_for_xml(ref.source_xml)
        candidates: list[Path] = []
        if root is not None:
            candidates.extend((root / "fonts" / declared.name, root / "etc" / declared))
        candidates.extend((ref.source_xml.parent / declared, ref.source_xml.parent / declared.name))
        for candidate in candidates:
            if candidate.is_file():
                return candidate, ref.index
    if ref.postscript_name:
        match = postscript_index.get(normalize(ref.postscript_name))
        if match:
            return match
    return None, ref.index


def median(values: Iterable[float]) -> float | None:
    items = [float(value) for value in values if math.isfinite(float(value))]
    return float(statistics.median(items)) if items else None


def percentile(values: Iterable[float], ratio: float) -> float | None:
    items = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not items:
        return None
    if len(items) == 1:
        return items[0]
    position = max(0.0, min(1.0, ratio)) * (len(items) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return items[lower]
    fraction = position - lower
    return items[lower] * (1.0 - fraction) + items[upper] * fraction


def glyph_group(font: TTFont, codepoints: Sequence[int]) -> dict[str, float | int | None]:
    cmap = font.getBestCmap() or {}
    glyph_set = font.getGlyphSet()
    hmtx = font["hmtx"].metrics if "hmtx" in font else {}
    bounds: list[tuple[float, float, float, float]] = []
    advances: list[float] = []
    hits = 0
    seen: set[str] = set()
    for codepoint in codepoints:
        glyph_name = cmap.get(codepoint)
        if not glyph_name or glyph_name in seen or glyph_name not in glyph_set:
            continue
        seen.add(glyph_name)
        hits += 1
        if glyph_name in hmtx:
            advances.append(float(hmtx[glyph_name][0]))
        pen = BoundsPen(glyph_set)
        try:
            glyph_set[glyph_name].draw(pen)
        except Exception:
            continue
        if pen.bounds is not None:
            bounds.append(tuple(float(value) for value in pen.bounds))
    y_mins = [item[1] for item in bounds]
    y_maxs = [item[3] for item in bounds]
    heights = [item[3] - item[1] for item in bounds]
    widths = [item[2] - item[0] for item in bounds]
    centers = [(item[1] + item[3]) / 2.0 for item in bounds]
    return {
        "hits": hits,
        "boundsHits": len(bounds),
        "yMin": median(y_mins),
        "yMax": median(y_maxs),
        "height": median(heights),
        "inkWidth": median(widths),
        "advance": median(advances),
        "centerY": median(centers),
        "yMinP25": percentile(y_mins, 0.25),
        "yMaxP75": percentile(y_maxs, 0.75),
    }


def inspect_font(path: Path, face_index: int, hash_fonts: bool) -> dict[str, object]:
    kwargs: dict[str, object] = {"lazy": False, "recalcTimestamp": False, "recalcBBoxes": False}
    try:
        with path.open("rb") as stream:
            magic = stream.read(4)
    except OSError as exc:
        raise TemplateError(str(exc)) from exc
    if magic == b"ttcf":
        kwargs["fontNumber"] = max(0, face_index)
    font = TTFont(str(path), **kwargs)
    try:
        if "head" not in font or "hhea" not in font:
            raise TemplateError("缺少 head/hhea 表")
        head = font["head"]
        hhea = font["hhea"]
        os2 = font["OS/2"] if "OS/2" in font else None
        metrics: dict[str, int | None] = {
            "unitsPerEm": int(head.unitsPerEm),
            "headYMin": int(getattr(head, "yMin", 0)),
            "headYMax": int(getattr(head, "yMax", 0)),
            "hheaAscent": int(hhea.ascent),
            "hheaDescent": int(hhea.descent),
            "hheaLineGap": int(hhea.lineGap),
            "typoAscender": int(getattr(os2, "sTypoAscender", 0)) if os2 else None,
            "typoDescender": int(getattr(os2, "sTypoDescender", 0)) if os2 else None,
            "typoLineGap": int(getattr(os2, "sTypoLineGap", 0)) if os2 else None,
            "winAscent": int(getattr(os2, "usWinAscent", 0)) if os2 else None,
            "winDescent": int(getattr(os2, "usWinDescent", 0)) if os2 else None,
            "capHeight": int(getattr(os2, "sCapHeight", 0)) if os2 and hasattr(os2, "sCapHeight") else None,
            "xHeight": int(getattr(os2, "sxHeight", 0)) if os2 and hasattr(os2, "sxHeight") else None,
            "weightClass": int(getattr(os2, "usWeightClass", 400)) if os2 else 400,
            "widthClass": int(getattr(os2, "usWidthClass", 5)) if os2 else 5,
            "fsSelection": int(getattr(os2, "fsSelection", 0)) if os2 else 0,
        }
        stat = path.stat()
        result: dict[str, object] = {
            "path": str(path),
            "faceIndex": max(0, face_index) if magic == b"ttcf" else -1,
            "size": int(stat.st_size),
            "mtimeNs": int(stat.st_mtime_ns),
            "names": sorted(font_names(font)),
            "metrics": metrics,
            "probeSchema": PROBE_SCHEMA,
            "probes": {name: glyph_group(font, points) for name, points in PROBE_GROUPS.items()},
        }
        if hash_fonts:
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            result["sha256"] = digest.hexdigest()
        return result
    finally:
        font.close()


def build_template(
    xml_paths: Sequence[Path],
    font_roots: Sequence[Path],
    fingerprint: str,
    hash_fonts: bool = False,
    capture_revision: int = CAPTURE_REVISION,
) -> dict[str, object]:
    readable_xmls = [path for path in xml_paths if path.is_file()]
    if not readable_xmls:
        raise TemplateError("没有找到可读取的 Android 字体 XML")
    if capture_revision != CAPTURE_REVISION:
        raise TemplateError(f"不支持的模板采集修订：{capture_revision}")
    postscript_index = build_postscript_index(font_roots)
    slots: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []
    cache: dict[tuple[str, int], dict[str, object]] = {}
    seen: set[tuple[str, str, int, str, str]] = set()
    for xml_path in readable_xmls:
        try:
            refs = parse_xml(xml_path)
        except (OSError, ET.ParseError) as exc:
            failures.append({"source": str(xml_path), "error": str(exc)})
            continue
        for ref in refs:
            resolved, face_index = resolve_ref(ref, postscript_index)
            key = (str(xml_path), normalize(ref.family), ref.weight, ref.style, ref.declared or ref.postscript_name)
            if key in seen:
                continue
            seen.add(key)
            roles = classify_roles(ref, resolved)
            replaceable = "protected" not in roles and "fallback" not in roles and (
                "global-ui" in roles or "mono" in roles or "clock" in roles
                or "display" in roles or "dynamic" in roles
            )
            slot: dict[str, object] = {
                "family": ref.family,
                "familyNormalized": normalize(ref.family),
                "familyAttributes": ref.family_attrs,
                "sourceXml": str(xml_path),
                "declared": ref.declared,
                "postScriptName": ref.postscript_name,
                "weight": ref.weight,
                "style": ref.style,
                "index": ref.index,
                "axes": ref.axes,
                "roles": roles,
                "replaceable": replaceable,
                "resolvedPath": str(resolved) if resolved else "",
            }
            if resolved:
                cache_key = (str(resolved), face_index)
                try:
                    if cache_key not in cache:
                        cache[cache_key] = inspect_font(resolved, face_index, hash_fonts)
                    slot["font"] = cache[cache_key]
                except Exception as exc:
                    failures.append({"source": str(resolved), "error": str(exc)})
                    slot["fontError"] = str(exc)
            else:
                slot["fontError"] = "无法解析字体文件"
            slots.append(slot)
    slots.sort(key=lambda item: (
        0 if item["replaceable"] else 1,
        str(item["familyNormalized"]),
        int(item["weight"]),
        str(item["resolvedPath"]),
    ))
    role_counts: dict[str, int] = {}
    for slot in slots:
        for role in slot["roles"]:
            role_counts[role] = role_counts.get(role, 0) + 1
    return {
        "schema": SCHEMA,
        "captureRevision": CAPTURE_REVISION,
        "probeSchema": PROBE_SCHEMA,
        "fingerprint": fingerprint,
        "xml": [str(path) for path in readable_xmls],
        "fontRoots": [str(path) for path in font_roots if path.exists()],
        "summary": {
            "slots": len(slots),
            "replaceable": sum(1 for slot in slots if slot["replaceable"]),
            "resolved": sum(1 for slot in slots if slot["resolvedPath"]),
            "roles": dict(sorted(role_counts.items())),
            "failures": len(failures),
        },
        "slots": slots,
        "failures": failures,
    }


def atomic_json_write(payload: dict[str, object], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--xml", action="append", default=[], type=Path)
    parser.add_argument("--font-root", action="append", default=[], type=Path)
    parser.add_argument("--fingerprint", default="")
    parser.add_argument("--capture-revision", type=int, default=CAPTURE_REVISION)
    parser.add_argument("--hash-fonts", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = build_template(
            args.xml,
            args.font_root,
            args.fingerprint,
            args.hash_fonts,
            args.capture_revision,
        )
        atomic_json_write(payload, args.output)
        print(json.dumps({"status": "ok", **payload["summary"], "output": str(args.output)}, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc) or exc.__class__.__name__}, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())