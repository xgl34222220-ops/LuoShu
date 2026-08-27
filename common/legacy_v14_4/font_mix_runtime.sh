#!/system/bin/sh
# v14.4 composite engine compatibility wrapper.
# The original v14.1 font_mix engine is preserved byte-for-byte as font_mix_engine.sh.
# This wrapper only bridges its async task lifecycle to the current private payload boot mode.
set +e
RUNTIME="${MODDIR:-}"
REALMOD="${LUOSHU_REAL_MODDIR:-/data/adb/modules/LuoShu}"
ENGINE="$RUNTIME/common/font_mix_engine.sh"
TASK_FILE="$RUNTIME/config/mix_task.conf"
LEGACY_MODE="$RUNTIME/config/font_runtime_legacy_v14_4.conf"
LOG_FILE="$RUNTIME/logs/fontswitch.log"

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
        printf 'pipeline=legacy-v14-composite\n'
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

monitor_task() {
    _wanted="$1"
    _loops=0
    while [ "$_loops" -lt 720 ]; do
        _task="$(read_task_value task)"
        _state="$(read_task_value state)"
        if [ "$_task" = "$_wanted" ]; then
            case "$_state" in
                success)
                    mark_legacy_mix_mode
                    printf '[%s] legacy-v14 composite task committed: %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" "$_wanted" >>"$LOG_FILE" 2>/dev/null || true
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
        _out="$(MODDIR="$RUNTIME" LUOSHU_REAL_MODDIR="$REALMOD" sh "$ENGINE" "$@" 2>&1)"
        _rc=$?
        printf '%s\n' "$_out"
        if [ "$_rc" -eq 0 ]; then
            _task=$(printf '%s\n' "$_out" | sed -n 's/^.*"task":"\([^"]*\)".*$/\1/p' | tail -n1)
            if [ -n "$_task" ]; then
                ( trap '' HUP; MODDIR="$RUNTIME" LUOSHU_REAL_MODDIR="$REALMOD" sh "$0" monitor "$_task" ) </dev/null >>"$LOG_FILE" 2>&1 &
            fi
        fi
        exit "$_rc"
        ;;
    status|recover)
        exec sh "$ENGINE" "$@"
        ;;
    *)
        exec sh "$ENGINE" "$@"
        ;;
esac
