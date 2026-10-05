#!/system/bin/sh
# LuoShu foreground font switch task guard.
# The worker is detached from the App. Task ownership is verified with PID + task
# sidecar + boot ID so recycled Android PIDs can never keep a dead task locked.
set +e

MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then
        MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"
    else
        MODDIR="/data/adb/modules/LuoShu"
    fi
fi
MODULE_DIR="$MODDIR"
[ -f "$MODDIR/common/runtime_paths.sh" ] && {
    . "$MODDIR/common/runtime_paths.sh"
    luoshu_runtime_paths_init "$MODDIR" || exit 126
}
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
MANAGER="${LUOSHU_FONT_MANAGER:-$MODDIR/common/font_manager.sh}"
TASK_FILE="${LUOSHU_SWITCH_TASK_FILE:-$MODDIR/config/switch_task.conf}"
LOG_FILE="${LUOSHU_SWITCH_LOG:-$MODDIR/logs/fontswitch.log}"
STATUS_SCRIPT="$MODDIR/common/module_status.sh"
HISTORY_TOOL="$MODDIR/system/bin/luoshu-history"
BACKGROUND_TASK="$MODDIR/common/background_task.sh"
WORKER_PID_FILE="${LUOSHU_SWITCH_WORKER_PID_FILE:-${LUOSHU_TASKS_DIR:-$MODDIR/.luoshu-state/tasks}/switch_task_worker.pid}"
LOAD_VERIFY_STATE="$MODDIR/config/device-font-load-verification.conf"
LIVE_JOURNAL="$MODDIR/config/font-live-transaction.conf"
NEXT_STATE="$MODDIR/config/font-payload-next.conf"
[ -f "$BACKGROUND_TASK" ] && . "$BACKGROUND_TASK"
START_LOCK="${LUOSHU_SWITCH_START_LOCK:-${LUOSHU_TASKS_DIR:-$MODDIR/.luoshu-state/tasks}/font_switch_start.lock}"

TIMEOUT_SECONDS="${LUOSHU_SWITCH_TIMEOUT_SECONDS:-360}"
case "$TIMEOUT_SECONDS" in ''|*[!0-9]*) TIMEOUT_SECONDS=360 ;; esac
[ "$TIMEOUT_SECONDS" -ge 30 ] 2>/dev/null || TIMEOUT_SECONDS=30
[ "$TIMEOUT_SECONDS" -le 900 ] 2>/dev/null || TIMEOUT_SECONDS=900
HEARTBEAT_INTERVAL="${LUOSHU_SWITCH_HEARTBEAT_INTERVAL:-2}"
case "$HEARTBEAT_INTERVAL" in ''|*[!0-9]*) HEARTBEAT_INTERVAL=2 ;; esac
[ "$HEARTBEAT_INTERVAL" -ge 1 ] 2>/dev/null || HEARTBEAT_INTERVAL=1
[ "$HEARTBEAT_INTERVAL" -le 10 ] 2>/dev/null || HEARTBEAT_INTERVAL=10

json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
}

current_boot_id() {
    if type luoshu_current_boot_id >/dev/null 2>&1; then
        luoshu_current_boot_id
        return
    fi
    _id=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n')
    [ -n "$_id" ] || _id=$(getprop ro.runtime.firstboot 2>/dev/null | tr -d '\r\n')
    [ -n "$_id" ] || _id=unknown
    printf '%s\n' "$_id"
}

read_value() {
    sed -n "s/^${1}=//p" "$TASK_FILE" 2>/dev/null | head -n1 | tr -d '\r\n'
}

