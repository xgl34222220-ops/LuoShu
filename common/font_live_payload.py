#!/usr/bin/env python3
"""Copy immutable live generations without sharing writable source inodes."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys


def prepare(source, cache, boot, temporary):
    source, cache, temporary = Path(source), Path(cache), Path(temporary)
    if source.is_symlink() or not source.is_dir() or cache.is_symlink():
        raise ValueError("unsafe payload root")
    cache.mkdir(parents=True, exist_ok=True)
    for old in cache.glob("generation-*"):
        record = old / ".generation.json"
        if not re.fullmatch(r"generation-[0-9a-f]{64}", old.name):
            continue
        if old.is_symlink() or not old.is_dir() or record.is_symlink():
            continue
        try:
            saved = json.loads(record.read_text())
        except (OSError, ValueError):
            continue
        if (saved.get("schema") == "luoshu-live-font-v1" and
                saved.get("digest") == old.name.removeprefix("generation-") and
                saved.get("bootId") and saved["bootId"] != boot):
            shutil.rmtree(old)
    entries, inodes, needed = [], {}, 0
    digest = hashlib.sha256()
    for current, directories, files in os.walk(source, followlinks=False):
        if any((Path(current) / name).is_symlink() for name in directories):
            raise ValueError("payload directory symlink")
        directories.sort()
        for name in sorted(files):
            path = Path(current) / name
            if Path(current) == source and name in {'.luoshu-next-transaction.conf', '.luoshu-mix-generation.conf', '.luoshu-metrics-report.json'}:
                continue
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("payload contains non-regular file")
            identity = (info.st_dev, info.st_ino)
            relative = path.relative_to(source)
            digest.update(str(relative).encode() + b"\0")
            if identity not in inodes:
                value = hashlib.sha256()
                with path.open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        value.update(block)
                inodes[identity] = value.digest()
                needed += info.st_size
            digest.update(inodes[identity])
            entries.append((path, relative, identity))
    generation = cache / ("generation-" + digest.hexdigest())
    if generation.exists():
        if generation.is_symlink() or not generation.is_dir():
            raise ValueError("unsafe generation")
        record_file = generation / ".generation.json"
        if record_file.is_symlink():
            raise ValueError("unsafe generation record")
        record = json.loads(record_file.read_text())
        if record.get("bootId") != boot or record.get("digest") != digest.hexdigest():
            raise ValueError("generation identity mismatch")
        checked = {}
        for _, relative, identity in entries:
            destination = generation / relative
            info = destination.lstat()
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("cached generation is not immutable")
            cache_identity = (info.st_dev, info.st_ino)
            if cache_identity not in checked:
                value = hashlib.sha256()
                with destination.open('rb') as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b''):
                        value.update(block)
                checked[cache_identity] = value.digest()
            if checked[cache_identity] != inodes[identity]:
                raise ValueError("cached generation content mismatch")
        return generation
    if shutil.disk_usage(cache).free < needed + 16 * 1024 * 1024:
        raise ValueError("insufficient free space for immutable live payload")
    temporary.mkdir(mode=0o755)
    copied = {}
    try:
        for path, relative, identity in entries:
            destination = temporary / relative
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            if identity in copied:
                os.link(copied[identity], destination)
            else:
                shutil.copyfile(path, destination)
                os.chmod(destination, 0o644)
                copied[identity] = destination
        record = {"schema": "luoshu-live-font-v1", "bootId": boot,
                  "digest": digest.hexdigest(), "bytes": needed}
        (temporary / ".generation.json").write_text(json.dumps(record))
        temporary.rename(generation)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return generation


if __name__ == "__main__":
    try:
        if sys.argv[1:2] == ['--lock-exec']:
            lock = Path(sys.argv[2])
            if lock.is_symlink():
                raise ValueError('unsafe live lock')
            descriptor = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.set_inheritable(descriptor, True)
            os.environ['LUOSHU_LIVE_LOCK_FD'] = str(descriptor)
            os.execvp(sys.argv[3], sys.argv[3:])
        print(prepare(*sys.argv[1:]))
    except (OSError, ValueError, TypeError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
