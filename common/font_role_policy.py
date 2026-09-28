#!/usr/bin/env python3
"""Role protection for isolated staged fonts; never modifies a live ROM file.

Code monospace families retain their original faces. OEM clock/numeral fonts
such as MitypeMono are a distinct role, unless XML explicitly assigns them to
monospace. This module uses no subprocesses, watchers or background services.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re


def families(slot: dict | None) -> list[str]:
    values = (slot or {}).get('families', [])
    return [re.sub(r'[ _]+', '-', v.strip().lower()) for v in values
            if isinstance(v, str)] if isinstance(values, list) else []


def is_clock_slot(name: str, slot: dict | None = None) -> bool:
    label = ' '.join([name.lower(), *families(slot)])
    return any(word in label for word in ('clock', 'mitype', 'lockscreen', 'lock-screen', 'numeral'))


def code_name(name: str) -> bool:
    # Keep known code families case-insensitive; Monotype is a foundry, not mono.
    stem = re.sub(r'[-_ ]+', '', Path(name).stem.lower())
    roots = ('droidsansmono', 'notosansmono', 'notoserifmono', 'notomono',
             'robotomono', 'cutivemono', 'sourcecodepro', 'courier', 'consolas', 'monaco')
    if any(stem.startswith(root) for root in roots):
        return True
    # Split CamelCase before lowercasing: DroidSansMono is code, Monotype is not.
    words = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', '-', name)
    words = re.split(r'[^a-z0-9]+', words.lower())
    if name.lower().endswith(('mono', 'monovf', 'monospace')):
        return True
    return any(word in ('mono', 'monospace', 'monospaced', 'monovf', 'courier',
                        'consolas', 'monaco', 'sourcecode') for word in words)


def is_code_monospace(name: str, slot: dict | None = None) -> bool:
    names = families(slot)
    # An explicit code-family assignment wins even for an OEM clock filename.
    explicit = ('monospace', 'sans-serif-monospace', 'ui-monospace', 'serif-monospace',
                'roboto-mono', 'noto-mono', 'noto-sans-mono', 'noto-serif-mono',
                'droid-sans-mono', 'courier', 'monaco')
    if any(f == m or f.startswith(m + '-') for f in names for m in explicit):
        return True
    if is_clock_slot(name, slot):
        return False
    if any(code_name(f) for f in names) or code_name(Path(name).stem):
        return True
    # isFixedPitch describes spacing, not a code/terminal role. Explicit UI
    # families can have tabular digits or fixed-pitch faces without being code.
    if names:
        from font_config_overlay import is_safe_family
        if any(is_safe_family(f) for f in names):
            return False
    # Optional evidence captured from trusted stock; do not inspect the active
    # replacement under /system and mistake its metrics for original metrics.
    metrics = (slot or {}).get('metrics', {})
    return isinstance(metrics, dict) and metrics.get('isFixedPitch') is True


def slot_for(data: dict, logical: str) -> dict:
    indexed = data.get('slots', {})
    slot = indexed.get(logical, {}) if isinstance(indexed, dict) else {}
    return slot if isinstance(slot, dict) else {}


def assert_isolated(module: Path, stage: Path) -> None:
    live = (module / '.luoshu-payload').resolve()
    resolved = stage.resolve()
    if resolved == module.resolve() or resolved == live or live in resolved.parents:
        raise ValueError('拒绝修改本次启动正在使用的字体负载')
    for root in stage.glob('*/fonts'):
        if root.is_symlink() or not root.resolve().is_relative_to(resolved):
            raise ValueError('字体暂存目录包含指向外部的链接')


def protected_aliases(stage: Path, data: dict) -> list[Path]:
    result = []
    for root in sorted(stage.glob('*/fonts')):
        if not root.is_dir() or root.is_symlink():
            continue
        for path in sorted(root.iterdir()):
            if path.suffix.lower() not in ('.ttf', '.otf', '.ttc', '.otc'):
                continue
            logical = '/' + path.relative_to(stage).as_posix()
            if is_code_monospace(path.name, slot_for(data, logical)):
                result.append(path)
    return result


def record_preserved(stage: Path, logicals: list[str], replaced: list[str] | tuple[str, ...] = ()) -> list[str]:
    sidecar = stage / '.luoshu-stock-preserved.paths'
    existing = sidecar.read_text().splitlines() if sidecar.is_file() else []
    # Freshly generated UI slots override obsolete preservation decisions in an
    # old copied stage. Do not edit active payloads or unrelated exclusions.
    existing = [p for p in existing if p not in replaced]
    # This file is consumed by boot repair with grep -Fx, not evaluated as shell.
    paths = sorted({p for p in [*existing, *logicals]
                    if p.startswith('/') and '\n' not in p and '\r' not in p
                    and len(Path(p).parts) == 4 and Path(p).parts[2] == 'fonts'
                    and '..' not in Path(p).parts})
    temporary = sidecar.with_name(sidecar.name + f'.tmp.{os.getpid()}')
    try:
        temporary.write_text(''.join(p + '\n' for p in paths), encoding='utf-8')
        temporary.chmod(0o644)
        os.replace(temporary, sidecar)
    finally:
        temporary.unlink(missing_ok=True)
    return paths


def cleanup(module: Path, stage: Path) -> dict:
    assert_isolated(module, stage)
    if not stage.is_dir():
        raise ValueError('字体暂存目录不存在')
    try:
        data = json.loads((module / 'config/device_font_inventory.json').read_text())
        if not isinstance(data, dict) or data.get('state') != 'ready':
            data = {}
    except (OSError, ValueError):
        data = {}
    aliases = protected_aliases(stage, data)
    logicals = ['/' + p.relative_to(stage).as_posix() for p in aliases]
    # Write boot-repair exclusions first; a removed face must not be recreated
    # by the old missing-slot mapper on the following boot.
    paths = record_preserved(stage, logicals)
    for alias in aliases:
        alias.unlink(missing_ok=True)
    result = {'schema': 'luoshu-font-role-protection-v1',
              'removedStagedAliases': logicals, 'preservedStockPaths': paths}
    report = stage / '.luoshu-font-role-report.json'
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    report.chmod(0o644)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('module', type=Path)
    parser.add_argument('stage', type=Path)
    args = parser.parse_args()
    print(json.dumps(cleanup(args.module, args.stage), ensure_ascii=False))
