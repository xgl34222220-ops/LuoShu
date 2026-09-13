#!/usr/bin/env python3
"""Chinese App integration. Keep the standalone v1 transaction implementation intact."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from google_font_fallback_core import *

def describe(backend: Android, journal: Journal, module: Path) -> dict:
    """Read actual component + compatible v1 undo record; never change Android."""
    current = backend.snapshot(journal.user)
    saved = journal.read()
    valid = saved is not None and same_install(saved, current)
    supported = current['declared'] and current['packageState'] in (0, 1)
    disabled = current['componentState'] == 2
    ready = module_ready(module)
    can_restore = bool(valid and current['declared'] and
                       current['componentState'] in (2, saved['original']))
    if saved is not None and (not valid or not can_restore):
        state, title = 'conflict', '需要检查恢复记录'
        message = '组件状态或 GMS 安装身份已经变化，未覆盖其他操作。请先查看诊断信息。'
    elif not supported:
        state, title = 'unavailable', '当前环境不支持开启'
        message = '未确认字体提供组件可用，或 Google Play 服务整包已停用；不会修改整个谷歌服务。'
    elif disabled and valid:
        state, title = 'enabled', '已开启 Google 字体兼容'
        message = '已识别洛书或独立脚本保存的恢复记录。只停用了字体提供组件；字体效果请重启后检查。'
    elif disabled:
        state, title = 'external', '字体组件已由其他方式停用'
        message = '没有洛书的恢复记录，不能猜测原状态；请通过原操作恢复。'
    elif saved is not None:
        state, title = 'changed', '组件已恢复，记录待核对'
        message = '可点击恢复原设置，核验后清理本功能的恢复记录。'
    else:
        state, title = 'off', '尚未开启 Google 字体兼容'
        message = ('遇到谷歌商店英文、数字恢复默认时，可手动开启此兼容选项。'
                   if ready else '请先启用洛书模块并应用自定义字体，再开启此兼容选项。')
    return {'status': 'diagnostic', 'state': state, 'title': title, 'message': message,
            'user': journal.user, 'managed': bool(valid), 'componentDisabled': disabled,
            'canEnable': bool(supported and ready and saved is None and not disabled),
            'canRestore': can_restore, 'snapshot': current}


def restore_owned(backend: Android, directory: Path) -> dict:
    """Uninstall cleanup: only users with our validated journal, never all users."""
    if not directory.exists():
        return {'status': 'unchanged', 'message': '没有本功能的恢复记录。'}
    restored, errors = [], []
    with locked_store(directory):
        for path in sorted(directory.glob('user-*.json')):
            match = re.fullmatch(r'user-(\d+)[.]json', path.name)
            if not match or not 0 <= int(match[1]) <= 21474:
                continue
            user = int(match[1])
            try:
                restore(backend, Journal(directory, user))
                restored.append(user)
            except (FallbackError, OSError, ValueError) as error:
                errors.append({'user': user, 'message': str(error)})
    return {'status': 'error' if errors else 'restored', 'users': restored,
            'errors': errors, 'message': '卸载前恢复未全部完成；保留失败记录。' if errors else '已核验并恢复有记录的用户设置。'}


def main() -> int:
    parser = argparse.ArgumentParser(description='洛书 Google 字体兼容：仅 FontsProvider，可恢复。')
    parser.add_argument('action', choices=('status', 'enable', 'restore', 'restore-owned'), nargs='?', default='status')
    parser.add_argument('--user', type=int, help='指定 Android 用户；不处理全部用户。')
    parser.add_argument('--json', action='store_true', help='仅输出结构化结果，供内置中文界面使用。')
    args = parser.parse_args()
    try:
        if os.geteuid() != 0:
            raise FallbackError('需要 Root；未执行任何修改。')
        backend = Android()
        if args.action == 'restore-owned':
            result = restore_owned(backend, STORE)
            print(json.dumps(result, ensure_ascii=False))
            return 1 if result['status'] == 'error' else 0
        user = args.user if args.user is not None else backend.current_user()
        if not 0 <= user <= 21474:
            raise FallbackError('无效的 Android 用户编号。')
        if args.action == 'enable' and not module_ready(MODULE):
            raise FallbackError('请先启用洛书并应用自定义字体；未停用 Google 字体提供组件。')
        if not args.json and args.action != 'status':
            print('注意：此开关影响该用户所有依赖 GMS 下载字体的应用，也可能影响下载式表情字体。')
            print('Android 修改组件状态时可能重启相关 GMS 进程。不会清除账户、App 数据或字体目录。')
        with locked_store(STORE):
            journal = Journal(STORE, user)
            if args.action == 'status':
                result = describe(backend, journal, MODULE)
            else:
                result = enable(backend, journal) if args.action == 'enable' else restore(backend, journal)
                if args.json:
                    try:
                        result['current'] = describe(backend, journal, MODULE)
                    except (FallbackError, OSError, ValueError):
                        result['refreshNeeded'] = True
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (FallbackError, OSError, ValueError) as error:
        print(json.dumps({'status': 'error', 'message': str(error)}, ensure_ascii=False),
              file=sys.stdout if args.json else sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
