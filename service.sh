#!/system/bin/sh
# LuoShu service router.
# Normal installations keep the current v4 service unchanged. Once the isolated
# physical compatibility runtime is selected, background v4 payload rebuilds stay off.
# App font inventory remains prewarmed through config/native_font_index.json.
set +e
MODDIR="${0%/*}"
LEGACY_MODE="$MODDIR/config/font_runtime_legacy_v14_4.conf"
V4_SERVICE="$MODDIR/.luoshu-runtime/core/service.sh"

# Start from the real entry point before either service route is selected. The
# mount loader sees $0=service_v4.sh on one route and is absent on the other.
if [ -f "$MODDIR/common/google_font_provider_service.sh" ]; then
    (
        MODDIR="$MODDIR" MODULE_DIR="$MODDIR" \
            sh "$MODDIR/common/google_font_provider_service.sh" boot
    ) </dev/null >/dev/null 2>&1 &
fi

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
    _verified_generation=$(cksum "$MODDIR/config/font-payload-activated.conf" 2>/dev/null)

    # A mount transaction or partition nonce does not prove the selected bytes
    # reached Android's font namespace. Verify once after boot, retaining both
    # active and retired payloads on missing or mismatched evidence.
    _verify_rc=2
    if [ -f "$MODDIR/common/device_font_load_verify.sh" ]; then
        MODDIR="$MODDIR" MODULE_DIR="$MODDIR" \
            sh "$MODDIR/common/device_font_load_verify.sh" verify >> "$LOG" 2>&1
        _verify_rc=$?
    fi
    _verify_state=$(sed -n 's/^state=//p' "$VERIFY" 2>/dev/null | head -n1)
    [ -n "$_verify_state" ] || _verify_state=pending
    # A crashed/missing verifier cannot promote an older success record.
    case "$_verify_rc:$_verify_state" in
        0:verified|0:not-applicable|1:failed|2:pending) ;;
        *) _verify_state=pending ;;
    esac

    case "$_verify_state" in
        verified|not-applicable)
            # Foreground transactions own their stage directories. Cleanup may
            # only retire this verified generation while holding their shared
            # lock; a new selection or prepared generation keeps its recovery copy.
            _verified_manifest=$(sed -n 's/^manifestDigest=//p' "$VERIFY" 2>/dev/null | head -n1)
            if [ -f "$MODDIR/common/font_switch_lock.sh" ]; then
                . "$MODDIR/common/font_switch_lock.sh"
                _cleanup_owner=$(sh -c 'printf "%s\n" "$PPID"')
                case "$_cleanup_owner" in ''|*[!0-9]*) _cleanup_owner=$$ ;; esac
                if luoshu_font_lock_acquire "$MODDIR/.font_switch.lock" "$_cleanup_owner"; then
                    _cleanup_active=$(sed -n '1p' "$MODDIR/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
                    [ -n "$_cleanup_active" ] || _cleanup_active=default
                    _cleanup_generation=$(cksum "$MODDIR/config/font-payload-activated.conf" 2>/dev/null)
                    _cleanup_next=$(sed -n 's/^state=//p' "$MODDIR/config/font-payload-next.conf" 2>/dev/null | head -n1)
                    if [ "$_cleanup_active" = "$_active" ] && \
                       [ "$_cleanup_generation" = "$_verified_generation" ] && \
                       [ "$_cleanup_next" != prepared ] && [ ! -d "$MODDIR/.luoshu-payload-next" ] && \
                       MODDIR="$MODDIR" MODULE_DIR="$MODDIR" sh "$MODDIR/common/device_font_load_verify.sh" status >/dev/null 2>&1 && \
                       [ "$(sed -n 's/^manifestDigest=//p' "$VERIFY" 2>/dev/null | head -n1)" = "$_verified_manifest" ]; then
                        rm -f "$MODDIR/config/text_reboot_required.conf" 2>/dev/null || true
                        rm -rf "$MODDIR/.luoshu-retired" 2>/dev/null || true
                    fi
                    luoshu_font_lock_release "$MODDIR/.font_switch.lock" "$_cleanup_owner" >/dev/null 2>&1 || true
                fi
            fi
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
        if [ -f "$MODDIR/config/stock_inventory_scan_pending" ]; then
            _stock_scan=$(LUOSHU_FRESH_STOCK_SCAN=1 MODDIR="$MODDIR" sh "$MODDIR/common/font_manager.sh" action stock_scan 2>&1)
            printf '[%s] deferred stock inventory: %s\n' \
                "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" "$_stock_scan" >> "$LOG" 2>/dev/null || true
        fi
        MODDIR="$MODDIR" sh "$MODDIR/common/font_manager.sh" action list --native-index >/dev/null 2>&1 || true
    fi

    printf '[%s] physical compatibility service complete: %s (%s)\n' \
        "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" "$_active" "$_verify_state" >> "$LOG" 2>/dev/null
) &

exit 0
