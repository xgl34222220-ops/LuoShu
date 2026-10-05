#!/system/bin/sh
# v14.4 composite engine compatibility wrapper.
# Bridges the bounded engine lifecycle to the current private payload boot mode.
set +e
RUNTIME="${MODDIR:-}"
REALMOD="${LUOSHU_REAL_MODDIR:-/data/adb/modules/LuoShu}"
. "$REALMOD/common/runtime_paths.sh" || exit 126
luoshu_runtime_paths_init "$REALMOD" || exit 126
. "$REALMOD/common/background_task.sh" || exit 126
ENGINE="$RUNTIME/common/font_mix_engine.sh"
TASK_FILE="$LUOSHU_CONFIG_DIR/mix_task.conf"
LEGACY_MODE="$LUOSHU_CONFIG_DIR/font_runtime_legacy_v14_4.conf"
LOG_FILE="$LUOSHU_LOG_DIR/fontswitch.log"
MIX_ROUTER="$REALMOD/common/legacy_v14_4/mix_router.sh"
FINALIZE_STATE="$LUOSHU_CONFIG_DIR/mix-finalize-state.conf"
WORKER_PID="$LUOSHU_TASKS_DIR/mix_worker.pid"

read_task_value() {
    sed -n "s/^${1}=//p" "$TASK_FILE" 2>/dev/null | head -n1 | tr -d '\r\n'
}

mark_legacy_mix_mode() {
    mkdir -p "$RUNTIME/config" 2>/dev/null || true
    _tmp="${LEGACY_MODE}.tmp.$$"
    {
        printf 'enabled=true\n'
        printf 'core=v14.4.0\n'
        printf 'font=mix\n'
        printf 'pipeline=atomic-next-boot-composite\n'
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } >"$_tmp" 2>/dev/null && mv -f "$_tmp" "$LEGACY_MODE" 2>/dev/null || true
    chmod 0600 "$LEGACY_MODE" 2>/dev/null || true
    rm -f \
        "$RUNTIME/config/font-payload-rebuild-pending.conf" \
        "$RUNTIME/config/font-payload-reapply-notified.conf" \
        "$RUNTIME/config/device-font-cache-pending.conf" \
        "$RUNTIME/config/device-font-engine.conf" \
        "$RUNTIME/config/device-font-installed.conf" \
        "$RUNTIME/config/device-font-dynamic-mount.conf" \
        "$RUNTIME/config/device-font-load-verification.json" \
        "$RUNTIME/config/font-runtime-targets.conf" \
        "$RUNTIME/config/font-target-aliases.conf" \
        "$RUNTIME/config/font-target-coverage.conf" \
        "$RUNTIME/config/font-config-overlay.conf" 2>/dev/null || true
}

finalize_next_payload() {
    [ -f "$MIX_ROUTER" ] || return 1
    MODDIR="$REALMOD" LUOSHU_REAL_MODDIR="$REALMOD" \
        sh "$MIX_ROUTER" finalize >> "$LOG_FILE" 2>&1
}

write_finalize_state() {
    _mfs_state="$1"
    _mfs_message="$2"
    _mfs_tmp="${FINALIZE_STATE}.tmp.$$"
    {
        printf 'state=%s\n' "$_mfs_state"
        printf 'requestId=%s\n' "${LUOSHU_MIX_REQUEST_ID:-}"
        printf 'message=%s\n' "$_mfs_message"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } >"$_mfs_tmp" 2>/dev/null && mv -f "$_mfs_tmp" "$FINALIZE_STATE" 2>/dev/null || true
    chmod 0644 "$FINALIZE_STATE" 2>/dev/null || true
}

mark_interrupted_task() {
    _mit_task="$1"; _mit_message="$2"
    [ "$(read_task_value task)" = "$_mit_task" ] && [ "$(read_task_value state)" = running ] || return 0
    _mit_tmp="$TASK_FILE.tmp.$$"
    {
        printf 'task=%s\nstate=failed\nmessage=%s\n' "$_mit_task" "$_mit_message"
        for _mit_key in cjk latin digit started; do
            printf '%s=%s\n' "$_mit_key" "$(read_task_value "$_mit_key")"
        done
        printf 'finished=%s\n' "$(date +%s)"
    } >"$_mit_tmp" 2>/dev/null && mv -f "$_mit_tmp" "$TASK_FILE" 2>/dev/null
}

