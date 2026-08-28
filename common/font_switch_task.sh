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
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
MANAGER="${LUOSHU_FONT_MANAGER:-$MODDIR/common/font_manager.sh}"
TASK_FILE="${LUOSHU_SWITCH_TASK_FILE:-$MODDIR/config/switch_task.conf}"
LOG_FILE="${LUOSHU_SWITCH_LOG:-$MODDIR/logs/fontswitch.log}"
STATUS_SCRIPT="$MODDIR/common/module_status.sh"
HISTORY_TOOL="$MODDIR/system/bin/luoshu-history"
BACKGROUND_TASK="$MODDIR/common/background_task.sh"
WORKER_PID_FILE="${LUOSHU_SWITCH_WORKER_PID_FILE:-$MODDIR/config/switch_task_worker.pid}"
LOAD_VERIFY_STATE="$MODDIR/config/device-font-load-verification.conf"
[ -f "$BACKGROUND_TASK" ] && . "$BACKGROUND_TASK"
START_LOCK="${LUOSHU_SWITCH_START_LOCK:-$MODDIR/.font_switch_start.lock}"

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
    [ "$_reused" = true ] || _reused=false
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
    _state=$(read_value state)
    case "$_state" in queued|running) ;; *) return 0 ;; esac
    _task=$(read_value task); _font=$(read_value font); _started=$(read_value started)
    _pid=$(read_value pid); _task_boot=$(read_value bootId); _now_boot=$(current_boot_id)
    _percent=$(read_value percent); _elapsed=$(read_value elapsed)
    case "$_started" in ''|*[!0-9]*) _started=0 ;; esac

    if [ -n "$_task_boot" ] && [ -n "$_now_boot" ] && [ "$_task_boot" != "$_now_boot" ]; then
        write_task "$_task" failed "$_font" '设备已重启，上一字体切换任务已结束' \
            "$_started" "$(date +%s 2>/dev/null || echo 0)" '' '' '' "${_elapsed:-0}" "$_now_boot" false 100
        type luoshu_clear_task_pid >/dev/null 2>&1 && luoshu_clear_task_pid "$WORKER_PID_FILE" "$_task"
        return 0
    fi

    worker_alive "$_task" "$_pid" && return 0

    # Give a freshly queued worker a short spawn grace period. After that, a missing
    # identity sidecar is a dead task, not a reason to lock the App for minutes.
    _now=$(date +%s 2>/dev/null || echo 0)
    _age=$((_now - _started))
    [ "$_state" = queued ] && [ "$_age" -ge 0 ] 2>/dev/null && [ "$_age" -lt 8 ] 2>/dev/null && return 0

    write_task "$_task" failed "$_font" '字体切换进程已结束，任务锁已自动释放' \
        "$_started" "$_now" '' '' '' "${_elapsed:-0}" "$_now_boot" false 100
    type luoshu_clear_task_pid >/dev/null 2>&1 && luoshu_clear_task_pid "$WORKER_PID_FILE" "$_task"
}

terminate_child_tree() {
    _child="$1"
    if command -v pgrep >/dev/null 2>&1; then
        for _desc in $(pgrep -P "$_child" 2>/dev/null); do kill -TERM "$_desc" 2>/dev/null || true; done
    fi
    kill -TERM "$_child" 2>/dev/null || true
    sleep 1
    if pid_alive "$_child"; then
        if command -v pgrep >/dev/null 2>&1; then
            for _desc in $(pgrep -P "$_child" 2>/dev/null); do kill -KILL "$_desc" 2>/dev/null || true; done
        fi
        kill -KILL "$_child" 2>/dev/null || true
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
    LUOSHU_SWITCH_PROGRESS_FILE="$_progress_file" sh "$MANAGER" action switch "$_font" > "$_output" 2>&1 &
    _child=$!; _elapsed=0; _next_heartbeat=0
    while pid_alive "$_child"; do
        if [ "$_elapsed" -ge "$TIMEOUT_SECONDS" ]; then
            terminate_child_tree "$_child"; wait "$_child" 2>/dev/null || true; return 124
        fi
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
}

run_worker() {
    _task="$1"; _font="$2"; _started="$3"
    _output="${TASK_FILE}.output.${_task}"
    _progress="${TASK_FILE}.progress.${_task}"
    trap 'rm -f "$_progress" 2>/dev/null || true; type luoshu_clear_task_pid >/dev/null 2>&1 && luoshu_clear_task_pid "$WORKER_PID_FILE" "$_task"' EXIT HUP INT TERM
    mkdir -p "${LOG_FILE%/*}" 2>/dev/null || true
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
            write_task "$_task" success "$_font" '100% · 字体已准备完成，完整重启后生效' \
                "$_started" "$_finished" '' '' '' 0 '' false 100
            [ -f "$HISTORY_TOOL" ] && MODDIR="$MODDIR" sh "$HISTORY_TOOL" record-direct "$_font" >/dev/null 2>&1 || true
        fi
    elif [ "$_rc" -eq 124 ] || [ "$_rc" -eq 137 ]; then
        cat "$_output" >> "$LOG_FILE" 2>/dev/null || true
        write_task "$_task" failed "$_font" "字体切换超过 ${TIMEOUT_SECONDS} 秒，已终止；当前启动字体未被改动" \
            "$_started" "$_finished" '' '' '' "$TIMEOUT_SECONDS" '' false 100
    else
        _message=$(sed -n 's/.*"message":"\([^"]*\)".*/\1/p' "$_output" 2>/dev/null | tail -n1)
        [ -n "$_message" ] || _message="字体切换失败（代码 $_rc），当前启动字体未被改动"
        cat "$_output" >> "$LOG_FILE" 2>/dev/null || true
        write_task "$_task" failed "$_font" "$_message" "$_started" "$_finished" '' '' '' 0 '' false 100
    fi
    rm -f "$_output" "$_progress" 2>/dev/null || true
}

