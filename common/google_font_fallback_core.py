#!/usr/bin/env python3
"""Explicit, reversible GMS FontsProvider switch (GPL-3.0).

Concept: MrCarb0n/killgmsfont. Independently implemented: no cache deletion,
no scheduler changes, no hooks, no daemon, no whole-package disable. The only
mutable Android component is the exact FontsProvider below, for one user.
Enabling blocks provider requests, NOT bundled fonts or existing file handles.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from typing import Any

GMS = 'com.google.android.gms'
PROVIDER = GMS + '.fonts.provider.FontsProvider'
COMPONENT = GMS + '/' + PROVIDER
STORE = Path('/data/adb/luoshu-google-font-fallback')
MODULE = Path('/data/adb/modules/LuoShu')
SCHEMA = 'luoshu-google-font-fallback-v1'


class FallbackError(RuntimeError):
    pass


def parse_snapshot(text: str, user: int) -> dict[str, Any]:
    """Read live dumpsys, never package-restrictions.xml (which can lag).

    Restrict overrides to the installed package's requested User block; do not
    read the older ROM copy in Hidden system packages or another user's flags.
    Unknown/malformed output is an error, never assumed to be 'default'.
    """
    if not 0 <= user <= 21474 or any(x in text.lower() for x in (
            'dump timed out', 'dump timeout', 'permission denial', 'can\'t find service')):
        raise FallbackError('无法可靠读取包管理器状态；未修改组件。')
    sections = re.findall(r'(?ms)^Packages:\s*\n(.*?)(?=^\S|\Z)', text)
    if len(sections) != 1:
        raise FallbackError('未找到唯一的已安装软件包区域；未猜测组件状态。')
    packages = re.findall(r'(?ms)^  Package \[' + re.escape(GMS)
                          + r'\][^\n]*\n(.*?)(?=^  Package \[|\Z)', sections[0])
    if len(packages) != 1:
        raise FallbackError('未找到唯一的 Google Play 服务软件包。')
    package = packages[0]
    appid = re.search(r'^\s+(?:appId|userId)=(\d+)\b', package, re.M)
    version = re.search(r'\bversionCode=(\d+)\b', package)
    users = list(re.finditer(r'(?m)^( +)User (\d+):([^\n]*)$', package))
    matches = [(i, m) for i, m in enumerate(users) if int(m[2]) == user]
    if not appid or not version or len(matches) != 1:
        raise FallbackError('GMS 用户、版本或安装身份不完整；未修改组件。')
    i, entry = matches[0]
    if not re.search(r'\binstalled=true\b', entry[3]):
        raise FallbackError('此用户未安装 Google Play 服务。')
    app_enabled = re.search(r'\benabled=(\d+)\b', entry[3])
    if not app_enabled:
        raise FallbackError('GMS 整包启用状态未知。')
    part = package[entry.end(): users[i + 1].start() if i + 1 < len(users) else len(package)]
    first = re.search(r'^\s+firstInstallTime=([^\n]+)', part, re.M)
    if first is None:  # Older Android prints a package-wide install time.
        first = re.search(r'^\s+firstInstallTime=([^\n]+)', package[:users[0].start()], re.M)
    if first is None:
        raise FallbackError('当前用户的 GMS 安装身份不完整；未修改组件。')
    # Nested user components have greater indentation than the User header.
    user_indent = len(entry[1])
    state_value = 0
    seen = set()
    component_list = None
    list_indent = 0
    for line in part.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip(' '))
        if indent <= user_indent:
            break
        if ('enabledComponents' in stripped or 'disabledComponents' in stripped) and stripped not in ('enabledComponents:', 'disabledComponents:'):
            raise FallbackError('组件列表格式未知；未猜测原始状态。')
        if stripped in ('enabledComponents:', 'disabledComponents:'):
            component_list = 1 if stripped == 'enabledComponents:' else 2
            list_indent = indent
            continue
        if component_list is not None and indent <= list_indent:
            component_list = None
        if component_list is not None:
            name = stripped
            if '/' in name:
                pkg, name = name.split('/', 1)
                if pkg != GMS:
                    continue
            if name.startswith('.'):
                name = GMS + name
            if name == PROVIDER:
                seen.add(component_list)
                state_value = component_list
    if len(seen) > 1:
        raise FallbackError('字体组件同时出现在启用和停用列表；拒绝修改。')
    # Require evidence from live registered provider metadata, not merely its
    # name in a stale disabled-component override left after a GMS update.
    prefix = text.split('Packages:', 1)[0]
    declared = bool(re.search(re.escape(GMS) + r'/(?:'
                              + re.escape(PROVIDER) + r'|\.fonts\.provider\.FontsProvider)'
                              + r'(?=[\s}\]])', prefix))
    return {'user': user, 'appId': int(appid[1]), 'versionCode': int(version[1]),
            'firstInstallTime': first[1].strip(), 'packageState': int(app_enabled[1]),
            'component': COMPONENT, 'componentState': state_value, 'declared': declared}


class Android:
    def run(self, *args: str) -> str:
        try:
            completed = subprocess.run(list(args), text=True, encoding='utf-8',
                                       errors='replace', capture_output=True, timeout=12)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise FallbackError('Android 命令不可用或超时：' + args[0]) from error
        if completed.returncode != 0:
            raise FallbackError('Android 命令失败：' + ' '.join(args[:2]))
        if 'exception' in completed.stdout.lower() or 'error:' in completed.stdout.lower():
            raise FallbackError('Android 拒绝操作；未把错误输出当作成功。')
        return completed.stdout

    def current_user(self) -> int:
        value = self.run('/system/bin/am', 'get-current-user').strip()
        if not value.isdigit() or not 0 <= int(value) <= 21474:
            raise FallbackError('无法确定当前 Android 用户；未默认修改用户 0。')
        return int(value)

    def snapshot(self, user: int) -> dict[str, Any]:
        return parse_snapshot(self.run('/system/bin/dumpsys', '-t', '10', 'package', GMS), user)

    def change(self, user: int, state_value: int) -> None:
        # Never accept a caller-supplied package/component or a shell fragment.
        command = {0: 'default-state', 1: 'enable', 2: 'disable'}[state_value]
        self.run('/system/bin/pm', command, '--user', str(user), COMPONENT)


def same_install(saved: dict, current: dict) -> bool:
    return all(saved[key] == current[key] for key in ('user', 'appId', 'firstInstallTime'))


def validate_journal(data: dict, user: int) -> None:
    if (not isinstance(data, dict) or data.get('schema') != SCHEMA
            or data.get('component') != COMPONENT or type(data.get('user')) is not int
            or data['user'] != user or type(data.get('appId')) is not int
            or not isinstance(data.get('firstInstallTime'), str)
            or type(data.get('original')) is not int or data['original'] not in (0, 1)):
        raise FallbackError('恢复记录无效；不会执行其中的任意组件或命令。')


def secure_file(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022:
        raise FallbackError('恢复记录所有者或权限不安全。')


class Journal:
    def __init__(self, directory: Path, user: int):
        self.directory = directory
        self.user = user
        self.path = directory / f'user-{user}.json'

    def read(self) -> dict | None:
        if not self.path.exists() and not self.path.is_symlink():
            return None
        secure_file(self.path)
        if self.path.stat().st_size > 16384:
            raise FallbackError('恢复记录大小异常。')
        with self.path.open() as stream:
            data = json.load(stream)
        validate_journal(data, self.user)
        return data

    def save(self, data: dict) -> None:
        validate_journal(data, self.user)
        fd, raw = tempfile.mkstemp(prefix='.journal-', dir=self.directory)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(raw, self.path)
            self.sync_directory()
        finally:
            Path(raw).unlink(missing_ok=True)

    def sync_directory(self) -> None:
        fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)
        self.sync_directory()


@contextmanager
def locked_store(directory: Path):
    directory.mkdir(mode=0o700, parents=False, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise FallbackError('恢复目录不是当前 Root 独占的真实目录。')
    fd = os.open(directory / 'operation.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise FallbackError('另一项字体来源操作正在执行。') from error
        yield
    finally:
        os.close(fd)  # Keep lock inode stable; a killed process releases flock.


def restore(backend: Android, journal: Journal) -> dict:
    saved = journal.read()
    if saved is None:
        return {'status': 'unchanged', 'message': '没有本工具的修改记录；未擅自启用字体组件。'}
    current = backend.snapshot(journal.user)
    if not same_install(saved, current) or not current['declared']:
        raise FallbackError('GMS 安装身份或组件已变化；保留记录，未覆盖新安装状态。')
    value = current['componentState']
    if value == saved['original']:
        journal.clear()
        return {'status': 'restored', 'message': '组件已处于开启前状态，恢复记录已清理。'}
    if value != 2:
        raise FallbackError('组件已被其他操作改动；保留现场，不强制覆盖。')
    backend.change(journal.user, saved['original'])
    after = backend.snapshot(journal.user)
    if not same_install(saved, after) or after['componentState'] != saved['original']:
        raise FallbackError('恢复尚未验证成功；保留恢复记录，可再次运行 restore。')
    journal.clear()
    return {'status': 'restored', 'message': '已恢复原组件状态；请完整重启。',
            'originalState': saved['original'], 'user': journal.user}


def enable(backend: Android, journal: Journal) -> dict:
    saved = journal.read()
    current = backend.snapshot(journal.user)
    if not current['declared'] or current['packageState'] not in (0, 1):
        raise FallbackError('没有确认字体提供组件存在，或 GMS 整包已停用；未修改。')
    if saved is not None:
        if not same_install(saved, current):
            raise FallbackError('GMS 安装身份已变化；请先检查旧恢复记录。')
        if current['componentState'] == 2:
            return {'status': 'component-disabled', 'message': '字体提供组件已停用；未重复修改。'}
        raise FallbackError('已有恢复记录且组件状态已变化；先运行 restore 再决定是否开启。')
    if current['componentState'] == 2:
        return {'status': 'externally-disabled',
                'message': '该组件本来就已停用，不归本工具接管；反弹需要排查其他字体来源。'}
    saved = {**current, 'schema': SCHEMA, 'original': current['componentState']}
    journal.save(saved)  # Durable write-ahead record before any Android mutation.
    try:
        # Re-read just before writing; do not overwrite an intervening user's edit.
        latest = backend.snapshot(journal.user)
        if not same_install(saved, latest) or latest['componentState'] != saved['original']:
            journal.clear()
            raise FallbackError('操作前状态发生变化；已取消，未修改组件。')
        backend.change(journal.user, 2)
        after = backend.snapshot(journal.user)
        if not same_install(saved, after) or after['componentState'] != 2:
            raise FallbackError('停用后的状态未验证通过。')
    except FallbackError as error:
        try:
            outcome = restore(backend, journal)
        except FallbackError:
            raise FallbackError(str(error) + ' 回滚待确认，恢复记录保留，请运行 restore。') from error
        raise FallbackError(str(error) + ' 已恢复开启前状态。') from error
    return {'status': 'component-disabled', 'user': journal.user,
            'message': '已验证仅 FontsProvider 被停用。请完整重启后检查 Google 商店；这不代表字体渲染已经验收。',
            'undo': '重新运行本脚本并传入 restore；移除洛书模块前先恢复。'}


def module_ready(module: Path) -> bool:
    try:
        return ('id=LuoShu' in (module / 'module.prop').read_text().splitlines()
                and not any((module / flag).exists() for flag in ('disable', 'remove'))
                and (module / 'config/active_font.conf').read_text().strip() not in ('', 'default'))
    except OSError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description='洛书 Google 字体来源开关：仅 FontsProvider，可恢复。')
    parser.add_argument('action', choices=('status', 'enable', 'restore'), nargs='?', default='status')
    parser.add_argument('--user', type=int, help='仅操作指定用户；默认通过系统获取当前用户，不处理全部用户。')
    args = parser.parse_args()
    try:
        if os.geteuid() != 0:
            raise FallbackError('需要 Root；未执行任何修改。')
        backend = Android()
        user = args.user if args.user is not None else backend.current_user()
        if not 0 <= user <= 21474:
            raise FallbackError('无效的 Android 用户编号。')
        if args.action == 'status':
            current = backend.snapshot(user)
            print(json.dumps({'status': 'diagnostic', **current}, ensure_ascii=False, indent=2))
            return 0
        if args.action == 'enable' and not module_ready(MODULE):
            raise FallbackError('请先启用洛书并应用自定义字体；未停用 Google 字体提供组件。')
        print('注意：此开关影响该用户所有依赖 GMS 下载字体的应用，也可能影响下载式表情字体。')
        print('Android 修改组件状态时可能重启相关 GMS 进程。不会清除账户、App 数据或字体目录。')
        with locked_store(STORE):
            journal = Journal(STORE, user)
            result = enable(backend, journal) if args.action == 'enable' else restore(backend, journal)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (FallbackError, OSError, ValueError) as error:
        print(json.dumps({'status': 'error', 'message': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
