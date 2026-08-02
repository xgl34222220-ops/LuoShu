#!/usr/bin/env python3
"""Materialize a font source at concrete variation-axis values for LuoShu.

Variable fonts are pinned to every requested fvar axis. TTC/OTC collections are
reduced to one deterministic face whose coverage and weight satisfy the selected
role.  The CJK face is the complete composite base, so it must also contain Latin,
digits and common punctuation; a collection containing those scripts in separate
faces is rejected instead of silently choosing an incomplete face.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from fontTools.ttLib import TTCollection, TTFont
from fontTools.varLib.instancer import instantiateVariableFont

from font_metrics_normalize import normalize_font_metrics

CJK_PROBES = tuple(map(ord, "一丁七万三上下不与中为主人了二于五人今从他会但你作使入全国其分到前力十又只可同后和在地大天好学家小年心我日时有来民生的看种行要见言这"))
LATIN_PROBES = tuple(map(ord, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"))
DIGIT_PROBES = tuple(map(ord, "0123456789"))
PUNCTUATION_PROBES = tuple(map(ord, ".,!?-:;()[]/+'\"，。！？：；（）【】《》、"))
AXIS_TAG_RE = re.compile(r"^[ -~]{1,4}$")


class InstanceError(RuntimeError):
    pass


def is_collection(path: Path) -> bool:
    with path.open("rb") as stream:
        return stream.read(4) == b"ttcf"


def collection_count(path: Path) -> int:
    if not is_collection(path):
        return 1
    collection = TTCollection(str(path), lazy=True)
    try:
        return len(collection.fonts)
    finally:
        collection.close()


def open_face(path: Path, index: int, *, lazy: bool = True) -> TTFont:
    kwargs: dict[str, Any] = {
        "lazy": lazy,
        "recalcTimestamp": False,
    }
    if is_collection(path):
        kwargs["fontNumber"] = index
    return TTFont(str(path), **kwargs)


def font_weight(font: TTFont) -> int:
    try:
        return int(font["OS/2"].usWeightClass)
    except Exception:
        return 400


def usable(font: TTFont, probes: tuple[int, ...]) -> tuple[int, set[str]]:
    cmap = font.getBestCmap() or {}
    glyph_order = set(font.getGlyphOrder())
    names: set[str] = set()
    hits = 0
    for codepoint in probes:
        name = cmap.get(codepoint)
        if not name or name == ".notdef" or name not in glyph_order:
            continue
        hits += 1
        names.add(name)
    return hits, names


def coverage_profile(font: TTFont) -> dict[str, tuple[int, int, int]]:
    result: dict[str, tuple[int, int, int]] = {}
    for name, probes in (
        ("cjk", CJK_PROBES),
        ("latin", LATIN_PROBES),
        ("digits", DIGIT_PROBES),
        ("punctuation", PUNCTUATION_PROBES),
    ):
        hits, glyphs = usable(font, probes)
        result[name] = hits, len(probes), len(glyphs)
    return result


def fraction(value: tuple[int, int, int]) -> float:
    return value[0] / value[1] if value[1] else 1.0


def face_valid(profile: dict[str, tuple[int, int, int]], role: str) -> bool:
    if role == "cjk":
        cjk_hits, _cjk_total, cjk_unique = profile["cjk"]
        return (
            fraction(profile["cjk"]) >= 0.95
            and cjk_unique >= max(12, int(cjk_hits * 0.75))
            and fraction(profile["latin"]) == 1.0
            and fraction(profile["digits"]) == 1.0
            and fraction(profile["punctuation"]) >= 0.85
        )
    if role == "latin":
        return fraction(profile["latin"]) == 1.0
    return fraction(profile["digits"]) == 1.0


def face_score(font: TTFont, role: str, weight: int) -> tuple[int, float, int, int]:
    profile = coverage_profile(font)
    if role == "cjk":
        selected = ("cjk", "latin", "digits", "punctuation")
    elif role == "latin":
        selected = ("latin",)
    else:
        selected = ("digits",)
    score = sum(fraction(profile[name]) for name in selected)
    hits = sum(profile[name][0] for name in selected)
    return 1 if face_valid(profile, role) else 0, score, hits, -abs(font_weight(font) - weight)


def pick_face(path: Path, role: str, weight: int) -> int:
    best: tuple[tuple[int, float, int, int], int] | None = None
    for index in range(collection_count(path)):
        font = open_face(path, index, lazy=True)
        try:
            score = face_score(font, role, weight)
        finally:
            font.close()
        if best is None or score > best[0]:
            best = score, index
    if best is None or best[0][0] != 1:
        role_name = {"cjk": "中文基底", "latin": "英文", "digit": "数字"}[role]
        raise InstanceError(f"无法从 {path.name} 中找到覆盖完整的{role_name}字体面")
    return best[1] if is_collection(path) else -1


def clamp_weight(value: float | int) -> int:
    return max(1, min(1000, int(round(float(value)))))


def parse_axis_spec(spec: str) -> dict[str, float]:
    result: dict[str, float] = {}
    for raw_item in str(spec or "").split(","):
        item = raw_item.strip()
        if not item:
            continue
        if "=" not in item:
            raise InstanceError(f"无效轴参数：{item}")
        tag, raw_value = item.split("=", 1)
        tag = tag.strip()
        if not AXIS_TAG_RE.fullmatch(tag):
            raise InstanceError(f"无效轴标签：{tag}")
        try:
            result[tag] = float(raw_value.strip())
        except ValueError as exc:
            raise InstanceError(f"轴 {tag} 的数值无效") from exc
    return result


def materialize(source: Path, output: Path, role: str, requested_weight: int, requested_axes: dict[str, float]) -> dict[str, object]:
    if not source.is_file() or source.stat().st_size < 12:
        raise InstanceError(f"字体源文件不可用：{source}")
    requested_weight = clamp_weight(requested_axes.get("wght", requested_weight))
    face = pick_face(source, role, requested_weight)
    kwargs: dict[str, object] = {
        "lazy": False,
        "recalcTimestamp": False,
        "recalcBBoxes": True,
    }
    if face >= 0:
        kwargs["fontNumber"] = face
    font = TTFont(str(source), **kwargs)
    variable = "fvar" in font
    location: dict[str, float] = {}
    ignored_axes: list[str] = []
    try:
        if variable:
            known_axes = {str(axis.axisTag): axis for axis in font["fvar"].axes}
            ignored_axes = sorted(tag for tag in requested_axes if tag not in known_axes)
            for tag, axis in known_axes.items():
                requested = requested_axes.get(tag, float(axis.defaultValue))
                location[tag] = float(max(axis.minValue, min(axis.maxValue, requested)))
            font = instantiateVariableFont(font, location, inplace=False, optimize=True)
        elif requested_axes:
            ignored_axes = sorted(tag for tag in requested_axes if tag != "wght")

        # Recheck after variable-font instancing.  A malformed variation table must
        # never turn a previously valid face into an incomplete output unnoticed.
        post_profile = coverage_profile(font)
        if not face_valid(post_profile, role):
            raise InstanceError("可变轴实例化后的字体面缺少该角色所需字形")

        final_weight = clamp_weight(location.get("wght", requested_weight))
        if "OS/2" in font:
            font["OS/2"].usWeightClass = final_weight
        for tag in ("DSIG", "LTSH", "hdmx", "VDMX"):
            if tag in font:
                del font[tag]
        metrics = normalize_font_metrics(font)

        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=output.name + ".", suffix=".tmp", dir=output.parent, delete=False) as handle:
            temp_path = Path(handle.name)
        try:
            font.save(str(temp_path), reorderTables=False)
            if temp_path.stat().st_size < 4096:
                raise InstanceError("可变轴实例化输出异常为空")
            os.chmod(temp_path, 0o644)
            os.replace(temp_path, output)
        finally:
            temp_path.unlink(missing_ok=True)
        return {
            "status": "ok",
            "source": str(source),
            "output": str(output),
            "role": role,
            "weight": final_weight,
            "face": face,
            "variable": variable,
            "location": location,
            "ignoredAxes": ignored_axes,
            "coverage": {
                name: round(fraction(values) * 100)
                for name, values in post_profile.items()
            },
            "metrics": metrics,
            "size": output.stat().st_size,
        }
    finally:
        font.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--role", choices=("cjk", "latin", "digit"), required=True)
    parser.add_argument("--weight", type=int, default=400)
    parser.add_argument("--axes", default="")
    return parser.parse_args()


def main() -> int:
    try:
        args = parse_args()
        result = materialize(Path(args.input), Path(args.output), args.role, args.weight, parse_axis_spec(args.axes))
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except MemoryError:
        print(json.dumps({"status": "error", "message": "字体可变轴实例化时内存不足"}, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 12
    except Exception as error:
        print(json.dumps({"status": "error", "message": str(error) or error.__class__.__name__}, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1


if __name__ == "__main__":
    import sys
    raise SystemExit(main())
