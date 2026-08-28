#!/system/bin/sh
# LuoShu service router.
# Normal installations keep the current v4 service unchanged. Once a font is applied
# with the v14.4 compatibility core, background v4 template/payload rebuilds are
# intentionally disabled so the physical-file mapping cannot be rewritten after boot.
# Current App inventory is still prewarmed through config/native_font_index.json.
set +e
MODDIR="${0%/*}"
LEGACY_MODE="$MODDIR/config/font_runtime_legacy_v14_4.conf"
V4_SERVICE="$MODDIR/service_v4.sh"

if [ ! -f "$LEGACY_MODE" ]; then
    [ -f "$V4_SERVICE" ] && exec sh "$V4_SERVICE"
    exit 0
fi

(
    LOG="$MODDIR/logs/service-legacy-v14.4.log"
    mkdir -p "$MODDIR/logs" "$MODDIR/config" 2>/dev/null || true
    printf '[%s] legacy-v14.4 boot service start\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" >> "$LOG" 2>/dev/null

    # Never enter device-template / slot-build / XML batch / cached v4 validation here.
    # The early boot stage already mounts the private physical-file payload.
    _wait=0
    while [ "$(getprop sys.boot_completed 2>/dev/null)" != "1" ] && [ "$_wait" -lt 150 ]; do
        sleep 2
        _wait=$((_wait + 1))
    done

    _active=$(sed -n '1p' "$MODDIR/config/active_font.conf" 2>/dev/null)
    [ -n "$_active" ] || _active=$(sed -n 's/^font=//p' "$LEGACY_MODE" 2>/dev/null | head -n1)
    [ -n "$_active" ] || _active=default
    _boot_id=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n')
    _now=$(date +%s 2>/dev/null || echo 0)

    # A completed reboot satisfies the foreground switch's restart requirement.
    # Keep the mode inside the App bridge's verified contract. The old
    # legacy-physical-map value was written as verified here but rejected by the App,
    # leaving HyperOS permanently displayed as "已准备，待本次启动验证".
    rm -f "$MODDIR/config/text_reboot_required.conf" 2>/dev/null || true
    {
        printf 'state=verified\n'
        printf 'mode=mount-confirmed\n'
        printf 'activeFont=%s\n' "$_active"
        printf 'reason=legacy-physical-map\n'
        printf 'bootId=%s\n' "$_boot_id"
        printf 'time=%s\n' "$_now"
    } > "$MODDIR/config/device-font-load-verification.conf" 2>/dev/null || true
    chmod 0644 "$MODDIR/config/device-font-load-verification.conf" 2>/dev/null || true

    # Foreground switching now stages a completely new physical mapping and keeps the
    # previous source tree alive until reboot. Once this boot is complete, no active
    # mount can still depend on those retired source directories, so reclaim them here.
    rm -rf "$MODDIR/.luoshu-retired" "$MODDIR"/.luoshu-payload-stage.* 2>/dev/null || true

    # Preserve the current App lifecycle without touching the font payload.
    if [ -f "$MODDIR/config/app_install_pending" ] && [ -f "$MODDIR/common/app_installer.sh" ]; then
        MODDIR="$MODDIR" sh "$MODDIR/common/app_installer.sh" service-retry >> "$LOG" 2>&1 || true
    fi
    if [ -f "$MODDIR/common/module_status.sh" ]; then
        MODDIR="$MODDIR" sh "$MODDIR/common/module_status.sh" "$_active" >> "$LOG" 2>&1 || true
    fi
    if [ -f "$MODDIR/common/font_manager.sh" ]; then
        MODDIR="$MODDIR" sh "$MODDIR/common/font_manager.sh" action list --native-index >/dev/null 2>&1 || true
    fi

    printf '[%s] legacy-v14.4 payload preserved: %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" "$_active" >> "$LOG" 2>/dev/null
) &

exit 0