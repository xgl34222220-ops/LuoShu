#!/usr/bin/env python3
"""ROM 覆盖回归门禁：每个 ROM 夹具下"替换 / 保留原厂"的文件名单不得退化。

对 scripts/rom_coverage_baseline.json 中每个 ROM 夹具（只是文件名，不是真机清单），
在临时目录里按名字建出占位文件，调用模块真实的 shell 映射函数得到"会被替换"的文件：

* hyperos：common/legacy_v14_4/hyperos_full_coverage.sh 的 ``_lhcc_names_for_root``
  （其中的名单由 common/hyperos_physical_policy.py 生成，分组开关取默认值）加
  ``_lhcc_collection_names_for_root``（暂存时按本机字体面编译的 CJK 集合）；
* coloros：common/coloros_global.sh 的 ``get_all_coloros_files``（只计夹具中存在的文件）加
  ``coloros_collection_names_for_root``（暂存时由 coloros_metrics_batch 按本机字体面编译的 CJK 集合）；
* originos / flyme：common/origin_flyme_global.sh 的 ``luoshu_oem_slot_names_for_root``
  （ROM 专有精确槽位 + 名称规则，时钟/等宽/图标/Emoji 等保护规则同实机映射）。

规则（--check，CI 与 scripts/check.sh 使用）：

* 夹具中每个"保留原厂"的文件都必须在基线 ``keptStock`` 中登记非空理由，否则失败。
  所以任何文件从"替换"变为"保留原厂"都会失败，除非在基线里显式写明理由。
* ``legacyReplaced``（1bf06137 时替换过的文件，由 --write --legacy-ref 生成）必须
  仍被替换或已在 ``keptStock`` 登记理由。
* 新增替换（基线里是保留原厂、现在被替换）允许通过，只提示用 --write 更新基线。

--write 重新生成 ``replaced`` 并保留已有理由；新出现的保留项写入 ``TODO`` 理由，
--check 会把 TODO 视为未登记。只依赖标准库与 POSIX sh。
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / 'scripts/rom_coverage_baseline.json'
SCHEMA = 'rom-coverage-baseline-v1'

MAPPERS = {
    'hyperos': ('common/legacy_v14_4/hyperos_full_coverage.sh',
                '. "$1"; _lhcc_static_names() { :; }; _lhcc_names_for_root "$2"; '
                '_lhcc_collection_names_for_root "$2"'),
    'coloros': ('common/coloros_global.sh',
                '. "$1"; get_all_coloros_files; '
                '! type coloros_collection_names_for_root >/dev/null 2>&1 || '
                'coloros_collection_names_for_root "$2"'),
    'originos': ('common/origin_flyme_global.sh',
                 '. "$1"; luoshu_oem_slot_names_for_root originos "$2"'),
    'flyme': ('common/origin_flyme_global.sh',
              '. "$1"; luoshu_oem_slot_names_for_root flyme "$2"'),
}


def _clean_env(temp: Path, fonts: Path) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items()
           if not key.startswith('LUOSHU_')}
    for key in ('MODDIR', 'MODULE_DIR', 'PWD'):
        env[key] = str(temp / 'module')
    env['LUOSHU_REAL_MODDIR'] = str(temp / 'module')
    missing = str(temp / 'absent')
    env.update({
        'LUOSHU_COLOROS_SYSTEM_FONTS_ROOT': str(fonts),
        'LUOSHU_COLOROS_SYSTEM_EXT_FONTS_ROOT': missing,
        'LUOSHU_COLOROS_PRODUCT_FONTS_ROOT': missing,
    })
    return env


def replaced_names(rom: str, fixture: list[str], mapper_root: Path = ROOT,
                   script_path: Path | None = None,
                   extra_env: dict[str, str] | None = None) -> list[str]:
    """Run the ROM's real shell mapper over placeholder files named ``fixture``."""
    relative, script = MAPPERS[rom]
    shell = script_path or (mapper_root / relative)
    with tempfile.TemporaryDirectory() as raw:
        temp = Path(raw)
        fonts = temp / 'fonts'
        fonts.mkdir()
        (temp / 'module').mkdir()
        for name in fixture:
            (fonts / name).write_bytes(b'rom coverage fixture; not a font\n')
        env = _clean_env(temp, fonts)
        env.update(extra_env or {})
        proc = subprocess.run(['sh', '-c', script, 'sh', str(shell), str(fonts)],
                              cwd=temp, env=env, check=True,
                              text=True, capture_output=True, timeout=120)
    wanted = set(fixture)
    return sorted({line.strip() for line in proc.stdout.split() if line.strip() in wanted})


