#!/usr/bin/env python3
"""LuoShu font engine v3: replace text font files, keep stock line metrics.

Inputs: the device font topology (which files exist and how fonts.xml uses
them), the stock XML snapshots, and the user's source fonts (one family, or a
CJK/Latin/digit composite). Output: a payload tree plus a deployment manifest
in the format the next-boot and self-mount layers already consume.

Per target file the output is the user's font with the stock hhea/OS/2 line
metrics. A variable source stays variable (XML nodes get wght axes); otherwise
one static instance per needed weight is generated and XML nodes are pointed at
it. See docs/LUOSHU_ENGINE_V3.md.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import struct
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fontTools.ttLib import TTCollection, TTFont

import font_role_shadow
import luoshu_merge
import luoshu_payload as payload_format

ENGINE_REVISION = 2
REPORT_SCHEMA = "luoshu-engine-report-v1"
REPLACE_ROLES = {"ui-sans", "cjk", "latin", "clock", "numeric"}
COMPOSITE_ROLES = ("cjk", "latin", "digit")
HAN_RANGE = range(0x4E00, 0xA000)
LATIN_LETTERS = frozenset(map(ord, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"))
DIGITS = frozenset(map(ord, "0123456789"))
MIN_HAN = 3000
USE_TYPO_METRICS = 1 << 7


class EngineError(RuntimeError):
    pass


def _deadline_check(deadline: float | None) -> None:
    if deadline is not None and time.time() > deadline:
        raise EngineError("字体生成超出时间预算，当前字体未改变")


def _canonical(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _file_identity(path: Path) -> str:
    """Cheap content identity for cache keys: size, mtime and the first/last MiB."""
    stat = path.stat()
    digest = hashlib.sha256(f"{stat.st_size}:{int(stat.st_mtime)}".encode())
    with path.open("rb") as handle:
        digest.update(handle.read(1 << 20))
        if stat.st_size > 2 << 20:
            handle.seek(-(1 << 20), os.SEEK_END)
            digest.update(handle.read(1 << 20))
    return digest.hexdigest()


def _collection_count(path: Path) -> int:
    with path.open("rb") as handle:
        header = handle.read(12)
    if header[:4] == b"ttcf" and len(header) >= 12:
        return max(1, struct.unpack(">I", header[8:12])[0])
    return 1


# ---------------------------------------------------------------- sources


@dataclass(frozen=True)
class Face:
    path: Path
    index: int
    weight: int
    italic: bool
    axes: tuple[tuple[str, float, float, float], ...]
    han: int
    latin: int
    digits: int
    identity: str
    glyf: bool = True

    @property
    def variable_weight(self) -> tuple[float, float] | None:
        for tag, minimum, _default, maximum in self.axes:
            if tag == "wght":
                return minimum, maximum
        return None

    def axis_tags(self) -> set[str]:
        return {tag for tag, *_ in self.axes}

    def location(self, weight: int, pinned: dict[str, float] | None = None) -> dict[str, float]:
        """A full location pinning every axis: wght from ``weight`` unless pinned."""
        result: dict[str, float] = {}
        for tag, minimum, default, maximum in self.axes:
            value = (pinned or {}).get(tag)
            if value is None:
                value = float(weight) if tag == "wght" else default
            result[tag] = max(minimum, min(maximum, float(value)))
        return result


def _inspect(path: Path) -> list[Face]:
    identity = _file_identity(path)
    faces: list[Face] = []
    for index in range(_collection_count(path)):
        font = TTFont(str(path), fontNumber=index, lazy=True)
        try:
            cmap = font.getBestCmap() or {}
            os2 = font["OS/2"] if "OS/2" in font else None
            italic = bool(os2 and os2.fsSelection & 1) or bool(font["head"].macStyle & 2)
            axes = tuple(
                (str(axis.axisTag), float(axis.minValue), float(axis.defaultValue), float(axis.maxValue))
                for axis in font["fvar"].axes
            ) if "fvar" in font else ()
            if any(tag == "ital" for tag, *_ in axes):
                italic = False
            faces.append(Face(
                path=path, index=index,
                weight=int(os2.usWeightClass) if os2 else 400,
                italic=italic, axes=axes,
                han=sum(1 for point in cmap if point in HAN_RANGE),
                latin=sum(1 for point in LATIN_LETTERS if point in cmap),
                digits=sum(1 for point in DIGITS if point in cmap),
                identity=f"{identity}:{index}",
                glyf="glyf" in font,
            ))
        finally:
            font.close()
    return faces


def _pick(faces: list[Face], weight: int, italic: bool) -> tuple[Face, dict[str, float] | None]:
    """Face and (for variable faces) location rendering ``weight``/``italic``."""
    styled = [face for face in faces if face.italic == italic] or faces
    for face in sorted(styled, key=lambda item: -(item.variable_weight or (0, 0))[1]):
        span = face.variable_weight
        if span and span[0] <= weight <= span[1]:
            pinned = {"ital": 1.0} if italic and "ital" in face.axis_tags() else {}
            return face, face.location(weight, pinned)
    static = [face for face in styled if not face.axes]
    if static:
        return min(static, key=lambda item: (abs(item.weight - weight), item.weight)), None
    face = min(styled, key=lambda item: abs(item.weight - weight))
    return face, face.location(weight)


def _load(face: Face, lazy: bool = True) -> TTFont:
    font = TTFont(str(face.path), fontNumber=face.index, lazy=lazy, recalcBBoxes=False, recalcTimestamp=False)
    font.flavor = None
    return font


def _instantiate(face: Face, location: dict[str, float] | None) -> TTFont:
    if not location:
        return _load(face)
    from fontTools.varLib import instancer
    font = _load(face, lazy=False)
    instancer.instantiateVariableFont(font, location, inplace=True, updateFontNames=False)
    return font


@dataclass
class Sources:
    mode: str
    faces: dict[str, list[Face]]
    settings: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_spec(cls, spec: dict[str, Any]) -> "Sources":
        mode = str(spec.get("mode") or "single")
        if mode == "single":
            files = [Path(item) for item in spec.get("files") or []]
            if not files:
                raise EngineError("没有指定源字体文件")
            faces = [face for path in files for face in _inspect(path)]
            return cls("single", {"single": faces})
        if mode != "composite":
            raise EngineError(f"未知源字体模式：{mode}")
        roles = spec.get("roles") or {}
        faces: dict[str, list[Face]] = {}
        settings: dict[str, dict[str, Any]] = {}
        for role in COMPOSITE_ROLES:
            item = roles.get(role) or {}
            files = [Path(value) for value in item.get("files") or []]
            if not files:
                raise EngineError(f"组合缺少{ {'cjk': '中文', 'latin': '英文', 'digit': '数字'}[role] }字体")
            faces[role] = [face for path in files for face in _inspect(path)]
            settings[role] = {
                "mode": "fixed" if item.get("mode") == "fixed" else "auto",
                "axes": {str(k): float(v) for k, v in (item.get("axes") or {}).items()},
            }
        if not any(face.han >= MIN_HAN for face in faces["cjk"]):
            raise EngineError("组合的中文字体缺少常用汉字")
        if not any(face.latin == len(LATIN_LETTERS) for face in faces["latin"]):
            raise EngineError("组合的英文字体缺少完整英文字母")
        if not any(face.digits == len(DIGITS) for face in faces["digit"]):
            raise EngineError("组合的数字字体缺少 0-9")
        return cls("composite", faces, settings)

    @property
    def has_han(self) -> bool:
        return any(face.han >= MIN_HAN for faces in self.faces.values() for face in faces)

    @property
    def has_latin(self) -> bool:
        return any(face.latin == len(LATIN_LETTERS) for faces in self.faces.values() for face in faces)

    def variable_face(self, italic: bool) -> Face | None:
        """Single mode only: the variable face that serves every weight."""
        if self.mode != "single":
            return None
        faces = self.faces["single"]
        candidates = [face for face in faces if face.variable_weight and face.italic == italic]
        if not candidates and italic:
            candidates = [face for face in faces if face.variable_weight and "ital" in face.axis_tags()]
        if not candidates:
            return None
        return max(candidates, key=lambda face: face.variable_weight[1] - face.variable_weight[0])

    def _variable_glyf(self, role: str) -> Face | None:
        faces = [face for face in self.faces[role]
                 if face.variable_weight and face.glyf and not face.italic]
        return max(faces, key=lambda face: face.variable_weight[1] - face.variable_weight[0], default=None)

    def composite_variable(self) -> bool:
        """A variable CJK base in auto mode: one variable composite serves every weight."""
        return (self.mode == "composite" and self.settings["cjk"]["mode"] == "auto"
                and self._variable_glyf("cjk") is not None)

    def is_variable(self) -> bool:
        return self.variable_face(False) is not None or self.composite_variable()

    def variable_key(self) -> str:
        if self.mode == "single":
            face = self.variable_face(False)
            return _canonical({"variable": face.identity if face else "", "rev": ENGINE_REVISION})
        return _canonical({"variableComposite": self.identity(), "rev": ENGINE_REVISION})

    def build_variable_composite(self) -> TTFont:
        face = self._variable_glyf("cjk")
        assert face is not None
        base = _load(face)
        for role in ("latin", "digit"):
            setting = self.settings[role]
            source_face = None if setting["mode"] == "fixed" else self._variable_glyf(role)
            fixed: dict[str, float] | None = None
            if source_face is None:
                source_face, location = self._role_pick(role, int(dict(
                    (tag, default) for tag, _min, default, _max in face.axes).get("wght", 400)))
                fixed = location or {}
            source = _load(source_face)
            try:
                luoshu_merge.import_glyphs_variable(base, source, role, fixed)
            finally:
                source.close()
        return base

    def identity(self) -> str:
        return _canonical({
            "mode": self.mode,
            "faces": {role: sorted(face.identity for face in faces) for role, faces in self.faces.items()},
            "settings": self.settings,
        })

    def _role_pick(self, role: str, weight: int) -> tuple[Face, dict[str, float] | None]:
        setting = self.settings[role]
        faces = self.faces[role]
        if setting["mode"] == "fixed":
            pinned = setting["axes"]
            wanted = int(pinned.get("wght", weight))
            face, location = _pick(faces, wanted, False)
            if face.axes:
                location = face.location(wanted, pinned)
            return face, location
        return _pick(faces, weight, False)

    def build_instance(self, weight: int, italic: bool) -> TTFont:
        """A static font rendering ``weight`` (and ``italic`` where the source has it)."""
        if self.mode == "single":
            face, location = _pick(self.faces["single"], weight, italic)
            return _instantiate(face, location)
        face, location = self._role_pick("cjk", weight)
        base = _instantiate(face, location)
        for role in ("latin", "digit"):
            src_face, src_location = self._role_pick(role, weight)
            source = _load(src_face)
            try:
                luoshu_merge.import_glyphs(base, source, role, src_location)
            finally:
                source.close()
        return base

    def instance_key(self, weight: int, italic: bool) -> str:
        if self.mode == "single":
            face, location = _pick(self.faces["single"], weight, italic)
            return _canonical({"face": face.identity, "location": location, "rev": ENGINE_REVISION})
        parts = {}
        for role in COMPOSITE_ROLES:
            face, location = self._role_pick(role, weight)
            parts[role] = {"face": face.identity, "location": location}
        return _canonical({"composite": parts, "rev": ENGINE_REVISION})


# ---------------------------------------------------------------- targets


@dataclass
class Target:
    path: str
    role: str
    partition: str
    weight: int
    italic: bool
    face_count: int
    metrics: dict[str, Any]
    refs: list[dict[str, Any]]


def _italic_style(value: Any) -> bool:
    return str(value or "").lower() in {"italic", "oblique"}


def _coverage(slot: dict[str, Any]) -> dict[str, Any]:
    metrics = slot.get("metrics") if isinstance(slot.get("metrics"), dict) else {}
    coverage = metrics.get("coverage") if isinstance(metrics.get("coverage"), dict) else {}
    return coverage


def _face_count(path: str, slot: dict[str, Any], stock_paths: dict[str, Path]) -> int:
    refs = [ref for ref in slot.get("xmlRefs") or [] if isinstance(ref, dict)]
    from_refs = max([int(ref.get("index") or 0) for ref in refs] + [int(slot.get("faceIndex") or 0)]) + 1
    if not path.lower().endswith((".ttc", ".otc")) and str(slot.get("format") or "").upper() != "TTC":
        return 1
    for candidate in (stock_paths.get(path), Path(path)):
        if candidate is not None:
            try:
                return max(_collection_count(candidate), from_refs)
            except OSError:
                continue
    return from_refs


def _stock_file(path: str, stock_paths: dict[str, Path]) -> Path | None:
    """The stock bytes of a slot: an explicit map, the pre-mount lower snapshot,
    then the live path (a previous LuoShu output there keeps stock line metrics)."""
    parts = Path(path).parts
    candidates = [stock_paths.get(path)]
    if len(parts) >= 4 and parts[2] == "fonts":
        lower = Path(os.environ.get("LUOSHU_SELF_MOUNT_STATE_ROOT", "/data/adb/luoshu/self-mount"))
        candidates.append(lower / "lower" / f"{parts[1]}-fonts" / Path(*parts[3:]))
    if not Path(path).is_symlink():  # a link (HyperOS theme overlay) is never a stock file
        candidates.append(Path(path))
    return next((item for item in candidates if item is not None and item.is_file()), None)


def _read_metrics(file: Path, face_index: int = 0) -> dict[str, Any]:
    """Topology-style metrics read from the stock file itself. The scanner only
    measures legacy-replaceable slots, so OEM UI fonts (ColorOS SysFont-*,
    OSans-Solid-Digits) can arrive without them."""
    try:
        font = TTFont(str(file), fontNumber=face_index if _collection_count(file) > 1 else -1, lazy=True)
    except Exception:  # unreadable stock file: the slot stays stock
        return {}
    try:
        hhea = font["hhea"]
        result: dict[str, Any] = {
            "upem": int(font["head"].unitsPerEm),
            "hhea": {"ascent": int(hhea.ascent), "descent": int(hhea.descent), "lineGap": int(hhea.lineGap)},
        }
        if "OS/2" in font:
            os2 = font["OS/2"]
            result["os2"] = {
                "typoAscender": int(os2.sTypoAscender), "typoDescender": int(os2.sTypoDescender),
                "typoLineGap": int(os2.sTypoLineGap), "winAscent": int(os2.usWinAscent),
                "winDescent": int(os2.usWinDescent), "fsSelection": int(os2.fsSelection),
            }
            result["weightClass"] = int(os2.usWeightClass)
        cmap = font.getBestCmap() or {}
        han = sum(1 for point in cmap if 0x4E00 <= point <= 0x9FFF)
        latin = sum(1 for point in cmap if 0x41 <= point <= 0x5A or 0x61 <= point <= 0x7A)
        digits = sum(1 for point in range(0x30, 0x3A) if point in cmap)
        result["coverage"] = {"hasHan": han > 0, "hanCount": han, "hasLatin": latin > 0, "latinCount": latin,
                              "hasDigits": digits == 10, "digitCount": digits}
        return result
    except (KeyError, AttributeError):
        return {}
    finally:
        font.close()


def enrich_topology(topology: dict[str, Any], stock_paths: dict[str, Path]) -> dict[str, Any]:
    """Fills in metrics the scanner skipped, for slots that may be text fonts.

    The scanner measures only legacy-replaceable slots; ColorOS SysFont-*,
    OSans-* and OplusOSUI-* arrive bare, so without their coverage they were
    unclassifiable (unknown-protected) or kept stock for missing metrics."""
    roles, _shadow = font_role_shadow.build(topology)
    role_slots = roles.get("slots") if isinstance(roles.get("slots"), dict) else {}
    slots = dict(topology.get("slots") or {})
    changed = False
    for path, slot in slots.items():
        if not isinstance(slot, dict) or path.startswith("/data/"):
            continue
        metrics = slot.get("metrics") if isinstance(slot.get("metrics"), dict) else {}
        if isinstance(metrics.get("hhea"), dict) and metrics.get("upem"):
            continue
        role = str((role_slots.get(path) or {}).get("role") or "unknown-protected")
        if role not in REPLACE_ROLES and role != "unknown-protected":
            continue
        stock = _stock_file(path, stock_paths)
        measured = _read_metrics(stock, int(slot.get("faceIndex") or 0)) if stock is not None else {}
        if measured:
            slots[path] = dict(slot, metrics=measured)
            changed = True
    return dict(topology, slots=slots) if changed else topology


def plan_targets(
    topology: dict[str, Any],
    roles: dict[str, Any],
    sources: Sources,
    stock_paths: dict[str, Path],
) -> tuple[list[Target], dict[str, str]]:
    slots = topology.get("slots") if isinstance(topology.get("slots"), dict) else {}
    role_slots = roles.get("slots") if isinstance(roles.get("slots"), dict) else {}
    targets: list[Target] = []
    kept: dict[str, str] = {}
    for path in sorted(slots):
        slot = slots[path]
        if not isinstance(slot, dict):
            continue
        role = str((role_slots.get(path) or {}).get("role") or "unknown-protected")
        metrics = slot.get("metrics") if isinstance(slot.get("metrics"), dict) else {}
        coverage = _coverage(slot)
        has_han = bool(coverage.get("hasHan")) or int(coverage.get("hanCount") or 0) > 0
        has_latin = bool(coverage.get("hasLatin")) or int(coverage.get("latinCount") or 0) > 0
        if role == "unknown-protected" and has_han and has_latin:
            role = "broad-text"
        elif role not in REPLACE_ROLES:
            continue
        if path.startswith("/data/"):
            kept[path] = "dynamic-font"
            continue
        if sources.mode == "single":
            if has_han and not sources.has_han:
                kept[path] = "source-has-no-han"
                continue
            if not has_han and has_latin and not sources.has_latin:
                kept[path] = "source-has-no-latin"
                continue
        if not isinstance(metrics.get("hhea"), dict) or not metrics.get("upem"):
            kept[path] = "stock-metrics-missing"
            continue
        parts = Path(path).parts
        if len(parts) < 3 or parts[1] not in payload_format.ALLOWED_PARTITIONS:
            kept[path] = "unsupported-partition"
            continue
        targets.append(Target(
            path=path, role=role, partition=parts[1],
            weight=int(slot.get("weight") or metrics.get("weightClass") or 400),
            italic=_italic_style(slot.get("style")) or "italic" in Path(path).name.lower(),
            face_count=_face_count(path, slot, stock_paths),
            metrics=metrics,
            refs=[dict(ref) for ref in slot.get("xmlRefs") or [] if isinstance(ref, dict)],
        ))
    return targets, kept


# ---------------------------------------------------------------- output


def _line_metrics(target: Target) -> dict[str, int]:
    metrics = target.metrics
    hhea = metrics.get("hhea") or {}
    os2 = metrics.get("os2") or {}
    return {
        "upem": int(metrics.get("upem") or 1000),
        "ascent": int(hhea.get("ascent") or metrics.get("ascent") or 0),
        "descent": int(hhea.get("descent") or metrics.get("descent") or 0),
        "lineGap": int(hhea.get("lineGap") or 0),
        "typoAscender": int(os2.get("typoAscender", hhea.get("ascent", 0)) or 0),
        "typoDescender": int(os2.get("typoDescender", hhea.get("descent", 0)) or 0),
        "typoLineGap": int(os2.get("typoLineGap") or 0),
        "winAscent": int(os2.get("winAscent", hhea.get("ascent", 0)) or 0),
        "winDescent": int(os2.get("winDescent", -int(hhea.get("descent", 0) or 0)) or 0),
        "useTypo": int(bool(int(os2.get("fsSelection") or 0) & USE_TYPO_METRICS)),
    }


def apply_line_metrics(font: TTFont, line: dict[str, int]) -> None:
    """Stock line height on the user's glyphs, scaled to the output UPEM."""
    scale = font["head"].unitsPerEm / max(1, line["upem"])

    def scaled(value: int) -> int:
        return int(round(value * scale))

    hhea = font["hhea"]
    hhea.ascent, hhea.descent, hhea.lineGap = scaled(line["ascent"]), scaled(line["descent"]), scaled(line["lineGap"])
    if "OS/2" in font:
        os2 = font["OS/2"]
        os2.sTypoAscender = scaled(line["typoAscender"])
        os2.sTypoDescender = scaled(line["typoDescender"])
        os2.sTypoLineGap = scaled(line["typoLineGap"])
        os2.usWinAscent = max(0, scaled(line["winAscent"]))
        os2.usWinDescent = max(0, scaled(abs(line["winDescent"])))
        if line["useTypo"]:
            os2.fsSelection |= USE_TYPO_METRICS
            os2.version = max(os2.version, 4)
        else:
            os2.fsSelection &= ~USE_TYPO_METRICS
    # Variable line metrics would let the line height change with weight.
    if "MVAR" in font:
        del font["MVAR"]


