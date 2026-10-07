#!/system/bin/sh
# One boot/apply reconciliation. No idle font watcher remains after this exits.
set +e

MODDIR="${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
if [ -f "$MODDIR/common/runtime_paths.sh" ]; then
    . "$MODDIR/common/runtime_paths.sh"
    luoshu_runtime_paths_init "$MODDIR" || exit 1
fi
_provider_tasks="${LUOSHU_TASKS_DIR:-$MODDIR/.luoshu-state/tasks}"
mkdir -p "$_provider_tasks" || exit 1
SCOPE="$MODDIR/common/task_scope.sh"
[ -f "$SCOPE" ] || exit 1
if [ -z "${LUOSHU_TASK_SCOPE_PID:-}" ]; then
    exec sh "$SCOPE" run --pid-file "$_provider_tasks/font-provider-service.pid" \
        --task font-provider-service --timeout "${LUOSHU_GOOGLE_FONT_TASK_TIMEOUT:-1200}" -- sh "$0" "$@"
fi

BRIDGE="$MODDIR/common/google_font_provider_bridge.sh"
THEME_BRIDGE="$MODDIR/common/hyperos_theme_font_bridge.sh"
FALLBACK="$MODDIR/common/google_font_fallback.sh"
LOCK="$_provider_tasks/google-font-provider.lock"
[ -f "$BRIDGE" ] || exit 0
[ -f "$MODDIR/common/font_switch_lock.sh" ] && . "$MODDIR/common/font_switch_lock.sh"
type luoshu_font_lock_acquire >/dev/null 2>&1 || exit 1
luoshu_font_lock_acquire "$LOCK" "$$" || exit 0
trap 'luoshu_font_lock_release "$LOCK" "$$" >/dev/null 2>&1 || true' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

provider_run() {
    MODDIR="$MODDIR" MODULE_DIR="$MODDIR" LUOSHU_GOOGLE_FONT_ALLOW_RESTART=0 \
        sh "$1" "$2"
}

provider_restore() {
    _provider_restore_rc=0
    provider_run "$BRIDGE" restore || _provider_restore_rc=1
    if [ -f "$THEME_BRIDGE" ]; then
        provider_run "$THEME_BRIDGE" restore || _provider_restore_rc=1
    fi
    return "$_provider_restore_rc"
}

# The boot entry gets one bounded readiness wait. Explicit reconciliation is
# immediate, and neither path waits for future downloads or a new selection.
case "${1:-boot}" in
    boot)
        _provider_wait_limit="${LUOSHU_GOOGLE_FONT_BOOT_WAIT_SECONDS:-600}"
        case "$_provider_wait_limit" in ''|*[!0-9]*) _provider_wait_limit=600 ;; esac
        [ "$_provider_wait_limit" -le 600 ] || _provider_wait_limit=600
        _provider_waited=0
        while [ "$(getprop sys.boot_completed 2>/dev/null)" != 1 ]; do
            [ -d "$MODDIR" ] || exit 0
            if [ -f "$MODDIR/disable" ] || [ -f "$MODDIR/remove" ]; then
                provider_restore; exit $?
            fi
            [ "$_provider_waited" -lt "$_provider_wait_limit" ] || exit 0
            sleep 1
            _provider_waited=$((_provider_waited + 1))
        done
        ;;
    apply|now|reconcile) ;;
    restore) provider_restore; exit $? ;;
    *) echo "Usage: $0 {boot|apply|reconcile|restore}" >&2; exit 2 ;;
esac

[ -d "$MODDIR" ] || exit 0
_provider_active=$(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
if [ -z "$_provider_active" ] || [ "$_provider_active" = default ] || \
   [ -f "$MODDIR/disable" ] || [ -f "$MODDIR/remove" ]; then
    provider_restore
    exit $?
fi

# This remains a finite boot/apply pass. Only a validated existing undo record
# with a same-install verified GMS package update reset can cause a component
# write. A missing record, unchanged revision or explicit enable stays untouched.
_provider_fallback_rc=0
if [ -f "$FALLBACK" ]; then
    _provider_fallback_log="${LUOSHU_LOG_DIR:-$MODDIR/logs}/google-font-compatibility.log"
    mkdir -p "${_provider_fallback_log%/*}" 2>/dev/null || true
    _provider_fallback_bytes=$(stat -c '%s' "$_provider_fallback_log" 2>/dev/null)
    case "$_provider_fallback_bytes" in ''|*[!0-9]*) _provider_fallback_bytes=0 ;; esac
    [ "$_provider_fallback_bytes" -lt 1048576 ] || \
        mv -f "$_provider_fallback_log" "${_provider_fallback_log}.1" 2>/dev/null || true
    MODDIR="$MODDIR" MODULE_DIR="$MODDIR" \
        sh "$FALLBACK" reconcile-owned --json >> "$_provider_fallback_log" 2>&1 || \
        _provider_fallback_rc=1
fi

provider_run "$BRIDGE" apply
_provider_google_rc=$?
_provider_theme_rc=2
if [ -f "$THEME_BRIDGE" ]; then
    provider_run "$THEME_BRIDGE" apply
    _provider_theme_rc=$?
fi
# Check only the queued old descriptors seen in this pass. Foreground apps are
# preserved; any retained recovery records are data, never a waiting process.
_provider_refresh_rc=0
if [ -s "$MODDIR/config/google-font-refresh-pending.conf" ]; then
    provider_run "$BRIDGE" refresh || _provider_refresh_rc=1
fi
case "$_provider_google_rc:$_provider_theme_rc:$_provider_refresh_rc:$_provider_fallback_rc" in
    0:0:0:0|0:2:0:0|2:0:0:0|2:2:0:0) exit 0 ;;
    *) exit 1 ;;
esac