write_task() {
    _task="$1"; _state="$2"; _font="$3"; _message="$4"
    _started="$5"; _finished="$6"; _pid="$7"
    _heartbeat="${8:-$(date +%s 2>/dev/null || echo 0)}"
    _timeout="${9:-$TIMEOUT_SECONDS}"; _elapsed="${10:-0}"
    _boot="${11:-$(current_boot_id)}"; _reused="${12:-false}"; _percent="${13:-0}"
    _terminal_state="${14:-}"; _terminal_message="${15:-}"; _cleanup_confirmed="${16:-false}"
    _live_applied="${17:-false}"; _activation="${18:-pending-reboot}"
    [ "$_reused" = true ] || _reused=false
    [ "$_cleanup_confirmed" = true ] || _cleanup_confirmed=false
    [ "$_live_applied" = true ] || _live_applied=false
    case "$_percent" in ''|*[!0-9]*) _percent=0 ;; esac
    [ "$_percent" -ge 0 ] 2>/dev/null || _percent=0
    [ "$_percent" -le 100 ] 2>/dev/null || _percent=100
    mkdir -p "${TASK_FILE%/*}" 2>/dev/null || return 1
    _tmp="${TASK_FILE}.tmp.$$"
    {
        printf 'task=%s\n' "$_task"
        printf 'state=%s\n' "$_state"
        printf 'font=%s\n' "$_font"
        printf 'message=%s\n' "$_message"
        printf 'started=%s\n' "$_started"
        printf 'finished=%s\n' "$_finished"
        printf 'pid=%s\n' "$_pid"
        printf 'heartbeat=%s\n' "$_heartbeat"
        printf 'timeout=%s\n' "$_timeout"
        printf 'elapsed=%s\n' "$_elapsed"
        printf 'percent=%s\n' "$_percent"
        printf 'bootId=%s\n' "$_boot"
        printf 'reused=%s\n' "$_reused"
        printf 'terminalState=%s\n' "$_terminal_state"
        printf 'terminalMessage=%s\n' "$_terminal_message"
        printf 'cleanupConfirmed=%s\n' "$_cleanup_confirmed"
        printf 'liveApplied=%s\n' "$_live_applied"
        printf 'activation=%s\n' "$_activation"
    } > "$_tmp" 2>/dev/null || return 1
    mv -f "$_tmp" "$TASK_FILE" 2>/dev/null || return 1
    chmod 0644 "$TASK_FILE" 2>/dev/null || true
}

mark_load_verification_pending() {
    _font="$1"; _tmp="${LOAD_VERIFY_STATE}.tmp.$$"
    mkdir -p "${LOAD_VERIFY_STATE%/*}" 2>/dev/null || return 1
    {
        printf 'state=pending\n'
        printf 'mode=compatibility\n'
        printf 'activeFont=%s\n' "$_font"
        printf 'reason=awaiting-full-reboot\n'
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_tmp" 2>/dev/null || return 1
    mv -f "$_tmp" "$LOAD_VERIFY_STATE" 2>/dev/null || return 1
    chmod 0600 "$LOAD_VERIFY_STATE" 2>/dev/null || true
}

pid_alive() {
    case "$1" in ''|*[!0-9]*) return 1 ;; esac
    kill -0 "$1" 2>/dev/null
}

worker_alive() {
    _task="$1"; _pid="$2"
    if type luoshu_task_pid_alive >/dev/null 2>&1; then
        luoshu_task_pid_alive "$WORKER_PID_FILE" "$_task"
        return $?
    fi
    pid_alive "$_pid"
}

live_journal_pending() {
    [ -e "$LIVE_JOURNAL" ] || [ -L "$LIVE_JOURNAL" ]
}

recover_live_transaction() {
    live_journal_pending || return 0
    [ -f "$MODDIR/common/font_live_switch.sh" ] || return 125
    # Recovery is launched only after exact process cleanup and is itself
    # finite. Never clear a pending mount journal on process proof alone.
    _rlt_token="font-live-recover-$$-$(date +%s 2>/dev/null || echo 0)"
    MODDIR="$MODDIR" sh "$(luoshu_scope_runner)" request-run "$_rlt_token" 30 -- \
        sh "$MODDIR/common/font_live_switch.sh" recover >/dev/null 2>&1 || return 125
    live_journal_pending && return 125
    return 0
}

start_lock_acquire() {
    if type luoshu_font_lock_acquire >/dev/null 2>&1; then
        luoshu_font_lock_acquire "$START_LOCK" "$$"
        return $?
    fi
    mkdir "$START_LOCK" 2>/dev/null || return 2
    printf '%s\n' "$$" > "$START_LOCK/pid" 2>/dev/null || { rmdir "$START_LOCK" 2>/dev/null || true; return 1; }
}

start_lock_release() {
    if type luoshu_font_lock_release >/dev/null 2>&1; then
        luoshu_font_lock_release "$START_LOCK" "$$" >/dev/null 2>&1 || true
        return 0
    fi
    _owner=$(sed -n '1p' "$START_LOCK/pid" 2>/dev/null)
    [ -z "$_owner" ] || [ "$_owner" = "$$" ] || return 1
    rm -f "$START_LOCK/pid" 2>/dev/null || true
    rmdir "$START_LOCK" 2>/dev/null || true
}