class Builder:
    """Generates and caches instances and per-target outputs."""

    def __init__(self, sources: Sources, cache_dir: Path, deadline: float | None):
        self.sources = sources
        self.cache = cache_dir
        self.cache.mkdir(parents=True, exist_ok=True)
        self.deadline = deadline
        self.used: set[Path] = set()
        self.stats = {"instancesBuilt": 0, "instancesCached": 0, "outputsBuilt": 0, "outputsCached": 0}

    def _base_path(self, kind: str, weight: int, italic: bool) -> tuple[Path, str]:
        if kind == "variable" and self.sources.mode == "single":
            face = self.sources.variable_face(italic)
            assert face is not None
            key = _canonical({"variable": face.identity, "rev": ENGINE_REVISION})
            return face.path, key
        key = self.sources.variable_key() if kind == "variable" else self.sources.instance_key(weight, italic)
        path = self.cache / f"inst-{key[:32]}.ttf"
        self.used.add(path)
        if path.is_file():
            self.stats["instancesCached"] += 1
            return path, key
        _deadline_check(self.deadline)
        font = (self.sources.build_variable_composite() if kind == "variable"
                else self.sources.build_instance(weight, italic))
        try:
            for tag in ("DSIG", "LTSH", "hdmx", "VDMX"):
                if tag in font:
                    del font[tag]
            temp = path.with_suffix(".part")
            font.save(str(temp))
            os.replace(temp, path)
        finally:
            font.close()
        self.stats["instancesBuilt"] += 1
        return path, key

    def output(self, specs: list[tuple[str, int, bool]], line: dict[str, int]) -> Path:
        """One output file: a face per spec ((kind, weight, italic)), all with
        the stock line metrics. More than one face makes a collection."""
        bases = []
        for kind, weight, italic in specs:
            base, key = self._base_path(kind, weight, italic)
            index = 0
            if kind == "variable" and self.sources.mode == "single":
                face = self.sources.variable_face(italic)
                index = face.index if face else 0
            bases.append((base, key, index))
        out_key = _canonical({"bases": [key for _, key, _ in bases], "line": line, "rev": ENGINE_REVISION})
        suffix = ".ttc" if len(bases) > 1 else ".ttf"
        path = self.cache / f"out-{out_key[:32]}{suffix}"
        self.used.add(path)
        if path.is_file():
            self.stats["outputsCached"] += 1
            return path
        _deadline_check(self.deadline)
        temp = path.with_suffix(".part")
        fonts = []
        try:
            for base, _key, index in bases:
                font = TTFont(str(base), fontNumber=index, lazy=True, recalcBBoxes=False, recalcTimestamp=False)
                font.flavor = None
                apply_line_metrics(font, line)
                fonts.append(font)
            if len(fonts) > 1:
                collection = TTCollection()
                collection.fonts = fonts
                collection.save(str(temp), shareTables=True)
            else:
                fonts[0].save(str(temp))
            os.replace(temp, path)
        finally:
            for font in fonts:
                font.close()
            temp.unlink(missing_ok=True)
        self.stats["outputsBuilt"] += 1
        return path

    def prune(self) -> None:
        for path in self.cache.glob("*"):
            if path.is_file() and path not in self.used:
                path.unlink(missing_ok=True)


