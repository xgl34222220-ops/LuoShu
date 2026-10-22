#!/usr/bin/env python3
"""fs-verity for LuoShu-owned replacements of protected /data/fonts files.

Android's FontManagerService marks updatable fonts (/data/fonts/files: Emoji and
Google-delivered fonts) with ``hasVerity``. When such a font is opened, hwui
aborts the process if the visible file has no fs-verity bit, a different
``head.fontRevision`` or a different PostScript name. A LuoShu bind over one of
those paths must therefore be a sealed, metadata-compatible file, or it must not
exist at all.

This helper only seals module-owned replacement inodes (the provider clone
cache inside the module and the per-namespace staging copy). Original update
files, keys, signatures, sysctls and framework checks are never changed.

Linux UAPI: FS_IOC_ENABLE_VERITY / FS_IOC_MEASURE_VERITY.

Ported from 字域 Ziyu v1.4.8 ``common/font_verity.py`` (作者 酷安@柔性体,
shishui611-art/Ziyu, GPL-3.0-only) and adapted for LuoShu: module-relative
ownership, explicit "unsupported" classification and a ``probe`` action.

Exit codes: 0 ok, 1 failure, 3 fs-verity unsupported by kernel/filesystem.
"""
from __future__ import annotations

import errno
import fcntl
import os
from pathlib import Path
import struct
import sys

ENABLE = 0x40806685
MEASURE = 0xC0046686
EXIT_UNSUPPORTED = 3
STAGE_PREFIX = ".luoshu-provider-"

# Kernel or filesystem without fs-verity (no CONFIG_FS_VERITY, ext4/f2fs
# without the verity feature, tmpfs/overlay/sdcardfs...). These never succeed
# on a retry, so callers must drop the protected replacement instead.
UNSUPPORTED_ERRNOS = frozenset(
    value for value in (
        errno.ENOTTY, errno.EOPNOTSUPP, getattr(errno, "ENOTSUP", errno.EOPNOTSUPP),
        errno.ENOSYS, errno.EINVAL,
    )
)


class VerityUnsupported(OSError):
    """fs-verity cannot be enabled on this file's filesystem."""


def _strip_proc_root(text: str) -> str:
    # The namespace helper reaches the module through /proc/1/root.
    prefix = "/proc/1/root/"
    while text.startswith(prefix):
        text = "/" + text[len(prefix):]
    return text


def measured(path) -> str:
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        value = bytearray(struct.pack("=HH", 0, 64) + bytes(64))
        fcntl.ioctl(fd, MEASURE, value, True)
        algorithm, size = struct.unpack_from("=HH", value)
        if algorithm not in (1, 2) or size not in (32, 64):
            raise ValueError("unexpected fs-verity digest")
        return bytes(value[:4 + size]).hex()
    finally:
        os.close(fd)


def seal(path) -> str:
    """Enable fs-verity on a closed regular file and return its digest.

    Raises VerityUnsupported when the kernel/filesystem cannot provide it.
    """
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("fs-verity source is not a regular file")
    try:
        return measured(path)
    except OSError as error:
        if error.errno in UNSUPPORTED_ERRNOS and error.errno != errno.EINVAL:
            raise VerityUnsupported(error.errno, f"fs-verity unsupported: {error.strerror}") from error
        if error.errno != errno.ENODATA:
            raise
    # A read-only descriptor is required and no writer may stay open
    # (ETXTBSY). The filesystem stores the Merkle tree; the inode becomes
    # immutable, which is exactly what FontManagerService expects.
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        last_error: OSError | None = None
        for block_size in _block_sizes():
            try:
                fcntl.ioctl(fd, ENABLE, enable_argument(block_size))
                last_error = None
                break
            except OSError as error:
                if error.errno == errno.EEXIST:
                    last_error = None
                    break
                last_error = error
                # Kernels before 6.3 only accept block_size == PAGE_SIZE.
                if error.errno != errno.EINVAL:
                    break
        if last_error is not None:
            if last_error.errno in UNSUPPORTED_ERRNOS:
                raise VerityUnsupported(last_error.errno,
                                        f"fs-verity unsupported: {last_error.strerror}") from last_error
            raise last_error
    finally:
        os.close(fd)
    return measured(path)


def enable_argument(block_size: int) -> bytes:
    # struct fsverity_enable_arg: version=1, hash_algorithm=SHA-256, block_size,
    # no salt, no builtin signature. AOSP VerityUtils also uses 4096.
    return struct.pack("=IIIIQIIQ11Q", 1, 1, block_size, 0, 0, 0, 0, 0, *([0] * 11))


def _block_sizes() -> list[int]:
    sizes = [4096]
    try:
        page = int(os.sysconf("SC_PAGE_SIZE"))
    except (ValueError, OSError):
        page = 4096
    if page not in sizes and page > 0:
        sizes.append(page)
    return sizes


def owned(path: Path, module_root: Path | None = None) -> bool:
    """Only module files and per-namespace staging copies may be sealed."""
    module_root = module_root or Path(__file__).resolve().parents[1]
    root_text = _strip_proc_root(module_root.as_posix()).rstrip("/")
    roots = [root_text + "/"]
    parent, name = os.path.split(root_text)
    if os.path.basename(parent) == "modules":
        roots.append(os.path.join(os.path.dirname(parent), "modules_update", name) + "/")
    text = _strip_proc_root(os.path.realpath(_strip_proc_root(os.path.abspath(path))))
    if any(text.startswith(root) for root in roots):
        return True
    stage_dirs = {"/data/local/tmp"}
    configured = os.environ.get("LUOSHU_GOOGLE_FONT_STAGE_DIR", "").rstrip("/")
    if configured:
        stage_dirs.add(_strip_proc_root(configured))
    resolved = Path(text)
    return resolved.parent.as_posix() in stage_dirs and resolved.name.startswith(STAGE_PREFIX)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        raise ValueError("usage: font_verity.py {seal|check} PATH")
    command, raw = argv
    path = Path(raw)
    if command == "seal":
        if not owned(path):
            raise ValueError("refusing to seal an original or unrelated file")
        print(seal(path))
    elif command == "check":
        print(measured(path))
    else:
        raise ValueError("unknown fs-verity action")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except VerityUnsupported as error:
        print(f"font fs-verity unsupported: {error}", file=sys.stderr)
        raise SystemExit(EXIT_UNSUPPORTED)
    except Exception as error:
        print(f"font fs-verity check failed: {error}", file=sys.stderr)
        raise SystemExit(1)
