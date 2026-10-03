#!/usr/bin/env python3
"""Reject fake/truncated collections before the staged payload is published.

This validates container structure only. It neither rewrites fonts nor certifies
glyph coverage, metrics, variable axes, or an OEM's complete rendering contract.
"""
import argparse
import json
import os
from pathlib import Path
import struct
import tempfile

SFNT = (b'\x00\x01\x00\x00', b'OTTO', b'true')
MAX_FACES = 256


def collection_faces(path):
    size = path.stat().st_size
    with path.open('rb') as stream:
        head = stream.read(12)
        if len(head) != 12 or head[:4] != b'ttcf':
            raise ValueError('TTC/OTC 路径被单字体或损坏文件覆盖')
        version, count = struct.unpack('>II', head[4:])
        if version not in (0x10000, 0x20000) or not 1 <= count <= MAX_FACES:
            raise ValueError('字体集合版本或字体面数量无效')
        offsets = stream.read(4 * count)
        if len(offsets) != 4 * count:
            raise ValueError('字体集合索引被截断')
        header_size = 12 + 4 * count + (12 if version == 0x20000 else 0)
        if size < header_size:
            raise ValueError('字体集合头被截断')
        for offset in struct.unpack('>' + 'I' * count, offsets):
            if offset < header_size or offset > size - 12:
                raise ValueError('字体集合索引越界')
            stream.seek(offset)
            face = stream.read(12)
            if face[:4] not in SFNT:
                raise ValueError('字体集合包含无效字体面')
            tables = struct.unpack('>H', face[4:6])[0]
            if not 1 <= tables <= 4096 or offset + 12 + tables * 16 > size:
                raise ValueError('字体集合表目录无效')
            directory = stream.read(tables * 16)
            for index in range(tables):
                _, _, start, length = struct.unpack('>4sIII', directory[index * 16:(index + 1) * 16])
                if start > size or length > size - start:
                    raise ValueError('字体集合数据表越界')
    return count


def validate(payload, request):
    report = {'schema': 'composite-collection-contract-v1', 'requestId': request,
              'result': 'PASS', 'collections': [], 'errors': []}
    for path in sorted(payload.rglob('*')):
        if not path.is_file() or path.suffix.lower() not in ('.ttc', '.otc'):
            continue
        relative = path.relative_to(payload).as_posix()
        try:
            count = collection_faces(path)
            report['collections'].append({'path': relative, 'faces': count})
        except (OSError, ValueError, struct.error) as error:
            report['errors'].append({'path': relative, 'reason': str(error)})
    if report['errors']:
        report['result'] = 'FAIL'
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--request', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.payload.is_dir():
        raise SystemExit('复合字体暂存负载不存在')
    report = validate(args.payload, args.request)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.composite-contract.', dir=args.output.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, args.output)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    if report['result'] != 'PASS':
        for error in report['errors']:
            print('[MIX] 集合格式核查失败：' + error['path'] + '：' + error['reason'], flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