reconcile_task() {
    [ -s "$TASK_FILE" ] || return 0
    _rt_state=$(read_value state)
    case "$_rt_state" in queued|running|success|failed|cleanup-pending) ;; *) return 0 ;; esac
    _rt_task=$(read_value task); _rt_font=$(read_value font); _rt_started=$(read_value started)
    _rt_pid=$(read_value pid); _rt_boot=$(read_value bootId); _rt_now_boot=$(current_boot_id)
    _rt_percent=$(read_value percent); _rt_elapsed=$(read_value elapsed)
    _rt_message=$(read_value message); _rt_reused=$(read_value reused)
    _rt_terminal=$(read_value terminalState); _rt_terminal_message=$(read_value terminalMessage)
    _rt_confirmed=$(read_value cleanupConfirmed)
    _rt_live=$(read_value liveApplied); _rt_activation=$(read_value activation)
    case "$_rt_started" in ''|*[!0-9]*) _rt_started=0 ;; esac

    if [ -n "$_rt_boot" ] && [ -n "$_rt_now_boot" ] && [ "$_rt_boot" != "$_rt_now_boot" ]; then
        if live_journal_pending; then
            write_task "$_rt_task" cleanup-pending "$_rt_font" '字体挂载事务等待恢复，请刷新重试' \
                "$_rt_started" '' '' '' '' "${_rt_elapsed:-0}" "$_rt_boot" false 100 failed '设备已重启，上一字体切换任务已结束'
        else
            case "$_rt_state" in queued|running|cleanup-pending)
            write_task "$_rt_task" failed "$_rt_font" '设备已重启，上一字体切换任务已结束' \
                "$_rt_started" "$(date +%s 2>/dev/null || echo 0)" '' '' '' "${_rt_elapsed:-0}" "$_rt_boot" false 100 '' '' true
            ;;
            esac
        fi
        type luoshu_clear_task_pid >/dev/null 2>&1 && luoshu_clear_task_pid "$WORKER_PID_FILE" "$_rt_task"
        return 0
    fi

    worker_alive "$_rt_task" "$_rt_pid" && return 0

    case "$_rt_state" in success|failed|cleanup-pending)
        if ! live_journal_pending && { sh "$(luoshu_scope_runner)" cleaned "$WORKER_PID_FILE" "$_rt_task" >/dev/null 2>&1 || [ "$_rt_confirmed" = true ]; }; then
            if [ "$_rt_state" = cleanup-pending ]; then
                case "$_rt_terminal" in success|failed) ;; *) _rt_terminal=failed ;; esac
                [ -n "$_rt_terminal_message" ] || _rt_terminal_message='任务子进程已回收'
                write_task "$_rt_task" "$_rt_terminal" "$_rt_font" "$_rt_terminal_message" \
                    "$_rt_started" "$(date +%s 2>/dev/null || echo 0)" '' '' '' "${_rt_elapsed:-0}" "$_rt_boot" "$_rt_reused" 100 '' '' true "$_rt_live" "$_rt_activation"
            fi
            return 0
        fi
        if [ "$_rt_state" != cleanup-pending ]; then
            write_task "$_rt_task" cleanup-pending "$_rt_font" '任务清理尚未确认，请刷新重试' \
                "$_rt_started" '' '' '' '' "${_rt_elapsed:-0}" "$_rt_boot" "$_rt_reused" "${_rt_percent:-100}" "$_rt_state" "$_rt_message" false "$_rt_live" "$_rt_activation"
        fi
        return 0
        ;;
    esac

    # Give a freshly queued worker a short spawn grace period. After that, a missing
    # supervisor must be settled before releasing the task for another switch.
    _rt_now=$(date +%s 2>/dev/null || echo 0)
    _rt_age=$((_rt_now - _rt_started))
    [ "$_rt_state" = queued ] && [ "$_rt_age" -ge 0 ] 2>/dev/null && [ "$_rt_age" -lt 8 ] 2>/dev/null && return 0

    if luoshu_clear_task_pid "$WORKER_PID_FILE" "$_rt_task" && ! live_journal_pending; then
        write_task "$_rt_task" failed "$_rt_font" '字体切换进程已结束，任务子进程已回收' \
            "$_rt_started" "$_rt_now" '' '' '' "${_rt_elapsed:-0}" "$_rt_now_boot" false 100 '' '' true
    else
        write_task "$_rt_task" cleanup-pending "$_rt_font" '任务清理尚未确认，请刷新重试' \
            "$_rt_started" '' '' '' '' "${_rt_elapsed:-0}" "$_rt_now_boot" false "${_rt_percent:-0}" failed '字体切换进程已结束'
    fi
}

