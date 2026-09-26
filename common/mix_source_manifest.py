#!/usr/bin/env python3
"""Record real per-role weights without relabeling a composite's SFNT metadata."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct

SCHEMA = 'luoshu-mix-source-weights-v1'


def source_weight(path: Path) -> int:
    # Prepared inputs are single, instantiated SFNT faces. Read only the directory
    # and OS/2 prefix, so a large CFF or glyf table is never loaded or compiled.
    with path.open('rb') as stream:
        header = stream.read(12)
        if len(header) != 12 or header[:4] not in (b'\0\1\0\0', b'OTTO', b'true'):
            raise ValueError(f'{path.name}: prepared source is not a single SFNT face')
        count = struct.unpack_from('>H', header, 4)[0]
        if not 0 < count <= 4096:
            raise ValueError(f'{path.name}: invalid table count')
        for _ in range(count):
            record = stream.read(16)
            if len(record) != 16:
                raise ValueError(f'{path.name}: truncated table directory')
            tag, _, offset, length = struct.unpack('>4sIII', record)
            if tag == b'OS/2':
                if length < 6:
                    raise ValueError(f'{path.name}: truncated OS/2 table')
                stream.seek(offset)
                prefix = stream.read(6)
                if len(prefix) != 6:
                    raise ValueError(f'{path.name}: truncated OS/2 data')
                weight = struct.unpack_from('>H', prefix, 4)[0]
                if not 1 <= weight <= 1000:
                    raise ValueError(f'{path.name}: invalid source weight')
                return weight
    raise ValueError(f'{path.name}: prepared source has no OS/2 weight')


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--anchor', required=True)
    parser.add_argument('--composite', type=Path, required=True)
    parser.add_argument('--target-weight', type=int, default=400)
    for role in ('cjk', 'latin', 'digit'):
        parser.add_argument(f'--{role}', type=Path, required=True)
        parser.add_argument(f'--{role}-mode', choices=('fixed', 'auto'), default='fixed')
        parser.add_argument(f'--{role}-axes', default='')
    args = parser.parse_args()
    if Path(args.anchor).name != args.anchor or not args.anchor.endswith('.font'):
        parser.error('anchor must be one store-local .font name')
    request = os.environ.get('LUOSHU_MIX_REQUEST_ID', '')
    data = {'schema': SCHEMA, 'requestId': request, 'sources': {}}
    if args.manifest.exists():
        data = json.loads(args.manifest.read_text())
        if data.get('schema') != SCHEMA or data.get('requestId') != request:
            raise ValueError('mix source manifest belongs to a different request')
    entry = {'targetWeight': args.target_weight, 'digest': digest(args.composite)}
    for role in ('cjk', 'latin', 'digit'):
        entry[role + 'Weight'] = source_weight(getattr(args, role))
        entry[role + 'Mode'] = getattr(args, role + '_mode')
        entry[role + 'Axes'] = getattr(args, role + '_axes')
    data['sources'][args.anchor] = entry
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.manifest.with_name(args.manifest.name + f'.tmp.{os.getpid()}')
    temporary.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True) + '\n')
    os.replace(temporary, args.manifest)


if __name__ == '__main__':
    main()
