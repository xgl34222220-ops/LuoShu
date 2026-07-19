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
    raise ValueError("字体面不包含受支持的 glyf、CFF 或 CFF2 轮廓")


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
        ext = extension(font)
        stem = clean_name(f"{family}-{subfamily}-TTCFace{index + 1:02d}-{source_hash[:10]}", f"{label}-TTCFace{index + 1:02d}-{source_hash[:10]}")
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


def extract(source: Path, output_dir: Path, label: str) -> dict[str, Any]:
    if not source.is_file() or source.stat().st_size < 12:
        raise ValueError("TTC 文件不存在或文件过小")
    source_hash = file_sha256(source)
    count = collection_count(source)
    if count < 1 or count > 128:
        raise ValueError("TTC 字体面数量异常")
    faces = [save_face(source, output_dir, source_hash, clean_name(label, "ImportedTTC"), index) for index in range(count)]
    imported = sum(1 for face in faces if not face["duplicate"])
    duplicates = len(faces) - imported
    return {
        "status": "ok",
        "data": {
            "kind": "collection",
            "sourceUid": f"sha256:{source_hash}",
            "faceCount": count,
            "imported": imported,
            "duplicates": duplicates,
            "duplicate": imported == 0,
            "message": f"已拆分并导入 {imported} 个字体面" if imported else "该 TTC 的全部字体面均已存在",
            "faces": faces,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--label", default="ImportedTTC")
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                extract(Path(args.input), Path(args.output_dir), args.label),
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
