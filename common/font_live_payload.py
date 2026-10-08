#!/usr/bin/env python3
"""Copy immutable live generations without sharing writable source inodes."""
import fcntl
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys


def _source_identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _read_source(path, info, destination=None):
    """Hash the complete opened source, optionally copying that same byte stream."""
    expected = _source_identity(info)
    value = hashlib.sha256()
    with path.open('rb') as stream:
        if _source_identity(os.fstat(stream.fileno())) != expected:
            raise ValueError('payload source changed before read')
        with destination.open('xb') if destination is not None else nullcontext() as output:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                value.update(block)
                if output is not None:
                    output.write(block)
        if (_source_identity(os.fstat(stream.fileno())) != expected or
                _source_identity(path.lstat()) != expected):
            raise ValueError('payload source changed during read')
    return value.digest()


def _verify_generation(generation, digest, boot, entries, inodes):
    if generation.is_symlink() or not generation.is_dir():
        raise ValueError('unsafe generation')
    record_file = generation / '.generation.json'
    if record_file.is_symlink():
        raise ValueError('unsafe generation record')
    record = json.loads(record_file.read_text())
    if record.get('bootId') != boot or record.get('digest') != digest:
        raise ValueError('generation identity mismatch')
    checked = {}
    for _, relative, identity, _ in entries:
        destination = generation / relative
        info = destination.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('cached generation is not immutable')
        cache_identity = (info.st_dev, info.st_ino)
        if cache_identity not in checked:
            value = hashlib.sha256()
            with destination.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    value.update(block)
            checked[cache_identity] = value.digest()
        if checked[cache_identity] != inodes[identity]:
            raise ValueError('cached generation content mismatch')


def prepare(source, cache, boot, temporary):
    source, cache, temporary = Path(source), Path(cache), Path(temporary)
    if source.is_symlink() or not source.is_dir() or cache.is_symlink():
        raise ValueError("unsafe payload root")
    cache.mkdir(parents=True, exist_ok=True)
    current_boot_generation = False
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
                saved.get("bootId")):
            if saved["bootId"] != boot:
                shutil.rmtree(old)
            else:
                current_boot_generation = True
    entries, sizes, needed = [], {}, 0
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
            if identity not in sizes:
                sizes[identity] = info.st_size
                needed += info.st_size
            entries.append((path, relative, identity, info))
    # With no recorded generation of this boot, fuse the full SHA and independent
    # copy. Existing generations are still verified below. Keep the warm path
    # free of staging writes whenever this boot already has a reusable candidate.
    stream_copy = not current_boot_generation
    created = False
    inodes, copied, digest = {}, {}, hashlib.sha256()
    try:
        if stream_copy:
            if shutil.disk_usage(cache).free < needed + 16 * 1024 * 1024:
                raise ValueError('insufficient free space for immutable live payload')
            temporary.mkdir(mode=0o755)
            created = True
        for path, relative, identity, info in entries:
            destination = temporary / relative if stream_copy else None
            if stream_copy:
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            if identity not in inodes:
                inodes[identity] = _read_source(path, info, destination)
                if stream_copy:
                    os.chmod(destination, 0o644)
                    copied[identity] = destination
            elif stream_copy:
                os.link(copied[identity], destination)
            digest.update(str(relative).encode() + b'\0')
            digest.update(inodes[identity])
        # Check aliases and earlier files too before accepting the whole tree.
        if any(_source_identity(path.lstat()) != _source_identity(info)
               for path, _, _, info in entries):
            raise ValueError('payload source changed during preparation')
        generation = cache / ('generation-' + digest.hexdigest())
        if generation.exists() or generation.is_symlink():
            _verify_generation(generation, digest.hexdigest(), boot, entries, inodes)
            return generation
        if not stream_copy:
            if shutil.disk_usage(cache).free < needed + 16 * 1024 * 1024:
                raise ValueError('insufficient free space for immutable live payload')
            temporary.mkdir(mode=0o755)
            created = True
            for path, relative, identity, info in entries:
                destination = temporary / relative
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                if identity in copied:
                    os.link(copied[identity], destination)
                else:
                    if _source_identity(path.lstat()) != _source_identity(info):
                        raise ValueError('payload source changed before copy')
                    shutil.copyfile(path, destination)
                    if _source_identity(path.lstat()) != _source_identity(info):
                        raise ValueError('payload source changed during copy')
                    os.chmod(destination, 0o644)
                    copied[identity] = destination
            if any(_source_identity(path.lstat()) != _source_identity(info)
                   for path, _, _, info in entries):
                raise ValueError('payload source changed during preparation')
        record = {"schema": "luoshu-live-font-v1", "bootId": boot,
                  "digest": digest.hexdigest(), "bytes": needed}
        (temporary / ".generation.json").write_text(json.dumps(record))
        temporary.rename(generation)
    finally:
        if created and temporary.exists():
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
