#!/system/bin/sh
# 洛书前台字体切换守卫。
# App 只观察这一项任务；实际切换在独立 Root 会话中执行，超时会终止 font_manager，
# 由 switch_font 的事务 trap 恢复上一套可用负载。
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
[ "$TIMEOUT_SECONDS" -ge 5 ] 2>/dev/null || TIMEOUT_SECONDS=5
[ "$TIMEOUT_SECONDS" -le 900 ] 2>/dev/null || TIMEOUT_SECONDS=900
HEARTBEAT_INTERVAL="${LUOSHU_SWITCH_HEARTBEAT_INTERVAL:-5}"
case "$HEARTBEAT_INTERVAL" in ''|*[!0-9]*) HEARTBEAT_INTERVAL=5 ;; esac
[ "$HEARTBEAT_INTERVAL" -ge 1 ] 2>/dev/null || HEARTBEAT_INTERVAL=1
[ "$HEARTBEAT_INTERVAL" -le 30 ] 2>/dev/null || HEARTBEAT_INTERVAL=30

json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
}

current_boot_id() {
    if type luoshu_current_boot_id >/dev/null 2>&1; then
        luoshu_current_boot_id
        return
    fi
    _cbi=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n')
    [ -n "$_cbi" ] || _cbi=$(getprop ro.runtime.firstboot 2>/dev/null | tr -d '\r\n')
    [ -n "$_cbi" ] || _cbi=unknown
    printf '%s\n' "$_cbi"
}

read_value() {
    _key="$1"
    sed -n "s/^${_key}=//p" "$TASK_FILE" 2>/dev/null | head -n1 | tr -d '\r\n'
}

write_task() {
    _task="$1"
    _state="$2"
    _font="$3"
    _message="$4"
    _started="$5"
    _finished="$6"
    _pid="$7"
    _heartbeat="${8:-$(date +%s 2>/dev/null || echo 0)}"
    _timeout="${9:-$TIMEOUT_SECONDS}"
    _elapsed="${10:-0}"
    _boot_id="${11:-$(current_boot_id)}"
    _reused="${12:-false}"
    [ "$_reused" = true ] || _reused=false
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
        printf 'bootId=%s\n' "$_boot_id"
        printf 'reused=%s\n' "$_reused"
    } > "$_tmp" 2>/dev/null || return 1
    mv -f "$_tmp" "$TASK_FILE" 2>/dev/null || return 1
    chmod 0644 "$TASK_FILE" 2>/dev/null || true
}

mark_load_verification_pending() {
    _font="$1"
    _tmp="${LOAD_VERIFY_STATE}.tmp.$$"
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

task_pid_alive() {
    _pid="$1"
    case "$_pid" in ''|*[!0-9]*) return 1 ;; esac
    kill -0 "$_pid" 2>/dev/null
}

start_lock_acquire() {
    if type luoshu_font_lock_acquire >/dev/null 2>&1; then
        luoshu_font_lock_acquire "$START_LOCK" "$$"
        return $?
    fi
    mkdir "$START_LOCK" 2>/dev/null || return 2
    printf '%s\n' "$$" > "$START_LOCK/pid" 2>/dev/null || {
        rmdir "$START_LOCK" 2>/dev/null || true
        return 1
    }
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
    _state="$(read_value state)"
    case "$_state" in queued|running) ;; *) return 0 ;; esac
    _task="$(read_value task)"
    _font="$(read_value font)"
    _started="$(read_value started)"
    _task_boot="$(read_value bootId)"
    _now_boot="$(current_boot_id)"
    if [ -n "$_task_boot" ] && [ -n "$_now_boot" ] && [ "$_task_boot" != "$_now_boot" ]; then
        write_task "$_task" failed "$_font" '设备已重启，上一字体切换任务已结束' \
            "$_started" "$(date +%s 2>/dev/null || echo 0)" '' '' '' 0 "$_now_boot"
        type luoshu_clear_task_pid >/dev/null 2>&1 && luoshu_clear_task_pid "$WORKER_PID_FILE" "$_task"
        return 0
    fi
    _pid="$(read_value pid)"
    task_pid_alive "$_pid" && return 0
    write_task "$_task" failed "$_font" '字体切换进程异常结束，已保留上一套字体' "$_started" "$(date +%s 2>/dev/null || echo 0)" ''
    type luoshu_clear_task_pid >/dev/null 2>&1 && luoshu_clear_task_pid "$WORKER_PID_FILE" "$_task"
}