terminate_child_tree() {
    if type luoshu_terminate_task_tree >/dev/null 2>&1; then
        luoshu_terminate_task_tree "$1"
    else
        kill -TERM "$1" 2>/dev/null || true
    fi
}

progress_value() {
    _file="$1"; _fallback="$2"
    _p=$(sed -n 's/^percent=//p' "$_file" 2>/dev/null | head -n1)
    case "$_p" in ''|*[!0-9]*) _p="$_fallback" ;; esac
    [ "$_p" -le 95 ] 2>/dev/null || _p=95
    printf '%s\n' "$_p"
}

progress_message() {
    _file="$1"; _fallback="$2"; _p="$3"
    _m=$(sed -n 's/^message=//p' "$_file" 2>/dev/null | head -n1 | tr -d '\r\n')
    [ -n "$_m" ] || _m="$_fallback"
    printf '%s%% · %s\n' "$_p" "$_m"
}

run_bounded() {
    _font="$1"; _output="$2"; _task="$3"; _started="$4"; _progress_file="$5"
    _switch_manager_pidfile="${LUOSHU_TASKS_DIR:-$MODDIR/.luoshu-state/tasks}/switch-manager-$_task.pid"
    LUOSHU_SWITCH_PROGRESS_FILE="$_progress_file" LUOSHU_SWITCH_REQUEST_ID="$_task" sh "$(luoshu_scope_runner)" run \
        --pid-file "$_switch_manager_pidfile" --task "manager-$_task" --timeout "$TIMEOUT_SECONDS" \
        -- sh "$MANAGER" action switch "$_font" > "$_output" 2>&1 &
    _child=$!; _switch_child=$_child; _elapsed=0; _next_heartbeat=0
    while pid_alive "$_child"; do
        if [ "$_elapsed" -ge "$_next_heartbeat" ]; then
            _fallback=$((5 + (_elapsed * 80 / TIMEOUT_SECONDS)))
            [ "$_fallback" -le 85 ] 2>/dev/null || _fallback=85
            _percent=$(progress_value "$_progress_file" "$_fallback")
            _message=$(progress_message "$_progress_file" '正在准备下一启动字体负载' "$_percent")
            write_task "$_task" running "$_font" "$_message" "$_started" '' "$$" \
                "$(date +%s 2>/dev/null || echo 0)" "$TIMEOUT_SECONDS" "$_elapsed" "$(current_boot_id)" false "$_percent" || true
            _next_heartbeat=$((_elapsed + HEARTBEAT_INTERVAL))
        fi
        sleep 1; _elapsed=$((_elapsed + 1))
    done
    wait "$_child"
    _switch_rc=$?
    _switch_child=
    return "$_switch_rc"
}

worker_signal_exit() {
    _switch_signal_code="$1"
    trap '' HUP INT TERM
    if [ -n "${_switch_child:-}" ]; then
        if [ -n "${_switch_manager_pidfile:-}" ]; then
            luoshu_stop_task_pid "$_switch_manager_pidfile" "manager-$_worker_task" >/dev/null 2>&1 || true
        fi
        wait "$_switch_child" 2>/dev/null || true
        _switch_child=
    fi
    write_task "$_worker_task" failed "$_font" '字体切换已终止，当前启动字体未被改动' \
        "$_started" "$(date +%s 2>/dev/null || echo 0)" '' '' '' "${_elapsed:-0}" '' false 100 || true
    exit "$_switch_signal_code"
}