SLOT_COMPAT = 'common/coloros_slot_compat.sh'
# Slots the ColorOS slot compatibility mode must never write, whatever the switch says.
SLOT_COMPAT_PROTECTED = ('clock', 'mono', 'icon', 'emoji', 'symbol', 'serif', 'italic', 'myanmar')


def slot_compat_admitted(names: list[str], mapper_root: Path = ROOT) -> list[str]:
    """Names the slot compatibility mode would accept as OPlus slots."""
    if not names:
        return []
    script = '. "$1"; shift; for n in "$@"; do luoshu_coloros_slot_compat_slot_ok "$n" && printf "%s\\n" "$n"; done; :'
    with tempfile.TemporaryDirectory() as raw:
        env = {key: value for key, value in os.environ.items() if not key.startswith('LUOSHU_')}
        env['LUOSHU_REAL_MODDIR'] = str(Path(raw) / 'module')
        proc = subprocess.run(['sh', '-c', script, 'sh', str(mapper_root / SLOT_COMPAT), *names],
                              cwd=raw, env=env, check=True, text=True, capture_output=True, timeout=120)
    return sorted({line.strip() for line in proc.stdout.splitlines() if line.strip()})


def slot_compat_errors(fixture: list[str], mapper_root: Path = ROOT) -> list[str]:
    """The opt-in mode must not change overlay coverage nor admit protected slots."""
    errors: list[str] = []
    off = replaced_names('coloros', fixture, mapper_root)
    with tempfile.TemporaryDirectory() as raw:
        conf = Path(raw) / 'coloros_slot_compat.conf'
        conf.write_text('enabled=1\n', encoding='utf-8')
        on = replaced_names('coloros', fixture, mapper_root,
                            extra_env={'LUOSHU_COLOROS_SLOT_COMPAT_CONF': str(conf)})
    if on != off:
        errors.append('[coloros] 槽位兼容模式开启后改变了 /system 覆盖名单：'
                      f'新增 {sorted(set(on) - set(off))} 缺少 {sorted(set(off) - set(on))}')
    probes = list(fixture) + ['OplusOSUI-Mono-Regular.ttf', 'ColorOSUI-Clock-Regular.ttf',
                              'OplusOSUI-Icon.ttf', 'SysFont-Myanmar-Regular.ttf', 'OplusOSUI-Italic.ttf']
    for name in slot_compat_admitted(probes, mapper_root):
        if any(token in name.lower() for token in SLOT_COMPAT_PROTECTED):
            errors.append(f'[coloros] 槽位兼容模式会写入受保护槽位 {name}（时钟/等宽/图标等必须保持原厂）')
    return errors


def _reason_ok(reason: object) -> bool:
    return isinstance(reason, str) and bool(reason.strip()) and not reason.strip().upper().startswith('TODO')