terminate_child_tree() {
    _child="$1"
    if command -v pgrep >/dev/null 2>&1; then
        for _desc in $(pgrep -P "$_child" 2>/dev/null); do
            kill -TERM "$_desc" 2>/dev/null || true
        done
    fi
    kill -TERM "$_child" 2>/dev/null || true
    sleep 1
    if task_pid_alive "$_child"; then
        if command -v pgrep >/dev/null 2>&1; then
            for _desc in $(pgrep -P "$_child" 2>/dev/null); do
                kill -KILL "$_desc" 2>/dev/null || true
            done
        fi
        kill -KILL "$_child" 2>/dev/null || true
    fi
}

run_bounded() {
    _font="$1"
    _output="$2"
    _task="$3"
    _started="$4"

    sh "$MANAGER" action switch "$_font" > "$_output" 2>&1 &
    _child=$!
    _elapsed=0
    _next_heartbeat=0
    while task_pid_alive "$_child"; do
        if [ "$_elapsed" -ge "$TIMEOUT_SECONDS" ]; then
            terminate_child_tree "$_child"
            wait "$_child" 2>/dev/null || true
            return 124
        fi
        if [ "$_elapsed" -ge "$_next_heartbeat" ]; then
            _heartbeat=$(date +%s 2>/dev/null || echo 0)
            write_task "$_task" running "$_font" "正在验证并应用字体（已用 ${_elapsed} 秒）" \
                "$_started" '' "$$" "$_heartbeat" "$TIMEOUT_SECONDS" "$_elapsed" || true
            _next_heartbeat=$((_elapsed + HEARTBEAT_INTERVAL))
        fi
        sleep 1
        _elapsed=$((_elapsed + 1))
    done
    wait "$_child"
}