run_worker() {
    _task="$1"; _font="$2"; _started="$3"
    _worker_task=$_task
    _output="${LUOSHU_TASK_SCOPE_TMPDIR:-${LUOSHU_TMP_DIR:-${TASK_FILE%/*}}}/switch.output.${_task}"
    _progress="${LUOSHU_TASK_SCOPE_TMPDIR:-${LUOSHU_TMP_DIR:-${TASK_FILE%/*}}}/switch.progress.${_task}"
    trap 'rm -f "$_output" "$_progress" 2>/dev/null || true; type luoshu_clear_task_pid >/dev/null 2>&1 && luoshu_clear_task_pid "$WORKER_PID_FILE" "$_worker_task"' EXIT
    trap 'worker_signal_exit 129' HUP
    trap 'worker_signal_exit 130' INT
    trap 'worker_signal_exit 143' TERM
    mkdir -p "${LOG_FILE%/*}" "${_output%/*}" 2>/dev/null || true
    printf 'percent=2\nmessage=正在启动字体切换任务\n' > "$_progress" 2>/dev/null || true
    write_task "$_task" running "$_font" '2% · 正在启动字体切换任务' "$_started" '' "$$" '' '' 0 '' false 2 || exit 1
    printf '[%s] safe switch start: %s task=%s timeout=%ss\n' \
        "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$_font" "$_task" "$TIMEOUT_SECONDS" >> "$LOG_FILE" 2>/dev/null || true

    run_bounded "$_font" "$_output" "$_task" "$_started" "$_progress"
    _rc=$?; _finished=$(date +%s 2>/dev/null || echo 0)
    if [ "$_rc" -eq 0 ] && grep -q '"status":"ok"' "$_output" 2>/dev/null; then
        cat "$_output" >> "$LOG_FILE" 2>/dev/null || true
        if grep -q '"reused":true' "$_output" 2>/dev/null; then
            write_task "$_task" success "$_font" '100% · 当前字体已验证，无需重新生成或重启' \
                "$_started" "$_finished" '' '' '' 0 '' true 100
        else
            mark_load_verification_pending "$_font" || true
            if grep -q '"liveApplied":true' "$_output" 2>/dev/null; then
                write_task "$_task" success "$_font" '100% · 当前启动已挂载新字体，重启后完整生效' \
                    "$_started" "$_finished" '' '' '' 0 '' false 100 '' '' false true live-mounted
            else
                write_task "$_task" success "$_font" '100% · 字体已准备完成，完整重启后生效' \
                    "$_started" "$_finished" '' '' '' 0 '' false 100
            fi
            [ -f "$HISTORY_TOOL" ] && MODDIR="$MODDIR" sh "$HISTORY_TOOL" record-direct "$_font" >/dev/null 2>&1 || true
        fi
    elif [ "$_rc" -eq 124 ] || [ "$_rc" -eq 137 ]; then
        cat "$_output" >> "$LOG_FILE" 2>/dev/null || true
        _last_stage=$(progress_message "$_progress" '正在准备下一启动字体负载' "$(progress_value "$_progress" 0)")
        _timeout_message="字体切换超过 ${TIMEOUT_SECONDS} 秒，已终止（${_last_stage}）；当前启动字体未被改动"
        if [ "$(sed -n 's/^requestId=//p' "$NEXT_STATE" 2>/dev/null | head -n1)" = "$_task" ]; then
            _timeout_message="字体切换超过 ${TIMEOUT_SECONDS} 秒，已终止（${_last_stage}）；已保存的字体在重启后完整生效"
        elif live_journal_pending; then
            _timeout_message="字体切换超过 ${TIMEOUT_SECONDS} 秒，已终止（${_last_stage}）；挂载事务等待恢复"
        fi
        write_task "$_task" failed "$_font" "$_timeout_message" \
            "$_started" "$_finished" '' '' '' "$TIMEOUT_SECONDS" '' false 100
    else
        _message=$(sed -n 's/.*"message":"\([^"]*\)".*/\1/p' "$_output" 2>/dev/null | tail -n1)
        [ "$_rc" -ne 0 ] || _rc=1
        [ -n "$_message" ] || _message="字体切换失败（代码 $_rc），当前启动字体未被改动"
        cat "$_output" >> "$LOG_FILE" 2>/dev/null || true
        write_task "$_task" failed "$_font" "$_message" "$_started" "$_finished" '' '' '' 0 '' false 100
    fi
    rm -f "$_output" "$_progress" 2>/dev/null || true
    return "$_rc"
}