# ---------------------------------------------------------------- XML


def _snapshot_xml(source_xml: str, root: Path | None, explicit: dict[str, Path]) -> Path | None:
    if source_xml in explicit and explicit[source_xml].is_file():
        return explicit[source_xml]
    parts = Path(source_xml).parts
    if root is not None and len(parts) >= 4 and parts[0] == "/" and parts[2] == "etc":
        candidate = root / parts[1] / Path(*parts[3:])
        if candidate.is_file():
            return candidate
    return None


def _parse_xml(path: Path) -> ET.ElementTree:
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    return ET.parse(str(path), parser=parser)


@dataclass
class NodeAction:
    # Face of the replaced file this node renders; None keeps the node's index.
    index: int | None
    axes: dict[str, float]
    variable: bool


# Files the pre-v3 universal pipeline added (LuoShu-<stock stem>-<weight>[i].ttf).
# A snapshot captured while that XML was mounted still names them; they no
# longer exist, so their families silently vanish unless mapped back.
_OLD_GENERATED = re.compile(r"^LuoShu-(.+)-[1-9]00i?\.(?:ttf|otf|ttc)$", re.IGNORECASE)
# HyperOS lists <stock>_Overlay.ttf first in sans-serif: a symlink to the theme
# font under /data (an 8.9 KB Latin/digit stub on HyperOS 3). Left alone it
# keeps stock Latin and digits in front of the replaced font.
_THEME_OVERLAY = re.compile(r"^(.+)_Overlay(\.(?:ttf|otf|ttc))$", re.IGNORECASE)


