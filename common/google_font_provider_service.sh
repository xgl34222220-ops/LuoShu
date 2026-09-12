#!/system/bin/sh
# Apply during startup, then maintain lazily downloaded fonts for this boot.
set +e

MODDIR="${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
BRIDGE="$MODDIR/common/google_font_provider_bridge.sh"
THEME_BRIDGE="$MODDIR/common/hyperos_theme_font_bridge.sh"
LOCK="$MODDIR/.google-font-provider.lock"
LOG="$MODDIR/logs/google-font-provider.log"

[ -f "$BRIDGE" ] || exit 0
[ -f "$MODDIR/common/font_switch_lock.sh" ] && . "$MODDIR/common/font_switch_lock.sh"
[ -f "$MODDIR/common/background_task.sh" ] && . "$MODDIR/common/background_task.sh"

_provider_child=
provider_signal_exit() {
    _provider_signal_code="$1"
    trap '' HUP INT TERM
    if [ -n "$_provider_child" ]; then
        if type luoshu_terminate_task_tree >/dev/null 2>&1; then
            luoshu_terminate_task_tree "$_provider_child"
        else
            kill -TERM "$_provider_child" 2>/dev/null || true
        fi
        wait "$_provider_child" 2>/dev/null || true
    fi
    exit "$_provider_signal_code"
}

provider_run() {
    MODDIR="$MODDIR" MODULE_DIR="$MODDIR" LUOSHU_GOOGLE_FONT_ALLOW_RESTART="$3" \
        sh "$1" "$2" >/dev/null 2>&1 &
    _provider_child=$!
    wait "$_provider_child"
    _provider_apply_rc=$?
    _provider_child=
    return "$_provider_apply_rc"
}

provider_apply() {
    provider_run "$BRIDGE" apply "$1"
    _provider_google_rc=$?
    _provider_theme_rc=2
    if [ -f "$THEME_BRIDGE" ]; then
        provider_run "$THEME_BRIDGE" apply 0
        _provider_theme_rc=$?
    fi
    # Either adapter can need repair even when the other has no targets.
    case "$_provider_google_rc:$_provider_theme_rc" in
        0:0|0:2|2:0) return 0 ;;
        2:2) return 2 ;;
        *) return 1 ;;
    esac
}

provider_fingerprint() {
    _provider_google_fp=$(MODDIR="$MODDIR" sh "$BRIDGE" fingerprint 2>/dev/null) || return 1
    _provider_theme_fp=
    if [ -f "$THEME_BRIDGE" ]; then
        _provider_theme_fp=$(MODDIR="$MODDIR" sh "$THEME_BRIDGE" fingerprint 2>/dev/null) || return 1
    fi
    printf 'google|%s\ntheme|%s\n' "$_provider_google_fp" "$_provider_theme_fp"
}

provider_restore_theme() {
    # Restore both adapters. Keep this function name for older lifecycle callers.
    _provider_cleanup_rc=0
    provider_restore_bridge "$BRIDGE" || _provider_cleanup_rc=1
    [ ! -f "$THEME_BRIDGE" ] || provider_restore_bridge "$THEME_BRIDGE" || _provider_cleanup_rc=1
    return "$_provider_cleanup_rc"
}

provider_restore_bridge() {
    _provider_restore_bridge="$1"
    _provider_restore_attempt=1
    while [ "$_provider_restore_attempt" -le 3 ]; do
        provider_run "$_provider_restore_bridge" restore 0 && return 0
        # Removal can finish while a child is unwinding. Do not recreate a
        # removed module just to record an already obsolete cleanup failure.
        [ -d "$MODDIR" ] && [ -f "$_provider_restore_bridge" ] || return 0
        mkdir -p "${LOG%/*}" 2>/dev/null || true
        printf '[%s] font restore failed (attempt %s/3); namespace journal retained\n' \
            "$(date '+%F %T' 2>/dev/null)" "$_provider_restore_attempt" >> "$LOG" 2>/dev/null || true
        [ "$_provider_restore_attempt" -lt 3 ] || return 1
        # Keep the bounded retry pause cancellable through the same child-tree
        # handler as apply/restore; disabling must never leave a waiting worker.
        sleep 3 &
        _provider_child=$!
        wait "$_provider_child"
        _provider_child=
        _provider_restore_attempt=$((_provider_restore_attempt + 1))
    done
    return 1
}

# A bare mkdir lock survives an interrupted boot and used to disable all later
# attempts. Reuse the module's PID/start-time/boot-identity lock implementation.
# Acquire before waiting for boot too: repeated service entries must not leave
# several sleeping boot waiters around for ten minutes.
type luoshu_font_lock_acquire >/dev/null 2>&1 || exit 1
luoshu_font_lock_acquire "$LOCK" "$$" || exit 0
trap 'luoshu_font_lock_release "$LOCK" "$$" >/dev/null 2>&1 || true' EXIT
trap 'provider_signal_exit 129' HUP
trap 'provider_signal_exit 130' INT
trap 'provider_signal_exit 143' TERM

