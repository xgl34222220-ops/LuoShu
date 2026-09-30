"""Kernel-view stock provenance, not cryptographic vendor authentication.

A lower/mirror must map to the same read-only block filesystem location as the
partition ancestor. Mere directory existence or different replacement bytes is
never evidence. Re-evaluate on every use: mount IDs are namespace/boot-local.
"""
from __future__ import annotations
import hashlib
import itertools
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


STOCK_CAPTURE_REVISION = 2


def _location(mount, path):
    return str(Path(mount['root']) / Path(path).relative_to(mount['point']))


def _prove_location(logical, actual, rows):
    logical = Path(logical)
    if not logical.is_absolute() or '..' in logical.parts or len(logical.parts) < 3:
        raise ValueError('stock-provenance-invalid-logical-path')
    if logical.parts[1] in {'data', 'proc', 'sys', 'dev', 'tmp', 'mnt', 'sdcard', 'storage'}:
        raise ValueError('stock-provenance-not-rom-partition')
    # Android may expose a partition as /system/product as well as /product.
    # The font/config root's partition ancestor, never the font directory/file
    # itself, supplies the independent ROM mount anchor.
    boundary = next((i for i, part in enumerate(logical.parts)
                     if i >= 2 and part in {'fonts', 'font', 'etc'}), 2)
    partition = Path(*logical.parts[:boundary]).resolve()
    expected = str(partition.joinpath(*logical.parts[boundary:]))
    ancestors = [m for m in rows if _within(str(partition), m['point'])]
    if not ancestors:
        raise ValueError('stock-provenance-partition-mount-missing')
    origins = [m for m in ancestors if m['fs'] in {'ext4', 'erofs', 'squashfs'}
               and m['source'].startswith('/dev/block/')
               and 'ro' in m['options'] and 'ro' in m['superOptions']]
    if not origins:
        raise ValueError('stock-provenance-partition-not-readonly-block')
    visible = [m for m in rows if _within(str(actual), m['point'])]
    if not visible:
        raise ValueError('stock-provenance-actual-mount-missing')
    mounted = max(visible, key=lambda m: (len(m['point']), int(m['id'])))
    matching = [m for m in origins if mounted['device'] == m['device']
                and mounted['fs'] == m['fs']
                and _location(mounted, actual) == _location(m, expected)]
    if not matching:
        raise ValueError('stock-provenance-filesystem-lineage-mismatch')
    origin = max(matching, key=lambda m: (len(m['point']), int(m['id'])))
    return dict(device=origin['device'], filesystem=origin['fs'],
                filesystemPath=_location(origin, expected), originMountId=origin['id'],
                actualMountId=mounted['id'])


