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

    # Everything below is maintenance, not mount confirmation. The verification
    # record above is already final. Let the device finish its own boot burst,
    # then continue at low CPU/I/O priority and skip work whose inputs are unchanged.
    _housekeeping="$MODDIR/common/boot_housekeeping.sh"
    [ -f "$_housekeeping" ] && . "$_housekeeping"
    _deferred_start=$(date +%s 2>/dev/null || echo 0)
    type luoshu_boot_settle >/dev/null 2>&1 && luoshu_boot_settle
    type luoshu_boot_lower_priority >/dev/null 2>&1 && luoshu_boot_lower_priority

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
        # native_font_index.json only depends on the module version, the active
        # selection and the public font folder. When none changed since the last
        # successful prewarm, the router/task-scope/v4 start-up is pure cost.
        _index_key=''
        type luoshu_native_index_boot_key >/dev/null 2>&1 && \
            _index_key=$(luoshu_native_index_boot_key "$MODDIR" "$_active" 2>/dev/null)
        if type luoshu_native_index_boot_fresh >/dev/null 2>&1 && \
           luoshu_native_index_boot_fresh "$MODDIR" "$_index_key"; then
            printf '[%s] native font index unchanged; prewarm skipped\n' \
                "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" >> "$LOG" 2>/dev/null || true
        elif MODDIR="$MODDIR" sh "$MODDIR/common/font_manager.sh" action list --native-index >/dev/null 2>&1; then
            type luoshu_native_index_boot_record >/dev/null 2>&1 && \
                luoshu_native_index_boot_record "$MODDIR" "$_index_key"
        fi
    fi
    type luoshu_boot_housekeep >/dev/null 2>&1 && luoshu_boot_housekeep "$MODDIR"

    _deferred_end=$(date +%s 2>/dev/null || echo 0)
    printf '[%s] physical compatibility service complete: %s (%s) deferredSeconds=%s\n' \
        "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" "$_active" "$_verify_state" \
        "$((_deferred_end - _deferred_start))" >> "$LOG" 2>/dev/null
) &

exit 0
