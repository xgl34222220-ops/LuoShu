#!/system/bin/sh
# Bounded task launch and verified cancellation; no process-name/group kills.

luoshu_scope_runner() {
    printf '%s\n' "${LUOSHU_TASK_SCOPE_RUNNER:-${LUOSHU_REAL_MODDIR:-${MODDIR:-${MODULE_DIR:-}}}/common/task_scope.sh}"
}

luoshu_scope_run() {
    _lsr_task="$1"; _lsr_timeout="$2"; shift 2
    sh "$(luoshu_scope_runner)" request-run "$_lsr_task" "$_lsr_timeout" -- "$@"
}

luoshu_stop_module_tasks() (
    _lsmt_module="$1"
    sh "$(luoshu_scope_runner)" cancel-all "$_lsmt_module"
)

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

luoshu_task_pid_alive() {
    _ltpa_pid_file="$1"
    _ltpa_task="${2:-}"
    if [ -f "${_ltpa_pid_file}.owner.json" ]; then
        sh "$(luoshu_scope_runner)" alive "$_ltpa_pid_file" "$_ltpa_task" >/dev/null 2>&1
        return $?
    fi
    _ltpa_pid=$(luoshu_pid_value "$_ltpa_pid_file")
    [ -n "$_ltpa_pid" ] || return 1

    # PID 在完整重启后可能被复用。带 boot sidecar 的任务必须属于当前启动周期。
    if [ -s "${_ltpa_pid_file}.boot" ]; then
        _ltpa_expected_boot=$(cat "${_ltpa_pid_file}.boot" 2>/dev/null | tr -d '\r\n')
        _ltpa_current_boot=$(luoshu_current_boot_id)
        [ -n "$_ltpa_expected_boot" ] && [ "$_ltpa_expected_boot" = "$_ltpa_current_boot" ] || return 1
    fi

    # Pre-scope records have no proof of ownership. Never trust PID alone.
    [ -s "${_ltpa_pid_file}.start" ] && [ -s "${_ltpa_pid_file}.boot" ] || return 1
    _ltpa_stat=$(cat "/proc/$_ltpa_pid/stat" 2>/dev/null) || return 1
    _ltpa_tail=${_ltpa_stat##*) }
    set -- $_ltpa_tail
    [ "$1" != Z ] || return 1
    shift 19
    [ "$1" = "$(cat "${_ltpa_pid_file}.start" 2>/dev/null)" ] || return 1
    kill -0 "$_ltpa_pid" 2>/dev/null || return 1
    if [ -n "$_ltpa_task" ]; then
        # A numeric PID can be recycled by Android. The task sidecar and, when available,
        # the worker command line must both still belong to the same LuoShu task.
        [ -s "${_ltpa_pid_file}.task" ] || return 1
        [ "$(cat "${_ltpa_pid_file}.task" 2>/dev/null)" = "$_ltpa_task" ] || return 1
        if [ -r "/proc/$_ltpa_pid/cmdline" ]; then
            tr '\000' '\n' < "/proc/$_ltpa_pid/cmdline" 2>/dev/null | grep -Fqx -- "$_ltpa_task" || return 1
        fi
    fi
    return 0
}

luoshu_clear_task_pid() {
    _lctp_pid_file="$1"
    _lctp_task="${2:-}"
    # A worker's terminal write occurs before the supervisor reaps descendants.
    # Only the supervisor may clear its live ownership record.
    [ "${LUOSHU_TASK_SCOPE_PIDFILE:-}" != "$_lctp_pid_file" ] || return 0
    # Do not erase evidence after an externally SIGKILLed supervisor, nor
    # pre-scope sidecars from this boot without a proof of child cleanup.
    luoshu_task_pid_alive "$_lctp_pid_file" "$_lctp_task" && return 0
    if [ -n "$_lctp_task" ] && [ -s "${_lctp_pid_file}.task" ] && [ "$(cat "${_lctp_pid_file}.task" 2>/dev/null)" != "$_lctp_task" ]; then
        return 0
    fi
    sh "$(luoshu_scope_runner)" cancel "$_lctp_pid_file" "$_lctp_task" >/dev/null 2>&1
}

luoshu_stop_task_pid() {
    _lstp_pid_file="$1"
    _lstp_task="${2:-$(cat "${_lstp_pid_file}.task" 2>/dev/null)}"
    sh "$(luoshu_scope_runner)" cancel "$_lstp_pid_file" "$_lstp_task"
}

# Cancellation is rare: take one process-tree snapshot, rather than running a
# pgrep for every child. Keep the descendants after their parents exit so a
# grandchild FontTools worker cannot escape the final KILL by being reparented.
# Start-time checks keep the saved list from signalling a recycled PID.
luoshu_terminate_task_tree() (
    _ltt_root="$1"
    case "$_ltt_root" in ''|*[!0-9]*|0|1) return 1 ;; esac
    [ "$_ltt_root" != "$$" ] || return 1
    _ltt_proc_root="${LUOSHU_PROC_ROOT:-/proc}"
    _ltt_identity() {
        IFS= read -r _ltt_stat 2>/dev/null < "$_ltt_proc_root/$1/stat" || return 1
        _ltt_tail=${_ltt_stat##*) }
        [ "$_ltt_tail" != "$_ltt_stat" ] || return 1
        set -- $_ltt_tail
        [ "$#" -ge 20 ] || return 1
        shift 19
        printf '%s\n' "$1"
    }
    _ltt_pids=$(ps -A -o PID,PPID 2>/dev/null | awk -v root="$_ltt_root" '
        $1 ~ /^[0-9]+$/ && $2 ~ /^[0-9]+$/ { parent[$1] = $2 }
        function children(p, child) {
            if (seen[p]++) return
            for (child in parent) if (parent[child] == p) children(child)
            print p
        }
        END { children(root) }
    ')
    _ltt_saved=$(
        for _ltt_pid in $_ltt_pids; do
            _ltt_start=$(_ltt_identity "$_ltt_pid") || continue
            printf '%s:%s\n' "$_ltt_pid" "$_ltt_start"
        done
    )
    for _ltt_signal in TERM KILL; do
        for _ltt_record in $_ltt_saved; do
            _ltt_pid=${_ltt_record%%:*}
            _ltt_start=${_ltt_record#*:}
            [ "$(_ltt_identity "$_ltt_pid" 2>/dev/null)" = "$_ltt_start" ] || continue
            kill -"$_ltt_signal" "$_ltt_pid" 2>/dev/null || true
        done
        [ "$_ltt_signal" != TERM ] || sleep 1
    done
)

luoshu_start_detached() {
    _lsd_pid_file="$1"
    _lsd_task="$2"
    _lsd_log_file="$3"
    shift 3
    [ "$#" -gt 0 ] || return 2
    mkdir -p "${_lsd_pid_file%/*}" "${_lsd_log_file%/*}" 2>/dev/null || return 1
    if luoshu_task_pid_alive "$_lsd_pid_file"; then
        return 3
    fi

    # Shell function variables are global on Android /system/bin/sh. Keep function-specific
    # names here: the old generic _task variable was cleared by luoshu_clear_task_pid(), so
    # every new worker wrote an empty .task sidecar and was falsely recovered as interrupted.
    luoshu_clear_task_pid "$_lsd_pid_file" || return $?
    # The supervisor replaces cleanup evidence only after its locked recheck.

    _lsd_runner=$(luoshu_scope_runner)
    [ -f "$_lsd_runner" ] || return 126
    _lsd_timeout="${LUOSHU_TASK_TIMEOUT_SECONDS:-900}"
    ( trap '' HUP; exec sh "$_lsd_runner" run --pid-file "$_lsd_pid_file" \
        --task "$_lsd_task" --timeout "$_lsd_timeout" -- "$@" ) </dev/null >>"$_lsd_log_file" 2>&1 &
    _lsd_pid=$!
    case "$_lsd_pid" in ''|*[!0-9]*) return 1 ;; esac
    # Identity and ready handshake are written by the supervisor, never $!.
    # A very fast task may already have a complete cleanup proof instead.
    _lsd_tries=0
    while [ "$_lsd_tries" -lt 100 ]; do
        [ "$(cat "${_lsd_pid_file}.ready" 2>/dev/null)" != "$_lsd_task" ] || return 0
        if grep -Fq '"task": "'"$_lsd_task"'"' "${_lsd_pid_file}.cleanup.json" 2>/dev/null; then
            return 0
        fi
        kill -0 "$_lsd_pid" 2>/dev/null || { wait "$_lsd_pid" 2>/dev/null; return 1; }
        sleep .02
        _lsd_tries=$((_lsd_tries + 1))
    done
    luoshu_stop_task_pid "$_lsd_pid_file" "$_lsd_task" >/dev/null 2>&1 || true
    return 1
}
