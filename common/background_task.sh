#!/system/bin/sh
# Root 后台任务启动器：脱离 App 的 su 会话、终端与进程组。

luoshu_pid_value() {
    _lpv_file="$1"
    sed -n '1{s/[^0-9].*$//;p;}' "$_lpv_file" 2>/dev/null
}

luoshu_task_pid_alive() {
    _ltpa_pid_file="$1"
    _ltpa_task="${2:-}"
    _ltpa_pid=$(luoshu_pid_value "$_ltpa_pid_file")
    [ -n "$_ltpa_pid" ] || return 1
    kill -0 "$_ltpa_pid" 2>/dev/null || return 1
    if [ -n "$_ltpa_task" ]; then
        # A numeric PID can be recycled by Android. The task sidecar and, when available,
        # the worker command line must both still belong to the same LuoShu task.
        [ -s "${_ltpa_pid_file}.task" ] || return 1
        [ "$(cat "${_ltpa_pid_file}.task" 2>/dev/null)" = "$_ltpa_task" ] || return 1
        if [ -r "/proc/$_ltpa_pid/cmdline" ]; then
            _ltpa_cmdline=$(tr '\000' ' ' < "/proc/$_ltpa_pid/cmdline" 2>/dev/null)
            case "$_ltpa_cmdline" in *"$_ltpa_task"*) ;; *) return 1 ;; esac
        fi
    fi
    return 0
}

luoshu_clear_task_pid() {
    _lctp_pid_file="$1"
    _lctp_task="${2:-}"
    if [ -n "$_lctp_task" ] && [ -s "${_lctp_pid_file}.task" ] && [ "$(cat "${_lctp_pid_file}.task" 2>/dev/null)" != "$_lctp_task" ]; then
        return 0
    fi
    rm -f "$_lctp_pid_file" "${_lctp_pid_file}.task" 2>/dev/null || true
}

luoshu_stop_task_pid() {
    _lstp_pid_file="$1"
    _lstp_pid=$(luoshu_pid_value "$_lstp_pid_file")
    [ -z "$_lstp_pid" ] || ! kill -0 "$_lstp_pid" 2>/dev/null || kill "$_lstp_pid" 2>/dev/null || true
    luoshu_clear_task_pid "$_lstp_pid_file"
}

luoshu_start_detached() {
    _lsd_pid_file="$1"
    _lsd_task="$2"
    _lsd_log_file="$3"
    shift 3
    [ "$#" -gt 0 ] || return 2
    mkdir -p "${_lsd_pid_file%/*}" "${_lsd_log_file%/*}" 2>/dev/null || return 1
    if luoshu_task_pid_alive "$_lsd_pid_file" "$_lsd_task"; then
        return 3
    fi

    # Shell function variables are global on Android /system/bin/sh. Keep function-specific
    # names here: the old generic _task variable was cleared by luoshu_clear_task_pid(), so
    # every new worker wrote an empty .task sidecar and was falsely recovered as interrupted.
    luoshu_clear_task_pid "$_lsd_pid_file"

    if command -v nohup >/dev/null 2>&1 && command -v setsid >/dev/null 2>&1; then
        MODDIR="${MODDIR:-}" nohup setsid "$@" </dev/null >>"$_lsd_log_file" 2>&1 &
    elif command -v toybox >/dev/null 2>&1 && toybox nohup --help >/dev/null 2>&1 && toybox setsid --help >/dev/null 2>&1; then
        MODDIR="${MODDIR:-}" toybox nohup toybox setsid "$@" </dev/null >>"$_lsd_log_file" 2>&1 &
    elif command -v nohup >/dev/null 2>&1; then
        MODDIR="${MODDIR:-}" nohup "$@" </dev/null >>"$_lsd_log_file" 2>&1 &
    else
        ( trap '' HUP; exec "$@" ) </dev/null >>"$_lsd_log_file" 2>&1 &
    fi
    _lsd_pid=$!
    case "$_lsd_pid" in ''|*[!0-9]*) return 1 ;; esac
    printf '%s\n' "$_lsd_pid" >"$_lsd_pid_file" 2>/dev/null || return 1
    printf '%s\n' "$_lsd_task" >"${_lsd_pid_file}.task" 2>/dev/null || true
    chmod 0644 "$_lsd_pid_file" "${_lsd_pid_file}.task" 2>/dev/null || true
    return 0
}
