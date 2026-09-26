#!/system/bin/sh
# v14.4 composite engine compatibility wrapper.
# font_mix_engine.sh generates source anchors for inventory-driven mapping.
# This wrapper only bridges its async task lifecycle to the current private payload boot mode.
set +e
RUNTIME="${MODDIR:-}"
REALMOD="${LUOSHU_REAL_MODDIR:-/data/adb/modules/LuoShu}"
ENGINE="$RUNTIME/common/font_mix_engine.sh"
TASK_FILE="$RUNTIME/config/mix_task.conf"
LEGACY_MODE="$RUNTIME/config/font_runtime_legacy_v14_4.conf"
LOG_FILE="$RUNTIME/logs/fontswitch.log"
MIX_ROUTER="$REALMOD/common/legacy_v14_4/mix_router.sh"
FINALIZE_STATE="$REALMOD/config/mix-finalize-state.conf"

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
    # An old monitor must not clobber a newer request. A same-request failure
    # keeps the actual inventory error instead of the generic commit summary.
    _mfs_request="${LUOSHU_MIX_REQUEST_ID:-}"
    _mfs_current=$(sed -n 's/^requestId=//p' "$REALMOD/config/mix-stage-next.conf" 2>/dev/null | head -n1)
    [ -n "$_mfs_current" ] || _mfs_current=$(sed -n 's/^requestId=//p' "$REALMOD/config/font-payload-next.conf" 2>/dev/null | head -n1)
    [ -n "$_mfs_request" ] && [ "$_mfs_request" = "$_mfs_current" ] || return 0
    _mfs_existing=$(sed -n 's/^requestId=//p' "$FINALIZE_STATE" 2>/dev/null | head -n1)
    if [ "$_mfs_existing" = "$_mfs_request" ] && grep -q '^state=failed$' "$FINALIZE_STATE" 2>/dev/null; then
        return 0
    fi
    _mfs_tmp="${FINALIZE_STATE}.tmp.$$"
    {
        printf 'state=%s\n' "$_mfs_state"
        printf 'requestId=%s\n' "$_mfs_request"
        printf 'task=%s\n' "$(read_task_value task)"
        printf 'message=%s\n' "$_mfs_message"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } >"$_mfs_tmp" 2>/dev/null && mv -f "$_mfs_tmp" "$FINALIZE_STATE" 2>/dev/null || true
    chmod 0644 "$FINALIZE_STATE" 2>/dev/null || true
}

monitor_task() {
    _wanted="$1"
    _loops=0
    while [ "$_loops" -lt 720 ]; do
        _task="$(read_task_value task)"
        _state="$(read_task_value state)"
        # The shared task record has moved on. Keeping this monitor alive for
        # another twelve minutes only polls the next task and can never commit
        # the superseded one.
        [ -z "$_task" ] || [ "$_task" = "$_wanted" ] || exit 0
        if [ "$_task" = "$_wanted" ]; then
            case "$_state" in
                success)
                    # Do not depend on the App staying alive long enough to poll status.
                    # A completed fixed-weight task must atomically become the real
                    # module's next-boot payload from this background monitor too.
                    write_finalize_state running '正在提交下一启动字体负载'
                    if finalize_next_payload; then
                        write_finalize_state success '复合字体已准备，完整重启后生效'
                        mark_legacy_mix_mode
                        printf '[%s] legacy-v14 composite task committed for next boot: %s\n' \
                            "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" "$_wanted" >>"$LOG_FILE" 2>/dev/null || true
                    else
                        write_finalize_state failed '复合字体已生成，但下一启动负载提交失败'
                        printf '[%s] legacy-v14 composite task finished but next payload commit FAILED: %s\n' \
                            "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" "$_wanted" >>"$LOG_FILE" 2>/dev/null || true
                    fi
                    exit 0
                    ;;
                failed) exit 0 ;;
            esac
        fi
        sleep 1
        _loops=$((_loops + 1))
    done
    exit 0
}

case "${1:-status}" in
    monitor)
        monitor_task "${2:-}"
        ;;
    start)
        # Capturing an asynchronous engine with command substitution can keep the
        # substitution pipe alive for the background worker on Android. That makes
        # this start call wait for the whole build and pins the outer task at 34%.
        mkdir -p "$RUNTIME/cache" 2>/dev/null || true
        _response="$RUNTIME/cache/mix-engine-start.$$.json"
        rm -f "$_response" 2>/dev/null || true
        [ "${LUOSHU_MIX_CONTROLLER_OWNS_COMMIT:-false}" = true ] || \
            rm -f "$FINALIZE_STATE" 2>/dev/null || true
        MODDIR="$RUNTIME" LUOSHU_REAL_MODDIR="$REALMOD" \
            sh "$ENGINE" "$@" >"$_response" 2>&1
        _rc=$?
        cat "$_response" 2>/dev/null || true
        if [ "$_rc" -eq 0 ]; then
            _task=$(sed -n 's/^.*"task":"\([^"]*\)".*$/\1/p' "$_response" 2>/dev/null | tail -n1)
            # The weighted controller owns prepare/finalize for nested source
            # generation. A second monitor used to rerun failed inventory work.
            if [ -n "$_task" ] && [ "${LUOSHU_MIX_CONTROLLER_OWNS_COMMIT:-false}" != true ]; then
                ( trap '' HUP; MODDIR="$RUNTIME" LUOSHU_REAL_MODDIR="$REALMOD" sh "$0" monitor "$_task" ) </dev/null >>"$LOG_FILE" 2>&1 &
            fi
        fi
        rm -f "$_response" 2>/dev/null || true
        exit "$_rc"
        ;;
    status|recover)
        exec sh "$ENGINE" "$@"
        ;;
    *)
        exec sh "$ENGINE" "$@"
        ;;
esac
