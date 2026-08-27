#!/system/bin/sh
# Wait for Android/GMS startup, then apply the Google downloadable-font bridge.
set +e

MODDIR="${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
BRIDGE="$MODDIR/common/google_font_provider_bridge.sh"
LOCK="$MODDIR/.google-font-provider.lock"
LOG="$MODDIR/logs/google-font-provider.log"

[ -f "$BRIDGE" ] || exit 0

_waited=0
while [ "$(getprop sys.boot_completed 2>/dev/null)" != 1 ] && [ "$_waited" -lt 600 ]; do
    sleep 3
    _waited=$((_waited + 3))
done
[ "$(getprop sys.boot_completed 2>/dev/null)" = 1 ] || exit 0

if ! mkdir "$LOCK" 2>/dev/null; then
    exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT HUP INT TERM

_attempt=1
_limit="${LUOSHU_GOOGLE_FONT_RETRIES:-24}"
case "$_limit" in ''|*[!0-9]*) _limit=24 ;; esac
[ "$_limit" -ge 1 ] 2>/dev/null || _limit=1

while [ "$_attempt" -le "$_limit" ]; do
    MODDIR="$MODDIR" MODULE_DIR="$MODDIR" sh "$BRIDGE" apply >/dev/null 2>&1
    _rc=$?
    [ "$_rc" -eq 0 ] && exit 0
    [ "$_attempt" -lt "$_limit" ] || break
    sleep 5
    _attempt=$((_attempt + 1))
done

mkdir -p "$MODDIR/logs" 2>/dev/null || true
printf '[%s] provider service exhausted retries: code=%s attempts=%s\n' \
    "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "${_rc:-2}" "$_attempt" \
    >> "$LOG" 2>/dev/null || true
exit 0