def _stock_name(declared: str, source_xml: str, resolve: dict[tuple[str, str], str]) -> str | None:
    """The stock file an unresolvable XML name stands for, if any."""
    if (source_xml, declared) in resolve:
        return None
    overlay = _THEME_OVERLAY.match(declared)
    if overlay:
        base = overlay.group(1) + overlay.group(2)
        return base if (source_xml, base) in resolve else None
    match = _OLD_GENERATED.match(declared)
    if not match:
        return None
    stem = match.group(1).lower()
    names = sorted(name for xml, name in resolve if xml == source_xml and Path(name).stem.lower() == stem)
    return names[0] if names else None


def _rewrite_xml(
    path: Path,
    source_xml: str,
    resolve: dict[tuple[str, str], str],
    action_for,
) -> tuple[bytes, int] | None:
    tree = _parse_xml(path)
    changed = 0
    for element in tree.getroot().iter():
        if not isinstance(element.tag, str) or element.tag != "font":
            continue
        declared = (element.text or "").strip()
        if not declared:
            continue
        stock = _stock_name(declared, source_xml, resolve)
        if stock is not None:
            element.text = (element.text or "").replace(declared, stock, 1)
            declared = stock
            changed += 1
        logical = resolve.get((source_xml, declared))
        if logical is None:
            continue
        weight = int(element.get("weight") or 400)
        italic = _italic_style(element.get("style"))
        action: NodeAction | None = action_for(logical, weight, italic)
        if action is None:
            continue
        if action.index is not None:
            if action.index or element.get("index") is not None:
                element.set("index", str(action.index))
        for child in list(element):
            if isinstance(child.tag, str) and child.tag == "axis":
                tail = child.tail
                element.remove(child)
                if tail and tail.strip():
                    element.text = (element.text or "") + tail
        for tag, value in action.axes.items():
            axis = ET.SubElement(element, "axis")
            axis.set("tag", tag)
            axis.set("stylevalue", f"{value:g}")
        if "postScriptName" in element.attrib:
            del element.attrib["postScriptName"]
        changed += 1
    original = ET.tostring(_parse_xml(path).getroot(), encoding="unicode")
    if not changed or ET.tostring(tree.getroot(), encoding="unicode") == original:
        return None
    body = ET.tostring(tree.getroot(), encoding="unicode")
    return ("<?xml version=\"1.0\" encoding=\"utf-8\"?>\n" + body + "\n").encode("utf-8"), changed


