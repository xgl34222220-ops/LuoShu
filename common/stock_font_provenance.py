"""Kernel-view stock provenance, not cryptographic vendor authentication.

A lower/mirror must map to the same read-only block filesystem location as the
partition ancestor. Mere directory existence or different replacement bytes is
never evidence. Re-evaluate on every use: mount IDs are namespace/boot-local.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import re


def _unescape(value):
    return re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), value)


def _mounts():
    rows = []
    for line in Path(os.environ.get('LUOSHU_MOUNTINFO', '/proc/self/mountinfo')).read_text().splitlines():
        left, sep, right = line.partition(' - ')
        a, b = left.split(), right.split()
        if not sep or len(a) < 6 or len(b) < 3:
            continue
        rows.append(dict(id=a[0], device=a[2], root=_unescape(a[3]),
                         point=_unescape(a[4]), options=a[5].split(','),
                         fs=b[0], source=_unescape(b[1]), superOptions=b[2].split(',')))
    return rows


def _within(path, root):
    return path == root or path.startswith(root.rstrip('/') + '/')


def verify_stock_path(logical_path, actual_path):
    logical = Path(logical_path)
    if not logical.is_absolute() or '..' in logical.parts or len(logical.parts) < 3:
        raise ValueError('stock-provenance-invalid-logical-path')
    if logical.parts[1] in {'data', 'proc', 'sys', 'dev', 'tmp', 'mnt'}:
        raise ValueError('stock-provenance-not-rom-partition')
    # Resolve partition aliases, but never resolve the logical font itself through
    # a replacement symlink. A system-as-root ancestor can legitimately be /.
    partition = Path('/' + logical.parts[1]).resolve()
    expected = str(partition.joinpath(*logical.parts[2:]))
    actual = os.path.abspath(actual_path)
    rows = _mounts()
    ancestors = [m for m in rows if _within(str(partition), m['point'])]
    if not ancestors:
        raise ValueError('stock-provenance-partition-mount-missing')
    # A covering mount does not erase the original mountinfo row. Keep the
    # original read-only partition as a candidate, but accept it only when the
    # actual lower maps to that exact filesystem device and location below.
    origins = [m for m in ancestors if m['fs'] in {'ext4', 'erofs', 'squashfs'}
               and m['source'].startswith('/dev/block/')
               and 'ro' in m['options'] and 'ro' in m['superOptions']]
    if not origins:
        raise ValueError('stock-provenance-partition-not-readonly-block')
    visible = [m for m in rows if _within(actual, m['point'])]
    if not visible:
        raise ValueError('stock-provenance-actual-mount-missing')
    mounted = max(visible, key=lambda m: (len(m['point']), int(m['id'])))
    def location(m, path):
        return str(Path(m['root']) / Path(path).relative_to(m['point']))
    matching = [m for m in origins if mounted['device'] == m['device']
                and mounted['fs'] == m['fs']
                and location(mounted, actual) == location(m, expected)]
    if not matching:
        raise ValueError('stock-provenance-filesystem-lineage-mismatch')
    origin = max(matching, key=lambda m: (len(m['point']), int(m['id'])))
    # First prove the lexical alias inode belongs to the expected ROM path.
    # Then follow only links whose own inode and final target remain on that
    # same read-only partition. Never resolve the possibly overlaid live alias.
    current = Path(actual)
    followed = 0
    while True:
        changed = False
        parts = current.parts
        for count in range(1, len(parts)):
            prefix = Path(*parts[:count + 1])
            if not prefix.is_symlink():
                continue
            link_rows = [m for m in rows if _within(str(prefix), m['point'])]
            link_mount = max(link_rows, key=lambda m: (len(m['point']), int(m['id']))) if link_rows else None
            if (not link_mount or link_mount['device'] != origin['device']
                    or link_mount['fs'] != origin['fs']):
                raise ValueError('stock-provenance-alias-link-unproven')
            followed += 1
            if followed > 40:
                raise ValueError('stock-provenance-alias-loop')
            target = Path(os.readlink(prefix))
            if not target.is_absolute():
                target = prefix.parent / target
            current = Path(os.path.abspath(target.joinpath(*parts[count + 1:])))
            changed = True
            break
        if not changed:
            break
    if str(current) != str(Path(actual_path).resolve(strict=True)):
        raise ValueError('stock-provenance-alias-resolution-ambiguous')
    final_rows = [m for m in rows if _within(str(current), m['point'])]
    final_mount = max(final_rows, key=lambda m: (len(m['point']), int(m['id']))) if final_rows else None
    if (not final_mount or final_mount['device'] != origin['device']
            or final_mount['fs'] != origin['fs']
            or not _within(location(final_mount, str(current)), origin['root'])):
        raise ValueError('stock-provenance-alias-target-unproven')
    try:
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        namespace = os.readlink('/proc/self/ns/mnt')
    except OSError as exc:
        raise ValueError('stock-provenance-runtime-identity-missing') from exc
    return dict(schema='stock-view-proof-v1', verified=True, bootId=boot,
                mountNamespace=namespace, device=origin['device'], filesystem=origin['fs'],
                filesystemPath=location(origin, expected), originMountId=origin['id'],
                actualMountId=mounted['id'])


def stock_identity(logical_path, actual_path, face_index, build_key, *, provenance_path=None):
    digest = hashlib.sha256()
    with Path(actual_path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    try:
        proof_path = actual_path if provenance_path is None else provenance_path
        proof = verify_stock_path(logical_path, proof_path)
        if Path(proof_path).resolve(strict=True) != Path(actual_path).resolve(strict=True):
            raise ValueError('stock-provenance-resolved-file-mismatch')
    except (ValueError, OSError) as exc:
        proof = dict(schema='stock-view-proof-v1', verified=False, reason=str(exc))
    return dict(logicalPath=str(logical_path), faceIndex=int(face_index),
                sha256=digest.hexdigest(), buildKey=str(build_key), provenance=proof)
