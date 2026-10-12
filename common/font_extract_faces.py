#!/usr/bin/env python3
"""Safely extract every TTC/OTC face into an independent SFNT font file."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from fontTools.ttLib import TTCollection, TTFont

try:  # same module directory on device and in CI
    from font_capability import inspect_face, weight_from_name
except Exception:  # pragma: no cover - extractor still works without it
    inspect_face = None
    weight_from_name = None

COLOR_TABLES = ("COLR", "CBDT", "CBLC", "sbix", "SVG ")
WEIGHT_LABELS = {100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Regular", 500: "Medium",
                 600: "SemiBold", 700: "Bold", 800: "ExtraBold", 900: "Black"}


class UnsupportedFace(ValueError):
    """A collection face that cannot serve as a text font."""

SAFE_RE = re.compile(r"[^0-9A-Za-z\u3400-\u9fff._ -]+")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clean_name(value: str, fallback: str) -> str:
    value = SAFE_RE.sub("-", str(value or "").replace("/", "-").replace("\\", "-"))
    value = re.sub(r"[ _-]+", "-", value).strip(" .-")
    return (value or fallback)[:72]


def font_name(font: TTFont, name_id: int, fallback: str) -> str:
    try:
        return (font["name"].getDebugName(name_id) or fallback).strip()
    except Exception:
        return fallback


def best_family(font: TTFont) -> str:
    try:
        return (font["name"].getBestFamilyName() or font_name(font, 1, "ImportedFont")).strip()
    except Exception:
        return font_name(font, 1, "ImportedFont")


def best_subfamily(font: TTFont) -> str:
    try:
        return (font["name"].getBestSubFamilyName() or font_name(font, 2, "Regular")).strip()
    except Exception:
        return font_name(font, 2, "Regular")


def extension(font: TTFont) -> str:
    if "glyf" in font:
        return "ttf"
    if "CFF " in font or "CFF2" in font:
        return "otf"
    raise UnsupportedFace("字体面不包含受支持的 glyf、CFF 或 CFF2 轮廓（仅位图或损坏）")


def style_label(source: Path, index: int, subfamily: str) -> str:
    """Library file label the family parser understands.

    Faces of one collection share a family stem and differ only by a weight
    suffix (``-Bold``), italic faces as ``-Italic[-Weight]``; detect_font_family
    therefore groups them as one family instead of one family per face.
    """
    weight, italic, variable = 400, "italic" in subfamily.lower(), False
    if inspect_face is not None:
        info = inspect_face(source, index)
        weight, italic, variable = info.weight, info.italic, bool(info.wght)
    elif weight_from_name is not None:
        weight = weight_from_name(subfamily) or 400
    if variable:
        return "Variable-Italic" if italic else "Variable"
    nearest = min(WEIGHT_LABELS, key=lambda value: (abs(value - weight), value))
    label = WEIGHT_LABELS[nearest]
    if italic:
        return "Italic" if label == "Regular" else f"Italic-{label}"
    return label


def collection_count(path: Path) -> int:
    with path.open("rb") as stream:
        if stream.read(4) != b"ttcf":
            raise ValueError("文件不是 TTC/OTC 字体集合")
    collection = TTCollection(str(path), lazy=True)
    try:
        return len(collection.fonts)
    finally:
        collection.close()


def save_face(source: Path, output_dir: Path, source_hash: str, label: str, index: int) -> dict[str, Any]:
    font = TTFont(str(source), fontNumber=index, lazy=False, recalcTimestamp=False, recalcBBoxes=True)
    try:
        family = best_family(font)
        subfamily = best_subfamily(font)
        if any(tag in font for tag in COLOR_TABLES):
            raise UnsupportedFace("彩色 Emoji 字体面不作为文字字体导入")
        if "cmap" not in font:
            raise UnsupportedFace("字体面缺少 cmap 字符映射表")
        ext = extension(font)
        style = style_label(source, index, subfamily)
        base = clean_name(f"{family}-{source_hash[:8]}", f"{label}-{source_hash[:8]}")
        stem = f"{base}-{style}"
        if f"{stem}.{ext}" in _ALL_WRITTEN:  # two faces of one style in this collection
            stem = f"{base}-F{index + 1:02d}-{style}"
        target = output_dir / f"{stem}.{ext}"
        output_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(prefix=target.name + ".", suffix=".tmp", dir=output_dir, delete=False) as handle:
            temp_path = Path(handle.name)
        try:
            font.save(str(temp_path), reorderTables=False)
            if temp_path.stat().st_size < 4096:
                raise ValueError("拆分后的字体文件异常为空")
            new_hash = file_sha256(temp_path)
            duplicate = target.is_file() and file_sha256(target) == new_hash
            if duplicate:
                temp_path.unlink(missing_ok=True)
            else:
                os.chmod(temp_path, 0o644)
                os.replace(temp_path, target)
            return {
                "faceIndex": index,
                "sourceUid": f"sha256:{source_hash}:face:{index}",
                "fileUid": f"sha256:{new_hash}",
                "family": family,
                "subfamily": subfamily,
                "name": f"{family} {subfamily}".strip(),
                "fileName": target.name,
                "path": str(target),
                "format": ext.upper(),
                "duplicate": duplicate,
            }
        finally:
            temp_path.unlink(missing_ok=True)
    finally:
        font.close()


_ALL_WRITTEN: set[str] = set()


def extract(source: Path, output_dir: Path, label: str, wanted: set[int] | None = None) -> dict[str, Any]:
    if not source.is_file() or source.stat().st_size < 12:
        raise ValueError("TTC 文件不存在或文件过小")
    source_hash = file_sha256(source)
    count = collection_count(source)
    if count < 1 or count > 128:
        raise ValueError("TTC 字体面数量异常")
    _ALL_WRITTEN.clear()
    indices = [index for index in range(count) if wanted is None or index in wanted]
    if not indices:
        raise ValueError("指定的字体面索引不在该集合中")
    faces = []
    skipped = []
    for index in indices:
        try:
            face = save_face(source, output_dir, source_hash, clean_name(label, "ImportedTTC"), index)
        except UnsupportedFace as error:
            skipped.append({"faceIndex": index, "reason": str(error)})
            continue
        _ALL_WRITTEN.add(face["fileName"])
        faces.append(face)
    if not faces:
        reasons = "；".join(sorted({item["reason"] for item in skipped})) or "没有可用字体面"
        raise ValueError(f"字体集合中没有可作为文字字体的字体面：{reasons}")
    imported = sum(1 for face in faces if not face["duplicate"])
    duplicates = len(faces) - imported
    message = f"已拆分并导入 {imported} 个字体面" if imported else "该字体集合的全部字体面均已存在"
    if skipped:
        message += f"，跳过 {len(skipped)} 个不支持的字体面"
    return {
        "status": "ok",
        "data": {
            "kind": "collection",
            "sourceUid": f"sha256:{source_hash}",
            "faceCount": count,
            "imported": imported,
            "duplicates": duplicates,
            "duplicate": imported == 0,
            "skipped": skipped,
            "message": message,
            "faces": faces,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--label", default="ImportedTTC")
    parser.add_argument("--faces", default="", help="comma separated face indexes (default: all)")
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                extract(Path(args.input), Path(args.output_dir), args.label,
                        {int(item) for item in args.faces.split(",") if item.strip()} or None),
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 0
    except Exception as error:
        print(
            json.dumps(
                {"status": "error", "message": str(error) or error.__class__.__name__},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
