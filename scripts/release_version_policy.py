#!/usr/bin/env python3
"""Release numbering only; runtime font behaviour is not changed.

The refactor series resets the display version, NEVER the Android upgrade code.
Its offset is fixed, not supplied by environment or untrusted metadata.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

REFACTOR_OFFSET = 50000


def version_info(version: str, series: str = '') -> dict:
    match = re.fullmatch(r'v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([A-Za-z0-9.-]+))?', version)
    if match is None:
        raise ValueError('版本号格式无效')
    major, minor, patch = map(int, match.group(1, 2, 3))
    suffix = match[4]
    if minor >= 100 or patch >= 100:
        raise ValueError('次版本与修订号必须小于 100，避免升级编号冲突')
    if series not in ('', 'legacy', 'refactor'):
        raise ValueError('未知发布系列')
    refactor = series == 'refactor'
    if refactor and (major < 1 or (minor, patch) not in ((0, 0), (major, major))):
        raise ValueError('重构版按 n.0.0 → n.n.n → (n+1).0.0 编号')
    code = (REFACTOR_OFFSET if refactor else 0) + major * 10000 + minor * 100 + patch
    if code <= 0 or code * 100 + 1 > 2100000000:
        raise ValueError('内部升级编号超出 Android 发布范围')
    canonical = 'v' + version.removeprefix('v')
    tag = ('refactor-' if refactor else '') + canonical
    next_stable = ''
    if refactor:
        next_stable = f'v{major}.{major}.{major}' if (minor, patch) == (0, 0) else f'v{major+1}.0.0'
    return {'version': canonical, 'series': series or 'legacy', 'versionCode': code,
            'appVersionCode': code * 100 + 1, 'tag': tag,
            'notesFile': f'RELEASE_NOTES_{tag}.md',
            'title': ('洛书·重构版 ' + canonical[1:] if refactor else '洛书 ' + canonical),
            'nextStable': next_stable, 'prerelease': suffix is not None}


def read_properties(path: Path) -> dict[str, str]:
    data = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        if key in data:
            raise ValueError('版本属性重复：' + key)
        data[key] = value.strip()
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--module', type=Path, default=Path('module.prop'))
    parser.add_argument('--field', choices=('versionCode', 'tag', 'notesFile', 'title', 'nextStable'))
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        props = read_properties(args.module)
        info = version_info(props['version'], props.get('versionSeries', ''))
        if args.check and int(props['versionCode']) != info['versionCode']:
            raise ValueError(f"versionCode 应为 {info['versionCode']}，实际为 {props['versionCode']}")
        print(info[args.field] if args.field else json.dumps(info, ensure_ascii=False))
        return 0
    except (OSError, KeyError, ValueError) as error:
        parser.exit(2, str(error) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
