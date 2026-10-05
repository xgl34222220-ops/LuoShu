#!/system/bin/sh
# One command, one bounded supervisor; bundled Python is never left idle.
_scope_mod="${LUOSHU_REAL_MODDIR:-${MODDIR:-${MODULE_DIR:-${0%/*}/..}}}"
if [ "${1:-}" = cancel-all ]; then
    # Installer/uninstaller invokes the NEW code against OLD registrations.
    # Reading/cancelling old tasks must not initialize or migrate old paths.
    _scope_mod="${0%/*}/.."
elif [ -f "$_scope_mod/common/runtime_paths.sh" ]; then
    . "$_scope_mod/common/runtime_paths.sh"
    luoshu_runtime_paths_init "$_scope_mod" || exit 126
fi
_scope_tasks="${LUOSHU_TASKS_DIR:-${LUOSHU_STATE_DIR:-$_scope_mod/.luoshu-state}/tasks}"
_scope_program="$_scope_mod/common/task_scope.py"
_scope_python="${LUOSHU_TASK_SCOPE_PYTHON:-$_scope_mod/common/python/bin/luoshu-python}"
[ -f "$_scope_program" ] && command -v "$_scope_python" >/dev/null 2>&1 || {
    printf '{"status":"error","message":"任务监督器不可用"}\n'
    exit 126
}
if [ -z "${LUOSHU_TASK_SCOPE_PYTHON:-}" ]; then
    PYTHONHOME="$_scope_mod/common/python"
    PYTHONPATH="$PYTHONHOME/lib/python3.14:$PYTHONHOME/lib/python3.14/site-packages"
    LD_LIBRARY_PATH="$PYTHONHOME/lib:$PYTHONHOME/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    export PYTHONHOME PYTHONPATH LD_LIBRARY_PATH
fi
case "${1:-}" in
    request-run|request-cancel)
        _scope_action="$1"; _scope_token="${2:-}"
        case "$_scope_token" in ''|*[!A-Za-z0-9_.-]*|.|..) exit 2 ;; esac
        [ "${#_scope_token}" -le 160 ] || exit 2
        mkdir -p "$_scope_tasks" || exit 126
        _scope_pidfile="$_scope_tasks/request-$_scope_token.pid"
        if [ "$_scope_action" = request-cancel ]; then
            exec "$_scope_python" "$_scope_program" cancel "$_scope_pidfile" "$_scope_token"
        fi
        _scope_timeout="${3:-360}"; shift 3
        [ "${1:-}" != -- ] || shift
        exec "$_scope_python" "$_scope_program" run --pid-file "$_scope_pidfile" \
            --task "$_scope_token" --timeout "$_scope_timeout" --parent-watch --request -- "$@"
        ;;
    *) exec "$_scope_python" "$_scope_program" "$@" ;;
esac