_waited=0
while [ "$(getprop sys.boot_completed 2>/dev/null)" != 1 ] && [ "$_waited" -lt 600 ]; do
    [ -d "$MODDIR" ] && [ ! -f "$MODDIR/disable" ] && [ ! -f "$MODDIR/remove" ] || { provider_restore_theme; exit $?; }
    sleep 3
    _waited=$((_waited + 3))
done
[ "$(getprop sys.boot_completed 2>/dev/null)" = 1 ] || exit 0

_attempt=1
_limit="${LUOSHU_GOOGLE_FONT_RETRIES:-24}"
case "$_limit" in ''|*[!0-9]*) _limit=24 ;; esac
[ "$_limit" -ge 1 ] 2>/dev/null || _limit=1
_fingerprint=
_boot_retry_age=0

while [ "$_attempt" -le "$_limit" ]; do
    [ -d "$MODDIR" ] && [ ! -f "$MODDIR/disable" ] && [ ! -f "$MODDIR/remove" ] || { provider_restore_theme; exit $?; }
    _active=$(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null)
    [ -n "$_active" ] && [ "$_active" != default ] || { provider_restore_theme; exit $?; }
    # Continue discovery throughout boot, but only generate/inspect fonts when
    # metadata changes. The former 24 unconditional applies repeatedly launched
    # Python and hashed large composite fonts even on a completely idle phone.
    _observed=$(provider_fingerprint)
    _repair=0
    [ -n "$_observed" ] && [ "$_observed" = "$_fingerprint" ] || _repair=1
    case "${_rc:-2}" in
        0|2) ;;
        *) [ "$_boot_retry_age" -lt 30 ] || _repair=1 ;;
    esac
    if [ "$_repair" = 1 ]; then
        provider_apply "${LUOSHU_GOOGLE_FONT_ALLOW_RESTART:-1}"
        _rc=$?
        _boot_retry_age=0
        # Keep the PRE-apply view, including at the handoff to the long-lived
        # watch. Downloads arriving during apply must remain visible changes.
        _fingerprint=$_observed
    fi
    [ ! -s "$MODDIR/config/google-font-refresh-pending.conf" ] || provider_run "$BRIDGE" refresh 0
    # GMS downloads families lazily. One mounted family must not end the boot
    # discovery window before Play opens or another font weight arrives. Binds
    # are idempotent; old consumer FDs use only the deferred background queue.
    [ "$_attempt" -lt "$_limit" ] || break
    sleep 5
    _boot_retry_age=$((_boot_retry_age + 5))
    _attempt=$((_attempt + 1))
done

# GMS can download another family/weight hours later, or restart into a new
# namespace. The old service stopped permanently after its two-minute window.
# Keep a sleeping shell, inspecting only metadata every 30 seconds. Unchanged
# state does not launch FontTools, clone fonts, mount files or restart apps.
_interval="${LUOSHU_GOOGLE_FONT_WATCH_INTERVAL:-30}"
case "$_interval" in ''|*[!0-9]*) _interval=30 ;; esac
[ "$_interval" -ge 15 ] 2>/dev/null || _interval=15
_watch_limit="${LUOSHU_GOOGLE_FONT_WATCH_CYCLES:--1}"
case "$_watch_limit" in -1) ;; ''|*[!0-9]*) _watch_limit=-1 ;; esac
[ "$_watch_limit" != 0 ] || exit 0
_watch_count=0
_retry_age=0
_fingerprint="${_fingerprint:-}"
while [ "$_watch_limit" = -1 ] || [ "$_watch_count" -lt "$_watch_limit" ]; do
    sleep "$_interval"
    _watch_count=$((_watch_count + 1))
    [ -d "$MODDIR" ] && [ ! -f "$MODDIR/disable" ] && [ ! -f "$MODDIR/remove" ] || { provider_restore_theme; exit $?; }
    _active=$(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null)
    [ -n "$_active" ] && [ "$_active" != default ] || { provider_restore_theme; exit $?; }
    _observed=$(provider_fingerprint)
    _retry_age=$((_retry_age + _interval))
    _repair=0
    [ -n "$_observed" ] && [ "$_observed" = "$_fingerprint" ] || _repair=1
    # A stable but partially failed mount gets another chance every five minutes;
    # no-target (2) is normal and will be revisited when a download appears.
    case "${_rc:-2}" in
        0|2) ;;
        *) [ "$_retry_age" -lt 300 ] || _repair=1 ;;
    esac
    if [ "$_repair" = 1 ]; then
        provider_apply 0
        _rc=$?
        _retry_age=0
        # Retain the PRE-apply view. A post-apply snapshot could include a new
        # download/process that apply never handled, hiding it permanently.
        # Our own binds may cause one extra idempotent pass, then settle.
        _fingerprint="$_observed"
    fi
    [ ! -s "$MODDIR/config/google-font-refresh-pending.conf" ] || provider_run "$BRIDGE" refresh 0
done
exit 0
