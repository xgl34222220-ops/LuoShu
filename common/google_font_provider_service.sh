#!/system/bin/sh
# Wait for Android/GMS startup, then apply the Google downloadable-font bridge.
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
    _active=$(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null)
    [ -n "$_active" ] && [ "$_active" != default ] || exit 0
    MODDIR="$MODDIR" MODULE_DIR="$MODDIR" sh "$BRIDGE" apply >/dev/null 2>&1
    _rc=$?
    # GMS downloads families lazily. One mounted family must not end the boot
    # discovery window before Play opens or another font weight arrives. Binds
    # are idempotent, so later passes do not keep force-stopping Play.
    [ "$_attempt" -lt "$_limit" ] || break
    sleep 5
    _attempt=$((_attempt + 1))
done

[ "${_rc:-2}" -eq 0 ] && exit 0

mkdir -p "$MODDIR/logs" 2>/dev/null || true
printf '[%s] provider service exhausted retries: code=%s attempts=%s\n' \
    "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "${_rc:-2}" "$_attempt" \
    >> "$LOG" 2>/dev/null || true
exit 0
