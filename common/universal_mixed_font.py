#!/usr/bin/env python3
"""Freeze generated composite sources for Universal; never reads user font libraries.

The composition workers already resolved each role's axes and fixed/auto choice.
This bridge only accepts their current request's generated output inside cache.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
import re
from pathlib import Path
import shutil
import tempfile


def conf(path: Path) -> dict[str, str]:
    return dict(line.split('=', 1) for line in path.read_text().splitlines() if '=' in line)


def current(module: Path, request: str) -> dict[str, str]:
    state = conf(module / 'config/mix-stage-next.conf')
    if not request or '/' in request or '\\' in request or state.get('requestId') != request or state.get('state') == 'cancelled' or (module / 'config/mix-cancelled-requests' / request).is_file():
        raise ValueError('composite request was superseded')
    return state


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


FIXED_SELECTION_POLICY = 'fixed-composite-selection-v1'
ROLES = ('cjk', 'latin', 'digit')


def selected_axes(spec: str) -> dict[str, float]:
    result = {}
    for item in spec.split(','):
        if not item.strip():
            continue
        if '=' not in item:
            raise ValueError('invalid fixed component axis selection')
        tag, value = (part.strip() for part in item.split('=', 1))
        if not re.fullmatch(r'[ -~]{4}', tag) or tag in result:
            raise ValueError('invalid or duplicate fixed component axis: ' + tag)
        number = float(value)
        if not math.isfinite(number):
            raise ValueError('non-finite fixed component axis: ' + tag)
        result[tag] = number
    return result


def fixed_roles(module: Path, request: str, state: dict[str, str], generation: dict[str, str]) -> dict:
    """Record intent separately from any verified component axis location.

    The static copy path does not emit instance reports. In that case a
    generation hash binds the chosen composite content, but cannot prove that
    a selected weight was an actual variable-axis coordinate.
    """
    task_path = module / 'config/axes_task.conf'
    task = conf(task_path) if task_path.is_file() else {}
    root = None
    if task.get('requestId') == request:
        if any(task.get(key, '') != state.get(key, '') for key in
               ('cjk', 'latin', 'digit', 'cjkAxes', 'latinAxes', 'digitAxes')):
            raise ValueError('fixed component request identity mismatch')
        root = Path(task.get('root', '')).resolve(strict=True)
        root.relative_to((module / 'cache').resolve())
    result = {}
    for role, internal in zip(ROLES, ('LuoShuMixCJK', 'LuoShuMixLatin', 'LuoShuMixDigit')):
        if state.get(role + 'Mode', 'fixed') != 'fixed':
            raise ValueError('fixed selection contains an auto component: ' + role)
        axes = selected_axes(state.get(role + 'Axes', ''))
        entry = {'mode': 'fixed', 'selectedAxes': axes,
                 'family': state.get(role, ''), 'effectiveAxes': {},
                 'axisProvenance': 'generation-hash-only'}
        component = root / 'fonts' / (internal + '-Regular.ttf') if root is not None else None
        report_path = Path(str(component) + '.json') if component is not None else None
        if component is not None and component.is_file():
            component.resolve(strict=True).relative_to(root)
            component_hash = digest(component)
            if generation.get(role + 'Hash') and generation[role + 'Hash'] != component_hash:
                raise ValueError('fixed component generation hash mismatch: ' + role)
            from fontTools.ttLib import TTFont
            with TTFont(component, lazy=True, recalcTimestamp=False) as prepared:
                if 'fvar' in prepared:
                    raise ValueError('fixed component was not fully instanced: ' + role)
                if 'OS/2' in prepared:
                    entry['componentWeightClass'] = int(prepared['OS/2'].usWeightClass)
            entry['componentSha256'] = component_hash
            if report_path is not None and not report_path.is_file():
                if any(tag != 'wght' for tag in axes):
                    raise ValueError('static fixed component cannot satisfy selected axes: ' + role)
                entry['axisProvenance'] = 'static-component'
        if report_path is not None and report_path.is_file():
            if not generation.get(role + 'Hash'):
                raise ValueError('fixed component generation hash missing: ' + role)
            instance = json.loads(report_path.read_text())
            if not isinstance(instance, dict) or instance.get('status') != 'ok' or instance.get('role') != role:
                raise ValueError('invalid fixed component axis report: ' + role)
            if not component.is_file() or Path(str(instance.get('output', ''))).resolve() != component.resolve():
                raise ValueError('fixed component report output mismatch: ' + role)
            component.resolve(strict=True).relative_to(root)
            if instance.get('size') != component.stat().st_size:
                raise ValueError('fixed component report size mismatch: ' + role)
            if instance.get('ignoredAxes'):
                raise ValueError('unsupported selected fixed component axis: ' + role)
            if type(instance.get('variable')) is not bool:
                raise ValueError('invalid fixed component variable status: ' + role)
            location = instance.get('location')
            if not isinstance(location, dict):
                raise ValueError('invalid fixed component axis location: ' + role)
            if instance['variable']:
                for tag, wanted in axes.items():
                    actual = location.get(tag)
                    if isinstance(actual, bool) or not isinstance(actual, (int, float)) or not math.isfinite(actual) or float(actual) != wanted:
                        raise ValueError('fixed component axis range does not cover selection: ' + role + ':' + tag)
                entry['effectiveAxes'] = dict(location)
                entry['axisProvenance'] = 'verified-instance-report'
            else:
                if location or any(tag != 'wght' for tag in axes):
                    raise ValueError('static fixed component cannot satisfy selected axes: ' + role)
                entry['axisProvenance'] = 'static-instance-report'
            entry['componentSha256'] = digest(component)
            entry['instanceReportSha256'] = digest(report_path)
        result[role] = entry
    return result


def freeze(module: Path, request: str, mode: str, source: Path) -> Path:
    module = module.resolve()
    state = current(module, request)
    source = source.resolve(strict=True)
    source.relative_to((module / 'cache').resolve())
    if mode == 'fixed':
        generation = conf(module / '.luoshu-mix-stage/.luoshu-mix-generation.conf')
        if generation.get('requestId') != request or any(generation.get(k) != state.get(k) for k in ('cjk', 'latin', 'digit')):
            raise ValueError('composite generation identity mismatch')
        if generation.get('compositeHash') != digest(source):
            raise ValueError('composite generation hash mismatch')
        role_selection = fixed_roles(module, request, state, generation)
        files = [source]
    else:
        task = conf(module / 'config/axes_task.conf')
        if Path(task.get('root', '')).resolve() != source:
            raise ValueError('multiweight root does not belong to current worker')
        if any(task.get(k) != state.get(k) for k in ('cjk', 'latin', 'digit', 'cjkAxes', 'latinAxes', 'digitAxes')):
            raise ValueError('multiweight request identity mismatch')
        files = sorted((source / 'fonts').glob('LuoShuAutoMix-*'))
        if len(files) != 9 or any(p.suffix.lower() not in {'.ttf', '.otf'} for p in files):
            raise ValueError('incomplete multiweight generated family')
        for path in files:
            path.resolve(strict=True).relative_to((module / 'cache').resolve())
    hashes = {p.name: digest(p) for p in files}
    identity = hashlib.sha256(json.dumps([request, state, hashes], sort_keys=True).encode()).hexdigest()
    parent = module / 'cache/universal-mixed-sources'
    parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.stage-', dir=parent))
    # Never overwrite sources referenced by an earlier frozen plan.
    destination = parent / (identity + '-' + stage.name.removeprefix('.stage-'))
    try:
        fonts = stage / 'fonts'
        fonts.mkdir()
        for p in files:
            name = 'LuoShuMix-Regular' + p.suffix if mode == 'fixed' else p.name.replace('LuoShuAutoMix-', 'LuoShuMix-')
            shutil.copyfile(p, fonts / name)
            if digest(fonts / name) != hashes[p.name]:
                raise ValueError('source changed during composite freeze')
        report = {'schema': 'universal-mixed-source-v1', 'requestId': request, 'mode': mode, 'selection': state, 'sourceHashes': hashes}
        if mode == 'fixed':
            report['mixedSelection'] = {
                'policy': FIXED_SELECTION_POLICY, 'requestId': request,
                'roles': role_selection,
                'fontPath': 'fonts/' + next(fonts.iterdir()).name,
                'fontSha256': hashes[source.name],
            }
        if mode == 'auto':
            report['axisProvenance'] = {str(p.relative_to(source / 'axis-provenance')): json.loads(p.read_text()) for p in (source / 'axis-provenance').glob('*/*.json')}
            from universal_mixed_variable import build_variable_family, discover_masters
            try:
                expected = {f'{weight}/{role}.ttf.instance.json' for weight in range(100, 901, 100) for role in ('cjk', 'latin', 'digit')}
                if set(report['axisProvenance']) != expected:
                    raise ValueError('missing component axis provenance')
                for key, instance in report['axisProvenance'].items():
                    weight = int(key.split('/')[0])
                    role = str(instance.get('role', ''))
                    if key.split('/')[1] != role + '.ttf.instance.json':
                        raise ValueError('component axis provenance role mismatch: ' + key)
                    if instance.get('ignoredAxes'):
                        raise ValueError('unsupported selected component axis: ' + key)
                    if instance.get('variable'):
                        selected = dict(entry.split('=', 1) for entry in task.get(role + 'Axes', '').split(',') if entry)
                        if task.get(role + 'Mode') == 'auto':
                            selected['wght'] = str(weight)
                        for tag, raw in selected.items():
                            wanted = float(raw)
                            actual = instance.get('location', {}).get(tag)
                            if not math.isfinite(wanted) or actual is None or float(actual) != wanted:
                                raise ValueError('component axis range does not cover selection: ' + key + ':' + tag)
                # Builder consumes legacy names; use the original validated copied masters.
                masters = discover_masters(fonts, family='LuoShuMix')
                variable = stage / 'variable.ttf'
                report['variable'] = build_variable_family(masters, variable)
                report['variable']['output'] = 'fonts/LuoShuMix-Regular.ttf'
                report['variable'].pop('path', None)
                # Prefer the actual variable source for every route. Static masters may
                # intentionally carry the fixed CJK base's weight metadata.
                for p in list(fonts.iterdir()):
                    p.unlink()
                os.replace(variable, fonts / 'LuoShuMix-Regular.ttf')
            except Exception as error:
                report['variableError'] = str(error)
                (stage / 'variable.ttf').unlink(missing_ok=True)
        (stage / 'source.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        current(module, request)
        os.replace(stage, destination)
        return destination
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--module', required=True, type=Path)
    p.add_argument('--request', required=True)
    p.add_argument('--mode', choices=['fixed', 'auto'])
    p.add_argument('--source', type=Path)
    p.add_argument('--check', action='store_true')
    args = p.parse_args()
    try:
        if args.check:
            current(args.module, args.request)
        else:
            if not args.mode or args.source is None:
                raise ValueError('mode/source required')
            print(freeze(args.module, args.request, args.mode, args.source))
        return 0
    except Exception as error:
        import sys
        print(str(error), file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
