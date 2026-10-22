#!/usr/bin/env python3
"""Safely extract supported font files from a ZIP archive into a flat directory.

Ported from 字域 Ziyu v1.4.8 common/font_zip_extract.py (作者 酷安@柔性体,
shishui611-art/Ziyu, GPL-3.0-only). LuoShu changes: also picks OTC and WOFF/WOFF2
web fonts (converted later by font_web_convert.py), skips macOS resource-fork
copies (__MACOSX/, ._name), and never executes or extracts anything else.

usage: font_zip_extract.py ARCHIVE DESTINATION MAX_FILES MAX_BYTES
Prints the number of extracted files; exit 1 with a Chinese reason on stderr.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath


FONT_SUFFIXES = {".ttf", ".otf", ".ttc", ".otc", ".woff", ".woff2"}
CHUNK_SIZE = 1024 * 1024


def _font_members(archive: zipfile.ZipFile):
    for info in archive.infolist():
        name = info.filename
        if not name or "\x00" in name or "\\" in name:
            raise ValueError("ZIP 条目路径无效")
        if any(ord(char) < 32 or ord(char) == 127 for char in name):
            raise ValueError("ZIP 条目路径包含控制字符")
        if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
            raise ValueError("ZIP 条目不能使用绝对路径")

        path = PurePosixPath(name)
        if any(part in ("", ".", "..") for part in name.split("/")):
            # A trailing slash belongs to a directory entry, which is ignored.
            if info.is_dir() and name.endswith("/") and all(
                part not in (".", "..") for part in name.split("/")[:-1]
            ):
                continue
            raise ValueError("ZIP 条目包含不安全路径")
        if info.is_dir():
            continue
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise ValueError("ZIP 字体包不允许包含符号链接")
        if path.parts[0] == "__MACOSX" or path.name.startswith("._"):
            continue
        if Path(path.name).suffix.lower() not in FONT_SUFFIXES:
            continue
        if len(path.name.encode("utf-8")) > 512:
            raise ValueError("字体文件名过长")
        yield info, path.name


def _unique_name(name: str, archive_path: str, destination: Path) -> str:
    if not (destination / name).exists():
        return name
    path = Path(name)
    tag = hashlib.sha256(archive_path.encode("utf-8")).hexdigest()[:8]
    candidate = f"{path.stem}-{tag}{path.suffix}"
    index = 2
    while (destination / candidate).exists():
        candidate = f"{path.stem}-{tag}-{index}{path.suffix}"
        index += 1
    return candidate


def extract(archive_path: Path, destination: Path, max_files: int, max_bytes: int) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise ValueError("字体临时目录必须为空")

    created: list[Path] = []
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            members = list(_font_members(archive))
            if not members:
                raise ValueError("ZIP 中没有找到 TTF / OTF / TTC / OTC / WOFF / WOFF2 字体")
            if len(members) > max_files:
                raise ValueError(f"字体包超过 {max_files} 个字体文件限制")
            declared_bytes = sum(info.file_size for info, _ in members)
            if declared_bytes > max_bytes:
                raise ValueError(f"字体包解压后超过 {max_bytes} 字节限制")

            total_written = 0
            for info, base_name in members:
                output = destination / _unique_name(base_name, info.filename, destination)
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                fd = os.open(output, flags, 0o600)
                created.append(output)
                actual_size = 0
                with os.fdopen(fd, "wb") as target, archive.open(info, "r") as source:
                    while True:
                        block = source.read(CHUNK_SIZE)
                        if not block:
                            break
                        actual_size += len(block)
                        total_written += len(block)
                        if total_written > max_bytes or actual_size > info.file_size:
                            raise ValueError("ZIP 解压数据超过声明大小或总容量限制")
                        target.write(block)
                if actual_size != info.file_size:
                    raise ValueError("ZIP 字体条目大小与声明不一致")
        return len(created)
    except Exception:
        for path in created:
            try:
                path.unlink()
            except OSError:
                pass
        raise


def main() -> int:
    if len(sys.argv) != 5:
        print("usage: font_zip_extract.py ARCHIVE DESTINATION MAX_FILES MAX_BYTES", file=sys.stderr)
        return 2
    archive = Path(sys.argv[1])
    destination = Path(sys.argv[2])
    try:
        max_files = int(sys.argv[3])
        max_bytes = int(sys.argv[4])
        if max_files <= 0 or max_bytes <= 0:
            raise ValueError("容量限制必须大于零")
        count = extract(archive, destination, max_files, max_bytes)
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as error:
        print(str(error) or "ZIP 字体包读取失败", file=sys.stderr)
        return 1
    print(count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
