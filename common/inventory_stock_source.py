#!/usr/bin/env python3
"""Resolve an original font for selective glyph replacement without reading overlays.

Old inventories can use captured stock lower/mirror views after metric validation.
A recorded actualPath or the currently mounted system path is never trusted without
an exact whole-file SHA256 produced by the original stock scan.
"""
from __future__ import annotations

from dataclasses import dataclass
import atexit
import hashlib
import os
from pathlib import Path
import re
import struct
from typing import Iterable

from fontTools.ttLib import TTFont
from font_slot_coverage import unicode_codepoints

_MUTABLE_PARTITIONS = {'data', 'data_mirror', 'sdcard', 'storage', 'mnt', 'proc',
                       'sys', 'dev', 'apex', 'tmp', 'metadata', 'cache', 'debug_ramdisk'}


class StockSourceError(RuntimeError):
    pass


def file_identity(path: Path) -> tuple[int, int, int, int, int]:
    info = path.stat()
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def codepoint_digest(points: Iterable[int]) -> str:
    digest = hashlib.sha256()
    for point in sorted(set(points)):
        digest.update(struct.pack('>I', point))
    return digest.hexdigest()


@dataclass(frozen=True)
class StockFont:
    path: Path
    face_index: int
    digest: str
    cmap_digest: str
    codepoints: frozenset[int]
    verified_by: str
    identity: tuple[int, int, int, int, int]

    def verify_unchanged(self) -> None:
        try:
            unchanged = file_identity(self.path) == self.identity
        except OSError:
            unchanged = False
        if not unchanged:
            raise StockSourceError('生成期间原厂字体来源发生变化')


@dataclass(frozen=True)
class _View:
    logical: Path
    actual: Path
    partition: str
    trust: str


def _safe_absolute(value: object) -> Path | None:
    if not isinstance(value, str) or not value.startswith('/'):
        return None
    if any(char in value for char in '\x00\r\n\t'):
        return None
    path = Path(value)
    if str(path) != value or '..' in path.parts:
        return None
    return path


def _plain_directory(path: Path, anchor: Path) -> bool:
    """A lower directory cannot be a symlink back into the mounted live tree."""
    try:
        relative = path.relative_to(anchor)
        current = anchor
        if current.is_symlink():
            return False
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                return False
        return path.is_dir()
    except (OSError, ValueError):
        return False


def _mirror_directory(path: Path, anchor: Path) -> bool:
    """Magisk mirrors may alias partitions within the same stock namespace."""
    try:
        return (not anchor.is_symlink() and path.resolve(strict=True).is_relative_to(anchor.resolve(strict=True))
                and path.is_dir())
    except (OSError, RuntimeError):
        return False


