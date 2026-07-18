#!/usr/bin/env python3
"""Safely extract font files from a Magisk/KernelSU/APatch module ZIP."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path, PurePosixPath

FONT_EXTENSIONS = {".ttf", ".otf", ".ttc"}
MAX_ENTRIES = 4000
MAX_FONT_FILES = 300
MAX_ENTRY_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 768 * 1024 * 1024


def safe_member(name: str) -> PurePosixPath | None:
    normalized = name.replace("\\", "/").lstrip("/")
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or ".." in path.parts:
        return None
    if any(part in {"", "."} for part in path.parts):
        return None
    return path


def clean_filename(name: str, index: int) -> str:
    leaf = PurePosixPath(name).name.strip()
    stem = Path(leaf).stem
    suffix = Path(leaf).suffix.lower()
    safe = "".join("_" if ord(char) < 32 or char in '\\/:*?\"<>|' else char for char in stem)
    safe = safe.strip(" .")[:150] or f"font-{index}"
    return f"{safe}{suffix}"


def extract(source: Path, output: Path) -> dict[str, object]:
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.stat().st_size > 256 * 1024 * 1024:
        raise ValueError("模块包超过 256 MB")
    output.mkdir(parents=True, exist_ok=True)
    extracted: list[dict[str, object]] = []
    module_prop = False
    total = 0
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_ENTRIES:
            raise ValueError("模块包文件数量异常")
        for info in infos:
            path = safe_member(info.filename)
            if path is None or info.is_dir():
                continue
            lower = str(path).lower()
            if lower == "module.prop" or lower.endswith("/module.prop"):
                module_prop = True
            suffix = path.suffix.lower()
            if suffix not in FONT_EXTENSIONS:
                continue
            if info.file_size < 12 or info.file_size > MAX_ENTRY_BYTES:
                continue
            total += info.file_size
            if total > MAX_TOTAL_BYTES:
                raise ValueError("模块内字体总大小异常")
            if len(extracted) >= MAX_FONT_FILES:
                raise ValueError("模块内字体文件超过 300 个")
            filename = clean_filename(path.name, len(extracted) + 1)
            target = output / f"{len(extracted):03d}-{filename}"
            with archive.open(info, "r") as source_stream, target.open("wb") as target_stream:
                shutil.copyfileobj(source_stream, target_stream, length=1024 * 1024)
            extracted.append(
                {
                    "source": str(path),
                    "path": str(target),
                    "name": filename,
                    "bytes": info.file_size,
                }
            )
    if not extracted:
        raise ValueError("没有在压缩包中找到 TTF、OTF 或 TTC 字体")
    return {
        "status": "ok",
        "modulePackage": module_prop,
        "count": len(extracted),
        "totalBytes": total,
        "fonts": extracted,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("output")
    args = parser.parse_args()
    try:
        result = extract(Path(args.source), Path(args.output))
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as error:
        print(
            json.dumps(
                {"status": "error", "message": str(error) or error.__class__.__name__},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