monitor_task() {
    _wanted="$1"
    _monitor_limit="${LUOSHU_MIX_MONITOR_TIMEOUT:-720}"
    case "$_monitor_limit" in ''|*[!0-9]*) _monitor_limit=720 ;; esac
    _loops=0
    while [ "$_loops" -lt "$_monitor_limit" ]; do
        _task="$(read_task_value task)"
        _state="$(read_task_value state)"
        # The shared task record has moved on. Keeping this monitor alive for
        # another twelve minutes only polls the next task and can never commit
        # the superseded one.
        [ -z "$_task" ] || [ "$_task" = "$_wanted" ] || exit 0
        if [ "$_task" = "$_wanted" ] && ! luoshu_task_pid_alive "$WORKER_PID" "$_wanted"; then
            # A terminal config alone is not cleanup evidence. Wait for the
            # matching supervisor proof, including adopted grandchildren.
            if ! sh "$(luoshu_scope_runner)" cleaned "$WORKER_PID" "$_wanted" >/dev/null 2>&1; then
                write_finalize_state failed '字体任务缺少可验证的进程回收记录，未提交下一启动负载'
                exit 1
            fi
            case "$_state" in
                success)
                    # Do not depend on the App staying alive long enough to poll status.
                    # A completed fixed-weight task must atomically become the real
                    # module's next-boot payload from this background monitor too.
                    write_finalize_state running '正在提交下一启动字体负载'
                    if finalize_next_payload; then
                        mark_legacy_mix_mode
                        printf '[%s] legacy-v14 composite task committed for next boot: %s\n' \
                            "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" "$_wanted" >>"$LOG_FILE" 2>/dev/null || true
                        write_finalize_state success '复合字体已准备，完整重启后生效'
                    else
                        write_finalize_state failed '复合字体已生成，但下一启动负载提交失败'
                        printf '[%s] legacy-v14 composite task finished but next payload commit FAILED: %s\n' \
                            "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" "$_wanted" >>"$LOG_FILE" 2>/dev/null || true
                    fi
                    exit 0
                    ;;
                failed) write_finalize_state failed "$(read_task_value message)"; exit 0 ;;
                cancelled) write_finalize_state cancelled '字体组合已取消，任务进程已回收'; exit 0 ;;
                running)
                    # Timeout or parent death can stop the wrapper before it
                    # writes a result. The supervisor proof is now definitive.
                    mark_interrupted_task "$_wanted" '字体组合任务已中断，任务进程已回收'
                    write_finalize_state failed '字体组合任务已中断，任务进程已回收'
                    exit 1 ;;
            esac
        fi
        sleep 1
        _loops=$((_loops + 1))
    done
    luoshu_stop_task_pid "$WORKER_PID" "$_wanted" >/dev/null 2>&1 || {
        write_finalize_state failed '字体组合超时，进程回收尚未确认'
        exit 1
    }
    mark_interrupted_task "$_wanted" '字体组合超时，任务进程已回收'
    write_finalize_state failed '字体组合超时，任务进程已回收'
    exit 1
}

case "${1:-status}" in
    monitor)
        monitor_task "${2:-}"
        ;;
    start)
        if [ -z "${LUOSHU_TASK_SCOPE_PIDFILE:-}" ]; then
            # The request scope owns the response file, then explicitly hands
            # only the finite engine/monitor jobs over to their own scopes.
            exec sh "$(luoshu_scope_runner)" request-run "mix-start-$(date +%s)-$$" 30 -- sh "$0" "$@"
        fi
        # Capturing an asynchronous engine with command substitution can keep the
        # substitution pipe alive for the background worker on Android. That makes
        # this start call wait for the whole build and pins the outer task at 34%.
        _response_root="${LUOSHU_TASK_SCOPE_TMPDIR:-$LUOSHU_TMP_DIR}"
        _response=$(mktemp "$_response_root/mix-engine-start.XXXXXX") || exit 1
        rm -f "$_response" 2>/dev/null || true
        rm -f "$FINALIZE_STATE" 2>/dev/null || true
        MODDIR="$RUNTIME" LUOSHU_REAL_MODDIR="$REALMOD" \
            sh "$ENGINE" "$@" >"$_response" 2>&1
        _rc=$?
        cat "$_response" 2>/dev/null || true
        if [ "$_rc" -eq 0 ]; then
            _task=$(sed -n 's/^.*"task":"\([^"]*\)".*$/\1/p' "$_response" 2>/dev/null | tail -n1)
            if [ -n "$_task" ]; then
                _monitor_timeout="${LUOSHU_MIX_MONITOR_TIMEOUT:-720}"
                case "$_monitor_timeout" in ''|*[!0-9]*) _monitor_timeout=720 ;; esac
                if ! LUOSHU_SCOPE_HANDOFF=1 LUOSHU_TASK_TIMEOUT_SECONDS="$((_monitor_timeout + 15))" \
                    luoshu_start_detached "$LUOSHU_TASKS_DIR/mix-monitor-$_task.pid" "$_task.monitor" "$LOG_FILE" \
                    sh "$0" monitor "$_task"; then
                    luoshu_stop_task_pid "$WORKER_PID" "$_task" >/dev/null 2>&1 || true
                    write_finalize_state failed '无法启动字体提交任务监督器'
                    _rc=1
                fi
            fi
        fi
        rm -f "$_response" 2>/dev/null || true
        exit "$_rc"
        ;;
    cancel)
        _cancel_task="${2:-$(read_task_value task)}"
        _cancel_reply=$(MODDIR="$RUNTIME" LUOSHU_REAL_MODDIR="$REALMOD" sh "$ENGINE" cancel "$_cancel_task")
        _cancel_rc=$?
        if [ "$_cancel_rc" -ne 0 ]; then
            printf '%s\n' "$_cancel_reply"
            exit "$_cancel_rc"
        fi
        luoshu_stop_task_pid "$LUOSHU_TASKS_DIR/mix-monitor-$_cancel_task.pid" "$_cancel_task.monitor" >/dev/null 2>&1 || {
            printf '{"status":"error","message":"字体组合进程已回收，但提交任务回收尚未确认","data":{"cleaned":false}}\n'
            exit 1
        }
        write_finalize_state cancelled '字体组合已取消，任务进程已回收'
        printf '%s\n' "$_cancel_reply"
        exit 0
        ;;
    status|recover)
        exec sh "$ENGINE" "$@"
        ;;
    *)
        exec sh "$ENGINE" "$@"
        ;;
esac