# ---------------------------------------------------------------- build


def _place(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
    except OSError:
        shutil.copyfile(source, destination)
    os.chmod(destination, 0o644)


def build(
    topology: dict[str, Any],
    spec: dict[str, Any],
    payload_root: Path,
    cache_dir: Path,
    xml_root: Path | None = None,
    xml_map: dict[str, Path] | None = None,
    stock_paths: dict[str, Path] | None = None,
    deadline: float | None = None,
    progress=None,
    live_root: Path | None = Path("/"),
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Returns (deployment manifest, report); writes ``payload_root``.

    ``live_root`` is where OEM XML copies must still exist to be rewritten (a
    stale snapshot of a removed file would fail boot verification); None skips
    the check (host replay)."""
    started = time.monotonic()
    topology = enrich_topology(topology, stock_paths or {})
    roles, _shadow = font_role_shadow.build(topology)
    sources = Sources.from_spec(spec)
    targets, kept = plan_targets(topology, roles, sources, stock_paths or {})
    if not any(target.role in {"ui-sans", "broad-text"} for target in targets):
        raise EngineError("没有可替换的系统界面字体，当前字体未改变")
    builder = Builder(sources, cache_dir, deadline)

    # Every (target, weight, italic) the device asks for.
    xml_weights: dict[str, set[tuple[int, bool]]] = {}
    resolve: dict[tuple[str, str], str] = {}
    for slot_path, slot in (topology.get("slots") or {}).items():
        for ref in slot.get("xmlRefs") or [] if isinstance(slot, dict) else []:
            if isinstance(ref, dict) and ref.get("sourceXml") and ref.get("declared"):
                resolve[(str(ref["sourceXml"]), str(ref["declared"]).strip())] = str(slot_path)
    documents = sorted({str(ref.get("sourceXml")) for target in targets for ref in target.refs
                        if ref.get("sourceXml") and not str(ref.get("sourceXml")).startswith("/data/")})
    snapshots: dict[str, Path] = {}
    for source_xml in documents:
        snapshot = _snapshot_xml(source_xml, xml_root, xml_map or {})
        if snapshot is None:
            raise EngineError(f"缺少原厂字体配置快照：{source_xml}")
        snapshots[source_xml] = snapshot
    # OEM copies of the system config (HyperOS system_ext hyper_fonts.xml,
    # miui_fonts.xml, ...) name the same files; the framework may load them
    # instead, so they are rewritten too. Names resolve by file: same partition
    # first, then /system/fonts.
    target_paths = {target.path for target in targets}
    for snapshot in sorted(xml_root.glob("*/*.xml")) if xml_root is not None and xml_root.is_dir() else []:
        partition = snapshot.parent.name
        source_xml = f"/{partition}/etc/{snapshot.name}"
        if source_xml in snapshots or source_xml.startswith("/data/") \
                or partition not in payload_format.ALLOWED_PARTITIONS:
            continue
        if live_root is not None and not (live_root / source_xml.lstrip("/")).is_file():
            continue
        try:
            nodes = list(_parse_xml(snapshot).getroot().iter("font"))
        except (ET.ParseError, OSError):
            continue
        mapped = False
        for element in nodes:
            declared = (element.text or "").strip()
            names = [declared]
            overlay = _THEME_OVERLAY.match(declared)
            if overlay:
                names.append(overlay.group(1) + overlay.group(2))
            old = _OLD_GENERATED.match(declared)
            if old:
                names.extend(sorted(Path(path).name for path in target_paths
                                    if Path(path).stem.lower() == old.group(1).lower()))
            found = next((f"{folder}/{name}" for name in names
                          for folder in (f"/{partition}/fonts", "/system/fonts")
                          if f"{folder}/{name}" in target_paths), None)
            if found is not None:
                resolve[(source_xml, Path(found).name)] = found
                mapped = True
        if mapped:
            snapshots[source_xml] = snapshot
    for target in targets:
        xml_weights[target.path] = {(int(ref.get("weight") or 400), _italic_style(ref.get("style")))
                                    for ref in target.refs}
    # Every node acts for a target (directly, through a theme overlay or a stale
    # generated name); the topology keeps one record per unresolved name and
    # none for OEM copies, so read the weights from the documents.
    for source_xml, snapshot in snapshots.items():
        for element in _parse_xml(snapshot).getroot().iter("font"):
            declared = (element.text or "").strip()
            stock = _stock_name(declared, source_xml, resolve)
            logical = resolve.get((source_xml, stock or declared))
            if logical in xml_weights:
                xml_weights[logical].add((int(element.get("weight") or 400), _italic_style(element.get("style"))))

    payload_root.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{payload_root.name}.", dir=str(payload_root.parent)))
    files: dict[str, dict[str, Any]] = {}
    node_actions: dict[str, dict[tuple[int, bool], NodeAction]] = {}
    replaced: list[dict[str, Any]] = []
    try:
        for position, target in enumerate(targets, 1):
            if progress:
                progress(position, len(targets), Path(target.path).name)
            line = _line_metrics(target)
            italic_variable = sources.variable_face(True)
            upright_variable = sources.variable_face(False)
            variable = sources.is_variable()
            actions: dict[tuple[int, bool], NodeAction] = {}
            # Only existing files can be replaced: a per-file bind mount cannot
            # add new names to a ROM directory. Extra weights become extra
            # faces of the same file and XML nodes select them by index.
            if variable:
                own_italic = target.italic and italic_variable is not None and italic_variable is not upright_variable
                specs = [("variable", target.weight, own_italic)] * target.face_count
                italic_index: int | None = None
                for weight, italic in sorted(xml_weights[target.path]):
                    axes = {"wght": float(weight)}
                    face = italic_variable if italic else upright_variable
                    if italic and face is not None and "ital" in face.axis_tags():
                        axes["ital"] = 1.0
                    index = None
                    if italic and face is not None and face is not upright_variable and not own_italic:
                        if italic_index is None:
                            specs.append(("variable", target.weight, True))
                            italic_index = len(specs) - 1
                        index = italic_index
                    actions[(weight, italic)] = NodeAction(index, axes, True)
            else:
                main_key = sources.instance_key(target.weight, target.italic)
                specs = [("static", target.weight, target.italic)] * target.face_count
                extra_index: dict[str, int] = {}
                for weight, italic in sorted(xml_weights[target.path]):
                    key = sources.instance_key(weight, italic)
                    if key == main_key:
                        actions[(weight, italic)] = NodeAction(None, {}, False)
                        continue
                    if key not in extra_index:
                        specs.append(("static", weight, italic))
                        extra_index[key] = len(specs) - 1
                    actions[(weight, italic)] = NodeAction(extra_index[key], {}, False)
            main = builder.output(specs, line)
            logical = payload_format._safe_logical(target.path)
            rel = payload_format._payload_relative(logical)
            _place(main, stage / rel)
            files[target.path] = _file_record(target.path, str(rel), stage / rel, "physical-font")
            node_actions[target.path] = actions
            replaced.append({"path": target.path, "role": target.role,
                             "variable": variable, "faces": len(specs)})

        def action_for(logical: str, weight: int, italic: bool) -> NodeAction | None:
            per_target = node_actions.get(logical)
            if per_target is None:
                return None
            return per_target.get((weight, italic)) or per_target.get((weight, False))

        xml_changes: list[dict[str, Any]] = []
        for source_xml, snapshot in snapshots.items():
            rendered = _rewrite_xml(snapshot, source_xml, resolve, action_for)
            if rendered is None:
                continue
            data, count = rendered
            logical = payload_format._safe_logical(source_xml)
            rel = payload_format._payload_relative(logical)
            (stage / rel).parent.mkdir(parents=True, exist_ok=True)
            (stage / rel).write_bytes(data)
            os.chmod(stage / rel, 0o644)
            files[source_xml] = _file_record(source_xml, str(rel), stage / rel, "xml", source_xml)
            xml_changes.append({"sourceXml": source_xml, "nodes": count})

        manifest = _write_manifest(stage, files, sources, targets)
        if payload_root.exists():
            shutil.rmtree(payload_root)
        os.replace(stage, payload_root)
        stage = None
    finally:
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)
    builder.prune()
    report = {
        "schema": REPORT_SCHEMA,
        "engineRevision": ENGINE_REVISION,
        "mode": sources.mode,
        "sources": spec,
        "deploymentId": manifest["deploymentId"],
        "replaced": replaced,
        "keptStock": [{"path": path, "reason": reason} for path, reason in sorted(kept.items())],
        "xml": xml_changes,
        "stats": builder.stats,
        "seconds": round(time.monotonic() - started, 2),
    }
    return manifest, report


def _file_record(logical: str, rel: str, path: Path, kind: str, source_xml: str = "") -> dict[str, Any]:
    return {
        "kind": kind,
        "logicalPath": logical,
        "payloadPath": rel,
        "sha256": payload_format._sha256(path),
        "bytes": int(path.stat().st_size),
        "artifactId": "",
        "sourceXml": source_xml,
    }


def _write_manifest(stage: Path, records: dict[str, dict[str, Any]], sources: Sources,
                    targets: list[Target]) -> dict[str, Any]:
    files = sorted(records.values(), key=lambda item: item["logicalPath"])
    digest = payload_format._payload_digest(files, [])
    plan_id = f"luoshu-engine:{_canonical({'sources': sources.identity(), 'targets': [t.path for t in targets], 'rev': ENGINE_REVISION})}"
    outputs_id = f"luoshu-engine:{_canonical([item['sha256'] for item in files])}"
    partitions = sorted({Path(item["logicalPath"]).parts[1] for item in files})
    semantic = {
        "fontPlanId": plan_id,
        "routeId": plan_id,
        "artifactManifestId": outputs_id,
        "payloadDigest": digest,
        "files": files,
        "dynamicMounts": [],
        "backendProfiles": payload_format.BACKEND_PROFILES,
    }
    deployment_id = f"sha256:{_canonical(semantic)}"
    manifest = {
        "schema": payload_format.SCHEMA,
        "deploymentRevision": payload_format.DEPLOYMENT_REVISION,
        "engine": {"name": "luoshu-engine", "revision": ENGINE_REVISION},
        "state": "prepared",
        "generatedAt": int(time.time()),
        "mutatesSystem": False,
        "mountsAtBoot": True,
        "backendNeutral": True,
        "deploymentId": deployment_id,
        "fontPlanId": plan_id,
        "routeId": plan_id,
        "artifactManifestId": outputs_id,
        "payloadDigest": digest,
        "summary": {
            "fileCount": len(files),
            "fontFileCount": sum(item["kind"] != "xml" for item in files),
            "xmlFileCount": sum(item["kind"] == "xml" for item in files),
            "dynamicMountCount": 0,
            "partitionCount": len(partitions),
            "backendCount": len(payload_format.BACKEND_PROFILES),
            "activationReady": True,
            "executableNow": False,
        },
        "partitions": partitions,
        "backendProfiles": copy.deepcopy(payload_format.BACKEND_PROFILES),
        "files": files,
        "dynamicMounts": [],
        "runtimeManifest": {
            "payloadPath": ".luoshu-runtime/deployment/deployment.json",
            "deploymentId": deployment_id,
        },
    }
    runtime = stage / ".luoshu-runtime/deployment/deployment.json"
    runtime.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    payload_format.validate_payload_integrity(manifest, stage)
    return manifest


# ---------------------------------------------------------------- CLI


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise EngineError(f"JSON 根节点无效：{path}")
    return value


def _path_map(path: Path | None) -> dict[str, Path]:
    if path is None:
        return {}
    return {str(k): Path(str(v)) for k, v in _load_json(path).items()}


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".part")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def parse_axes(value: str) -> dict[str, float]:
    """The App's ``tag=value`` list (``,`` or ``;`` separated)."""
    result: dict[str, float] = {}
    for item in re.split(r"[;,]", value or ""):
        tag, sep, raw = item.strip().partition("=")
        if not sep:
            continue
        if not re.fullmatch(r"[A-Za-z0-9]{4}", tag.strip()):
            raise EngineError(f"组合轴设置无效：{item.strip()}")
        try:
            result[tag.strip()] = float(raw)
        except ValueError as error:
            raise EngineError(f"组合轴数值无效：{item.strip()}") from error
    return result


def _spec_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.role_font:
        roles: dict[str, dict[str, Any]] = {role: {"files": []} for role in COMPOSITE_ROLES}
        for item in args.role_font:
            role, sep, path = item.partition(":")
            if not sep or role not in roles:
                raise EngineError(f"组合字体参数无效：{item}")
            roles[role]["files"].append(path)
        for item in args.role_mode:
            role, _sep, mode = item.partition("=")
            if role in roles:
                roles[role]["mode"] = mode
        for item in args.role_axes:
            role, _sep, axes = item.partition("=")
            if role in roles:
                roles[role]["axes"] = parse_axes(axes)
        return {"mode": "composite", "roles": roles}
    if not args.font:
        raise EngineError("没有指定源字体文件")
    return {"mode": "single", "files": list(args.font)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topology", required=True, type=Path)
    parser.add_argument("--spec", type=Path, help="source fonts: {mode, files | roles}")
    parser.add_argument("--font", action="append", default=[], help="single family: a source font file")
    parser.add_argument("--role-font", action="append", default=[], help="composite: ROLE:PATH")
    parser.add_argument("--role-mode", action="append", default=[], help="composite: ROLE=auto|fixed")
    parser.add_argument("--role-axes", action="append", default=[], help="composite: ROLE=tag=value,...")
    parser.add_argument("--xml-root", type=Path, help="stock XML snapshots: <root>/<partition>/<file>")
    parser.add_argument("--xml-map", type=Path)
    parser.add_argument("--stock-map", type=Path)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--payload-root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--progress", type=Path)
    args = parser.parse_args()

    deadline_raw = os.environ.get("LUOSHU_ENGINE_DEADLINE") or os.environ.get("LUOSHU_UNIVERSAL_DEADLINE")
    deadline = float(deadline_raw) if deadline_raw else None

    def progress(position: int, total: int, name: str) -> None:
        if args.progress is None:
            return
        percent = 10 + int(70 * (position - 1) / max(1, total))
        args.progress.write_text(f"percent={percent}\nmessage=正在生成字体 {position}/{total}：{name}\n",
                                 encoding="utf-8")

    try:
        spec = _load_json(args.spec) if args.spec else _spec_from_args(args)
        args.payload_root.parent.mkdir(parents=True, exist_ok=True)
        manifest, report = build(
            _load_json(args.topology), spec, args.payload_root, args.cache_dir,
            xml_root=args.xml_root, xml_map=_path_map(args.xml_map), stock_paths=_path_map(args.stock_map),
            deadline=deadline, progress=progress,
        )
        _atomic_json(args.manifest, manifest)
        _atomic_json(args.report, report)
    except (EngineError, luoshu_merge.MergeError, payload_format.DeploymentError, OSError, ValueError) as error:
        print(json.dumps({"status": "error", "message": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps({
        "status": "ok",
        "deploymentId": manifest["deploymentId"],
        "payloadDigest": manifest["payloadDigest"],
        "replacedCount": len(report["replaced"]),
        "keptStock": [Path(item["path"]).name for item in report["keptStock"]],
        "seconds": report["seconds"],
    }, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
