#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""LuoShu safe font extraction from a ZIP archive.

    font_zip_extract.py ARCHIVE OUTPUT_DIR [MAX_FILES] [MAX_TOTAL_BYTES]

Only font members (.ttf .otf .ttc .otc .woff .woff2) are written, flattened
into OUTPUT_DIR (which must exist). Nothing in the archive is executed.

Rejected outright (exit 1, reason on stderr):
  * absolute paths, drive letters, ".." components, control characters,
    NUL bytes in a font member's name;
  * font members stored as symbolic links or other non-regular files;
  * encrypted font members;
  * more font members than MAX_FILES, more central-directory entries than a
    fixed ceiling, or declared sizes above MAX_TOTAL_BYTES;
  * a member whose inflated data exceeds its declared size, the remaining
    total budget, or a sane compression ratio (decompression bomb).
Non-font members and macOS resource forks (__MACOSX/, ._*) are skipped.
Exit 2 means the archive could not be read or the arguments are wrong.
stdout gets one line per extracted file: "<size>\t<output path>".
"""

import os
import stat
import sys
import zipfile

FONT_EXTS = (".ttf", ".otf", ".ttc", ".otc", ".woff", ".woff2")
DEFAULT_MAX_FILES = 128
DEFAULT_MAX_TOTAL = 512 * 1024 * 1024
MAX_ENTRIES = 4096
MAX_RATIO = 200          # inflated / compressed
RATIO_FLOOR = 1 << 20    # ratios are only enforced above 1 MiB of output
CHUNK = 1 << 16


class Rejected(Exception):
    pass


def _bad_name(name):
    if not name or "\0" in name:
        return True
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in name):
        return True
    norm = name.replace("\\", "/")
    if norm.startswith("/") or (len(norm) > 1 and norm[1] == ":"):
        return True
    return any(part == ".." for part in norm.split("/"))


def _is_resource_fork(name):
    norm = name.replace("\\", "/")
    parts = [p for p in norm.split("/") if p]
    if not parts:
        return True
    return parts[0] == "__MACOSX" or parts[-1].startswith("._")


def _is_link_or_special(info):
    mode = (info.external_attr >> 16) & 0xFFFF
    if info.create_system == 3 and mode:  # Unix
        fmt = stat.S_IFMT(mode)
        return fmt not in (0, stat.S_IFREG)
    return False


def _flat_name(name, used):
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    base = "".join(ch for ch in base if ch not in ':*?"<>|').strip()
    stem, ext = os.path.splitext(base)
    stem = stem.strip(" .") or "font"
    stem = stem[:120]
    ext = ext.lower()
    cand = stem + ext
    n = 2
    while cand.lower() in used:
        cand = "%s-%d%s" % (stem, n, ext)
        n += 1
    used.add(cand.lower())
    return cand


def select_members(zf, max_files, max_total):
    infos = zf.infolist()
    if len(infos) > MAX_ENTRIES:
        raise Rejected("压缩包条目过多（超过 %d 个）" % MAX_ENTRIES)
    picked = []
    declared = 0
    for info in infos:
        name = info.filename
        if name.endswith("/") or info.is_dir():
            continue
        if _is_resource_fork(name):
            continue
        if not name.lower().endswith(FONT_EXTS):
            continue
        if _bad_name(name):
            raise Rejected("字体条目路径不安全：%s" % name[:80].encode("unicode_escape").decode("ascii"))
        if _is_link_or_special(info):
            raise Rejected("字体条目是符号链接或特殊文件：%s" % name[:80])
        if info.flag_bits & 0x1:
            raise Rejected("不支持加密的字体条目：%s" % name[:80])
        if info.file_size <= 0:
            continue
        picked.append(info)
        declared += info.file_size
        if len(picked) > max_files:
            raise Rejected("字体数量超过上限（最多 %d 个）" % max_files)
        if declared > max_total:
            raise Rejected("字体解压后总大小超过上限")
    return picked


def extract(archive, out_dir, max_files, max_total):
    if not os.path.isdir(out_dir):
        raise OSError("output directory missing")
    written = []
    budget = max_total
    try:
        with zipfile.ZipFile(archive) as zf:
            members = select_members(zf, max_files, max_total)
            used = {n.lower() for n in os.listdir(out_dir)}
            for info in members:
                target = os.path.join(out_dir, _flat_name(info.filename, used))
                limit = min(info.file_size, budget)
                total = 0
                fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
                written.append(target)
                with os.fdopen(fd, "wb") as out, zf.open(info) as src:
                    while True:
                        block = src.read(CHUNK)
                        if not block:
                            break
                        total += len(block)
                        if total > limit:
                            raise Rejected("字体条目实际解压大小超过声明：%s" % info.filename[:80])
                        if total > RATIO_FLOOR and total > MAX_RATIO * max(info.compress_size, 1):
                            raise Rejected("字体条目压缩比异常（疑似解压炸弹）：%s" % info.filename[:80])
                        out.write(block)
                if total != info.file_size:
                    raise Rejected("字体条目长度与声明不一致：%s" % info.filename[:80])
                budget -= total
                sys.stdout.write("%d\t%s\n" % (total, target))
    except Rejected:
        for path in written:
            try:
                os.unlink(path)
            except OSError:
                pass
        raise
    except (zipfile.BadZipFile, zipfile.LargeZipFile, NotImplementedError, EOFError) as exc:
        for path in written:
            try:
                os.unlink(path)
            except OSError:
                pass
        raise Rejected("ZIP 字体包读取失败（%s）" % type(exc).__name__)
    return written


def _int_arg(value, default):
    try:
        n = int(value)
        return n if n > 0 else default
    except (TypeError, ValueError):
        return default


def main(argv):
    if len(argv) < 3:
        sys.stderr.write("用法：font_zip_extract.py ARCHIVE OUTPUT_DIR [MAX_FILES] [MAX_TOTAL_BYTES]\n")
        return 2
    max_files = _int_arg(argv[3] if len(argv) > 3 else None, DEFAULT_MAX_FILES)
    max_total = _int_arg(argv[4] if len(argv) > 4 else None, DEFAULT_MAX_TOTAL)
    try:
        extract(argv[1], argv[2], max_files, max_total)
        return 0
    except Rejected as exc:
        sys.stderr.write("%s\n" % exc)
        return 1
    except zipfile.BadZipFile:
        sys.stderr.write("ZIP 字体包读取失败\n")
        return 1
    except OSError as exc:
        sys.stderr.write("解压失败：%s\n" % (exc.strerror or exc))
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
