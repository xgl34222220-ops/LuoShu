#!/usr/bin/env python3
"""Preflight and one task-owned, fully validated font-family snapshot."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

from font_inventory_batch import EXTENSIONS, MAGIC, family_of, identity
from font_coverage_fields import unique_object

MAX_CONFIG = 64 * 1024
MAX_RESPONSE = 1024 * 1024


def event(name, **fields):
    root = {'event': name, 'task': os.environ.get('LUOSHU_SWITCH_TASK_ID', ''),
            'token': os.environ.get('LUOSHU_TASK_SCOPE', ''),
            'boot': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    root.update(fields)
    print('[font-switch-input] ' + json.dumps(root, ensure_ascii=True, separators=(',', ':')),
          file=sys.stderr, flush=True)


def snapshot_digest(hashes):
    return hashlib.sha256(json.dumps(hashes, sort_keys=True, ensure_ascii=True,
                                    separators=(',', ':')).encode()).hexdigest()


def file_identity(path):
    link = path.lstat()
    target = path.stat()
    if not stat.S_ISREG(target.st_mode):
        raise ValueError('字体来源不是普通文件')
    return [identity(link), identity(target)]


def selection(public, family):
    if not family or family in ('.', '..', 'default') or any(c in family for c in '/\\\0\r\n|'):
        raise ValueError('字体标识无效')
    fonts = public / 'fonts'
    # Reading the directory must succeed, including when it has no matches.
    with os.scandir(fonts) as entries:
        names = [entry.name for entry in entries]
    chosen = []
    for extension in EXTENSIONS:
        for name in sorted((name for name in names if not name.startswith('.') and name.endswith(extension)), key=os.fsencode):
            if family_of(name) != family or family.startswith(('SysFont', 'SysSans')):
                continue
            path = fonts / name
            if not path.is_file():
                continue
            chosen.append({'name': name, 'identity': file_identity(path), 'config': False})
    if not chosen:
        raise ValueError('未找到字体')
    config = fonts / (family + '.conf')
    if config.exists() or config.is_symlink():
        chosen.append({'name': config.name, 'identity': file_identity(config), 'config': True})
    directory = fonts.stat()
    return {'family': family, 'directory': [directory.st_dev, directory.st_ino, directory.st_mode,
                                           directory.st_uid, directory.st_gid], 'files': chosen}


def fingerprint(selected):
    raw = json.dumps(selected, ensure_ascii=True, separators=(',', ':')).encode()
    return 'font-selection-v1:' + hashlib.sha256(raw).hexdigest()


def checked_read(path, record, destination=None, header_only=False):
    expected = record['identity']
    if file_identity(path) != expected:
        raise ValueError('字体文件已变化，请刷新后重试')
    digest = hashlib.sha256()
    header = b''
    with path.open('rb') as source:
        if identity(os.fstat(source.fileno())) != expected[1]:
            raise ValueError('字体来源已切换，请重试')
        total = 0
        while True:
            chunk = source.read(4 if header_only else 1024 * 1024)
            if not chunk:
                break
            if not header:
                header = chunk[:4]
            total += len(chunk)
            if record['config'] and total > MAX_CONFIG:
                raise ValueError('字体配置过大')
            digest.update(chunk)
            if destination is not None:
                destination.write(chunk)
            if header_only:
                break
        if identity(os.fstat(source.fileno())) != expected[1] or file_identity(path) != expected:
            raise ValueError('读取期间字体文件已变化，请重试')
    return digest.hexdigest(), header


def preflight(public, family):
    selected = selection(public, family)
    first = selected['files'][0]
    _, header = checked_read(public / 'fonts' / first['name'], first, header_only=True)
    if first['identity'][1][5] < 4096:
        raise ValueError('字体文件过小')
    if MAGIC.get(header) not in ('TTF', 'OTF', 'TTC'):
        raise ValueError('字体格式无法用于系统字体')
    if selection(public, family) != selected:
        raise ValueError('字体库已变化，请刷新后重试')
    return {'valid': True, 'fingerprint': fingerprint(selected), 'validation': 'preflight-only'}


def owned_workspace(module):
    token = os.environ.get('LUOSHU_TASK_SCOPE', '')
    raw = os.environ.get('LUOSHU_TASK_WORK_DIR', '')
    workspace = Path(raw)
    expected = module.resolve() / 'cache' / 'tasks' / token
    if not token or not raw or workspace.is_symlink() or workspace.resolve() != expected:
        raise ValueError('缺少任务专属字体工作区')
    if (workspace / '.luoshu-task-owner').read_text().strip() != token:
        raise ValueError('字体工作区身份不匹配')
    return workspace


def stage(message, percent):
    raw = os.environ.get('LUOSHU_SWITCH_PROGRESS_FILE')
    if raw:
        path = Path(raw)
        temporary = path.with_name(path.name + '.snapshot.tmp')
        temporary.write_text(f'percent={percent}\nmessage={message}\n')
        os.replace(temporary, path)


def make_snapshot(public, family, workspace, expected=''):
    selected = selection(public, family)
    if expected and fingerprint(selected) != expected:
        raise ValueError('预检后字体文件已变化，请刷新后重试')
    private = workspace / 'font-input'
    fonts = private / 'fonts'
    fonts.mkdir(mode=0o700, parents=True, exist_ok=False)
    (workspace / 'empty-legacy-fonts').mkdir(mode=0o700)
    hashes = {}
    for record in selected['files']:
        target = fonts / record['name']
        with target.open('xb') as output:
            hashes[record['name']], _ = checked_read(public / 'fonts' / record['name'], record, output)
        target.chmod(0o400)
    if selection(public, family) != selected:
        raise ValueError('复制期间字体库已变化，请刷新后重试')
    return private, selected, hashes


def confirm_snapshot(public, private, selected, hashes):
    if selection(public, selected['family']) != selected:
        raise ValueError('验证期间原字体已变化，请刷新后重试')
    copied_names = [(item['name'], item['config']) for item in selection(private, selected['family'])['files']]
    if copied_names != [(item['name'], item['config']) for item in selected['files']]:
        raise ValueError('验证期间字体副本集合已变化')
    for record in selected['files']:
        name = record['name']
        original, _ = checked_read(public / 'fonts' / name, record)
        copy_record = {'identity': file_identity(private / 'fonts' / name), 'config': record['config']}
        copied, _ = checked_read(private / 'fonts' / name, copy_record)
        if original != hashes[name] or copied != hashes[name]:
            raise ValueError('验证期间字体内容已变化，请刷新后重试')
    if selection(public, selected['family']) != selected:
        raise ValueError('验证后字体库已变化，请刷新后重试')


def full_validation(manager, family, workspace, env):
    output_path = workspace / 'font-validation.json'
    # Files avoid pipe inheritance and unbounded in-memory command output. The
    # existing task scope owns this process and its descendants for all 360 s.
    started = time.monotonic()
    with output_path.open('wb') as output:
        result = subprocess.run(['sh', str(manager), 'action', 'validate', family], env=env,
                                stdin=subprocess.DEVNULL, stdout=output, close_fds=True)
    with output_path.open('rb') as output:
        raw = output.read(MAX_RESPONSE + 1)
    if len(raw) > MAX_RESPONSE:
        raise ValueError('字体验证结果过大')
    try:
        root = json.loads(raw, object_pairs_hook=unique_object)
        data = root.get('data', {})
        event('full_validation', valid=data.get('valid') is True, cached=data.get('cached'),
              code=result.returncode, elapsed_ms=round((time.monotonic() - started) * 1000, 3))
        if result.returncode != 0 or root.get('status') != 'ok' or data.get('valid') is not True:
            raise ValueError(root.get('message') or data.get('error') or '完整字体验证未通过')
    except (TypeError, AttributeError, json.JSONDecodeError) as error:
        raise ValueError('完整字体验证返回无效结果') from error


def run_task(module, public, family, manager, expected=''):
    if family == 'default':
        os.execvpe('sh', ['sh', str(manager), 'action', 'switch', family], os.environ.copy())
    workspace = owned_workspace(module)
    stage('正在复制所选字体并固定文件版本', 3)
    private, selected, hashes = make_snapshot(public, family, workspace, expected)
    event('snapshot', source_fingerprint=fingerprint(selected), snapshot_digest=snapshot_digest(hashes),
          source_identities=[record['identity'] for record in selected['files']],
          file_count=len(selected['files']), selected_digest=hashes[selected['files'][0]['name']])
    env = dict(os.environ, MODDIR=str(module), MODULE_DIR=str(module), LUOSHU_PUBLIC_DIR=str(private),
               LEGACY_FONTS_DIR=str(workspace / 'empty-legacy-fonts'), LUOSHU_VALIDATION_MODE='full')
    stage('正在后台完整验证字体与字形覆盖', 4)
    full_validation(manager, family, workspace, env)
    stage('正在核对已验证字体，准备生成负载', 5)
    confirm_snapshot(public, private, selected, hashes)
    event('core_entry', source_rechecked=True, snapshot_digest=snapshot_digest(hashes),
          source_fingerprint=fingerprint(selected))
    # Frozen core has no pre-commit hook. From this entry onward it applies the
    # exact validated private copy; later public-library edits cannot change it.
    os.execvpe('sh', ['sh', str(manager), 'action', 'switch', family], env)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('preflight', 'run'))
    parser.add_argument('family')
    parser.add_argument('fingerprint', nargs='?', default='')
    args = parser.parse_args()
    module = Path(os.environ.get('MODDIR', Path(__file__).resolve().parent.parent))
    public = Path(os.environ.get('LUOSHU_PUBLIC_DIR', '/sdcard/LuoShu'))
    manager = Path(os.environ.get('LUOSHU_FONT_MANAGER', module / 'common/font_manager.sh'))
    try:
        if args.action == 'preflight':
            print(json.dumps({'status': 'ok', 'data': preflight(public, args.family)}, ensure_ascii=False, separators=(',', ':')))
        else:
            run_task(module, public, args.family, manager, args.fingerprint)
        return 0
    except (OSError, ValueError) as error:
        print(json.dumps({'status': 'error', 'message': str(error)}, ensure_ascii=False, separators=(',', ':')))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
