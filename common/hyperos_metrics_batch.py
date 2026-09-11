#!/usr/bin/env python3
"""Build HyperOS physical aliases in one process, without recompiling glyph outlines.

Only isolated staging trees may be passed here. Source anchors are pinned before any
alias is replaced, so neither iteration order nor a second partition changes inputs.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from fontTools.ttLib import TTFont
from font_metrics_normalize import _device_build_key, _pick_face, _promote_os2_for_typo_metrics
from font_slot_coverage import (is_han, is_cjk_routing_codepoint, remove_cjk_mappings,
                                preferred_unicode_codepoints, valid_coverage)

PARTS = ("system", "system_ext", "product", "mi_ext", "vendor", "odm", "oem",
         "my_product", "hw_product", "cust")


def weight_for_name(name: str) -> int:
    stem = Path(name).stem.lower()
    if stem.isdigit() and 100 <= int(stem) <= 900:
        return int(stem)
    for terms, weight in ((('extrabold', 'extra-bold'), 800),
                          (('semibold', 'semi-bold', 'demibold'), 600),
                          (('extralight', 'extra-light'), 200),
                          (('black', 'heavy'), 900), (('bold',), 700),
                          (('medium',), 500), (('light',), 300), (('thin',), 100)):
        if any(term in stem for term in terms):
            return weight
    return 400


def nonempty(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def pick_source(fonts: Path, name: str) -> Path:
    weight = weight_for_name(name)
    store = fonts / '.luoshu-font-store'
    # Numeric and exact aliases carry the actual multiweight selection. Do not
    # replace every weight with regular just because a regular anchor exists.
    candidates = (fonts / f'LuoShu-{weight}.ttf', store / f'wght-{weight}.font',
                  fonts / f'{weight}.ttf', fonts / name,
                  store / 'mix-composite.font', store / 'regular.font',
                  store / 'compact-regular.font', fonts / '400.ttf',
                  fonts / 'MiSansVF.ttf', fonts / 'Roboto-Regular.ttf')
    for path in candidates:
        if nonempty(path):
            return path
    raise ValueError(f'没有可用的源字体：{name}')


def read_inventory(module: Path) -> dict:
    try:
        data = json.loads((module / 'config/device_font_inventory.json').read_text())
        build = _device_build_key()
        if (data.get('schema') != 'device-font-inventory-v1' or
                data.get('state') != 'ready' or data.get('inventoryRevision') != 1 or
                (build and data.get('buildKey') != build)):
            return {}
        return data
    except (OSError, ValueError, AttributeError):
        return {}


def contract_for_slot(data: dict, logical: str) -> tuple:
    """Cache line metrics and the stock Skia top/bottom layout frame separately."""
    try:
        slot = (data.get('slots') or {}).get(logical, {})
        metrics = slot.get('metrics', {})
        upem = int(metrics['upem'])
        hhea = metrics['hhea']
        ascent, descent = int(hhea['ascent']), int(hhea['descent'])
        gap = int(hhea.get('lineGap', 0))
        if not (16 <= upem <= 16384 and 0 < ascent <= 32767 and
                -32768 <= descent <= 0 and 0 <= gap <= 32767):
            raise ValueError('invalid stock line metrics')
        os2 = metrics.get('os2', {})
        typo = (int(os2.get('typoAscender', ascent)),
                int(os2.get('typoDescender', descent)),
                int(os2.get('typoLineGap', gap)))
        win = (int(os2.get('winAscent', ascent)), int(os2.get('winDescent', -descent)))
        use_typo = bool(int(os2.get('fsSelection', 0)) & 128)
        if not (typo[0] > 0 and typo[1] <= 0 and typo[2] >= 0):
            if use_typo:
                raise ValueError('invalid stock typo metrics')
            typo = (ascent, descent, gap)
        values = (ascent, descent, gap, *typo, *win)
        if any(abs(v) > 4 * upem for v in values) or min(win) < 0:
            raise ValueError('invalid stock metrics')
        # Skia/FreeType reads SFNT head for top/bottom, independently of hhea
        # and OS/2. Old inventories have no head: retain their line contract,
        # but explicitly report that the padded layout frame remains unaligned.
        frame = None
        head = metrics.get('head', {})
        try:
            ymin, ymax = int(head['yMin']), int(head['yMax'])
            if -32768 <= ymin < ymax <= 32767 and ymax > 0:
                frame = (ymin, ymax)
        except (KeyError, TypeError, ValueError):
            pass
        return (upem, *values, use_typo, frame, 'stock')
    except (KeyError, TypeError, ValueError, ZeroDivisionError, AttributeError):
        # Older installations can lack a trustworthy inventory. Keep the known
        # compact fallback explicit in the report; never read the mounted overlay
        # as stock and never silently use an unnormalized raw font on errors.
        return (1000, 980, -300, 0, 980, -300, 0, 980, 350, True, None, 'fallback')


def write_metrics(source: Path, output: Path, contract: tuple,
                  cjk_fallback_codepoints: frozenset[int] | None = None,
                  stock_cjk_punctuation: frozenset[int] = frozenset()) -> dict:
    # lazy + recalcBBoxes=False retains glyf/CFF/gvar as raw tables. Loading glyph
    # bounds just to change hhea/OS2 used to recompile entire CJK fonts per slot.
    face = _pick_face(source)
    options = {'fontNumber': face} if face >= 0 else {}
    with source.open('rb') as stream, TTFont(
            stream, lazy=True, recalcBBoxes=False, recalcTimestamp=False, **options) as font:
        head, hhea, os2 = font['head'], font['hhea'], font['OS/2']
        upem = int(head.unitsPerEm)
        if not 16 <= upem <= 16384:
            raise ValueError('源字体 unitsPerEm 无效')
        scale = upem / contract[0]
        values = [round(v * scale) for v in contract[1:9]]
        if any(not -32768 <= v <= 32767 for v in values[:6]):
            raise ValueError('原厂度量超出源字体数值范围')
        if any(not 0 <= v <= 65535 for v in values[6:]):
            raise ValueError('原厂 Win 度量超出源字体数值范围')
        hhea.ascent, hhea.descent, hhea.lineGap = values[:3]
        _promote_os2_for_typo_metrics(os2)
        (os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap,
         os2.usWinAscent, os2.usWinDescent) = values[3:]
        os2.fsSelection = (os2.fsSelection & ~128) | (128 if contract[9] else 0)
        source_frame = (int(head.yMin), int(head.yMax))
        if contract[10] is not None:
            frame = tuple(round(v * scale) for v in contract[10])
            if not all(-32768 <= v <= 32767 for v in frame):
                raise ValueError('原厂上下边界超出源字体数值范围')
            # Android UI compatibility envelope, deliberately not a recomputed
            # outline union. Filling a small Clock/Roboto slot with a full CJK
            # font otherwise changes includeFontPadding and vertical centering.
            # The user's font and glyf/CFF/gvar remain untouched. Only staged
            # HyperOS aliases receive this envelope; old/no stock stays explicit.
            head.yMin, head.yMax = frame
        # MVAR can restore source line metrics at non-default variable weights.
        if 'MVAR' in font:
            del font['MVAR']
        removed = (remove_cjk_mappings(font, cjk_fallback_codepoints, stock_cjk_punctuation)
                   if cjk_fallback_codepoints else 0)
        # cmap glyph-name resolution can lazily load CFF to learn the glyph
        # order. Discard only those unmodified decoded tables so save copies
        # their original reader bytes instead of reserializing the outlines.
        for tag in ('glyf', 'CFF ', 'CFF2', 'gvar'):
            font.tables.pop(tag, None)
        font.save(output, reorderTables=False)
        report = {'sourceUpem': upem, 'sourceHead': list(source_frame),
                  'outputHead': [int(head.yMin), int(head.yMax)],
                  'layoutBoundsSource': 'stock' if contract[10] is not None else 'source',
                  'layoutBoundsDifferFromSource': source_frame != (head.yMin, head.yMax),
                  'removedCjkMappings': removed}
    os.chmod(output, 0o644)
    return report


def link_copy(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary = dest.with_name(dest.name + f'.tmp.{os.getpid()}')
    try:
        try:
            os.link(source, temporary)
        except OSError:
            shutil.copyfile(source, temporary)
        os.chmod(temporary, 0o644)
        os.replace(temporary, dest)
    finally:
        temporary.unlink(missing_ok=True)


def _specialized_slot(logical: str, slot: dict) -> bool:
    label = ' '.join([Path(logical).name, *slot.get('families', [])]).lower()
    return any(token in label for token in
               ('clock', 'mitype', 'mono', 'symbol', 'icon', 'emoji', 'math', 'music'))


def _latin_ui_slot(logical: str, slot: dict) -> bool:
    name = Path(logical).name.lower()
    families = [str(family).lower().replace('_', '-') for family in slot.get('families', [])]
    return (any(family.startswith(('sans-serif', 'system-ui', 'system-sans', 'roboto',
                                  'google-sans', 'misans', 'mi-sans', 'sys-sans', 'oppo-sans',
                                  'oplus-sans')) for family in families)
            or name.startswith(('roboto', 'misanslatin', 'googlesans', 'syssans', 'sysfont',
                                'sourcesanspro', 'opposans', 'oplussans', 'opsans')))


def _staged_cjk_fallback(data: dict, jobs: list, stage: Path) -> frozenset[int]:
    """Coverage proven to survive in generated, stock-Han UI fallback slots.

    These jobs will be written before any alias is switched. Never count a stock
    file outside staging or an unverified old inventory as a usable fallback.
    """
    points = set()
    seen = set()
    for source, dest, contract in jobs:
        logical = '/' + dest.relative_to(stage).as_posix()
        slot = (data.get('slots') or {}).get(logical, {})
        coverage = slot.get('metrics', {}).get('coverage')
        if (contract[-1] != 'stock' or not valid_coverage(coverage)
                or not coverage['hasHan'] or _specialized_slot(logical, slot)):
            continue
        # A private, named display family is not proof that sans-serif can
        # reach it. Count the scanner's selected system main face or the core
        # HyperOS CJK faces already covered by the OEM adapter.
        if (logical != data.get('mainSlotPath') and Path(logical).name not in
                {'MiSansVF.ttf', 'MiSansVF_Overlay.ttf', 'MiSansTCVF.ttf', 'MiSansL3.otf'}):
            continue
        stat = source.stat()
        key = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
        if key in seen:
            continue
        seen.add(key)
        face = _pick_face(source)
        options = {'fontNumber': face} if face >= 0 else {}
        with TTFont(source, lazy=True, recalcBBoxes=False, **options) as font:
            source_points = preferred_unicode_codepoints(font)
            if any(is_han(cp) for cp in source_points):
                points.update(cp for cp in source_points if is_cjk_routing_codepoint(cp))
    return frozenset(points)


def _cjk_routing(data: dict, logical: str, fallback: frozenset[int]) -> tuple:
    slot = (data.get('slots') or {}).get(logical, {})
    coverage = slot.get('metrics', {}).get('coverage')
    if not valid_coverage(coverage):
        return None, frozenset(), 'stock-coverage-refresh-pending'
    if _specialized_slot(logical, slot):
        return None, frozenset(), 'specialized-slot'
    if coverage['hasHan']:
        return None, frozenset(), 'stock-han-slot'
    if not coverage['hasLatin'] or not _latin_ui_slot(logical, slot):
        return None, frozenset(), 'not-latin-ui-slot'
    if not fallback:
        return None, frozenset(), 'no-staged-cjk-fallback'
    return fallback, frozenset(coverage['cjkPunctuation']), 'stock-latin-primary'


def build(module: Path, stage: Path, names: list[str]) -> dict:
    if stage.resolve() == (module / '.luoshu-payload').resolve():
        raise ValueError('拒绝修改本次启动正在使用的字体负载')
    fonts = stage / 'system/fonts'
    data = read_inventory(module)
    jobs = []
    for part in PARTS:
        root = Path(os.environ.get(f'LUOSHU_{part.upper()}_FONTS_ROOT', f'/{part}/fonts'))
        for name in dict.fromkeys(names):
            if Path(name).name != name or not name.endswith(('.ttf', '.otf')):
                raise ValueError(f'不安全的字体槽位：{name}')
            if (root / name).exists():
                logical = f'/{part}/fonts/{name}'
                jobs.append((pick_source(fonts, name), stage / part / 'fonts' / name,
                             contract_for_slot(data, logical)))
    if not jobs:
        raise ValueError('没有找到当前 ROM 的 HyperOS 字体目标')
    cjk_fallback = _staged_cjk_fallback(data, jobs, stage)
    store = fonts / '.luoshu-font-store'
    store.mkdir(parents=True, exist_ok=True)
    outputs = Path(tempfile.mkdtemp(prefix='hyperos-metrics-', dir=store))
    cache = {}
    output_reports = {}
    # Generate every distinct source/contract before replacing even one alias.
    # Thus subsequent sources cannot accidentally refer to earlier outputs.
    prepared = []
    slot_report = []
    fallback = 0
    try:
        for source, dest, contract in jobs:
            stat = source.stat()
            logical = '/' + dest.relative_to(stage).as_posix()
            routing, stock_punctuation, routing_reason = _cjk_routing(data, logical, cjk_fallback)
            if contract[-1] != 'stock':
                routing, stock_punctuation, routing_reason = None, frozenset(), 'invalid-stock-contract'
            key = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, contract,
                   routing, stock_punctuation)
            if key not in cache:
                output = outputs / f'{len(cache)}.font'
                output_reports[key] = write_metrics(source, output, contract, routing, stock_punctuation)
                cache[key] = output
            prepared.append((cache[key], dest))
            fallback += contract[-1] == 'fallback'
            slot_report.append({'slot': '/' + dest.relative_to(stage).as_posix(),
                                'metricsSource': contract[-1],
                                'referenceUpem': contract[0],
                                'hhea': list(contract[1:4]),
                                'typo': list(contract[4:7]),
                                'win': list(contract[7:9]),
                                'useTypoMetrics': contract[9],
                                'cjkRoutingSource': 'stock-fallback' if routing else 'source',
                                'cjkRoutingReason': routing_reason,
                                **output_reports[key]})
        for output, dest in prepared:
            link_copy(output, dest)
        report = stage / '.luoshu-metrics-report.json'
        report.write_text(json.dumps({'schema': 'luoshu-slot-metrics-v1',
                                      'slots': slot_report}, ensure_ascii=False), encoding='utf-8')
        report.chmod(0o644)
    except Exception:
        shutil.rmtree(outputs, ignore_errors=True)
        raise
    return {'mapped': len(jobs), 'generated': len(cache), 'fallbackSlots': fallback}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('module', type=Path)
    parser.add_argument('stage', type=Path)
    args = parser.parse_args()
    try:
        report = build(args.module, args.stage, sys.stdin.read().split())
        print(json.dumps(report, ensure_ascii=False))
        if report['fallbackSlots']:
            print(f"HyperOS：{report['fallbackSlots']} 个槽位缺少有效原厂度量，使用紧凑回退；可重新扫描原厂字体", file=sys.stderr)
        return 0
    except Exception as error:
        print(f'HyperOS 字体处理失败：{error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
