#!/usr/bin/env python3
"""Reject fake/truncated collections before the staged payload is published.

This validates structure and preserves the existing target's face count.
It neither rewrites fonts nor certifies
glyph coverage, metrics, variable axes, or an OEM's complete rendering contract.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile

SFNT = (b'\x00\x01\x00\x00', b'OTTO', b'true')
MAX_FACES = 256


def verify_build_report(path, relative, request, count):
    sidecar = path.with_name(path.name + '.luoshu-collection.json')
    if not sidecar.exists():
        return False  # Older stages have structural evidence only.
    with sidecar.open('rb') as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('集合生成证明过大')
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('集合生成证明包含重复字段')
            result[key] = value
        return result
    proof = json.loads(raw, object_pairs_hook=unique)
    if (not isinstance(proof, dict) or proof.get('schema') != 'composite-collection-build-v1'
            or proof.get('result') != 'PASS' or proof.get('requestId') != request
            or proof.get('target') != '/' + relative or proof.get('stockFaces') != count
            or not isinstance(proof.get('faces'), list) or len(proof['faces']) != count
            or any(not isinstance(face, dict) or face.get('index') != index
                   for index, face in enumerate(proof['faces']))):
        raise ValueError('集合生成证明与本次请求、路径或字体面索引不符')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    if proof.get('outputSha256') != digest.hexdigest():
        raise ValueError('集合字节与生成证明不符')
    return True


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


def validate(payload, request, stock_root=Path('/')):
    report = {'schema': 'composite-collection-contract-v1', 'requestId': request,
              'result': 'PASS', 'collections': [], 'errors': []}
    for path in sorted(payload.rglob('*')):
        if not path.is_file() or path.suffix.lower() not in ('.ttc', '.otc'):
            continue
        relative = path.relative_to(payload).as_posix()
        try:
            count = collection_faces(path)
            stock = stock_root / relative
            stock_count = collection_faces(stock) if os.path.lexists(stock) else None
            if stock_count is not None and count < stock_count:
                raise ValueError(f'字体集合缺少本机字体面：生成 {count}，原目标 {stock_count}')
            built = verify_build_report(path, relative, request, count)
            report['collections'].append({'path': relative, 'faces': count, 'stockFaces': stock_count,
                                          'generatedContractVerified': built})
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
    parser.add_argument('--stock-root', type=Path, default=Path('/'))
    args = parser.parse_args()
    if not args.payload.is_dir():
        raise SystemExit('复合字体暂存负载不存在')
    report = validate(args.payload, args.request, args.stock_root)
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