def resolve_stock_path(logical_path, actual_path, *, view_resolver=None):
    """Prove each alias inode and return the exact terminal path to open.

    A resolver only proposes paths. Every proposal must independently map to
    its logical target in a read-only ROM partition; data/overlay substitutes
    cannot pass. Absolute links are never opened through the live tree merely
    because their source alias was trusted.
    """
    logical = Path(logical_path)
    current = Path(os.path.abspath(actual_path))
    rows = _mounts()
    original = _prove_location(logical, current, rows)
    chain = []
    seen = set()
    for _ in range(41):
        key = (str(logical), str(current))
        if key in seen:
            raise ValueError('stock-provenance-alias-loop')
        seen.add(key)
        rows = _mounts()
        terminal_proof = _prove_location(logical, current, rows)
        alias = None
        parts = current.parts
        for count in range(1, len(parts)):
            prefix = Path(*parts[:count + 1])
            if prefix.is_symlink():
                suffix = parts[count + 1:]
                if len(suffix) >= len(logical.parts) - 1:
                    raise ValueError('stock-provenance-alias-link-unproven')
                logical_prefix = Path(*logical.parts[:len(logical.parts) - len(suffix)])
                _prove_location(logical_prefix, prefix, rows)
                alias = (prefix, logical_prefix, suffix)
                break
        if alias is None:
            if not current.exists():
                raise ValueError('stock-provenance-terminal-missing')
            try:
                boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
                namespace = os.readlink('/proc/self/ns/mnt')
            except OSError as exc:
                raise ValueError('stock-provenance-runtime-identity-missing') from exc
            return dict(original, schema='stock-view-proof-v1', verified=True,
                        bootId=boot, mountNamespace=namespace,
                        resolvedPath=str(current), resolvedLogicalPath=str(logical),
                        terminalProvenance=terminal_proof, aliasChain=chain)
        prefix, logical_prefix, suffix = alias
        target = Path(os.readlink(prefix))
        # Leading ../ segments can be normalized against an already-proven
        # directory. Embedded x/../ could cross another link: fail closed.
        named = False
        for part in target.parts:
            if part == '..' and named:
                raise ValueError('stock-provenance-alias-resolution-ambiguous')
            if part not in {'/', '.', '..'}:
                named = True
        target_logical = Path(os.path.abspath(
            (target if target.is_absolute() else logical_prefix.parent / target).joinpath(*suffix)))
        # Reject forbidden target namespaces before asking any resolver.
        if len(target_logical.parts) < 3 or target_logical.parts[1] in {'data', 'proc', 'sys', 'dev', 'tmp', 'mnt', 'sdcard', 'storage'}:
            raise ValueError('stock-provenance-alias-target-unproven: not-ROM')
        proposed = view_resolver(target_logical) if view_resolver is not None else ()
        if isinstance(proposed, (str, Path)):
            proposed = (proposed,)
        local = []
        if not target.is_absolute():
            local.append(Path(os.path.abspath((prefix.parent / target).joinpath(*suffix))))
        local.append(target_logical)
        candidates = itertools.chain(proposed or (), local)
        selected = None
        for candidate in candidates:
            candidate = Path(os.path.abspath(candidate))
            # A dangling absolute alias can still lead to a remappable ROM
            # target, so test the inode's existence without following it.
            if not candidate.exists() and not candidate.is_symlink():
                continue
            try:
                # A lazy resolver may have just created a request-owned bind.
                rows = _mounts()
                _prove_location(target_logical, candidate, rows)
            except (ValueError, OSError):
                continue
            selected = candidate
            break
        if selected is None:
            raise ValueError('stock-provenance-alias-target-unproven: no-proven-view')
        chain.append(dict(logicalPath=str(logical_prefix), actualPath=str(prefix),
                          targetLogicalPath=str(target_logical)))
        logical, current = target_logical, selected
    raise ValueError('stock-provenance-alias-loop')


def verify_stock_path(logical_path, actual_path):
    proof = resolve_stock_path(logical_path, actual_path)
    # Legacy callers open actual_path themselves. Do not claim it is safe if a
    # remapped view would be required to obtain the terminal we have proven.
    if str(Path(actual_path).resolve(strict=True)) != proof['resolvedPath']:
        raise ValueError('stock-provenance-alias-view-required')
    return proof


def stock_identity(logical_path, actual_path, face_index, build_key, *, provenance_path=None, view_resolver=None):
    digest = hashlib.sha256()
    with Path(actual_path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    try:
        proof_path = actual_path if provenance_path is None else provenance_path
        proof = (verify_stock_path(logical_path, proof_path) if view_resolver is None else
                 resolve_stock_path(logical_path, proof_path, view_resolver=view_resolver))
        if Path(proof["resolvedPath"]).resolve(strict=True) != Path(actual_path).resolve(strict=True):
            raise ValueError('stock-provenance-resolved-file-mismatch')
    except (ValueError, OSError) as exc:
        proof = dict(schema='stock-view-proof-v1', verified=False, reason=str(exc))
    return dict(captureRevision=STOCK_CAPTURE_REVISION, logicalPath=str(logical_path), faceIndex=int(face_index),
                sha256=digest.hexdigest(), buildKey=str(build_key), provenance=proof)
