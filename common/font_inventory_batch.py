#!/usr/bin/env python3
"""Bounded, stdlib-only user-font index. No outline parsing, shell forks or mounts.

v5 fingerprints cover font identities AND family configuration. `preview` is a
real stat/config snapshot with valid=false; only a completed scan is actionable.
"""
import argparse
from collections import OrderedDict
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import time

EXTENSIONS = ('.ttf', '.otf', '.ttc', '.TTF', '.OTF', '.TTC')
SUFFIXES = ('Regular', 'ExtraBold', 'UltraBold', 'ExtraLight', 'UltraLight', 'Bold',
            'Light', 'Medium', 'SemiBold', 'Thin', 'Black', 'Heavy', 'Italic',
            'Oblique', 'Condensed', 'Extended')
FAMILY_SUFFIXES = SUFFIXES + tuple(s.lower() for s in SUFFIXES) + (
    '常规', '粗体', '细体', '中等', '半粗', '极细', '特粗', '重', '斜体', '轻')
WEIGHTS = ('variable', 'thin', 'extralight', 'light', 'regular', 'medium',
           'semibold', 'bold', 'extrabold', 'black')
PREFERRED = ('regular', 'medium', 'bold', 'semibold', 'variable', 'light',
             'extralight', 'thin', 'extrabold', 'black')
MAGIC = {b'\x00\x01\x00\x00': 'TTF', b'true': 'TTF', b'\x00\x02\x00\x00': 'TTF',
         b'OTTO': 'OTF', b'ttcf': 'TTC', b'wOFF': 'WOFF', b'wOF2': 'WOFF2',
         b'PK\x03\x04': 'ZIP'}
PROTOCOL = 'font-list-v5'
MAX_CACHE_BYTES = 4 * 1024 * 1024
MAX_CONFIG_BYTES = 64 * 1024


def family_of(name):
    family = name.rsplit('.', 1)[0]
    # Preserve the shell's ordered single pass; Foo-Black-Italic != Foo-Italic-Black.
    for suffix in FAMILY_SUFFIXES:
        if family.endswith('-' + suffix):
            family = family[:-len(suffix) - 1]
    return family.rstrip(' \t\r\n\v\f-_')


def weight_of(name):
    lower = name.lower()
    groups = (
        ('variable', ('variable', 'var', '可变', 'vf')),
        ('thin', ('thin', '-100.', '_100.', '极细')),
        ('extralight', ('extralight', 'ultralight', 'extra-light', 'ultra-light', '-200.', '_200.')),
        ('light', ('light', '-300.', '_300.', '细体')),
        ('medium', ('medium', '-500.', '_500.', '中等')),
        ('semibold', ('semibold', 'demibold', '-600.', '_600.', '半粗')),
        ('extrabold', ('extrabold', 'ultrabold', 'extra-bold', 'ultra-bold', '-800.', '_800.')),
        ('bold', ('bold', '-700.', '_700.', '粗体')),
        ('black', ('black', 'heavy', '-900.', '_900.', '特粗', '重体')),
    )
    return next((weight for weight, patterns in groups if any(p in lower for p in patterns)), 'regular')


def size_label(size):
    if size < 1024:
        return f'{size} B'
    if size < 1048576:
        return f'{size // 1024} KB'
    if size < 1073741824:
        return f'{size // 1048576}.{(size % 1048576) // 104857} MB'
    return f'{size // 1073741824}.{(size % 1073741824) // 107374182} GB'


def clean_display(value):
    # Match existing CR/LF display escaping while JSON itself safely escapes tabs/quotes.
    return value.replace('\r', ' ').replace('\n', ' ')


