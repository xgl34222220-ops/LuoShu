#!/system/bin/sh
# Root 后台任务启动器：脱离 App 的 su 会话、终端与进程组。

luoshu_pid_value() {
    sed -n '1{s/[^0-9].*$//;p;}' "$1" 2>/dev/null
}

luoshu_task_pid_alive() {
    _pid_file="$1"
    _task="${2:-}"
    _pid=$(luoshu_pid_value "$_pid_file")
    [ -n "$_pid" ] || return 1
    kill -0 "$_pid" 2>/dev/null || return 1
    if [ -n "$_task" ]; then
        # A numeric PID can be recycled by Android. The task sidecar and, when available,
        # the worker command line must both still belong to the same LuoShu task.
        [ -s "${_pid_file}.task" ] || return 1
        [ "$(cat "${_pid_file}.task" 2>/dev/null)" = "$_task" ] || return 1
        if [ -r "/proc/$_pid/cmdline" ]; then
            _cmdline=$(tr '\000' ' ' < "/proc/$_pid/cmdline" 2>/dev/null)
            case "$_cmdline" in *"$_task"*) ;; *) return 1 ;; esac
        fi
    fi
    return 0
}

luoshu_clear_task_pid() {
    _pid_file="$1"
    _task="${2:-}"
    if [ -n "$_task" ] && [ -s "${_pid_file}.task" ] && [ "$(cat "${_pid_file}.task" 2>/dev/null)" != "$_task" ]; then
        return 0
    fi
    rm -f "$_pid_file" "${_pid_file}.task" 2>/dev/null || true
}

luoshu_stop_task_pid() {
    _pid_file="$1"
    _pid=$(luoshu_pid_value "$_pid_file")
    [ -z "$_pid" ] || ! kill -0 "$_pid" 2>/dev/null || kill "$_pid" 2>/dev/null || true
    luoshu_clear_task_pid "$_pid_file"
}

luoshu_start_detached() {
    _pid_file="$1"
    _task="$2"
    _log_file="$3"
    shift 3
    [ "$#" -gt 0 ] || return 2
    mkdir -p "${_pid_file%/*}" "${_log_file%/*}" 2>/dev/null || return 1
    if luoshu_task_pid_alive "$_pid_file" "$_task"; then
        return 3
    fi
    luoshu_clear_task_pid "$_pid_file"

    if command -v nohup >/dev/null 2>&1 && command -v setsid >/dev/null 2>&1; then
        MODDIR="${MODDIR:-}" nohup setsid "$@" </dev/null >>"$_log_file" 2>&1 &
    elif command -v toybox >/dev/null 2>&1 && toybox nohup --help >/dev/null 2>&1 && toybox setsid --help >/dev/null 2>&1; then
        MODDIR="${MODDIR:-}" toybox nohup toybox setsid "$@" </dev/null >>"$_log_file" 2>&1 &
    elif command -v nohup >/dev/null 2>&1; then
        MODDIR="${MODDIR:-}" nohup "$@" </dev/null >>"$_log_file" 2>&1 &
    else
        ( trap '' HUP; exec "$@" ) </dev/null >>"$_log_file" 2>&1 &
    fi
    _pid=$!
    case "$_pid" in ''|*[!0-9]*) return 1 ;; esac
    printf '%s\n' "$_pid" >"$_pid_file" 2>/dev/null || return 1
    printf '%s\n' "$_task" >"${_pid_file}.task" 2>/dev/null || true
    chmod 0644 "$_pid_file" "${_pid_file}.task" 2>/dev/null || true
    return 0
}
