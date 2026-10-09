#!/system/bin/sh
# Explicit enable only. Reconciliation repairs only a verified owned upgrade reset.
set -eu
HERE=$(CDPATH= cd -P -- "$(dirname -- "$0")" && pwd)
MODDIR="${MODDIR:-${MODULE_DIR:-${HERE%/*}}}"
export MODDIR
case "${1:-status}" in status|enable|restore|restore-owned|reconcile-owned|reapply-owned) ;; *)
    printf '%s\n' '{"status":"error","message":"不支持的 Google 字体操作。"}'; exit 2;;
esac
case "${1:-status}" in
    enable|reapply-owned|reconcile-owned)
        # Recheck at execution time; a fresh App snapshot can race a manager.
        # Explicit restoration must remain available while disabled/removing.
        if [ -e "$MODDIR/disable" ] || [ -L "$MODDIR/disable" ] ||
           [ -e "$MODDIR/remove" ] || [ -L "$MODDIR/remove" ]; then
            printf '%s\n' '{"status":"error","message":"模块已禁用或待移除，未修改 Google 字体兼容状态。恢复原状态仍可使用。"}'
            exit 1
        fi ;;
esac
if [ -f "$HERE/runtime_paths.sh" ]; then
    . "$HERE/runtime_paths.sh"
    luoshu_runtime_paths_init "$MODDIR" || exit 1
fi
PYROOT="$HERE/python"
if [ "$(id -u)" != 0 ]; then
    printf '%s\n' '{"status":"error","message":"请在 Root 管理器中为洛书授予 Root 权限。"}'; exit 1
fi
if [ ! -x "$PYROOT/bin/luoshu-python" ]; then
    printf '%s\n' '{"status":"error","message":"模块运行环境缺失，请安装配套模块并完整重启。"}'; exit 1
fi
if [ -z "${LUOSHU_TASK_SCOPE_PID:-}" ]; then
    [ -f "$HERE/task_scope.sh" ] || exit 1
    exec sh "$HERE/task_scope.sh" request-run "font-fallback-$$-$(date +%s)" \
        180 -- sh "$0" "$@"
fi
export PYTHONHOME="$PYROOT"
export PYTHONPATH="$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages"
export LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$PYROOT/bin/luoshu-python" "$HERE/google_font_fallback.py" "$@"
