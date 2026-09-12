#!/system/bin/sh
# Apply during startup, then maintain lazily downloaded fonts for this boot.
set +e

MODDIR="${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
BRIDGE="$MODDIR/common/google_font_provider_bridge.sh"
LOCK="$MODDIR/.google-font-provider.lock"
LOG="$MODDIR/logs/google-font-provider.log"

[ -f "$BRIDGE" ] || exit 0
[ -f "$MODDIR/common/font_switch_lock.sh" ] && . "$MODDIR/common/font_switch_lock.sh"

_waited=0
while [ "$(getprop sys.boot_completed 2>/dev/null)" != 1 ] && [ "$_waited" -lt 600 ]; do
    sleep 3
    _waited=$((_waited + 3))
done
[ "$(getprop sys.boot_completed 2>/dev/null)" = 1 ] || exit 0

# A bare mkdir lock survives an interrupted boot and used to disable all later
# attempts. Reuse the module's PID/start-time/boot-identity lock implementation.
type luoshu_font_lock_acquire >/dev/null 2>&1 || exit 1
luoshu_font_lock_acquire "$LOCK" "$$" || exit 0
trap 'luoshu_font_lock_release "$LOCK" "$$" >/dev/null 2>&1 || true' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

_attempt=1
_limit="${LUOSHU_GOOGLE_FONT_RETRIES:-24}"
case "$_limit" in ''|*[!0-9]*) _limit=24 ;; esac
[ "$_limit" -ge 1 ] 2>/dev/null || _limit=1

while [ "$_attempt" -le "$_limit" ]; do
    [ -d "$MODDIR" ] && [ ! -f "$MODDIR/disable" ] && [ ! -f "$MODDIR/remove" ] || exit 0
    _active=$(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null)
    [ -n "$_active" ] && [ "$_active" != default ] || exit 0
    # Keep the view from before the last boot apply. A download that arrives
    # while apply is working must remain a change at the first watch pass.
    if [ "$_attempt" -eq "$_limit" ] && [ "${LUOSHU_GOOGLE_FONT_WATCH_CYCLES:--1}" != 0 ]; then
        _fingerprint=$(MODDIR="$MODDIR" sh "$BRIDGE" fingerprint 2>/dev/null)
    fi
    MODDIR="$MODDIR" MODULE_DIR="$MODDIR" sh "$BRIDGE" apply >/dev/null 2>&1
    _rc=$?
    # GMS downloads families lazily. One mounted family must not end the boot
    # discovery window before Play opens or another font weight arrives. Binds
    # are idempotent, so later passes do not keep force-stopping Play.
    [ "$_attempt" -lt "$_limit" ] || break
    sleep 5
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
    [ -d "$MODDIR" ] && [ ! -f "$MODDIR/disable" ] && [ ! -f "$MODDIR/remove" ] || exit 0
    _active=$(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null)
    [ -n "$_active" ] && [ "$_active" != default ] || exit 0
    _observed=$(MODDIR="$MODDIR" sh "$BRIDGE" fingerprint 2>/dev/null)
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
        MODDIR="$MODDIR" MODULE_DIR="$MODDIR" LUOSHU_GOOGLE_FONT_ALLOW_RESTART=0 \
            sh "$BRIDGE" apply >/dev/null 2>&1
        _rc=$?
        _retry_age=0
        # Retain the PRE-apply view. A post-apply snapshot could include a new
        # download/process that apply never handled, hiding it permanently.
        # Our own binds may cause one extra idempotent pass, then settle.
        _fingerprint="$_observed"
    fi
done
exit 0
