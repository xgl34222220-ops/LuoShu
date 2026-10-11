#!/system/bin/sh
# LuoShu system OTA detection.
#
# After a successful font apply the ROM build (ro.build.fingerprint and
# ro.build.version.incremental) is recorded in config/system-build.conf. When a
# later boot reports a different fingerprint, the system was updated: the stock
# fonts LuoShu derived its payload from may have changed. Nothing is rebuilt or
# unmounted here; the existing stock rescan marker
# (config/stock_inventory_scan_pending, consumed by the pre-mount scan in
# post-fs-data/post-mount and by the deferred scan in service.sh) is set so the
# normal rescan/validation path runs, and the change is logged.
#
# Called from module_status.sh, which service.sh runs after sys.boot_completed=1.
set +e

luoshu_system_build_prop() {
    getprop "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

luoshu_system_ota_file() {
    printf '%s/config/system-build.conf\n' "$1"
}

luoshu_system_ota_value() {
    sed -n "s/^$2=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

luoshu_system_ota_log() {
    mkdir -p "$1/logs" 2>/dev/null || true
    printf '[%s] [SYSTEM-OTA] %s\n' \
        "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$2" \
        >> "$1/logs/fontswitch.log" 2>/dev/null || true
}

# luoshu_system_ota_record MODDIR FINGERPRINT INCREMENTAL [PREVIOUS_FINGERPRINT]
luoshu_system_ota_record() {
    _lsor_file=$(luoshu_system_ota_file "$1")
    mkdir -p "${_lsor_file%/*}" 2>/dev/null || return 1
    {
        printf 'fingerprint=%s\n' "$2"
        printf 'incremental=%s\n' "$3"
        printf 'previousFingerprint=%s\n' "${4:-}"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "${_lsor_file}.tmp.$$" 2>/dev/null && mv -f "${_lsor_file}.tmp.$$" "$_lsor_file" 2>/dev/null || {
        rm -f "${_lsor_file}.tmp.$$" 2>/dev/null || true
        return 1
    }
    chmod 0644 "$_lsor_file" 2>/dev/null || true
}

# luoshu_system_ota_check MODDIR ACTIVE_FONT MOUNT_STATE
# Returns 0 when an OTA was detected (rescan requested), 1 otherwise.
luoshu_system_ota_check() {
    _lsoc_module="$1"
    _lsoc_active="${2:-default}"
    _lsoc_mount="${3:-}"
    _lsoc_fp=$(luoshu_system_build_prop ro.build.fingerprint)
    [ -n "$_lsoc_fp" ] || return 1
    _lsoc_inc=$(luoshu_system_build_prop ro.build.version.incremental)
    _lsoc_file=$(luoshu_system_ota_file "$_lsoc_module")
    _lsoc_recorded=$(luoshu_system_ota_value "$_lsoc_file" fingerprint)

    if [ -n "$_lsoc_recorded" ] && [ "$_lsoc_recorded" != "$_lsoc_fp" ]; then
        _lsoc_old_inc=$(luoshu_system_ota_value "$_lsoc_file" incremental)
        mkdir -p "$_lsoc_module/config" 2>/dev/null || true
        : > "$_lsoc_module/config/stock_inventory_scan_pending" 2>/dev/null || true
        luoshu_system_ota_record "$_lsoc_module" "$_lsoc_fp" "$_lsoc_inc" "$_lsoc_recorded" >/dev/null 2>&1 || true
        luoshu_system_ota_log "$_lsoc_module" "检测到系统更新：${_lsoc_old_inc:-?} → ${_lsoc_inc:-?}（指纹 $_lsoc_recorded → $_lsoc_fp）；已标记重新扫描原厂字体并在下次挂载前校验，当前字体选择保留"
        return 0
    fi

    # Baseline: record the build only once a font is actually applied on it.
    if [ -z "$_lsoc_recorded" ] && [ "$_lsoc_active" != default ]; then
        case "$_lsoc_mount" in
            mounted|degraded|confirmed|verified)
                luoshu_system_ota_record "$_lsoc_module" "$_lsoc_fp" "$_lsoc_inc" >/dev/null 2>&1 || true
                ;;
        esac
    fi
    return 1
}
