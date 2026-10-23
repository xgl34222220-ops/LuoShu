#!/usr/bin/env python3
"""fs-verity helper for replacements of protected updatable fonts.

Android keeps updated system fonts under /data/fonts/files and only trusts a
file there when fs-verity is enabled on it (UpdatableFontDir/FontManagerService
in AOSP).  A bind-mounted replacement therefore has to carry its own verity
descriptor, otherwise the font is treated as tampered and dropped.

Kernel interface (Documentation/filesystems/fsverity.rst):
  FS_IOC_ENABLE_VERITY  _IOW('f', 133, struct fsverity_enable_arg)
  FS_IOC_MEASURE_VERITY _IOWR('f', 134, struct fsverity_digest)

Commands (one line of output each, stable for shell callers):
  enable PATH          -> "enabled" | "already" ; exit 0
  measure PATH         -> "sha256:<hex>"          ; exit 0
                          "none" (verity off)     ; exit 4
  compare A B          -> "match" exit 0 | "mismatch" exit 5 | "none" exit 4
Any command prints "unsupported:<reason>" and exits 3 when the kernel or the
filesystem cannot provide fs-verity, and "error:<reason>" with exit 1 otherwise.
"""
from __future__ import annotations

import errno
import fcntl
import os
import struct
import sys

FS_VERITY_HASH_ALG_SHA256 = 1
FS_VERITY_HASH_ALG_SHA512 = 2
_ALGORITHMS = {FS_VERITY_HASH_ALG_SHA256: "sha256", FS_VERITY_HASH_ALG_SHA512: "sha512"}
_MAX_DIGEST = 64

# struct fsverity_enable_arg: version, hash_algorithm, block_size, salt_size,
# salt_ptr, sig_size, __reserved1, sig_ptr, __reserved2[11]  (128 bytes)
_ENABLE_FORMAT = "=IIIIQIIQ11Q"
_ENABLE_SIZE = struct.calcsize(_ENABLE_FORMAT)
# struct fsverity_digest header: digest_algorithm, digest_size, then digest[]
_DIGEST_HEADER = "=HH"
_DIGEST_HEADER_SIZE = struct.calcsize(_DIGEST_HEADER)

_IOC_WRITE = 1
_IOC_READ = 2


def _ioc(direction: int, kind: str, number: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (ord(kind) << 8) | number


FS_IOC_ENABLE_VERITY = _ioc(_IOC_WRITE, "f", 133, _ENABLE_SIZE)
FS_IOC_MEASURE_VERITY = _ioc(_IOC_READ | _IOC_WRITE, "f", 134, _DIGEST_HEADER_SIZE)

# errno values meaning "this kernel/filesystem has no fs-verity for this file".
_UNSUPPORTED = {
    errno.ENOTTY, errno.EOPNOTSUPP, errno.ENOSYS, errno.EINVAL,
    getattr(errno, "ENOTSUP", errno.EOPNOTSUPP),
}


class Unsupported(Exception):
    pass


def _page_block_size() -> int:
    # Android creates font verity with 4 KiB Merkle blocks; kernels before 6.3
    # require block size == PAGE_SIZE, so follow the page size when it differs.
    try:
        size = os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError):
        size = 4096
    return size if size in (4096, 16384, 65536) else 4096


def enable(path: str) -> str:
    # FS_IOC_ENABLE_VERITY must be issued on a read-only descriptor and fails
    # with ETXTBSY while any writable descriptor is open on the inode.
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        arg = bytearray(struct.pack(_ENABLE_FORMAT, 1, FS_VERITY_HASH_ALG_SHA256,
                                    _page_block_size(), 0, 0, 0, 0, 0, *([0] * 11)))
        try:
            fcntl.ioctl(fd, FS_IOC_ENABLE_VERITY, arg, True)
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                return "already"
            if exc.errno in _UNSUPPORTED:
                raise Unsupported(errno.errorcode.get(exc.errno, str(exc.errno))) from exc
            raise
        return "enabled"
    finally:
        os.close(fd)


def measure(path: str) -> str | None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        buffer = bytearray(struct.pack(_DIGEST_HEADER, 0, _MAX_DIGEST) + bytes(_MAX_DIGEST))
        try:
            fcntl.ioctl(fd, FS_IOC_MEASURE_VERITY, buffer, True)
        except OSError as exc:
            if exc.errno == errno.ENODATA:
                return None
            if exc.errno in _UNSUPPORTED:
                raise Unsupported(errno.errorcode.get(exc.errno, str(exc.errno))) from exc
            raise
        algorithm, size = struct.unpack_from(_DIGEST_HEADER, buffer)
        if size <= 0 or size > _MAX_DIGEST:
            raise OSError(errno.EIO, "invalid fs-verity digest size")
        name = _ALGORITHMS.get(algorithm, f"alg{algorithm}")
        digest = bytes(buffer[_DIGEST_HEADER_SIZE:_DIGEST_HEADER_SIZE + size]).hex()
        return f"{name}:{digest}"
    finally:
        os.close(fd)


def _reason(exc: BaseException) -> str:
    if isinstance(exc, OSError) and exc.errno is not None:
        return errno.errorcode.get(exc.errno, str(exc.errno))
    return type(exc).__name__


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] not in ("enable", "measure", "compare") or \
            (argv[0] == "compare") != (len(argv) == 3) or len(argv) > 3:
        print("usage: font_verity.py enable PATH | measure PATH | compare A B", file=sys.stderr)
        return 2
    command = argv[0]
    try:
        if command == "enable":
            print(enable(argv[1]))
            return 0
        if command == "measure":
            value = measure(argv[1])
            print(value or "none")
            return 0 if value else 4
        first, second = measure(argv[1]), measure(argv[2])
        if first is None or second is None:
            print("none")
            return 4
        print("match" if first == second else "mismatch")
        return 0 if first == second else 5
    except Unsupported as exc:
        print(f"unsupported:{exc}")
        return 3
    except Exception as exc:  # noqa: BLE001 - stable one-line protocol for sh
        print(f"error:{_reason(exc)}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
