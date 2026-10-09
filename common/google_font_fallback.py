#!/usr/bin/env python3
"""Chinese App integration. Keep the standalone v1 transaction implementation intact."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from google_font_fallback_core import *
from google_font_fallback_core import module_ready as _core_module_ready


def module_ready(module: Path) -> bool:
    # A broken manager marker is still a disable/remove request.
    return _core_module_ready(module) and not any(
        (module / flag).is_symlink() for flag in ('disable', 'remove'))


class _ModuleWriteGuard:
    """Recheck compatibility disables at the actual Android write boundary."""
    def __init__(self, backend: Android, module: Path):
        self.backend, self.module = backend, module

    def snapshot(self, user: int) -> dict:
        return self.backend.snapshot(user)

    def change(self, user: int, state_value: int) -> None:
        # Original-state restoration remains available even after a late disable.
        if state_value == 2 and not module_ready(self.module):
            raise FallbackError('模块已禁用、待移除或未就绪；未重新停用 Google 字体组件。')
        self.backend.change(user, state_value)

def _verified_version(saved: dict) -> int | None:
    value = saved.get('lastVerifiedVersionCode', saved.get('versionCode'))
    return value if type(value) is int and value > 0 else None


def _verified_update_time(saved: dict) -> str | None:
    return validated_update_time(saved.get('lastVerifiedUpdateTime', saved.get('lastUpdateTime')))


def _same_revision(before: dict, after: dict) -> bool:
    return (before['versionCode'] == after['versionCode'] and
            validated_update_time(before.get('lastUpdateTime')) ==
            validated_update_time(after.get('lastUpdateTime')) and
            validated_code_path(before.get('codePath')) == validated_code_path(after.get('codePath')))


def _checkpoint(saved: dict, current: dict) -> dict:
    result = {**saved, 'lastVerifiedVersionCode': current['versionCode']}
    # Explicit None clears stale evidence but preserves the original undo's
    # snapshot fields, including the originally observed version and paths.
    result['lastVerifiedUpdateTime'] = validated_update_time(current.get('lastUpdateTime'))
    result['lastVerifiedCodePath'] = validated_code_path(current.get('codePath'))
    return result


def _owned_reset_reason(saved: dict, current: dict) -> str | None:
    version = _verified_version(saved)
    if version is None or saved['original'] != 0 or current['componentState'] != 0:
        return None
    if current['versionCode'] > version:
        return 'newer-version'
    before, after = _verified_update_time(saved), validated_update_time(current.get('lastUpdateTime'))
    old_path = validated_code_path(saved.get('lastVerifiedCodePath', saved.get('codePath')))
    new_path = validated_code_path(current.get('codePath'))
    # dumpsys dates are local-time strings. A timezone change alone must not
    # authorize a write: also require a different validated installed APK path.
    if (current['versionCode'] == version and before is not None and after is not None and after > before
            and old_path is not None and new_path is not None and old_path != new_path):
        return 'same-version-package-update'
    return None


def _can_reapply(saved: dict | None, current: dict, module: Path) -> bool:
    return bool(saved is not None and module_ready(module) and
                same_install(saved, current) and current['declared'] and
                current['packageState'] in (0, 1) and
                current['componentState'] in (2, saved['original']))


def _reapply_transaction(backend: Android, journal: Journal, saved: dict,
                         before: dict, restart: bool) -> dict:
    """Reassert only an owned component; retain its original durable undo.

    An explicit refresh can briefly restore that one component to its original
    setting before disabling it again. A failure returns it to the state seen
    before this attempt, rather than losing the original recovery record.
    """
    latest = backend.snapshot(journal.user)
    if (not same_install(saved, latest) or not latest['declared'] or
            latest['packageState'] != before['packageState'] or
            not _same_revision(before, latest) or
            latest['componentState'] != before['componentState']):
        raise FallbackError('重新应用前的组件状态已变化；保留记录，未覆盖其他操作。')
    original, rollback = saved['original'], before['componentState']
    try:
        if restart and rollback == 2:
            backend.change(journal.user, original)
            reopened = backend.snapshot(journal.user)
            if (not same_install(saved, reopened) or not reopened['declared'] or
                    reopened['packageState'] != before['packageState'] or
                    not _same_revision(before, reopened) or
                    reopened['componentState'] != original):
                raise FallbackError('重新应用的中间状态未验证通过。')
        backend.change(journal.user, 2)
        after = backend.snapshot(journal.user)
        if (not same_install(saved, after) or not after['declared'] or
                after['packageState'] != before['packageState'] or
                not _same_revision(before, after) or
                after['componentState'] != 2):
            raise FallbackError('重新应用后的组件状态未验证通过。')
        journal.save(_checkpoint(saved, after))
    except (FallbackError, OSError, ValueError) as error:
        try:
            current = backend.snapshot(journal.user)
            if (not same_install(saved, current) or not current['declared'] or
                    current['packageState'] != before['packageState'] or
                    not _same_revision(before, current) or
                    current['componentState'] not in (original, 2)):
                raise FallbackError('回滚时组件身份或状态已变化。')
            if current['componentState'] != rollback:
                backend.change(journal.user, rollback)
                current = backend.snapshot(journal.user)
                if (not same_install(saved, current) or not current['declared'] or
                        current['packageState'] != before['packageState'] or
                        not _same_revision(before, current) or current['componentState'] != rollback):
                    raise FallbackError('回滚尚未核验成功。')
        except (FallbackError, OSError, ValueError):
            raise FallbackError(str(error) + ' 回滚待确认，原恢复记录保留，请重新检测。') from error
        raise FallbackError(str(error) + ' 已回到本次操作前状态，原恢复记录保留。') from error
    return {'status': 'component-disabled', 'user': journal.user,
            'message': '已重新核验兼容设置，保留开启前的原恢复记录；请重新打开谷歌应用检查字体。'}


def reconcile_owned(backend: Android, journal: Journal, module: Path) -> dict:
    """One bounded package-update recovery; never enables an unowned feature.

    A newer version or strictly newer lastUpdateTime of the same version is
    package-update evidence, not proof of the user's rendering problem. Explicit
    enable edits, unchanged revisions and replacement installs are left alone.
    """
    saved = journal.read()
    unchanged = {'status': 'unchanged', 'user': journal.user}
    if saved is None or not module_ready(module):
        return {**unchanged, 'message': '未开启本功能或模块未使用自定义字体；没有修改 Google 组件。'}
    current = backend.snapshot(journal.user)
    if not _can_reapply(saved, current, module):
        return {**unchanged, 'message': '组件或安装身份已变化；保留恢复记录，没有覆盖其他操作。'}
    if current['componentState'] == 2:
        checkpoint = _checkpoint(saved, current)
        if checkpoint != saved:
            journal.save(checkpoint)
        return {**unchanged, 'message': '兼容组件仍保持停用；没有反复切换或重启 Google 服务。'}
    reason = _owned_reset_reason(saved, current)
    if reason is None:
        return {**unchanged, 'message': '没有确认 GMS 升级后的默认状态回退；请检测后明确选择重新应用。'}
    result = _reapply_transaction(_ModuleWriteGuard(backend, module), journal, saved, current, restart=False)
    result['recoveredAfterUpgrade'] = True
    result['recoveryReason'] = reason
    return result


def reapply_owned(backend: Android, journal: Journal, module: Path) -> dict:
    """Explicit repair without first discarding the existing undo record."""
    saved = journal.read()
    if saved is None:
        raise FallbackError('没有本功能的恢复记录；请先明确开启兼容，未接管其他工具设置。')
    current = backend.snapshot(journal.user)
    if not _can_reapply(saved, current, module):
        raise FallbackError('模块、组件或安装身份无法核验；保留记录，未重新应用。')
    return _reapply_transaction(_ModuleWriteGuard(backend, module), journal, saved, current, restart=True)


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
        message = '字体提供组件仍保持停用。若字体已回退，可明确重新应用兼容；旧字体句柄或应用自带字体需另外核实。'
    elif disabled:
        state, title = 'external', '字体组件已由其他方式停用'
        message = '没有洛书的恢复记录，不能猜测原状态；请通过原操作恢复。'
    elif saved is not None:
        state, title = 'changed', '组件已恢复，记录待核对'
        if _owned_reset_reason(saved, current) is not None:
            message = '检测到 GMS 软件包更新后组件回到默认状态。返回洛书前台会核验维护；也可重新应用兼容并保留原恢复记录。'
        else:
            message = '字体提供组件已回到开启前状态，尚未确认软件包更新。可明确重新应用兼容并保留原恢复记录，也可恢复原设置。'
    else:
        state, title = 'off', '尚未开启 Google 字体兼容'
        message = ('遇到谷歌商店英文、数字恢复默认时，可手动开启此兼容选项。'
                   if ready else '请先启用洛书模块并应用自定义字体，再开启此兼容选项。')
    return {'status': 'diagnostic', 'state': state, 'title': title, 'message': message,
            'user': journal.user, 'managed': bool(valid), 'componentDisabled': disabled,
            'canEnable': bool(supported and ready and saved is None and not disabled),
            'canRestore': can_restore, 'canReapply': _can_reapply(saved, current, module),
            'recoveryEvidence': _owned_reset_reason(saved, current) if valid and supported else None,
            'snapshot': current}


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
    parser.add_argument('action', choices=('status', 'enable', 'restore', 'restore-owned', 'reconcile-owned', 'reapply-owned'), nargs='?', default='status')
    parser.add_argument('--user', type=int, help='指定 Android 用户；不处理全部用户。')
    parser.add_argument('--json', action='store_true', help='仅输出结构化结果，供内置中文界面使用。')
    args = parser.parse_args()
    try:
        if os.geteuid() != 0:
            raise FallbackError('需要 Root；未执行任何修改。')
        backend = Android()
        directory = prepare_store(STORE, LEGACY_STORE)
        if args.action == 'restore-owned':
            result = restore_owned(backend, directory)
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
        with locked_store(directory):
            journal = Journal(directory, user)
            if args.action == 'status':
                result = describe(backend, journal, MODULE)
            elif args.action == 'reconcile-owned':
                result = reconcile_owned(backend, journal, MODULE)
            elif args.action == 'reapply-owned':
                result = reapply_owned(backend, journal, MODULE)
            else:
                result = enable(_ModuleWriteGuard(backend, MODULE), journal) if args.action == 'enable' else restore(backend, journal)
            if args.json and args.action != 'status':
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