def identity(info):
    return [info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def readable_directory(path):
    if not path.is_dir() or not os.access(path, os.R_OK | os.X_OK):
        raise PermissionError('字体目录暂不可读')
    # Reading with scandir must succeed even for a legitimate empty library.
    return list(os.scandir(path))


def snapshot(font_dir):
    entries = readable_directory(font_dir)
    by_name = {entry.name: entry for entry in entries}
    files = []
    fingerprints = []
    families = OrderedDict()
    for extension in EXTENSIONS:
        names = sorted((name for name in by_name if not name.startswith('.') and name.endswith(extension)), key=os.fsencode)
        for name in names:
            entry = by_name[name]
            if not entry.is_file(follow_symlinks=True):
                continue
            family = family_of(name)
            if not family or family.startswith(('SysFont', 'SysSans')) or '|' in name or '|' in family:
                continue
            info = entry.stat(follow_symlinks=False)
            target = entry.stat(follow_symlinks=True)
            fingerprints.append(['font', name, identity(info), identity(target)])
            record = {'name': name, 'family': family, 'weight': weight_of(name), 'stat': info}
            files.append(record)
            families.setdefault(family, []).append(record)
    configs = {}
    for family in families:
        name = family + '.conf'
        entry = by_name.get(name)
        if entry is None or not entry.is_file(follow_symlinks=True):
            continue
        info = entry.stat(follow_symlinks=False)
        target = entry.stat(follow_symlinks=True)
        fingerprints.append(['config', name, identity(info), identity(target)])
        configs[family] = font_dir / name
    encoded = json.dumps(fingerprints, ensure_ascii=True, separators=(',', ':')).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    total = sum(row['stat'].st_size for row in files)
    return families, configs, f'{PROTOCOL}:{digest}:{len(files)}:{total}', total


def config_values(path):
    if path is None:
        return {}
    values = {}
    # Bound even an abnormal single line, while retaining first-key/CR semantics.
    with path.open('rb') as stream:
        raw = stream.read(MAX_CONFIG_BYTES + 1)
    if len(raw) > MAX_CONFIG_BYTES:
        raise ValueError('字体配置超过 64 KiB 限制')
    for line in raw.decode('utf-8', errors='replace').split('\n'):
        if '=' in line:
            key, value = line.split('=', 1)
            if key in ('name', 'supports_cjk') and key not in values:
                values[key] = value
    return values


def current_font(config_dir):
    try:
        with (config_dir / 'active_font.conf').open('r', encoding='utf-8', errors='replace') as stream:
            return stream.readline().replace('\r', '').replace('\n', '') or 'default'
    except FileNotFoundError:
        return 'default'


def inventory(font_dir, config_dir, *, preview=False, captured=None):
    families, configs, fingerprint, total = captured or snapshot(font_dir)
    fonts = []
    for family, records in families.items():
        variants = {}
        for row in records:
            variants.setdefault(row['weight'], row['name'])
        weights = [weight for weight in WEIGHTS if weight in variants]
        representative = min(records, key=lambda row: PREFERRED.index(row['weight']))
        info = representative['stat']
        config = config_values(configs.get(family))
        variable = 'variable' in weights
        if preview:
            form = Path(representative['name']).suffix[1:].upper()
            valid, error = False, '等待字体核查'
        else:
            with (font_dir / representative['name']).open('rb') as stream:
                form = MAGIC.get(stream.read(4), 'UNKNOWN')
            valid = info.st_size >= 4096 and form != 'UNKNOWN'
            error = ('字体文件过小' if info.st_size < 4096 else '字体格式无法识别') if not valid else ''
        fonts.append({
            'id': family, 'name': clean_display(config.get('name') or family), 'weights': weights,
            'variants': {weight: variants[weight] for weight in weights},
            'familyType': 'variable' if variable else ('static-family' if len(weights) >= 2 else 'single'),
            'file': representative['name'], 'size': size_label(info.st_size), 'bytes': info.st_size,
            'format': form, 'valid': valid, 'warning': '', 'error': error, 'variable': variable,
            'supportsCjk': config.get('supports_cjk') != 'false',
            'date': datetime.fromtimestamp(info.st_mtime).strftime('%Y-%m-%d'),
            'provisional': preview,
        })
    return {'status': 'ok', 'data': {
        'current': current_font(config_dir), 'fingerprint': '' if preview else fingerprint,
        'sourceFingerprint': fingerprint, 'provisional': preview,
        'scanner': {'primary': 'batch-stat-preview' if preview else 'batch-header-v5', 'nativeAvailable': False},
        'stats': {'count': len(fonts), 'totalSize': size_label(total)}, 'fonts': fonts,
    }}


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n'


def atomic_write(path, value):
    descriptor, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, 0o644)
        os.replace(name, path)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


