#!/system/bin/sh
# Schedule device-font load verification after Android boot without blocking post-fs-data.
set +e

MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then
        MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"
    else
        MODDIR="/data/adb/modules/LuoShu"
    fi
fi

VERIFY_SCRIPT="$MODDIR/common/device_font_load_verify.sh"
BACKGROUND_TASK="$MODDIR/common/background_task.sh"
PID_FILE="$MODDIR/config/device-font-boot-verify.pid"
LOG_FILE="$MODDIR/logs/device-font-load-verify.log"
STATE_FILE="$MODDIR/config/device-font-load-verification.conf"

[ -f "$BACKGROUND_TASK" ] && . "$BACKGROUND_TASK"

BOOT_WAIT_LIMIT="${LUOSHU_BOOT_VERIFY_BOOT_WAIT_LIMIT:-600}"
SETTLE_SECONDS="${LUOSHU_BOOT_VERIFY_SETTLE_SECONDS:-12}"
IDLE_WAIT_LIMIT="${LUOSHU_BOOT_VERIFY_IDLE_WAIT_LIMIT:-300}"
POLL_SECONDS="${LUOSHU_BOOT_VERIFY_POLL_SECONDS:-3}"
for _numeric_name in BOOT_WAIT_LIMIT SETTLE_SECONDS IDLE_WAIT_LIMIT POLL_SECONDS; do
    eval "_numeric_value=\${$_numeric_name}"
    case "$_numeric_value" in ''|*[!0-9]*) eval "$_numeric_name=0" ;; esac
done
[ "$POLL_SECONDS" -ge 1 ] 2>/dev/null || POLL_SECONDS=1

_boot_verify_value() {
    sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

_boot_verify_write_pending() {
    _reason="$1"
    _active=$(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_active" ] || _active=default
    _tmp="${STATE_FILE}.tmp.$$"
    mkdir -p "${STATE_FILE%/*}" 2>/dev/null || return 1
    {
        printf 'state=pending\n'
        printf 'mode=compatibility\n'
        printf 'activeFont=%s\n' "$_active"
        printf 'reason=%s\n' "$_reason"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_tmp" 2>/dev/null || return 1
    mv -f "$_tmp" "$STATE_FILE" 2>/dev/null || return 1
    chmod 0600 "$STATE_FILE" 2>/dev/null || true
}

_boot_verify_busy() {
    [ -e "$MODDIR/.font_switch.lock" ] && return 0
    [ -f "$MODDIR/config/font-payload-rebuild-pending.conf" ] && return 0
    _switch_state=$(_boot_verify_value "$MODDIR/config/switch_task.conf" state)
    _mix_state=$(_boot_verify_value "$MODDIR/config/axes_task.conf" state)
    case "$_switch_state:$_mix_state" in
        queued:*|running:*|*:queued|*:running) return 0 ;;
    esac
    return 1
}

_boot_verify_worker() {
    _task="$1"
    _waited=0
    while [ "$(getprop sys.boot_completed 2>/dev/null)" != "1" ] && [ "$_waited" -lt "$BOOT_WAIT_LIMIT" ]; do
        sleep "$POLL_SECONDS"
        _waited=$((_waited + POLL_SECONDS))
    done
    if [ "$(getprop sys.boot_completed 2>/dev/null)" != "1" ]; then
        _boot_verify_write_pending boot-not-completed
        type luoshu_clear_task_pid >/dev/null 2>&1 && luoshu_clear_task_pid "$PID_FILE" "$_task"
        return 2
    fi

    # Let service.sh finish template refresh/index warm-up, then wait for active transactions.
    [ "$SETTLE_SECONDS" -eq 0 ] 2>/dev/null || sleep "$SETTLE_SECONDS"
    _idle_wait=0
    while _boot_verify_busy && [ "$_idle_wait" -lt "$IDLE_WAIT_LIMIT" ]; do
        sleep "$POLL_SECONDS"
        _idle_wait=$((_idle_wait + POLL_SECONDS))
    done
    if _boot_verify_busy; then
        _boot_verify_write_pending background-task-still-running
        printf '[%s] [LOAD-VERIFY] 后台字体任务仍在运行，本次延后验证\n' \
            "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" >> "$LOG_FILE" 2>/dev/null || true
        type luoshu_clear_task_pid >/dev/null 2>&1 && luoshu_clear_task_pid "$PID_FILE" "$_task"
        return 2
    fi

    if [ -f "$VERIFY_SCRIPT" ]; then
        MODDIR="$MODDIR" MODULE_DIR="$MODDIR" sh "$VERIFY_SCRIPT"
        _rc=$?
    else
        _boot_verify_write_pending verifier-missing
        _rc=1
    fi
    type luoshu_clear_task_pid >/dev/null 2>&1 && luoshu_clear_task_pid "$PID_FILE" "$_task"
    return "$_rc"
}

_boot_verify_schedule() {
    mkdir -p "$MODDIR/config" "$MODDIR/logs" 2>/dev/null || true
    _boot_id=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n' | cut -c1-16)
    [ -n "$_boot_id" ] || _boot_id=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null | cksum | awk '{print $1}')
    [ -n "$_boot_id" ] || _boot_id=$(date +%s 2>/dev/null || echo boot)
    _task="boot-verify-$_boot_id"

    if type luoshu_start_detached >/dev/null 2>&1; then
        luoshu_start_detached "$PID_FILE" "$_task" "$LOG_FILE" sh "$0" run "$_task"
        _rc=$?
        [ "$_rc" -eq 3 ] && return 0
        return "$_rc"
    fi

    if [ -s "$PID_FILE" ]; then
        _pid=$(head -n1 "$PID_FILE" 2>/dev/null)
        case "$_pid" in ''|*[!0-9]*) ;; *) kill -0 "$_pid" 2>/dev/null && return 0 ;; esac
    fi
    ( trap '' HUP; exec sh "$0" run "$_task" ) </dev/null >> "$LOG_FILE" 2>&1 &
    _pid=$!
    printf '%s\n' "$_pid" > "$PID_FILE" 2>/dev/null || true
    return 0
}

case "${1:-schedule}" in
    schedule) _boot_verify_schedule ;;
    run) _boot_verify_worker "${2:-boot-verify}" ;;
    *) exit 2 ;;
esac