run_worker() {
    _task="$1"
    _font="$2"
    _started="$3"
    _output="${TASK_FILE}.output.${_task}"
    trap 'type luoshu_clear_task_pid >/dev/null 2>&1 && luoshu_clear_task_pid "$WORKER_PID_FILE" "$_task"' EXIT HUP INT TERM
    mkdir -p "${LOG_FILE%/*}" 2>/dev/null || true
    write_task "$_task" running "$_font" '正在完整验证并映射系统字体槽' "$_started" '' "$$" || exit 1
    printf '[%s] bounded switch start: %s task=%s timeout=%ss\n' \
        "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$_font" "$_task" "$TIMEOUT_SECONDS" >> "$LOG_FILE" 2>/dev/null || true

    run_bounded "$_font" "$_output" "$_task" "$_started"
    _rc=$?
    _finished="$(date +%s 2>/dev/null || echo 0)"
    if [ "$_rc" -eq 0 ] && grep -q '"status":"ok"' "$_output" 2>/dev/null; then
        cat "$_output" >> "$LOG_FILE" 2>/dev/null || true
        if grep -q '"reused":true' "$_output" 2>/dev/null; then
            write_task "$_task" success "$_font" '当前字体已验证，无需重新生成或重启' \
                "$_started" "$_finished" '' '' '' 0 '' true
        else
            mark_load_verification_pending "$_font" || true
            write_task "$_task" success "$_font" '字体已准备完成；完整重启后自动验证实际加载状态' "$_started" "$_finished" ''
            [ -f "$HISTORY_TOOL" ] && MODDIR="$MODDIR" sh "$HISTORY_TOOL" record-direct "$_font" >/dev/null 2>&1 || true
        fi
    elif [ "$_rc" -eq 124 ] || [ "$_rc" -eq 137 ]; then
        cat "$_output" >> "$LOG_FILE" 2>/dev/null || true
        write_task "$_task" failed "$_font" "字体切换超过 ${TIMEOUT_SECONDS} 秒，已终止并回滚" "$_started" "$_finished" ''
    else
        _message="$(sed -n 's/.*"message":"\([^"]*\)".*/\1/p' "$_output" 2>/dev/null | tail -n1)"
        [ -n "$_message" ] || _message="字体切换失败（代码 $_rc），已保留上一套字体"
        cat "$_output" >> "$LOG_FILE" 2>/dev/null || true
        write_task "$_task" failed "$_font" "$_message" "$_started" "$_finished" ''
    fi
    rm -f "$_output" 2>/dev/null || true
}

start_task() {
    _font="$1"
    [ -n "$_font" ] || { printf '{"status":"error","message":"未指定字体"}\n'; return 0; }
    [ -f "$MANAGER" ] || { printf '{"status":"error","message":"字体管理器不存在"}\n'; return 0; }
    if ! start_lock_acquire; then
        printf '{"status":"error","message":"字体正在切换中，请稍候"}\n'
        return 0
    fi
    trap 'start_lock_release' EXIT
    reconcile_task
    _state="$(read_value state)"
    _pid="$(read_value pid)"
    if { [ "$_state" = queued ] || [ "$_state" = running ]; } && task_pid_alive "$_pid"; then
        printf '{"status":"error","message":"字体正在切换中，请稍候"}\n'
        return 0
    fi

    _started="$(date +%s 2>/dev/null || echo 0)"
    _task="${_started}-$$"
    write_task "$_task" queued "$_font" '字体切换任务正在启动' "$_started" '' '' || {
        printf '{"status":"error","message":"无法创建字体切换任务"}\n'
        return 0
    }

    export MODDIR LUOSHU_FONT_MANAGER="$MANAGER" LUOSHU_SWITCH_TASK_FILE="$TASK_FILE" \
        LUOSHU_SWITCH_LOG="$LOG_FILE" LUOSHU_SWITCH_TIMEOUT_SECONDS="$TIMEOUT_SECONDS" \
        LUOSHU_SWITCH_HEARTBEAT_INTERVAL="$HEARTBEAT_INTERVAL" LUOSHU_SWITCH_WORKER_PID_FILE="$WORKER_PID_FILE"

    if type luoshu_start_detached >/dev/null 2>&1; then
        luoshu_start_detached "$WORKER_PID_FILE" "$_task" "$LOG_FILE" sh "$0" run "$_task" "$_font" "$_started"
        _start_rc=$?
        if [ "$_start_rc" -ne 0 ] && [ "$_start_rc" -ne 3 ]; then
            write_task "$_task" failed "$_font" '无法启动独立字体切换任务' "$_started" "$(date +%s 2>/dev/null || echo 0)" ''
            printf '{"status":"error","message":"无法启动独立字体切换任务"}\n'
            return 0
        fi
        _worker=$(head -n1 "$WORKER_PID_FILE" 2>/dev/null)
    else
        ( trap '' HUP; exec sh "$0" run "$_task" "$_font" "$_started" ) </dev/null >> "$LOG_FILE" 2>&1 &
        _worker=$!
    fi
    case "$_worker" in ''|*[!0-9]*) _worker='' ;; esac
    write_task "$_task" running "$_font" '正在完整验证并映射系统字体槽' "$_started" '' "$_worker" || true
    printf '{"status":"ok","data":{"font":"%s","task":"%s","message":"任务已开始"}}\n' \
        "$(json_escape "$_font")" "$(json_escape "$_task")"
}

status_task() {
    _wanted="$1"
    reconcile_task
    [ -s "$TASK_FILE" ] || { printf '{"status":"error","message":"暂无切换任务"}\n'; return 0; }
    _task="$(read_value task)"
    if [ -n "$_wanted" ] && [ "$_wanted" != "$_task" ]; then
        printf '{"status":"error","message":"任务不存在或已被新任务替换"}\n'
        return 0
    fi
    _state="$(read_value state)"
    _font="$(read_value font)"
    _message="$(read_value message)"
    _started="$(read_value started)"
    _finished="$(read_value finished)"
    _heartbeat="$(read_value heartbeat)"
    _timeout="$(read_value timeout)"
    _elapsed="$(read_value elapsed)"
    _boot_id="$(read_value bootId)"
    _reused="$(read_value reused)"
    [ "$_reused" = true ] || _reused=false
    if [ "$_state" = success ] && [ -f "$STATUS_SCRIPT" ]; then
        MODDIR="$MODDIR" sh "$STATUS_SCRIPT" "$_font" >/dev/null 2>&1 || true
    fi
    printf '{"status":"ok","data":{"task":"%s","state":"%s","font":"%s","message":"%s","started":%s,"finished":%s,"heartbeat":%s,"timeout":%s,"elapsed":%s,"bootId":"%s","reused":%s}}\n' \
        "$(json_escape "$_task")" "$(json_escape "$_state")" "$(json_escape "$_font")" "$(json_escape "$_message")" \
        "${_started:-0}" "${_finished:-0}" "${_heartbeat:-0}" "${_timeout:-$TIMEOUT_SECONDS}" "${_elapsed:-0}" "$(json_escape "$_boot_id")" "$_reused"
}

case "${1:-status}" in
    start) start_task "${2:-}" ;;
    status) status_task "${2:-}" ;;
    reconcile) reconcile_task ;;
    run) run_worker "${2:-}" "${3:-}" "${4:-0}" ;;
    *) printf '{"status":"error","message":"未知切换命令"}\n' ;;
esac
exit 0
