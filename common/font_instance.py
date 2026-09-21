#!/usr/bin/env python3
"""Materialize a source face without confusing weight labels with real outlines.

The install-time inventory remains authoritative for device slots. This helper
only instances a selected user font; it never rescans a ROM or changes mounts.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import tempfile
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont
from fontTools.varLib.instancer import instantiateVariableFont

CJK_PROBES = tuple(map(ord, "中文字体系统默认洛书汉字国一的。"))
LATIN_PROBES = tuple(map(ord, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"))
DIGIT_PROBES = tuple(map(ord, "0123456789"))
AXIS_TAG_RE = re.compile(r"^[ -~]{1,4}$")
INSTANCE_REVISION = 2


class InstanceError(RuntimeError):
    pass


def is_collection(path: Path) -> bool:
    with path.open("rb") as stream:
        return stream.read(4) == b"ttcf"


def finite_number(value: object, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise InstanceError(f"{label}的数值无效") from exc
    if not math.isfinite(number):
        raise InstanceError(f"{label}必须是有限数值")
    return number


def clamp_weight(value: float | int) -> int:
    return max(1, min(1000, int(round(finite_number(value, "字重")))))


def font_weight(font: TTFont) -> int:
    try:
        return clamp_weight(font["OS/2"].usWeightClass)
    except (KeyError, AttributeError, InstanceError):
        return 400


def weight_distance(font: TTFont, requested: int) -> float:
    # A variable TTC face can reach a weight even when its OS/2 default is far
    # away. Comparing only that default used to choose an inferior static face.
    if "fvar" in font:
        for axis in font["fvar"].axes:
            if axis.axisTag == "wght":
                low = finite_number(axis.minValue, "wght 最小值")
                high = finite_number(axis.maxValue, "wght 最大值")
                if low > high:
                    raise InstanceError("字体 wght 轴范围无效")
                return abs(requested - max(low, min(high, requested)))
    return abs(font_weight(font) - requested)


def face_score(font: TTFont, role: str, weight: int) -> tuple[int, float]:
    cmap = font.getBestCmap() or {}
    probes = CJK_PROBES if role == "cjk" else LATIN_PROBES if role == "latin" else DIGIT_PROBES
    hits = sum(1 for cp in probes if cmap.get(cp) not in (None, ".notdef"))
    return hits, -weight_distance(font, weight)


def pick_face(path: Path, role: str, weight: int) -> int:
    if not is_collection(path):
        return -1
    collection = TTCollection(str(path), lazy=True)
    try:
        count = len(collection.fonts)
    finally:
        collection.close()
    best: tuple[tuple[int, float], int] | None = None
    for index in range(count):
        with TTFont(str(path), fontNumber=index, lazy=True, recalcTimestamp=False) as font:
            score = face_score(font, role, weight)
        if best is None or score > best[0]:
            best = score, index
    if best is None or best[0][0] == 0:
        raise InstanceError(f"无法从 {path.name} 中找到适合的{role}字体面")
    return best[1]


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
        if tag in result:
            raise InstanceError(f"重复的轴参数：{tag}")
        result[tag] = finite_number(raw_value.strip(), f"轴 {tag}")
    return result


def validate_output(path: Path) -> None:
    # Clock/digit subsets can be valid SFNTs below 4 KiB. File size is not a font
    # validity test. Reopen the staging file before replacing any previous result.
    with TTFont(str(path), lazy=False, recalcTimestamp=False) as font:
        for tag in ("head", "hhea", "hmtx", "maxp", "OS/2", "cmap", "name"):
            if tag not in font:
                raise InstanceError(f"生成字体缺少 {tag} 表")
            font[tag]
        if not any(tag in font for tag in ("glyf", "CFF ", "CFF2")):
            raise InstanceError("生成字体不包含可用轮廓")
        if "fvar" in font:
            raise InstanceError("字体仍有未固定的可变轴")
        names = set(font.getGlyphOrder())
        if not any(glyph != ".notdef" and glyph in names
                   for glyph in (font.getBestCmap() or {}).values()):
            raise InstanceError("生成字体没有可用 Unicode 字形映射")


def materialize(
    source: Path,
    output: Path,
    role: str,
    requested_weight: int,
    requested_axes: dict[str, float],
    *,
    preserve_metrics: bool = False,
) -> dict[str, object]:
    if role not in ("cjk", "latin", "digit"):
        raise InstanceError("字体角色无效")
    if not source.is_file() or source.stat().st_size < 12:
        raise InstanceError(f"字体源文件不可用：{source}")
    if source.resolve() == output.resolve():
        raise InstanceError("输出路径不能覆盖源字体")
    axes: dict[str, float] = {}
    for tag, value in requested_axes.items():
        if not isinstance(tag, str) or not AXIS_TAG_RE.fullmatch(tag):
            raise InstanceError(f"无效轴标签：{tag}")
        axes[tag] = finite_number(value, f"轴 {tag}")
    requested_weight = clamp_weight(axes.get("wght", requested_weight))
    face = pick_face(source, role, requested_weight)
    kwargs: dict[str, object] = {"lazy": False, "recalcTimestamp": False, "recalcBBoxes": True}
    if face >= 0:
        kwargs["fontNumber"] = face
    source_font = TTFont(str(source), **kwargs)
    font = source_font
    variable = "fvar" in font
    location: dict[str, float] = {}
    ignored_axes: list[str] = []
    try:
        source_weight = font_weight(font)
        if variable:
            known_axes = {str(axis.axisTag): axis for axis in font["fvar"].axes}
            ignored_axes = sorted(tag for tag in axes if tag not in known_axes)
            for tag, axis in known_axes.items():
                low = finite_number(axis.minValue, f"轴 {tag} 最小值")
                high = finite_number(axis.maxValue, f"轴 {tag} 最大值")
                default = finite_number(axis.defaultValue, f"轴 {tag} 默认值")
                if not low <= default <= high:
                    raise InstanceError(f"字体轴 {tag} 范围无效")
                requested = axes.get(tag, requested_weight if tag == "wght" else default)
                location[tag] = float(max(low, min(high, requested)))
            font = instantiateVariableFont(font, location, inplace=False, optimize=True)
        else:
            ignored_axes = sorted(axes)

        # No wght axis means no weight interpolation occurred. Preserve the
        # selected static face's weight instead of relabelling Regular as Bold.
        final_weight = clamp_weight(location.get("wght", source_weight))
        if "OS/2" in font:
            font["OS/2"].usWeightClass = final_weight
        for tag in ("DSIG", "LTSH", "hdmx", "VDMX"):
            if tag in font:
                del font[tag]
        if preserve_metrics:
            metrics = {"mode": "preserved"}
        else:
            from font_metrics_normalize import normalize_font_metrics
            metrics = normalize_font_metrics(font)

        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=output.name + ".", suffix=".tmp", dir=output.parent, delete=False) as handle:
            temp_path = Path(handle.name)
        try:
            font.save(str(temp_path), reorderTables=False)
            validate_output(temp_path)
            os.chmod(temp_path, 0o644)
            os.replace(temp_path, output)
        finally:
            temp_path.unlink(missing_ok=True)
        return {
            "status": "ok", "source": str(source), "output": str(output), "role": role,
            "weight": final_weight, "requestedWeight": requested_weight,
            "sourceWeight": source_weight,
            "weightMode": "variable-instance" if "wght" in location else "source-face",
            "weightMatched": final_weight == requested_weight,
            "instanceRevision": INSTANCE_REVISION,
            "face": face, "variable": variable, "location": location,
            "ignoredAxes": ignored_axes, "metrics": metrics, "size": output.stat().st_size,
        }
    finally:
        if font is not source_font:
            font.close()
        source_font.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--role", choices=("cjk", "latin", "digit"), required=True)
    parser.add_argument("--weight", type=int, default=400)
    parser.add_argument("--axes", default="")
    parser.add_argument("--preserve-metrics", action="store_true")
    return parser.parse_args()


def main(*, preserve_metrics_default: bool = False) -> int:
    try:
        args = parse_args()
        result = materialize(
            Path(args.input), Path(args.output), args.role, args.weight,
            parse_axis_spec(args.axes),
            preserve_metrics=preserve_metrics_default or args.preserve_metrics,
        )
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except MemoryError:
        print(json.dumps({"status": "error", "message": "字体可变轴实例化时内存不足"}, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 12
    except Exception as error:
        print(json.dumps({"status": "error", "message": str(error) or error.__class__.__name__}, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