class StockSourceResolver:
    def __init__(self, module: Path, inventory: dict, *, state_root: Path | None = None,
                 mirrors: Iterable[Path] | None = None):
        import font_inventory as base
        self.module = Path(module)
        self.inventory = inventory
        self.state_root = state_root or Path(os.environ.get(
            'LUOSHU_SELF_MOUNT_STATE_ROOT', '/data/adb/luoshu/self-mount'))
        self.mirrors = tuple(Path(path) for path in (mirrors if mirrors is not None else base.MIRROR_PREFIXES))
        self.views: dict[Path, list[_View]] = {}
        self._profile_cache: dict[tuple, tuple[dict, str, frozenset[int]]] = {}
        self._cmap_cache: dict[tuple, dict] = {}
        self._range_cache: dict[tuple, frozenset[int]] = {}
        self._digest_cache: dict[tuple, str] = {}
        self._recovery_attempted = False
        self._snapshot_cleanup = None
        records = {}
        for partition, logical in base.LOGICAL_FONT_ROOTS:
            records[logical] = {'partition': partition, 'logical': str(logical)}
        for entry in [*inventory.get('sourceRoots', []), *inventory.get('auxiliaryRoots', []),
                      *inventory.get('discoveredFontRoots', [])]:
            if not isinstance(entry, dict):
                continue
            logical = _safe_absolute(entry.get('logical'))
            partition = str(entry.get('partition', ''))
            if (logical is None or len(logical.parts) < 3 or logical.parts[1] != partition
                    or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', partition)
                    or partition in _MUTABLE_PARTITIONS):
                continue
            records[logical] = {**records.get(logical, {}), **entry}
        for partition in inventory.get('discoveredPartitions', []):
            if (isinstance(partition, str)
                    and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', partition)
                    and partition not in _MUTABLE_PARTITIONS):
                logical = Path('/') / partition / 'fonts'
                records.setdefault(logical, {'partition': partition, 'logical': str(logical)})
        self.records = records
        for logical, record in records.items():
            partition = record['partition']
            relative = logical.relative_to(Path('/') / partition)
            if relative == Path('fonts'):
                key = f'{partition}-fonts'
            else:
                expected = hashlib.sha256(f'{partition}/{relative.as_posix()}'.encode()).hexdigest()[:16]
                key = f'{partition}-nested-{expected}'
            if record.get('mountKey', key) != key:
                continue
            options = []
            lower = self.state_root / 'lower' / key
            if _plain_directory(lower, self.state_root):
                options.append(_View(logical, lower, partition, 'stock-lower'))
            for mirror in self.mirrors:
                candidate = mirror / logical.relative_to('/')
                if _mirror_directory(candidate, mirror):
                    options.append(_View(logical, candidate, partition, 'stock-mirror'))
            actual = _safe_absolute(record.get('actual'))
            for candidate in (actual, logical):
                if candidate is not None and candidate.is_dir() and not any(view.actual == candidate for view in options):
                    options.append(_View(logical, candidate, partition, 'scan-sha256'))
            if options:
                self.views[logical] = options

    def close(self) -> None:
        if self._snapshot_cleanup is not None:
            cleanup = self._snapshot_cleanup
            self._snapshot_cleanup = None
            atexit.unregister(cleanup)
            cleanup()

    def _recover_stock_views(self) -> bool:
        """Recover expired installer snapshots in the current engine namespace.

        This is only a fallback after lower/mirror/scan-hash sources failed. The
        non-recursive parent bind excludes child font mounts, proves at least
        one child inode differs, and is kept until generation finishes. No font
        bytes are copied and no visible Android mount is changed.
        """
        if self._recovery_attempted:
            return False
        self._recovery_attempted = True
        import stock_inventory_scan as wrapper
        recovered = False
        for partition in dict.fromkeys(record['partition'] for record in self.records.values()):
            roots = [logical for logical, record in self.records.items() if record['partition'] == partition]
            candidates = wrapper._partition_logical_candidates(partition, Path('/') / partition)
            for candidate in candidates:
                snapshot = wrapper._bind_parent_stock_snapshot(candidate)
                if snapshot is None:
                    continue
                for logical in roots:
                    actual = snapshot / logical.relative_to(Path('/') / partition)
                    if actual.is_dir():
                        self.views.setdefault(logical, []).insert(0, _View(logical, actual, partition, 'stock-snapshot'))
                        recovered = True
                break
            if not any(view.trust == 'stock-snapshot' for logical in roots for view in self.views.get(logical, [])):
                for logical in roots:
                    snapshot = wrapper._bind_parent_stock_snapshot(logical)
                    if snapshot is not None:
                        self.views.setdefault(logical, []).insert(0, _View(logical, snapshot, partition, 'stock-snapshot'))
                        recovered = True
        if wrapper._INSTALL_SNAPSHOTS:
            self._snapshot_cleanup = wrapper._cleanup_install_snapshots
            atexit.register(self._snapshot_cleanup)
        return recovered

    def _archived_cmap(self, font: TTFont, target: dict, evidence: dict) -> dict | None:
        """Reuse scan-time character facts only after the entire SFNT hash matched.

        Android copies and metric aliases of a 65k-glyph CFF used to decode its
        charset again at each switch. The scanner archives a canonical range
        set; the full file SHA, raw cmap SHA and point digest bind that set to
        this exact face. Header metrics are still read from the current file.
        """
        import font_inventory as base
        from fontTools.unicodedata import category, script
        ranges = evidence.get('codepointRanges')
        if ranges is None:
            return None
        expected = target.get('metrics') or {}
        point_digest = evidence.get('codepointSha256')
        cmap_digest = hashlib.sha256(font.reader['cmap']).hexdigest()
        if (not isinstance(point_digest, str) or not re.fullmatch('[0-9a-f]{64}', point_digest)
                or expected.get('stockCodepointSha256') != point_digest
                or expected.get('stockCmapSha256') != cmap_digest
                or evidence.get('cmapSha256') != cmap_digest):
            raise StockSourceError('存档字体字符指纹与原厂文件不一致，请重新扫描')
        if not isinstance(ranges, list) or len(ranges) > 0x110000:
            raise StockSourceError('存档字体字符范围无效，请重新扫描')
        previous = -2
        canonical = []
        for pair in ranges:
            if (not isinstance(pair, list) or len(pair) != 2
                    or any(type(point) is not int for point in pair)
                    or not 0 <= pair[0] <= pair[1] <= 0x10FFFF
                    or pair[0] <= previous + 1):
                raise StockSourceError('存档字体字符范围无效，请重新扫描')
            canonical.append(tuple(pair))
            previous = pair[1]
        range_key = (point_digest, tuple(canonical))
        points = self._range_cache.get(range_key)
        if points is None:
            points = frozenset(point for start, end in canonical for point in range(start, end + 1))
            if codepoint_digest(points) != point_digest:
                raise StockSourceError('存档字体字符集合校验失败，请重新扫描')
            self._range_cache[range_key] = points
        key = ('archived', point_digest)
        facts = self._cmap_cache.get(key)
        if facts is None:
            scripts = {}
            for point in points:
                char = chr(point)
                if category(char).startswith('L'):
                    value = script(char)
                    scripts[value] = scripts.get(value, 0) + 1
            facts = {'points': points, 'letterScripts': scripts,
                     'codepointRanges': [list(pair) for pair in canonical],
                     'coverage': base.summarize_coverage(font, points=points),
                     'digitCount': sum(0x30 <= p <= 0x39 or 0xFF10 <= p <= 0xFF19 for p in points),
                     'privateUseCount': sum(category(chr(p)) == 'Co' for p in points),
                     'codepointSha256': point_digest}
            self._cmap_cache[key] = facts
        return {**facts, 'cmapSha256': cmap_digest}

    def _measure(self, path: Path, face_index: int, identity: tuple, *,
                 digest: str = '', target: dict | None = None,
                 evidence: dict | None = None) -> tuple[dict, str, frozenset[int]]:
        import font_inventory as base
        # A whole-file SHA was verified before reaching this method. Independent
        # copied aliases therefore share the same measurements as hardlinks.
        key = digest or identity, face_index
        if key not in self._profile_cache:
            with path.open('rb') as stream:
                collection = stream.read(4) == b'ttcf'
            options = {'fontNumber': face_index} if collection else {}
            if not collection and face_index != 0:
                raise StockSourceError('原厂字体面索引与库存不一致')
            with TTFont(path, lazy=True, recalcTimestamp=False, **options) as font:
                # A CFF cmap load also decodes its potentially 65k-entry
                # charset. Fonts differing only in line metrics share those
                # expensive character facts, while every header is still read
                # and checked against its own exact stock contract below.
                cmap = (self._archived_cmap(font, target, evidence)
                        if digest and target is not None and evidence and evidence.get('sha256') == digest
                        else None)
                if cmap is None:
                    signature = tuple((tag, hashlib.sha256(font.reader[tag]).digest())
                                      for tag in ('cmap', 'maxp', 'post', 'CFF ', 'CFF2') if tag in font)
                    cmap = self._cmap_cache.get(signature)
                    if cmap is None:
                        cmap = base._cmap_metrics(font)
                        self._cmap_cache[signature] = cmap
                _format, metrics = base._read_metrics_uncached(path, face_index, _font=font, _cmap=cmap)
                cmap_digest, points = cmap['cmapSha256'], cmap['points']
            self._profile_cache[key] = metrics, cmap_digest, points
        return self._profile_cache[key]

    @staticmethod
    def _check_metrics(expected: dict, measured: dict) -> None:
        # Compare every recorded stock field that can distinguish an overlaid
        # generated font; optional newer proofs do not invalidate legacy v9.
        if not isinstance(expected, dict):
            raise StockSourceError('原厂字体度量不是有效对象')
        for key in ('upem', 'head', 'hhea', 'os2', 'weightClass', 'coverage'):
            if key in expected and measured.get(key) != expected[key]:
                raise StockSourceError('原厂字体度量与扫描清单不一致：' + key)
        if not all(key in expected for key in ('upem', 'hhea', 'os2', 'coverage')):
            raise StockSourceError('旧清单缺少原厂字体身份验证所需的度量信息')
        if expected.get('stockCmapSha256') and measured.get('stockCmapSha256') != expected['stockCmapSha256']:
            raise StockSourceError('原厂字符映射指纹与扫描清单不一致')
        if (expected.get('stockCodepointSha256')
                and measured.get('stockCodepointSha256') != expected['stockCodepointSha256']):
            raise StockSourceError('原厂字符集合指纹与扫描清单不一致')

    def _namespaces(self, root: Path, option: _View):
        # An alias can cross partition boundaries. A stale captured lower in
        # that other partition must not hide a valid original mirror there.
        original = {key: options[0] for key, options in self.views.items()}
        original[root] = option
        yield original
        emitted = {tuple(original.values())}
        for tier in range(1, max(len(options) for options in self.views.values())):
            chosen = {key: options[min(tier, len(options) - 1)] for key, options in self.views.items()}
            chosen[root] = option
            identity = tuple(chosen.values())
            if identity not in emitted:
                emitted.add(identity)
                yield chosen
        for key, options in self.views.items():
            if key == root:
                continue
            for alternate in options[1:]:
                chosen = {**original, key: alternate}
                identity = tuple(chosen.values())
                if identity not in emitted:
                    emitted.add(identity)
                    yield chosen

    def resolve(self, logical: str, face: dict | None = None) -> StockFont:
        import font_inventory as base
        path = _safe_absolute(logical)
        slot = self.inventory.get('slots', {}).get(logical)
        if path is None or not isinstance(slot, dict):
            raise StockSourceError('原厂字体目标不在设备库存中')
        target = face or slot
        try:
            face_index = int(target.get('faceIndex', slot.get('faceIndex', 0)))
        except (ValueError, TypeError) as error:
            raise StockSourceError('原厂字体面索引无效') from error
        if not 0 <= face_index < 256:
            raise StockSourceError('原厂字体面索引越界')
        evidence = target.get('stockSource') or slot.get('stockSource') or {}
        if not isinstance(evidence, dict):
            raise StockSourceError('原厂来源指纹不是有效对象')
        wanted_digest = str(evidence.get('sha256', ''))
        if wanted_digest and not re.fullmatch('[0-9a-f]{64}', wanted_digest):
            raise StockSourceError('原厂文件指纹格式无效')
        roots = sorted((root for root in self.views if path.is_relative_to(root)), key=lambda root: len(root.parts), reverse=True)
        errors = []
        for root in roots:
            for option in self.views[root]:
                # A raw recorded/live path is unavailable to legacy inventories.
                if option.trust == 'scan-sha256' and not wanted_digest:
                    continue
                for chosen in self._namespaces(root, option):
                    try:
                        return self._resolve_candidate(base, path, root, option, chosen, target,
                                                       slot, face_index, wanted_digest, evidence)
                    except (StockSourceError, base.InventoryError, OSError, ValueError) as error:
                        errors.append(str(error))
        if self._recover_stock_views():
            return self.resolve(logical, face)
        detail = errors[-1] if errors else '没有可验证的原厂lower/mirror或匹配扫描SHA256的原厂文件'
        raise StockSourceError(f'无法取得原厂字体 {logical}：{detail}')

    def _resolve_candidate(self, base, path, root, option, chosen, target, slot,
                           face_index, wanted_digest, evidence):
        selected = [base.FontRoot(view.partition, view.logical, view.actual) for view in chosen.values()]
        selected_root = next(item for item in selected if item.logical == root)
        physical = base._stock_font_path(selected_root, option.actual / path.relative_to(root), selected)
        # Cross-partition symlinks may finish in another view. Its actual trust,
        # not the first alias directory, is decisive.
        final_views = [view for view in chosen.values()
                       if physical.is_relative_to(view.actual.resolve())]
        final_trust = next((view.trust for view in final_views if view.trust != 'scan-sha256'), 'scan-sha256')
        if final_trust == 'scan-sha256' and not wanted_digest:
            raise StockSourceError('原厂链接只能解析到缺少完整指纹的当前系统字体')
        identity = file_identity(physical)
        digest = self._digest_cache.get(identity)
        if digest is None:
            digest = file_digest(physical)
            self._digest_cache[identity] = digest
        if wanted_digest and digest != wanted_digest:
            raise StockSourceError('原厂文件SHA256与扫描清单不一致')
        measured, cmap_digest, points = self._measure(physical, face_index, identity,
            digest=digest, target=target, evidence=evidence)
        self._check_metrics(target.get('metrics') or slot.get('metrics') or {}, measured)
        if evidence.get('cmapSha256') and evidence['cmapSha256'] != cmap_digest:
            raise StockSourceError('原厂字体面cmap指纹不一致')
        answer = StockFont(physical, face_index, digest, cmap_digest, points, final_trust, identity)
        answer.verify_unchanged()
        return answer

    profile = resolve
