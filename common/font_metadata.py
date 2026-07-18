#!/usr/bin/env python3
"""Inspect real font family and weight metadata for LuoShu.

This helper intentionally reads the font's internal name/OS2/fvar tables instead
of guessing from the filename.  It supports TTF, OTF and TTC/OTC collections.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from fontTools.ttLib import TTCollection, TTFont


def clean_text(value: str) -> str:
    return " ".join(str(value or "").replace("\t", " ").replace("\r", " ").replace("\n", " ").split()).strip()


def get_name(font: TTFont, *name_ids: int) -> str:
    table = font.get("name")
    if table is None:
        return ""
    candidates: list[tuple[int, str]] = []
    for record in table.names:
        if record.nameID not in name_ids:
            continue
        try:
            value = clean_text(record.toUnicode())
        except Exception:
            continue
        if not value:
            continue
        # Prefer Windows Unicode/English, then any Unicode record.
        score = 0
        if record.platformID == 3:
            score += 4
        elif record.platformID == 0:
            score += 3
        if record.langID in (0x409, 0):
            score += 2
        score += max(0, len(name_ids) - name_ids.index(record.nameID))
        candidates.append((score, value))
    return max(candidates, default=(0, ""))[1]


def os2_weight(font: TTFont) -> int:
    try:
        value = int(font["OS/2"].usWeightClass)
    except Exception:
        try:
            value = 700 if int(font["head"].macStyle) & 1 else 400
        except Exception:
            value = 400
    return max(1, min(1000, value))


def coverage_score(font: TTFont) -> int:
    probes = "中文字体系统洛书ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    cmap = font.getBestCmap() or {}
    return sum(1 for char in probes if ord(char) in cmap)


def round_weight(value: Any) -> int | None:
    try:
        number = int(round(float(value)))
    except Exception:
        return None
    if not math.isfinite(float(value)):
        return None
    return max(1, min(1000, number))


def inspect_face(font: TTFont, index: int) -> dict[str, Any]:
    family = get_name(font, 16, 1) or f"UnknownFamily{index + 1}"
    subfamily = get_name(font, 17, 2) or "Regular"
    postscript = get_name(font, 6)
    static_weight = os2_weight(font)
    variable = "fvar" in font
    axis: dict[str, int] | None = None
    weights: set[int] = set()

    if variable:
        weight_axis = next((item for item in font["fvar"].axes if str(item.axisTag) == "wght"), None)
        if weight_axis is not None:
            axis = {
                "min": round_weight(weight_axis.minValue) or 1,
                "default": round_weight(weight_axis.defaultValue) or static_weight,
                "max": round_weight(weight_axis.maxValue) or 1000,
            }
            for instance in font["fvar"].instances:
                value = round_weight(instance.coordinates.get("wght"))
                if value is not None:
                    weights.add(value)
            # The default is an actual font-defined location and must always be retained.
            weights.add(axis["default"])
            # Fonts without named instances still define a usable range.  In that case use
            # only the font's own endpoints/default, never a hard-coded five-weight set.
            if len(weights) == 1:
                weights.add(axis["min"])
                weights.add(axis["max"])
    if not weights:
        weights.add(static_weight)

    italic = False
    try:
        italic = bool(int(font["head"].macStyle) & 2)
    except Exception:
        italic = "italic" in subfamily.lower() or "oblique" in subfamily.lower()

    return {
        "index": index,
        "family": family,
        "subfamily": subfamily,
        "postscript": postscript,
        "weight": axis["default"] if axis else static_weight,
        "weights": sorted(weights),
        "variable": variable,
        "weightAxis": axis,
        "italic": italic,
        "coverage": coverage_score(font),
    }


def open_faces(path: Path) -> list[dict[str, Any]]:
    with path.open("rb") as stream:
        magic = stream.read(4)
    if magic == b"ttcf":
        collection = TTCollection(str(path), lazy=True)
        try:
            count = len(collection.fonts)
        finally:
            collection.close()
        faces = []
        for index in range(count):
            font = TTFont(str(path), fontNumber=index, lazy=True, recalcTimestamp=False)
            try:
                faces.append(inspect_face(font, index))
            finally:
                font.close()
        return faces
    font = TTFont(str(path), lazy=True, recalcTimestamp=False)
    try:
        return [inspect_face(font, 0)]
    finally:
        font.close()


def choose_primary_family(faces: list[dict[str, Any]]) -> str:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for face in faces:
        grouped[face["family"]].append(face)
    return max(
        grouped,
        key=lambda name: (
            len(grouped[name]),
            sum(int(face["coverage"]) for face in grouped[name]),
            -min(abs(int(face["weight"]) - 400) for face in grouped[name]),
            name,
        ),
    )


def inspect(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    faces = open_faces(path)
    if not faces:
        raise RuntimeError("字体中没有可读取的字体面")
    family = choose_primary_family(faces)
    selected = [face for face in faces if face["family"] == family]
    weights = sorted({int(weight) for face in selected for weight in face["weights"]})
    primary = max(selected, key=lambda face: (int(face["coverage"]), -abs(int(face["weight"]) - 400)))
    axes = [face["weightAxis"] for face in selected if face["weightAxis"]]
    axis = None
    if axes:
        axis = {
            "min": min(int(item["min"]) for item in axes),
            "default": int(primary["weightAxis"]["default"]) if primary.get("weightAxis") else int(primary["weight"]),
            "max": max(int(item["max"]) for item in axes),
        }
    return {
        "status": "ok",
        "file": path.name,
        "family": family,
        "subfamily": primary["subfamily"],
        "weight": int(primary["weight"]),
        "weights": weights,
        "variable": any(bool(face["variable"]) for face in selected),
        "collection": len(faces) > 1,
        "weightAxis": axis,
        "faceCount": len(faces),
        "faces": faces,
    }


def print_conf(result: dict[str, Any]) -> None:
    axis = result.get("weightAxis") or {}
    values = {
        "status": "ok",
        "family": clean_text(result.get("family", "")),
        "subfamily": clean_text(result.get("subfamily", "")),
        "weight": int(result.get("weight", 400)),
        "weights": ",".join(str(item) for item in result.get("weights", [])),
        "variable": str(bool(result.get("variable"))).lower(),
        "collection": str(bool(result.get("collection"))).lower(),
        "axisMin": axis.get("min", ""),
        "axisDefault": axis.get("default", ""),
        "axisMax": axis.get("max", ""),
        "faceCount": int(result.get("faceCount", 1)),
    }
    for key, value in values.items():
        print(f"{key}={value}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--format", choices=("json", "conf"), default="json")
    args = parser.parse_args()
    try:
        result = inspect(Path(args.input))
        if args.format == "conf":
            print_conf(result)
        else:
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as error:
        if args.format == "conf":
            print("status=error")
            print(f"message={clean_text(str(error) or error.__class__.__name__)}")
        else:
            print(json.dumps({"status": "error", "message": str(error) or error.__class__.__name__}, ensure_ascii=False, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
