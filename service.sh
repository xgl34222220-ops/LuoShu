#!/system/bin/sh
# LuoShu service router.
# Normal installations keep the current v4 service unchanged. Once the isolated
# physical compatibility runtime is selected, background v4 payload rebuilds stay off.
# App font inventory remains prewarmed through config/native_font_index.json.
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
    VERIFY="$MODDIR/config/device-font-load-verification.conf"
    MOUNT_STATE_FILE="$MODDIR/config/self-mount.conf"
    mkdir -p "$MODDIR/logs" "$MODDIR/config" 2>/dev/null || true
    printf '[%s] physical compatibility boot service start\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" >> "$LOG" 2>/dev/null

    _wait=0
    while [ "$(getprop sys.boot_completed 2>/dev/null)" != "1" ] && [ "$_wait" -lt 150 ]; do
        sleep 2
        _wait=$((_wait + 1))
    done
    [ "$(getprop sys.boot_completed 2>/dev/null)" = "1" ] || exit 0

    _active=$(sed -n '1p' "$MODDIR/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_active" ] || _active=$(sed -n 's/^font=//p' "$LEGACY_MODE" 2>/dev/null | head -n1 | tr -d '\r\n')
    [ -n "$_active" ] || _active=default
    _mount_state=$(sed -n 's/^state=//p' "$MOUNT_STATE_FILE" 2>/dev/null | head -n1 | tr -d '\r\n')
    _mount_failed=$(sed -n 's/^failed=//p' "$MOUNT_STATE_FILE" 2>/dev/null | head -n1 | tr -d '\r\n')
    _boot_id=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n')
    _now=$(date +%s 2>/dev/null || echo 0)

    rm -f "$MODDIR/config/text_reboot_required.conf" 2>/dev/null || true

    _verify_state=pending
    _verify_mode=compatibility
    _verify_reason=awaiting-mount-confirmation
    if [ "$_active" = default ]; then
        _verify_state=not-applicable
        _verify_mode=system
        _verify_reason=default-font
    else
        case "$_mount_state" in
            mounted|degraded|confirmed|verified)
                _verify_state=verified
                _verify_mode=mount-confirmed
                _verify_reason=physical-self-mount-active
                ;;
            failed)
                _verify_state=failed
                _verify_mode=compatibility
                _verify_reason="self-mount-failed${_mount_failed:+:$_mount_failed}"
                ;;
            *)
                _verify_state=pending
                _verify_mode=compatibility
                _verify_reason=mount-state-not-confirmed
                ;;
        esac
    fi

    {
        printf 'state=%s\n' "$_verify_state"
        printf 'mode=%s\n' "$_verify_mode"
        printf 'activeFont=%s\n' "$_active"
        printf 'reason=%s\n' "$_verify_reason"
        printf 'bootId=%s\n' "$_boot_id"
        printf 'time=%s\n' "$_now"
    } > "${VERIFY}.tmp.$$" 2>/dev/null && mv -f "${VERIFY}.tmp.$$" "$VERIFY" 2>/dev/null || true
    chmod 0644 "$VERIFY" 2>/dev/null || true

    case "$_verify_state" in
        verified|not-applicable)
            rm -rf "$MODDIR/.luoshu-retired" "$MODDIR"/.luoshu-payload-stage.* 2>/dev/null || true
            printf '[%s] font load confirmed: active=%s mount=%s\n' \
                "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" "$_active" "$_mount_state" >> "$LOG" 2>/dev/null
            ;;
        failed)
            printf '[%s] font load FAILED: active=%s mount=%s detail=%s; retired payload retained\n' \
                "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" "$_active" "$_mount_state" "$_mount_failed" >> "$LOG" 2>/dev/null
            ;;
        *)
            printf '[%s] font load pending: active=%s mount=%s; retired payload retained\n' \
                "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" "$_active" "${_mount_state:-unknown}" >> "$LOG" 2>/dev/null
            ;;
    esac

    if [ -f "$MODDIR/config/app_install_pending" ] && [ -f "$MODDIR/common/app_installer.sh" ]; then
        MODDIR="$MODDIR" sh "$MODDIR/common/app_installer.sh" service-retry >> "$LOG" 2>&1 || true
    fi
    if [ -f "$MODDIR/common/module_status.sh" ]; then
        MODDIR="$MODDIR" sh "$MODDIR/common/module_status.sh" "$_active" >> "$LOG" 2>&1 || true
    fi
    if [ -f "$MODDIR/common/font_manager.sh" ]; then
        MODDIR="$MODDIR" sh "$MODDIR/common/font_manager.sh" action list --native-index >/dev/null 2>&1 || true
    fi

    printf '[%s] physical compatibility service complete: %s (%s)\n' \
        "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" "$_active" "$_verify_state" >> "$LOG" 2>/dev/null
) &

exit 0