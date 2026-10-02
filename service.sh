#!/system/bin/sh
# LuoShu service router.
# Normal installations keep the current v4 service unchanged. Once the isolated
# physical compatibility runtime is selected, background v4 payload rebuilds stay off.
# App font inventory remains prewarmed through config/native_font_index.json.
set +e
MODDIR="${0%/*}"
UNIVERSAL_MODE="$MODDIR/config/universal-font-runtime.conf"
UNIVERSAL_RUNTIME="$MODDIR/common/universal_mount_runtime.sh"
UNIVERSAL_VERIFY="$MODDIR/common/universal_font_runtime_verify.sh"
LEGACY_MODE="$MODDIR/config/font_runtime_legacy_v14_4.conf"
V4_SERVICE="$MODDIR/.luoshu-runtime/core/service.sh"

if [ -s "$UNIVERSAL_MODE" ]; then
    # Phase 7/8 runtime may only consume the frozen deployment artifacts.
    # The legacy provider watcher re-discovers targets and chooses weights, so it
    # must not run once the universal deployment pipeline is active.
    [ -f "$UNIVERSAL_RUNTIME" ] && MODDIR="$MODDIR" MODULE_DIR="$MODDIR" \
        sh "$UNIVERSAL_RUNTIME" service >/dev/null 2>&1 || true
    # Phase 8 runs once per boot after boot-complete. It consumes only the frozen
    # Phase 4/6/7 artifacts and never starts a resident target-discovery loop.
    [ -f "$UNIVERSAL_VERIFY" ] && MODDIR="$MODDIR" MODULE_DIR="$MODDIR" \
        sh "$UNIVERSAL_VERIFY" schedule >/dev/null 2>&1 || true
    exit 0
fi

# Do not reinterpret a rejected Universal request as permission to mount legacy.
[ ! -f "$MODDIR/common/universal_next_boot.sh" ] || . "$MODDIR/common/universal_next_boot.sh"
if type universal_font_next_boot_blocks_legacy >/dev/null 2>&1 && universal_font_next_boot_blocks_legacy; then
    universal_font_next_boot_record_legacy_block
    _ufnb_log "queued Universal activation rejected; legacy hooks blocked for this boot"
    exit 1
fi


# Legacy/current production paths keep the Google provider compatibility service.
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

    # A mount transaction is not a Typeface consumer proof. The common verifier
    # binds even mount-only evidence to this boot, generation and selected font.
    if [ -f "$MODDIR/common/device_font_load_verify.sh" ]; then
        MODDIR="$MODDIR" MODULE_DIR="$MODDIR" sh "$MODDIR/common/device_font_load_verify.sh" status >> "$LOG" 2>&1 || true
    fi
    [ ! -f "$MODDIR/common/font_boot_state.sh" ] || . "$MODDIR/common/font_boot_state.sh"
    type luoshu_android_boot_health_record >/dev/null 2>&1 && luoshu_android_boot_health_record || true
    _verify_state=$(sed -n 's/^state=//p' "$VERIFY" 2>/dev/null | head -n1)
    if [ "$_active" = default ]; then
        rm -rf "$MODDIR/.luoshu-retired" "$MODDIR"/.luoshu-payload-stage.* 2>/dev/null || true
    fi
    # Keep rollback assets for custom fonts until actual consumer assurance exists.
    # Unconfirmed consumption is not a reason to reset a visibly working font.
    printf '[%s] font evidence: active=%s mount=%s state=%s; custom rollback retained\n' \
        "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" "$_active" "$_mount_state" "${_verify_state:-pending}" >> "$LOG" 2>/dev/null

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