def evaluate(rom: str, entry: dict, replaced: list[str]) -> tuple[list[str], list[str]]:
    """Return (errors, notes) for one ROM."""
    errors: list[str] = []
    notes: list[str] = []
    fixture = list(entry.get('fixture') or [])
    kept = dict(entry.get('keptStock') or {})
    now = set(replaced)
    before = set(entry.get('replaced') or [])
    legacy = set(entry.get('legacyReplaced') or [])
    for name in sorted(set(fixture) - now):
        if _reason_ok(kept.get(name)):
            continue
        if name in before:
            why = '基线中为"替换"'
        elif name in legacy:
            why = '1bf06137 时为"替换"'
        else:
            why = '未在基线登记'
        errors.append(
            f'[{rom}] {name} 现在保留原厂（{why}）。若属有意，请在 '
            f'scripts/rom_coverage_baseline.json 的 roms.{rom}.keptStock 中登记理由；否则修复映射。')
    for name in sorted(legacy - set(fixture)):
        errors.append(f'[{rom}] legacyReplaced 中的 {name} 不在夹具里，不能被核对。')
    for name in sorted(now - before):
        notes.append(f'[{rom}] 新增替换 {name}（允许）；可运行 --write 更新基线。')
    for name in sorted(now & set(kept)):
        notes.append(f'[{rom}] {name} 已被替换，keptStock 中的登记可以删除（--write）。')
    return errors, notes


def load(path: Path = BASELINE) -> dict:
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema') != SCHEMA:
        raise SystemExit(f'{path}: schema 应为 {SCHEMA}')
    return data


def check(path: Path = BASELINE) -> int:
    data = load(path)
    failed: list[str] = []
    for rom, entry in sorted(data['roms'].items()):
        if rom not in MAPPERS:
            failed.append(f'未知 ROM 夹具：{rom}')
            continue
        replaced = replaced_names(rom, list(entry['fixture']))
        errors, notes = evaluate(rom, entry, replaced)
        failed.extend(errors)
        for note in notes:
            print(note)
        print(f'[{rom}] 替换 {len(replaced)} / 夹具 {len(entry["fixture"])}')
        if rom == 'coloros':
            failed.extend(slot_compat_errors(list(entry['fixture'])))
    for line in failed:
        print('ERROR ' + line, file=sys.stderr)
    if failed:
        print('ROM 覆盖回归门禁失败：有文件从"替换"退化为"保留原厂"且未登记理由。', file=sys.stderr)
        return 1
    print('rom_coverage_gate: ok')
    return 0


def _legacy_replaced(rom: str, fixture: list[str], ref: str) -> list[str]:
    relative, _script = MAPPERS[rom]
    text = subprocess.run(['git', '-C', str(ROOT), 'show', f'{ref}:{relative}'],
                          check=True, capture_output=True, text=True).stdout
    with tempfile.TemporaryDirectory() as raw:
        shell = Path(raw) / Path(relative).name
        shell.write_text(text, encoding='utf-8')
        return replaced_names(rom, fixture, script_path=shell)


def write(path: Path = BASELINE, legacy_ref: str | None = None) -> int:
    data = load(path)
    for rom, entry in sorted(data['roms'].items()):
        fixture = sorted(dict.fromkeys(entry['fixture']))
        replaced = replaced_names(rom, fixture)
        old_kept = dict(entry.get('keptStock') or {})
        entry['fixture'] = fixture
        entry['replaced'] = replaced
        entry['keptStock'] = {name: old_kept.get(name, 'TODO: 登记保留原厂的理由')
                              for name in fixture if name not in replaced}
        if legacy_ref:
            entry['legacyRef'] = legacy_ref
            entry['legacyReplaced'] = _legacy_replaced(rom, fixture, legacy_ref)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'wrote {path}')
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n', 1)[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='default')
    mode.add_argument('--write', action='store_true')
    mode.add_argument('--print', action='store_true', help='print current replaced lists')
    parser.add_argument('--legacy-ref', help='with --write: also record legacyReplaced from this git ref')
    parser.add_argument('--baseline', type=Path, default=BASELINE)
    args = parser.parse_args(argv[1:])
    if args.write:
        return write(args.baseline, args.legacy_ref)
    if args.print:
        for rom, entry in sorted(load(args.baseline)['roms'].items()):
            replaced = replaced_names(rom, list(entry['fixture']))
            for name in entry['fixture']:
                print(f'{rom}\t{"REPLACE" if name in replaced else "STOCK"}\t{name}')
        return 0
    return check(args.baseline)


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
