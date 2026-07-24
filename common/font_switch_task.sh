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

MANAGER="${LUOSHU_FONT_MANAGER:-$MODDIR/common/font_manager.sh}"
TASK_FILE="${LUOSHU_SWITCH_TASK_FILE:-$MODDIR/config/switch_task.conf}"
LOG_FILE="${LUOSHU_SWITCH_LOG:-$MODDIR/logs/fontswitch.log}"
STATUS_SCRIPT="$MODDIR/common/module_status.sh"
BACKGROUND_TASK="$MODDIR/common/background_task.sh"
WORKER_PID_FILE="${LUOSHU_SWITCH_WORKER_PID_FILE:-$MODDIR/config/switch_task_worker.pid}"
LOAD_VERIFY_STATE="$MODDIR/config/device-font-load-verification.conf"
[ -f "$BACKGROUND_TASK" ] && . "$BACKGROUND_TASK"

# 大型 CJK 字体在部分低速存储设备上会超过旧版 45 秒。任务已脱离 App 会话，
# 因此给完整验证、事务快照、槽位映射和挂载同步共 110 秒，同时仍早于 App 的 120 秒观察上限结束。
TIMEOUT_SECONDS="${LUOSHU_SWITCH_TIMEOUT_SECONDS:-110}"
case "$TIMEOUT_SECONDS" in ''|*[!0-9]*) TIMEOUT_SECONDS=110 ;; esac
[ "$TIMEOUT_SECONDS" -ge 5 ] 2>/dev/null || TIMEOUT_SECONDS=5
[ "$TIMEOUT_SECONDS" -le 600 ] 2>/dev/null || TIMEOUT_SECONDS=600

json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
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

reconcile_task() {
    [ -s "$TASK_FILE" ] || return 0
    _state="$(read_value state)"
    case "$_state" in queued|running) ;; *) return 0 ;; esac
    _pid="$(read_value pid)"
    task_pid_alive "$_pid" && return 0
    _task="$(read_value task)"
    _font="$(read_value font)"
    _started="$(read_value started)"
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
    if command -v timeout >/dev/null 2>&1; then
        timeout "$TIMEOUT_SECONDS" sh "$MANAGER" action switch "$_font" > "$_output" 2>&1
        return $?
    fi
    if command -v toybox >/dev/null 2>&1 && toybox timeout --help >/dev/null 2>&1; then
        toybox timeout "$TIMEOUT_SECONDS" sh "$MANAGER" action switch "$_font" > "$_output" 2>&1
        return $?
    fi

    sh "$MANAGER" action switch "$_font" > "$_output" 2>&1 &
    _child=$!
    _elapsed=0
    while task_pid_alive "$_child" && [ "$_elapsed" -lt "$TIMEOUT_SECONDS" ]; do
        sleep 1
        _elapsed=$((_elapsed + 1))
    done
    if task_pid_alive "$_child"; then
        terminate_child_tree "$_child"
        wait "$_child" 2>/dev/null || true
        return 124
    fi
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

    run_bounded "$_font" "$_output"
    _rc=$?
    _finished="$(date +%s 2>/dev/null || echo 0)"
    if [ "$_rc" -eq 0 ] && grep -q '"status":"ok"' "$_output" 2>/dev/null; then
        cat "$_output" >> "$LOG_FILE" 2>/dev/null || true
        mark_load_verification_pending "$_font" || true
        write_task "$_task" success "$_font" '字体已准备完成；完整重启后自动验证实际加载状态' "$_started" "$_finished" ''
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
        LUOSHU_SWITCH_WORKER_PID_FILE="$WORKER_PID_FILE"

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
    if [ "$_state" = success ] && [ -f "$STATUS_SCRIPT" ]; then
        MODDIR="$MODDIR" sh "$STATUS_SCRIPT" "$_font" >/dev/null 2>&1 || true
    fi
    printf '{"status":"ok","data":{"task":"%s","state":"%s","font":"%s","message":"%s","started":%s,"finished":%s}}\n' \
        "$(json_escape "$_task")" "$(json_escape "$_state")" "$(json_escape "$_font")" "$(json_escape "$_message")" \
        "${_started:-0}" "${_finished:-0}"
}

case "${1:-status}" in
    start) start_task "${2:-}" ;;
    status) status_task "${2:-}" ;;
    reconcile) reconcile_task ;;
    run) run_worker "${2:-}" "${3:-}" "${4:-0}" ;;
    *) printf '{"status":"error","message":"未知切换命令"}\n' ;;
esac
exit 0