start_task() {
    _font="$1"
    [ -n "$_font" ] || { printf '{"status":"error","message":"未指定字体"}\n'; return 0; }
    [ -f "$MANAGER" ] || { printf '{"status":"error","message":"字体管理器不存在"}\n'; return 0; }
    start_lock_acquire
    _lock_rc=$?
    if [ "$_lock_rc" -ne 0 ]; then
        case "$_lock_rc" in
            2) printf '{"status":"error","message":"已有字体任务在运行中，请查看当前进度"}\n' ;;
            *) printf '{"status":"error","message":"字体任务锁异常，请重试"}\n' ;;
        esac
        return 0
    fi
    trap 'start_lock_release' EXIT
    reconcile_task
    _state=$(read_value state); _task_old=$(read_value task); _pid=$(read_value pid)
    if [ "$_state" = cleanup-pending ]; then
        printf '{"status":"error","message":"上一字体任务清理尚未确认，请刷新重试"}\n'; return 0
    fi
    if worker_alive "$_task_old" "$_pid" || luoshu_task_pid_alive "$WORKER_PID_FILE"; then
        printf '{"status":"error","message":"已有字体任务在运行中，请查看当前进度"}\n'; return 0
    fi
    if ! luoshu_clear_task_pid "$WORKER_PID_FILE"; then
        printf '{"status":"error","message":"上一字体任务清理尚未确认，请刷新重试"}\n'; return 0
    fi
    if ! recover_live_transaction; then
        printf '{"status":"error","message":"上一字体挂载事务等待恢复，请刷新重试"}\n'; return 0
    fi

    _started=$(date +%s 2>/dev/null || echo 0); _task="${_started}-$$"
    write_task "$_task" queued "$_font" '1% · 字体切换任务正在启动' "$_started" '' '' '' '' 0 '' false 1 || {
        printf '{"status":"error","message":"无法创建字体切换任务"}\n'; return 0
    }

    export MODDIR LUOSHU_FONT_MANAGER="$MANAGER" LUOSHU_SWITCH_TASK_FILE="$TASK_FILE" \
        LUOSHU_SWITCH_LOG="$LOG_FILE" LUOSHU_SWITCH_TIMEOUT_SECONDS="$TIMEOUT_SECONDS" \
        LUOSHU_SWITCH_HEARTBEAT_INTERVAL="$HEARTBEAT_INTERVAL" LUOSHU_SWITCH_WORKER_PID_FILE="$WORKER_PID_FILE"

    if type luoshu_start_detached >/dev/null 2>&1; then
        LUOSHU_TASK_TIMEOUT_SECONDS=$((TIMEOUT_SECONDS + 10))
        LUOSHU_SCOPE_HANDOFF=1
        export LUOSHU_TASK_TIMEOUT_SECONDS LUOSHU_SCOPE_HANDOFF
        luoshu_start_detached "$WORKER_PID_FILE" "$_task" "$LOG_FILE" sh "$0" run "$_task" "$_font" "$_started"
        _start_rc=$?
        if [ "$_start_rc" -ne 0 ]; then
            if luoshu_stop_task_pid "$WORKER_PID_FILE" "$_task" >/dev/null 2>&1; then
                write_task "$_task" failed "$_font" '无法启动独立字体切换任务' "$_started" "$(date +%s 2>/dev/null || echo 0)" '' '' '' 0 '' false 100 '' '' true
            else
                write_task "$_task" cleanup-pending "$_font" '任务清理尚未确认，请刷新重试' "$_started" '' '' '' '' 0 '' false 1 failed '无法启动独立字体切换任务'
            fi
            printf '{"status":"error","message":"无法启动独立字体切换任务"}\n'; return 0
        fi
        _worker=$(head -n1 "$WORKER_PID_FILE" 2>/dev/null)
    else
        printf '{"status":"error","message":"任务监督器不可用"}\n'; return 126
    fi
    case "$_worker" in ''|*[!0-9]*) _worker='' ;; esac
    # The worker owns all writes after spawn, including very fast completion.
    printf '{"status":"ok","data":{"font":"%s","task":"%s","message":"任务已开始"}}\n' \
        "$(json_escape "$_font")" "$(json_escape "$_task")"
}