def read_cache(path):
    try:
        with path.open('rb') as stream:
            raw = stream.read(MAX_CACHE_BYTES + 1)
        if len(raw) > MAX_CACHE_BYTES:
            return None
        value = json.loads(raw)
    except FileNotFoundError:
        return None
    except (ValueError, UnicodeError, RecursionError):
        return None
    if not isinstance(value, dict) or value.get('status') != 'ok':
        return None
    data = value.get('data')
    if not isinstance(data, dict) or not isinstance(data.get('fonts'), list):
        return None
    return value


def verify_inventory(value, fonts, config, captured):
    """Bind the response to a second snapshot in this same finite request.

    The App otherwise launches another ARM64 interpreter just to ask for this
    fingerprint. A changed directory must fail before either cache is written.
    Cached reads alone never carry current verification authority.
    """
    after = snapshot(fonts)
    if after[2] != captured[2]:
        raise ValueError('字体目录在扫描期间发生变化，列表尚未核实，请刷新重试')
    value['data']['current'] = current_font(config)
    value['data']['verification'] = {
        'schema': 'font-list-verification-v1',
        'fingerprint': after[2],
        'current': value['data']['current'],
    }
    return value


def ensure_storage(public_dir, config_dir, migrate=False):
    for path in (public_dir / 'fonts', public_dir / 'reports', public_dir / 'import', config_dir):
        path.mkdir(parents=True, exist_ok=True)
    # Existing import compatibility, outside preview/fingerprint: never overwrite a new file.
    legacy = Path(os.environ.get('LEGACY_FONTS_DIR', '/sdcard/Fonts'))
    if migrate and legacy.is_dir():
        for entry in os.scandir(legacy):
            if not entry.name.startswith('.') and entry.name.endswith(EXTENSIONS) and entry.is_file():
                target = public_dir / 'fonts' / entry.name
                if not target.exists():
                    shutil.copyfile(entry.path, target)


def execute(action, module_dir, public_dir):
    config = module_dir / 'config'
    fonts = public_dir / 'fonts'
    cached_path = config / 'native_font_index.json'
    key_path = config / 'native_font_index.key'
    if action == 'cached':
        value = read_cache(cached_path)
        if value is not None:
            # Persisted verification belongs to its old request, never this read.
            value['data'].pop('verification', None)
        return value or {'status': 'error', 'code': 'cache_miss', 'message': 'cache miss'}
    if action in ('preview', 'scan', 'refresh'):
        ensure_storage(public_dir, config, migrate=action != 'preview')
    captured = snapshot(fonts)
    if action == 'fingerprint':
        return {'status': 'ok', 'data': {'fingerprint': captured[2], 'current': current_font(config),
                                      'count': sum(map(len, captured[0].values())), 'bytes': captured[3]}}
    if action == 'preview':
        return inventory(fonts, config, preview=True, captured=captured)
    key = 'native-v5-batch|' + current_font(config) + '|' + captured[2]
    if action == 'scan':
        try:
            saved_key = key_path.read_text().strip()
        except FileNotFoundError:
            saved_key = ''
        if saved_key == key:
            cached = read_cache(cached_path)
            if cached is not None and cached['data'].get('fingerprint') == captured[2]:
                return verify_inventory(cached, fonts, config, captured)
    value = verify_inventory(inventory(fonts, config, captured=captured), fonts, config, captured)
    key = 'native-v5-batch|' + value['data']['current'] + '|' + captured[2]
    atomic_write(cached_path, compact(value))
    atomic_write(key_path, key + '\n')
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('cached', 'preview', 'scan', 'refresh', 'fingerprint'))
    parser.add_argument('--module', default=os.environ.get('MODDIR', str(Path(__file__).resolve().parent.parent)))
    parser.add_argument('--public', default=os.environ.get('LUOSHU_PUBLIC_DIR', '/sdcard/LuoShu'))
    args = parser.parse_args()
    started = time.monotonic()
    try:
        result = execute(args.action, Path(args.module), Path(args.public))
        code = 0
    except (OSError, ValueError) as exc:
        result = {'status': 'error', 'code': 'inventory_unavailable', 'message': '字体目录或索引暂不可读：' + str(exc)}
        code = 1
    print(compact(result), end='', flush=True)
    elapsed = round((time.monotonic() - started) * 1000, 3)
    data = result.get('data', {})
    count = data.get('stats', {}).get('count', data.get('count', 0))
    print(f'[font-inventory] stage={args.action} elapsed_ms={elapsed} count={count} code={code}', file=sys.stderr, flush=True)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
