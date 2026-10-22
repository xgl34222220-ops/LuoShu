#!/usr/bin/env python3
"""Convert WOFF / WOFF2 web-font containers to Android-usable SFNT (TTF/OTF/TTC).

Ported from 字域 Ziyu v1.4.8 common/font_web_convert.py (作者 酷安@柔性体,
shishui611-art/Ziyu, GPL-3.0-only) and adapted for LuoShu:

* WOFF (zlib) is decoded by FontTools, which works with the pure-Python runtime.
* WOFF2 needs Brotli. FontTools is tried first (works wherever a brotli module is
  importable, e.g. CI hosts); LuoShu's embedded Android runtime has no Brotli
  extension, so it falls back to the bundled static ARM64 helper
  ``common/python/bin/luoshu-woff2-decode`` built from pinned google/woff2 +
  google/brotli sources (MIT, see licenses/).
* An extension rename is never treated as conversion: the result must be a real
  SFNT with cmap/head and is validated again by font_check.sh afterwards.

CLI: font_web_convert.py --input FILE --output-dir DIR [--woff2-decoder PATH]
Prints one JSON object; exit 0 on success, 1 on error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from fontTools.ttLib import TTCollection, TTFont

MAGIC = {b"wOFF": "WOFF", b"wOF2": "WOFF2"}
SFNT_MAGIC = {
    b"\x00\x01\x00\x00": "TTF",
    b"true": "TTF",
    b"\x00\x02\x00\x00": "TTF",
    b"OTTO": "OTF",
    b"ttcf": "TTC",
}
DEFAULT_WOFF2_DECODER = Path(__file__).resolve().parent / "python/bin/luoshu-woff2-decode"
DECODER_TIMEOUT_SECONDS = 180
MISSING_DECODER_MESSAGE = (
    "WOFF2 需要 Brotli 解码，但内置解码器 luoshu-woff2-decode 不可用（缺失或无法执行）；"
    "请重新安装完整的洛书模块，或先在电脑上把字体转换为 TTF/OTF 再导入"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_stem(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in value)
    cleaned = cleaned.strip(".-_")
    return cleaned[:80] or "ConvertedFont"


def sfnt_format(path: Path) -> str:
    with path.open("rb") as stream:
        magic = stream.read(4)
    value = SFNT_MAGIC.get(magic)
    if value is None:
        raise ValueError("转换结果不是有效 SFNT/TTC 字体")
    return value


def extension_for_format(value: str) -> str:
    return {"TTF": "ttf", "OTF": "otf", "TTC": "ttc"}[value]


def validate_decoded(path: Path) -> tuple[str, int]:
    if path.stat().st_size < 12:
        raise ValueError("转换结果异常为空")
    fmt = sfnt_format(path)
    if fmt == "TTC":
        collection = TTCollection(str(path), lazy=True)
        try:
            count = len(collection.fonts)
            if count < 1 or count > 128:
                raise ValueError("转换后的 TTC 字体面数量异常")
            for font in collection.fonts:
                if "cmap" not in font or "head" not in font:
                    raise ValueError("转换后的 TTC 字体面缺少 cmap/head")
            return fmt, count
        finally:
            collection.close()

    font = TTFont(str(path), lazy=True, recalcTimestamp=False)
    try:
        if "cmap" not in font or "head" not in font:
            raise ValueError("转换结果缺少 cmap/head")
    finally:
        font.close()
    return fmt, 1


def _fonttools_decode(source: Path, output: Path) -> None:
    # Default (lazy=None) loading copies untouched tables as raw bytes, which keeps a
    # large CJK WOFF fast on the pure-Python device runtime; this mirrors
    # fontTools.ttLib.woff2.decompress().
    font = TTFont(str(source), recalcTimestamp=False)
    try:
        font.flavor = None
        font.save(str(output), reorderTables=False)
    finally:
        font.close()


def _ensure_executable(decoder: Path) -> bool:
    if not decoder.is_file():
        return False
    if os.access(decoder, os.X_OK):
        return True
    # Root managers extract module files as 0644; restore the intended mode once.
    try:
        os.chmod(decoder, decoder.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        return False
    return os.access(decoder, os.X_OK)


def _native_woff2_decode(source: Path, output: Path, decoder: Path) -> None:
    if not _ensure_executable(decoder):
        raise ValueError(MISSING_DECODER_MESSAGE)
    output.unlink(missing_ok=True)
    try:
        result = subprocess.run(
            [str(decoder), str(source), str(output)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=DECODER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise ValueError("WOFF2 解码超时") from error
    except OSError as error:
        raise ValueError(f"{MISSING_DECODER_MESSAGE}（{error.strerror or error}）") from error
    if result.returncode != 0 or not output.is_file():
        detail = " ".join((result.stderr or result.stdout or "").split())[:220]
        raise ValueError(f"WOFF2 解码失败{('：' + detail) if detail else ''}")


def _resolve_decoder(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    env = os.environ.get("LUOSHU_WOFF2_DECODER")
    if env:
        return Path(env)
    return DEFAULT_WOFF2_DECODER


def convert(
    source: Path,
    output_dir: Path,
    woff2_decoder: Path | None = None,
) -> dict[str, Any]:
    if not source.is_file() or source.stat().st_size < 12:
        raise ValueError("网页字体文件不存在或过小")
    with source.open("rb") as stream:
        container = MAGIC.get(stream.read(4))
    if container is None:
        raise ValueError("仅支持 WOFF / WOFF2 转换")

    output_dir.mkdir(parents=True, exist_ok=True)
    source_hash = sha256(source)
    decoder = _resolve_decoder(woff2_decoder)
    # Tests use this to reproduce the on-device runtime, where FontTools has no Brotli.
    force_native = container == "WOFF2" and os.environ.get("LUOSHU_WOFF2_FORCE_NATIVE") == "1"
    decode_method = "fonttools"

    with tempfile.NamedTemporaryFile(
        prefix=".luoshu-webfont-", suffix=".sfnt", dir=output_dir, delete=False
    ) as handle:
        temp = Path(handle.name)
    try:
        fonttools_error: Exception | None = None
        if not force_native:
            try:
                _fonttools_decode(source, temp)
            except Exception as error:  # noqa: BLE001 - any decoder failure falls through
                fonttools_error = error
        if force_native or fonttools_error is not None:
            if container != "WOFF2":
                raise ValueError(f"WOFF 解码失败：{fonttools_error}") from fonttools_error
            _native_woff2_decode(source, temp, decoder)
            decode_method = "native"

        output_format, face_count = validate_decoded(temp)
        ext = extension_for_format(output_format)
        output_hash = sha256(temp)
        stem = safe_stem(source.stem)
        target = output_dir / f"{stem}.{ext}"
        duplicate = False
        if target.exists():
            if target.is_file() and sha256(target) == output_hash:
                duplicate = True
            else:
                target = output_dir / f"{stem}-{source_hash[:10]}.{ext}"
                duplicate = target.is_file() and sha256(target) == output_hash
        if not duplicate:
            final_temp = target.with_name(target.name + f".tmp.{os.getpid()}")
            shutil.copyfile(temp, final_temp)
            os.chmod(final_temp, 0o644)
            os.replace(final_temp, target)
        return {
            "status": "ok",
            "sourceContainer": container,
            "sourceSha256": source_hash,
            "decodeMethod": decode_method,
            "outputFormat": output_format,
            "outputSha256": output_hash,
            "outputPath": str(target),
            "outputFileName": target.name,
            "faceCount": face_count,
            "duplicate": duplicate,
        }
    finally:
        temp.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--woff2-decoder", type=Path)
    args = parser.parse_args()
    try:
        result = convert(args.input, args.output_dir, args.woff2_decoder)
    except Exception as error:  # noqa: BLE001 - CLI reports every failure as JSON
        message = str(error) or error.__class__.__name__
        print(json.dumps({"status": "error", "message": message}, ensure_ascii=False, separators=(",", ":")))
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