status_task() {
    _wanted="$1"; reconcile_task
    [ -s "$TASK_FILE" ] || { printf '{"status":"error","message":"暂无切换任务"}\n'; return 0; }
    _task=$(read_value task)
    if [ -n "$_wanted" ] && [ "$_wanted" != "$_task" ]; then
        printf '{"status":"error","message":"任务不存在或已被新任务替换"}\n'; return 0
    fi
    _state=$(read_value state); _font=$(read_value font); _message=$(read_value message)
    case "$_state" in success|failed)
        if worker_alive "$_task" ''; then
            _state=running; _message='正在回收任务子进程';
        fi
        ;;
    esac
    _started=$(read_value started); _finished=$(read_value finished); _heartbeat=$(read_value heartbeat)
    _timeout=$(read_value timeout); _elapsed=$(read_value elapsed); _percent=$(read_value percent)
    _boot=$(read_value bootId); _reused=$(read_value reused)
    _live=$(read_value liveApplied); _activation=$(read_value activation)
    [ "$_reused" = true ] || _reused=false
    [ "$_live" = true ] && [ "$_boot" = "$(current_boot_id)" ] && ! live_journal_pending || _live=false
    [ -n "$_activation" ] || _activation=pending-reboot
    [ "$_live" = true ] || _activation=pending-reboot
    case "$_percent" in ''|*[!0-9]*) _percent=0 ;; esac
    if [ "$_state" = success ] && [ -f "$STATUS_SCRIPT" ]; then MODDIR="$MODDIR" sh "$STATUS_SCRIPT" "$_font" >/dev/null 2>&1 || true; fi
    printf '{"status":"ok","data":{"task":"%s","state":"%s","font":"%s","message":"%s","started":%s,"finished":%s,"heartbeat":%s,"timeout":%s,"elapsed":%s,"percent":%s,"bootId":"%s","reused":%s,"liveApplied":%s,"activation":"%s"}}\n' \
        "$(json_escape "$_task")" "$(json_escape "$_state")" "$(json_escape "$_font")" "$(json_escape "$_message")" \
        "${_started:-0}" "${_finished:-0}" "${_heartbeat:-0}" "${_timeout:-$TIMEOUT_SECONDS}" "${_elapsed:-0}" "$_percent" \
        "$(json_escape "$_boot")" "$_reused" "$_live" "$(json_escape "$_activation")"
}

cancel_task() {
    _cancel_wanted="$1"
    [ -n "$_cancel_wanted" ] || { printf '{"status":"error","message":"缺少任务身份"}\n'; return 2; }
    _cancel_current=$(read_value task)
    if [ -n "$_cancel_current" ] && [ "$_cancel_current" != "$_cancel_wanted" ] && \
       [ "$(cat "${WORKER_PID_FILE}.task" 2>/dev/null)" != "$_cancel_wanted" ]; then
        printf '{"status":"ok","data":{"task":"%s","cleaned":true,"state":"absent"}}\n' "$(json_escape "$_cancel_wanted")"
        return 0
    fi
    _cancel_result=$(luoshu_stop_task_pid "$WORKER_PID_FILE" "$_cancel_wanted")
    _cancel_rc=$?
    if [ "$_cancel_rc" -eq 0 ] && ! recover_live_transaction; then
        _cancel_rc=125
        _cancel_result="{\"status\":\"error\",\"data\":{\"task\":\"$(json_escape "$_cancel_wanted")\",\"cleaned\":false,\"state\":\"cleanup-pending\"},\"message\":\"字体挂载事务尚未恢复，请刷新重试\"}"
    fi
    if [ "$_cancel_rc" -eq 0 ] && [ "$_cancel_current" = "$_cancel_wanted" ]; then
        _cancel_state=$(read_value state)
        case "$_cancel_state" in queued|running|cleanup-pending)
            write_task "$_cancel_wanted" failed "$(read_value font)" '字体切换已取消，任务子进程已回收' \
                "$(read_value started)" "$(date +%s)" '' '' '' "$(read_value elapsed)" '' false 100 '' '' true
            ;;
        esac
    elif [ "$_cancel_rc" -ne 0 ] && [ "$_cancel_current" = "$_cancel_wanted" ]; then
        reconcile_task
    fi
    printf '%s\n' "$_cancel_result"
    return "$_cancel_rc"
}

case "${1:-status}" in
    start) start_task "${2:-}" ;;
    status) status_task "${2:-}" ;;
    reconcile) reconcile_task ;;
    cancel) cancel_task "${2:-}"; exit $? ;;
    run)
        if [ "${LUOSHU_TASK_SCOPE_PIDFILE:-}" != "$WORKER_PID_FILE" ]; then
            exec sh "$(luoshu_scope_runner)" run --pid-file "$WORKER_PID_FILE" --task "${2:-}" \
                --timeout "$((TIMEOUT_SECONDS + 10))" -- sh "$0" "$@"
        fi
        run_worker "${2:-}" "${3:-}" "${4:-0}"
        exit $?
        ;;
    *) printf '{"status":"error","message":"未知切换命令"}\n' ;;
esac
exit 0