start_task() {
    _font="$1"
    [ -n "$_font" ] || { printf '{"status":"error","message":"未指定字体"}\n'; return 0; }
    [ -f "$MANAGER" ] || { printf '{"status":"error","message":"字体管理器不存在"}\n'; return 0; }
    if ! start_lock_acquire; then
        printf '{"status":"error","message":"字体任务锁正在释放，请重试"}\n'; return 0
    fi
    trap 'start_lock_release' EXIT
    reconcile_task
    _state=$(read_value state); _task_old=$(read_value task); _pid=$(read_value pid)
    if { [ "$_state" = queued ] || [ "$_state" = running ]; } && worker_alive "$_task_old" "$_pid"; then
        printf '{"status":"error","message":"已有字体任务在运行中，请查看当前进度"}\n'; return 0
    fi

    _started=$(date +%s 2>/dev/null || echo 0); _task="${_started}-$$"
    write_task "$_task" queued "$_font" '1% · 字体切换任务正在启动' "$_started" '' '' '' '' 0 '' false 1 || {
        printf '{"status":"error","message":"无法创建字体切换任务"}\n'; return 0
    }

    export MODDIR LUOSHU_FONT_MANAGER="$MANAGER" LUOSHU_SWITCH_TASK_FILE="$TASK_FILE" \
        LUOSHU_SWITCH_LOG="$LOG_FILE" LUOSHU_SWITCH_TIMEOUT_SECONDS="$TIMEOUT_SECONDS" \
        LUOSHU_SWITCH_HEARTBEAT_INTERVAL="$HEARTBEAT_INTERVAL" LUOSHU_SWITCH_WORKER_PID_FILE="$WORKER_PID_FILE"

    if type luoshu_start_detached >/dev/null 2>&1; then
        luoshu_start_detached "$WORKER_PID_FILE" "$_task" "$LOG_FILE" sh "$0" run "$_task" "$_font" "$_started"
        _start_rc=$?
        if [ "$_start_rc" -ne 0 ] && [ "$_start_rc" -ne 3 ]; then
            write_task "$_task" failed "$_font" '无法启动独立字体切换任务' "$_started" "$(date +%s 2>/dev/null || echo 0)" '' '' '' 0 '' false 100
            printf '{"status":"error","message":"无法启动独立字体切换任务"}\n'; return 0
        fi
        _worker=$(head -n1 "$WORKER_PID_FILE" 2>/dev/null)
    else
        ( trap '' HUP; exec sh "$0" run "$_task" "$_font" "$_started" ) </dev/null >> "$LOG_FILE" 2>&1 &
        _worker=$!
    fi
    case "$_worker" in ''|*[!0-9]*) _worker='' ;; esac
    write_task "$_task" running "$_font" '2% · 正在启动字体切换任务' "$_started" '' "$_worker" '' '' 0 '' false 2 || true
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
    _started=$(read_value started); _finished=$(read_value finished); _heartbeat=$(read_value heartbeat)
    _timeout=$(read_value timeout); _elapsed=$(read_value elapsed); _percent=$(read_value percent)
    _boot=$(read_value bootId); _reused=$(read_value reused)
    [ "$_reused" = true ] || _reused=false
    case "$_percent" in ''|*[!0-9]*) _percent=0 ;; esac
    if [ "$_state" = success ] && [ -f "$STATUS_SCRIPT" ]; then MODDIR="$MODDIR" sh "$STATUS_SCRIPT" "$_font" >/dev/null 2>&1 || true; fi
    printf '{"status":"ok","data":{"task":"%s","state":"%s","font":"%s","message":"%s","started":%s,"finished":%s,"heartbeat":%s,"timeout":%s,"elapsed":%s,"percent":%s,"bootId":"%s","reused":%s}}\n' \
        "$(json_escape "$_task")" "$(json_escape "$_state")" "$(json_escape "$_font")" "$(json_escape "$_message")" \
        "${_started:-0}" "${_finished:-0}" "${_heartbeat:-0}" "${_timeout:-$TIMEOUT_SECONDS}" "${_elapsed:-0}" "$_percent" \
        "$(json_escape "$_boot")" "$_reused"
}

case "${1:-status}" in
    start) start_task "${2:-}" ;;
    status) status_task "${2:-}" ;;
    reconcile) reconcile_task ;;
    run) run_worker "${2:-}" "${3:-}" "${4:-0}" ;;
    *) printf '{"status":"error","message":"未知切换命令"}\n' ;;
esac
exit 0