#!/usr/bin/env python3
"""Materialize a font source at concrete variation-axis values for LuoShu v2.0.0.

Variable fonts are pinned to every requested fvar axis. TTC/OTC collections are
reduced to the face whose coverage and weight best match the requested role.
Plain static TTF/OTF files may be copied by the shell wrapper without invoking
this helper.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from io import BytesIO
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont
from fontTools.varLib.instancer import instantiateVariableFont

from font_metrics_normalize import normalize_font_metrics

CJK_PROBES = tuple(map(ord, "中文字体系统默认洛书汉字国一的。"))
LATIN_PROBES = tuple(map(ord, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"))
DIGIT_PROBES = tuple(map(ord, "0123456789"))
AXIS_TAG_RE = re.compile(r"^[ -~]{1,4}$")


class InstanceError(RuntimeError):
    pass


def is_collection(path: Path) -> bool:
    with path.open("rb") as stream:
        return stream.read(4) == b"ttcf"


def font_weight(font: TTFont) -> int:
    try:
        return int(font["OS/2"].usWeightClass)
    except Exception:
        return 400


def face_score(font: TTFont, role: str, weight: int) -> tuple[int, int]:
    cmap = font.getBestCmap() or {}
    probes = CJK_PROBES if role == "cjk" else LATIN_PROBES if role == "latin" else DIGIT_PROBES
    hits = sum(1 for codepoint in probes if codepoint in cmap)
    return hits, -abs(font_weight(font) - weight)


def pick_face(path: Path, role: str, weight: int) -> int:
    if not is_collection(path):
        return -1
    collection = TTCollection(str(path), lazy=True)
    try:
        count = len(collection.fonts)
    finally:
        collection.close()
    best: tuple[tuple[int, int], int] | None = None
    for index in range(count):
        font = TTFont(str(path), fontNumber=index, lazy=True, recalcTimestamp=False)
        try:
            score = face_score(font, role, weight)
        finally:
            font.close()
        if best is None or score > best[0]:
            best = score, index
    if best is None or best[0][0] == 0:
        raise InstanceError(f"无法从 {path.name} 中找到适合的{role}字体面")
    return best[1]


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


def materialize(
    source: Path,
    output: Path,
    role: str,
    requested_weight: int,
    requested_axes: dict[str, float],
    source_bytes: bytes | None = None,
) -> dict[str, object]:
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
    # In batch mode the caller has already read the file once; parsing that buffer avoids re-reading
    # a multi-megabyte font from storage for every weight.
    font = TTFont(BytesIO(source_bytes) if source_bytes is not None else str(source), **kwargs)
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
            "metrics": metrics,
            "size": output.stat().st_size,
        }
    finally:
        font.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input")
    parser.add_argument("--output")
    parser.add_argument("--batch")
    parser.add_argument("--role", choices=("cjk", "latin", "digit"), default="cjk")
    parser.add_argument("--weight", type=int, default=400)
    parser.add_argument("--axes", default="")
    return parser.parse_args()


def run_batch(job_file: Path) -> int:
    """Materialize several weights from one source in a single interpreter.

    A variable font has one file behind all nine weights, so the per-weight form started the
    embedded interpreter nine times and read the whole font nine times. The instancing itself
    genuinely differs per weight and still runs per job; everything around it does not need to.

    Job lines are tab separated:  input<TAB>output<TAB>role<TAB>weight<TAB>axes
    Result lines:                 output<TAB>ok|error<TAB>message
    """
    cache: dict[str, bytes] = {}
    failed = False
    for raw in job_file.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) < 4:
            print("\terror\tmalformed job line")
            failed = True
            continue
        source, output, role, weight = fields[0], fields[1], fields[2], fields[3]
        axes = fields[4] if len(fields) > 4 else ""
        try:
            key = str(Path(source))
            if key not in cache:
                if len(cache) >= 2:
                    cache.clear()
                cache[key] = Path(source).read_bytes()
            materialize(Path(source), Path(output), role, int(weight or 400),
                        parse_axis_spec(axes), source_bytes=cache[key])
        except Exception as error:  # noqa: BLE001 - reported per line so the batch continues
            message = (str(error) or error.__class__.__name__).replace("\n", " ").replace("\t", " ")
            print(f"{output}\terror\t{message}")
            failed = True
            continue
        print(f"{output}\tok\t")
    return 1 if failed else 0


def main() -> int:
    try:
        args = parse_args()
        if getattr(args, "batch", None):
            return run_batch(Path(args.batch))
        if not args.input or not args.output:
            raise InstanceError("缺少 --input/--output（除非使用 --batch）")
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
