#!/usr/bin/env python3
"""Serialize the one-time private-tree migration with a process-owned kernel lock.

The lock file stays at one inode. There is no PID journal to reap and no daemon:
after acquiring it this process becomes the migration shell through exec.
"""
from __future__ import annotations

import fcntl
import os
from pathlib import Path
import stat
import sys
import time


def main() -> int:
    if len(sys.argv) != 2:
        return 2
    module = Path(sys.argv[1]).resolve(strict=True)
    if module == Path("/") or not module.is_dir():
        return 1
    if (module / ".git").exists() or (module / ".git").is_symlink():
        return 1
    state = module / ".luoshu-state"
    if state.is_symlink() or (state.exists() and not state.is_dir()):
        return 1
    helper = module / "common/runtime_paths.sh"
    if not helper.is_file():
        return 1
    os.umask(0o077)
    state.mkdir(mode=0o700, exist_ok=True)
    descriptor = os.open(state / ".paths-migrate.flock",
                         os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
        os.close(descriptor)
        return 1
    deadline = time.monotonic() + 10
    while True:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() >= deadline:
                os.close(descriptor)
                return 2
            time.sleep(0.02)
    os.set_inheritable(descriptor, True)
    # Use positional arguments, never interpolate a pathname into shell code.
    os.execvp("sh", ["sh", "-c", '. "$1"; _luoshu_runtime_prepare_locked "$2"',
                     "luoshu-paths-migrate", str(helper), str(module)])
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError):
        raise SystemExit(1)
