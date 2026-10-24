#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""LuoShu web font unwrapper.

Turns one WOFF or WOFF2 container back into the plain SFNT (TTF/OTF/TTC) it
carries, so the result can go through LuoShu's normal font checks.

    font_web_convert.py SOURCE OUTPUT_DIR [--name STEM]

Prints exactly one JSON line on stdout:
    {"ok":true,"output":"/dir/Stem.ttf","source":"WOFF","format":"TTF","method":"zlib"}
    {"ok":false,"error":"..."}
Exit status is 0 on success and 1 on any failure.

Order of attempts:
  * FontTools, when importable (and, for WOFF2, only when a Brotli module is
    importable too, because FontTools needs one to read WOFF2);
  * WOFF 1.0: a small built-in reader following the W3C WOFF 1.0 file format
    (header, table directory, zlib-compressed table data);
  * WOFF2: the bundled static decoder `luoshu-woff2-decode INPUT OUTPUT`
    (built from google/woff2 + google/brotli, MIT).
The output file is written to a temporary name and renamed only after it is
complete; nothing is written outside OUTPUT_DIR.
"""

import json
import os
import struct
import subprocess
import sys
import zlib

MAX_INPUT = 256 * 1024 * 1024
MAX_OUTPUT = 512 * 1024 * 1024
MAX_TABLES = 4096
DECODER_TIMEOUT = 300

WOFF_SIG = b"wOFF"
WOFF2_SIG = b"wOF2"
FLAVOR_EXT = {
    b"\x00\x01\x00\x00": ("TTF", "ttf"),
    b"true": ("TTF", "ttf"),
    b"OTTO": ("OTF", "otf"),
    b"ttcf": ("TTC", "ttc"),
}


class ConvertError(Exception):
    pass


def emit(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def sfnt_kind(head):
    kind = FLAVOR_EXT.get(head[:4])
    if kind is None:
        raise ConvertError("转换结果不是 TTF/OTF/TTC 字体")
    return kind


def safe_stem(stem):
    cleaned = "".join(ch for ch in stem if ch.isprintable() and ch not in '/\\:\0')
    cleaned = cleaned.strip().strip(".")
    return cleaned[:120] or "WebFont"


# --------------------------------------------------------------------------
# WOFF 1.0 (W3C Recommendation, 13 Dec 2012), section 3-5.
# Header: signature, flavor, length, numTables, reserved, totalSfntSize,
# majorVersion, minorVersion, metaOffset, metaLength, metaOrigLength,
# privOffset, privLength  -> 44 bytes, big endian.
# Table directory entry: tag, offset, compLength, origLength, origChecksum.
# --------------------------------------------------------------------------
WOFF_HEADER = struct.Struct(">4s4sIHHIHHIIIII")
WOFF_ENTRY = struct.Struct(">4sIIII")


def _search_params(num_tables):
    entry_selector = 0
    while (1 << (entry_selector + 1)) <= num_tables:
        entry_selector += 1
    search_range = (1 << entry_selector) * 16
    return search_range, entry_selector, num_tables * 16 - search_range


def unwrap_woff1(data):
    if len(data) < WOFF_HEADER.size:
        raise ConvertError("WOFF 文件头不完整")
    (sig, flavor, length, num_tables, reserved, total_sfnt, _maj, _min,
     _mo, _ml, _mol, _po, _pl) = WOFF_HEADER.unpack_from(data, 0)
    if sig != WOFF_SIG:
        raise ConvertError("不是 WOFF 文件")
    if flavor not in FLAVOR_EXT or flavor == b"ttcf":
        raise ConvertError("WOFF 内含的字体类型不受支持")
    if length != len(data):
        raise ConvertError("WOFF 声明长度与文件大小不一致")
    if reserved != 0:
        raise ConvertError("WOFF 文件头保留字段非零")
    if num_tables == 0 or num_tables > MAX_TABLES:
        raise ConvertError("WOFF 表数量异常")
    dir_end = WOFF_HEADER.size + num_tables * WOFF_ENTRY.size
    if dir_end > len(data):
        raise ConvertError("WOFF 表目录不完整")
    if total_sfnt > MAX_OUTPUT or total_sfnt % 4:
        raise ConvertError("WOFF 声明的解包大小异常")

    entries = []
    seen = set()
    for i in range(num_tables):
        tag, off, comp, orig, checksum = WOFF_ENTRY.unpack_from(data, WOFF_HEADER.size + i * WOFF_ENTRY.size)
        if tag in seen:
            raise ConvertError("WOFF 含重复的表")
        seen.add(tag)
        if off < dir_end or off % 4 or off + comp > len(data):
            raise ConvertError("WOFF 表数据越界")
        if comp > orig:
            raise ConvertError("WOFF 表压缩长度大于原始长度")
        entries.append((tag, off, comp, orig, checksum))

    header_len = 12 + 16 * num_tables
    expected_total = header_len + sum((e[3] + 3) & ~3 for e in entries)
    if expected_total > MAX_OUTPUT:
        raise ConvertError("WOFF 解包后过大")
    if total_sfnt != expected_total:
        raise ConvertError("WOFF totalSfntSize 与表目录不一致")

    tables = {}
    for tag, off, comp, orig, checksum in entries:
        raw = data[off:off + comp]
        if comp < orig:
            inflater = zlib.decompressobj()
            try:
                body = inflater.decompress(raw, orig)
            except zlib.error:
                raise ConvertError("WOFF 表 %s 解压失败" % tag.decode("latin-1", "replace").strip())
            if len(body) != orig or inflater.unconsumed_tail or not inflater.eof:
                raise ConvertError("WOFF 表 %s 解压长度不符" % tag.decode("latin-1", "replace").strip())
        else:
            body = raw
        tables[tag] = (body, checksum)

    # SFNT table records must be sorted by tag; data follows in the same order,
    # each table padded to a 4-byte boundary.
    search_range, entry_selector, range_shift = _search_params(num_tables)
    out = bytearray(struct.pack(">4sHHHH", flavor, num_tables, search_range, entry_selector, range_shift))
    offset = header_len
    body_parts = []
    for tag in sorted(tables):
        body, checksum = tables[tag]
        out += struct.pack(">4sIII", tag, checksum, offset, len(body))
        pad = (-len(body)) % 4
        body_parts.append(body + b"\0" * pad)
        offset += len(body) + pad
    for part in body_parts:
        out += part
    return bytes(out), "zlib"


# --------------------------------------------------------------------------
# Strategies
# --------------------------------------------------------------------------
def via_fonttools(src, sig, dest):
    if os.environ.get("LUOSHU_WEB_CONVERT_NO_FONTTOOLS") == "1":
        return False
    try:
        from fontTools.ttLib import TTFont
    except Exception:
        return False
    if sig == WOFF2_SIG:
        try:
            import brotli  # noqa: F401
        except Exception:
            try:
                import brotlicffi  # noqa: F401
            except Exception:
                return False
    try:
        with open(src, "rb") as fh:
            head = fh.read(8)
        # Collections inside WOFF2 are left to the bundled decoder.
        if head[4:8] == b"ttcf":
            return False
        font = TTFont(src, recalcBBoxes=False, recalcTimestamp=False)
        font.flavor = None
        font.save(dest, reorderTables=False)
        font.close()
        return True
    except Exception:
        try:
            os.unlink(dest)
        except OSError:
            pass
        return False


def find_decoder():
    env = os.environ.get("LUOSHU_WOFF2_DECODER", "")
    if env:
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "python", "bin", "luoshu-woff2-decode")


def via_decoder(src, dest):
    decoder = find_decoder()
    if not os.path.isfile(decoder):
        raise ConvertError("缺少 WOFF2 解码组件")
    if not os.access(decoder, os.X_OK):
        raise ConvertError("WOFF2 解码组件没有执行权限")
    try:
        proc = subprocess.run([decoder, src, dest], stdout=subprocess.DEVNULL,
                              stderr=subprocess.PIPE, timeout=DECODER_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise ConvertError("WOFF2 解码超时")
    except OSError as exc:
        raise ConvertError("WOFF2 解码组件无法运行（%s）" % exc.strerror)
    if proc.returncode != 0 or not os.path.isfile(dest):
        reason = {3: "读取失败", 4: "文件损坏或格式不受支持", 5: "写入失败"}.get(proc.returncode, "退出码 %d" % proc.returncode)
        raise ConvertError("WOFF2 解码失败：%s" % reason)


def convert(src, out_dir, stem=None):
    try:
        size = os.path.getsize(src)
    except OSError:
        raise ConvertError("无法读取源文件")
    if size <= 0 or size > MAX_INPUT:
        raise ConvertError("网页字体文件大小超出范围")
    with open(src, "rb") as fh:
        sig = fh.read(4)
    if sig == WOFF_SIG:
        source = "WOFF"
    elif sig == WOFF2_SIG:
        source = "WOFF2"
    else:
        raise ConvertError("不是 WOFF/WOFF2 网页字体")

    if not os.path.isdir(out_dir):
        raise ConvertError("转换输出目录不存在")
    stem = safe_stem(stem or os.path.splitext(os.path.basename(src))[0])
    tmp = os.path.join(out_dir, ".%s.%d.part" % (stem, os.getpid()))
    method = None
    try:
        if via_fonttools(src, sig, tmp):
            method = "fonttools"
        elif source == "WOFF":
            with open(src, "rb") as fh:
                data = fh.read()
            sfnt, method = unwrap_woff1(data)
            with open(tmp, "wb") as fh:
                fh.write(sfnt)
        else:
            via_decoder(src, tmp)
            method = "woff2-decoder"
        out_size = os.path.getsize(tmp)
        if out_size < 12 or out_size > MAX_OUTPUT:
            raise ConvertError("转换结果大小异常")
        with open(tmp, "rb") as fh:
            fmt, ext = sfnt_kind(fh.read(4))
        dest = os.path.join(out_dir, "%s.%s" % (stem, ext))
        n = 2
        while os.path.exists(dest):
            dest = os.path.join(out_dir, "%s-%d.%s" % (stem, n, ext))
            n += 1
        os.replace(tmp, dest)
        return {"ok": True, "output": dest, "source": source, "format": fmt, "method": method}
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def main(argv):
    args = list(argv[1:])
    stem = None
    if "--name" in args:
        i = args.index("--name")
        if i + 1 >= len(args):
            emit({"ok": False, "error": "参数错误"})
            return 1
        stem = args[i + 1]
        del args[i:i + 2]
    if len(args) != 2:
        emit({"ok": False, "error": "用法：font_web_convert.py SOURCE OUTPUT_DIR [--name STEM]"})
        return 1
    try:
        emit(convert(args[0], args[1], stem))
        return 0
    except ConvertError as exc:
        emit({"ok": False, "error": str(exc)})
    except MemoryError:
        emit({"ok": False, "error": "内存不足，无法转换网页字体"})
    except Exception as exc:  # never leak a traceback into the shell JSON channel
        emit({"ok": False, "error": "网页字体转换异常（%s）" % type(exc).__name__})
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
