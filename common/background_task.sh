#!/system/bin/sh
# Root 后台任务启动器：脱离 App 的 su 会话、终端与进程组。

luoshu_current_boot_id() {
    _lcbi_value=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n')
    [ -n "$_lcbi_value" ] || _lcbi_value=$(getprop ro.runtime.firstboot 2>/dev/null | tr -d '\r\n')
    [ -n "$_lcbi_value" ] || _lcbi_value=unknown
    printf '%s\n' "$_lcbi_value"
}

luoshu_pid_value() {
    _lpv_file="$1"
    sed -n '1{s/[^0-9].*$//;p;}' "$_lpv_file" 2>/dev/null
}

# /proc stat field 22 is a process birth identity, unlike a reusable numeric PID.
luoshu_pid_start() (
    case "$1" in ''|*[!0-9]*|0|1) return 1 ;; esac
    IFS= read -r _lps_stat 2>/dev/null < "${LUOSHU_PROC_ROOT:-/proc}/$1/stat" || return 1
    _lps_tail=${_lps_stat##*) }
    [ "$_lps_tail" != "$_lps_stat" ] || return 1
    set -- $_lps_tail
    [ "$#" -ge 20 ] || return 1
    case "$1" in Z|X) return 1 ;; esac
    shift 19
    printf '%s\n' "$1"
)

luoshu_task_pid_alive() (
    _ltpa_pid_file="$1"
    _ltpa_task="${2:-}"
    _ltpa_pid=$(luoshu_pid_value "$_ltpa_pid_file")
    case "$_ltpa_pid" in ''|*[!0-9]*|0|1) return 1 ;; esac
    # Missing identity fails closed. A bare old PID is never authority to keep
    # a task busy or to signal any process (even if its command line matches).
    [ -s "${_ltpa_pid_file}.boot" ] && [ -s "${_ltpa_pid_file}.start" ] &&
        [ -s "${_ltpa_pid_file}.task" ] || return 1
    [ "$(cat "${_ltpa_pid_file}.boot" 2>/dev/null)" = "$(luoshu_current_boot_id)" ] || return 1
    _ltpa_start=$(luoshu_pid_start "$_ltpa_pid") || return 1
    [ "$_ltpa_start" = "$(cat "${_ltpa_pid_file}.start" 2>/dev/null)" ] || return 1
    [ -z "$_ltpa_task" ] || [ "$(cat "${_ltpa_pid_file}.task" 2>/dev/null)" = "$_ltpa_task" ] || return 1
    kill -0 "$_ltpa_pid" 2>/dev/null
)

luoshu_clear_task_pid() (
    _lctp_pid_file="$1"
    _lctp_task="${2:-}"
    if [ -n "$_lctp_task" ] && [ -s "${_lctp_pid_file}.task" ] && [ "$(cat "${_lctp_pid_file}.task" 2>/dev/null)" != "$_lctp_task" ]; then
        return 0
    fi
    # Workers cannot erase their supervisor before orphan cleanup has finished.
    # The supervisor removes these files after reaping its complete scope.
    [ -z "${LUOSHU_TASK_SCOPE:-}" ] || [ "$(cat "${_lctp_pid_file}.scope" 2>/dev/null)" != "$LUOSHU_TASK_SCOPE" ] || return 0
    luoshu_task_pid_alive "$_lctp_pid_file" "$_lctp_task" && return 0
    # A dead reaper can leave proven descendants; keep its recovery manifest.
    [ ! -s "${_lctp_pid_file}.identity" ] || return 0
    rm -f "$_lctp_pid_file" "${_lctp_pid_file}.task" "${_lctp_pid_file}.boot" \
        "${_lctp_pid_file}.start" "${_lctp_pid_file}.scope" 2>/dev/null || true
)

# Resolve the real module even through the frozen legacy runtime symlinks.
# The final two candidates also support the repository's standalone host tests.
luoshu_task_runtime() {
    _ltr_helper="${LUOSHU_TASK_HELPER:-}"
    for _ltr_base in "${LUOSHU_REAL_MODDIR:-}" "${MODDIR:-}" "${0%/*}" "${0%/*}/.."; do
        [ -n "$_ltr_helper" ] && break
        [ -n "$_ltr_base" ] || continue
        if [ -f "$_ltr_base/common/task_scope.py" ]; then
            _ltr_helper="$_ltr_base/common/task_scope.py"
        elif [ -f "$_ltr_base/task_scope.py" ]; then
            _ltr_helper="$_ltr_base/task_scope.py"
        fi
    done
    [ -f "$_ltr_helper" ] || return 1
    _ltr_helper=$(readlink -f "$_ltr_helper" 2>/dev/null) || return 1
    _ltr_root=${_ltr_helper%/*}/python
    if [ ! -e /system/bin/sh ] && command -v python3 >/dev/null 2>&1; then
        _ltr_python=$(command -v python3)
        _ltr_bundled=0
    elif [ -x "$_ltr_root/bin/luoshu-python" ]; then
        _ltr_python="$_ltr_root/bin/luoshu-python"
        _ltr_bundled=1
    else
        return 1
    fi
}

luoshu_task_helper() (
    luoshu_task_runtime || { echo '[task-scope] missing bounded task runtime' >&2; return 1; }
    if [ "$_ltr_bundled" = 1 ]; then
        export PYTHONHOME="$_ltr_root"
        export PYTHONPATH="$_ltr_root/lib/python3.14:$_ltr_root/lib/python3.14/site-packages"
        export LD_LIBRARY_PATH="$_ltr_root/lib:$_ltr_root/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    fi
    exec "$_ltr_python" "$_ltr_helper" "$@"
)

luoshu_stop_task_pid() (
    _lstp_pid_file="$1"
    _lstp_task="${2:-$(cat "${_lstp_pid_file}.task" 2>/dev/null)}"
    if [ -s "${_lstp_pid_file}.identity" ]; then
        luoshu_task_helper stop "$_lstp_pid_file" "$_lstp_task"
        return $?
    fi
    # Legacy sidecars cannot prove scope; do not signal their numeric PID.
    luoshu_clear_task_pid "$_lstp_pid_file" "$_lstp_task"
)

# Compatibility for a known freshly launched child. The helper pins every
# external PID with pidfd; no process-name/ps-grep or unverified group signals.
# New managed tasks use their subreaper scope, which also covers lost parents.
luoshu_terminate_task_tree() (
    _ltt_root="$1"
    case "$_ltt_root" in ''|*[!0-9]*|0|1) return 1 ;; esac
    [ "$_ltt_root" != "$$" ] && [ -n "${2:-}" ] || return 1
    luoshu_task_helper tree "$_ltt_root" "$2"
)

luoshu_start_detached() (
    _lsd_pid_file="$1"
    _lsd_task="$2"
    _lsd_log_file="$3"
    shift 3
    [ "$#" -gt 0 ] || return 2
    # Cache prewarming is optional. Never create another job after a font
    # transaction, or outside one: switching must return the module to idle.
    case "${_lsd_pid_file##*/}" in font-prewarm-*.pid) return 0 ;; esac
    # Python start_new_session is the equivalent of nohup setsid, with a finite
    # child subreaper added. It NEVER calls unshare or creates a mount namespace.
    luoshu_task_helper launch "$_lsd_pid_file" "$_lsd_task" "$_lsd_log_file" -- "$@"
)
