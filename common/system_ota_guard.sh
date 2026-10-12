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
#
# Early detection (luoshu_system_ota_early_boot) runs from the boot-loop guard's
# post-fs-data hook, before any LuoShu mount. On a fingerprint mismatch the
# generated XML overlay and the /data/fonts dynamic view were derived from the
# previous ROM, so this boot skips both: the generated XML is moved out of the
# payload for this boot only (the frozen self-mount then has no etc layer to
# mount) and font_safety.sh / the dynamic view helpers see the per-boot hold.
# Physical font slots still mount. The record itself is NOT updated here; the
# existing post-boot check above records the new build and requests the rescan.
# The held XML is put back on the next boot before anything validates it, so
# the payload manifest stays intact.
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

luoshu_system_ota_hold_file() {
    printf '%s/config/system-ota-boot-hold.conf\n' "$1"
}

luoshu_system_ota_held_root() {
    printf '%s/.luoshu-ota-held-xml\n' "$1"
}

luoshu_system_ota_current_boot() {
    if [ -n "${LUOSHU_BOOTLOOP_BOOT_ID:-}" ]; then
        printf '%s\n' "$LUOSHU_BOOTLOOP_BOOT_ID"
        return 0
    fi
    cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n'
}

# True only during the boot that detected the mismatch.
luoshu_system_ota_boot_hold_active() {
    _lsobh_module="${1:-${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}}"
    _lsobh_file=$(luoshu_system_ota_hold_file "$_lsobh_module")
    [ -s "$_lsobh_file" ] || return 1
    _lsobh_boot=$(luoshu_system_ota_value "$_lsobh_file" bootId)
    [ -n "$_lsobh_boot" ] || return 1
    [ "$_lsobh_boot" = "$(luoshu_system_ota_current_boot)" ]
}

luoshu_system_ota_payload_root() {
    if [ -d "$1/.luoshu-payload" ] && [ ! -L "$1/.luoshu-payload" ]; then
        printf '%s/.luoshu-payload\n' "$1"
    else
        printf '%s\n' "$1"
    fi
}

luoshu_system_ota_parts() {
    printf '%s\n' 'system system_ext product vendor odm oem my_product my_engineering my_company my_preload my_region my_stock oplus_product oplus_engineering oplus_version oplus_region mi_ext cust'
}

# Put XML held by an earlier OTA boot back into the payload. A file the user
# regenerated meanwhile (a newer apply) always wins over the held copy.
luoshu_system_ota_release_held_xml() {
    _lsorx_module="$1"
    _lsorx_held=$(luoshu_system_ota_held_root "$_lsorx_module")
    [ -d "$_lsorx_held" ] && [ ! -L "$_lsorx_held" ] || return 0
    _lsorx_payload=$(luoshu_system_ota_payload_root "$_lsorx_module")
    _lsorx_restored=0
    for _lsorx_part in $(luoshu_system_ota_parts); do
        for _lsorx_file in "$_lsorx_held/$_lsorx_part/etc"/*.xml; do
            [ -f "$_lsorx_file" ] && [ ! -L "$_lsorx_file" ] || continue
            _lsorx_target="$_lsorx_payload/$_lsorx_part/etc/${_lsorx_file##*/}"
            if [ -e "$_lsorx_target" ] || [ -L "$_lsorx_target" ]; then
                rm -f "$_lsorx_file" 2>/dev/null || true
                continue
            fi
            mkdir -p "${_lsorx_target%/*}" 2>/dev/null || continue
            mv -f "$_lsorx_file" "$_lsorx_target" 2>/dev/null && _lsorx_restored=$((_lsorx_restored + 1))
        done
    done
    rm -rf "$_lsorx_held" 2>/dev/null || true
    [ "$_lsorx_restored" -eq 0 ] || \
        luoshu_system_ota_log "$_lsorx_module" "已恢复上次系统更新首次开机暂停的 $_lsorx_restored 份字体 XML 覆盖"
    return 0
}

# luoshu_system_ota_early_boot MODDIR BOOT_ID
# Returns 0 when this boot holds back the XML overlay and dynamic view.
luoshu_system_ota_early_boot() {
    _lsoeb_module="$1"
    _lsoeb_boot="${2:-$(luoshu_system_ota_current_boot)}"
    [ -n "$_lsoeb_boot" ] || return 1
    _lsoeb_hold=$(luoshu_system_ota_hold_file "$_lsoeb_module")
    # post-fs-data may run more than once per boot (KernelSU/APatch, late-load).
    if [ "$(luoshu_system_ota_value "$_lsoeb_hold" bootId)" = "$_lsoeb_boot" ]; then
        return 0
    fi
    luoshu_system_ota_release_held_xml "$_lsoeb_module"

    _lsoeb_active=$(head -n1 "$_lsoeb_module/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_lsoeb_active" ] && [ "$_lsoeb_active" != default ] || return 1
    _lsoeb_recorded=$(luoshu_system_ota_value "$(luoshu_system_ota_file "$_lsoeb_module")" fingerprint)
    [ -n "$_lsoeb_recorded" ] || return 1
    _lsoeb_fp=$(luoshu_system_build_prop ro.build.fingerprint)
    [ -n "$_lsoeb_fp" ] || return 1
    [ "$_lsoeb_fp" != "$_lsoeb_recorded" ] || return 1

    _lsoeb_payload=$(luoshu_system_ota_payload_root "$_lsoeb_module")
    _lsoeb_held=$(luoshu_system_ota_held_root "$_lsoeb_module")
    _lsoeb_count=0
    for _lsoeb_part in $(luoshu_system_ota_parts); do
        for _lsoeb_xml in "$_lsoeb_payload/$_lsoeb_part/etc"/*.xml; do
            [ -f "$_lsoeb_xml" ] && [ ! -L "$_lsoeb_xml" ] || continue
            grep -q 'LuoShu' "$_lsoeb_xml" 2>/dev/null || continue
            mkdir -p "$_lsoeb_held/$_lsoeb_part/etc" 2>/dev/null || continue
            mv -f "$_lsoeb_xml" "$_lsoeb_held/$_lsoeb_part/etc/${_lsoeb_xml##*/}" 2>/dev/null && \
                _lsoeb_count=$((_lsoeb_count + 1))
        done
    done
    mkdir -p "$_lsoeb_module/config" 2>/dev/null || true
    {
        printf 'bootId=%s\n' "$_lsoeb_boot"
        printf 'fingerprint=%s\n' "$_lsoeb_fp"
        printf 'previousFingerprint=%s\n' "$_lsoeb_recorded"
        printf 'heldXml=%s\n' "$_lsoeb_count"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "${_lsoeb_hold}.tmp.$$" 2>/dev/null && mv -f "${_lsoeb_hold}.tmp.$$" "$_lsoeb_hold" 2>/dev/null || {
        rm -f "${_lsoeb_hold}.tmp.$$" 2>/dev/null || true
    }
    chmod 0644 "$_lsoeb_hold" 2>/dev/null || true
    # The existing rescan marker: consumed by the pre-mount stock scan and the
    # deferred scan in service.sh.
    : > "$_lsoeb_module/config/stock_inventory_scan_pending" 2>/dev/null || true
    luoshu_system_ota_log "$_lsoeb_module" "开机早期检测到系统更新（指纹 $_lsoeb_recorded → $_lsoeb_fp）：本次启动跳过 XML 覆盖（暂停 $_lsoeb_count 份）与 /data/fonts 动态视图，只挂载字体文件槽，交给系统更新重扫处理"
    return 0
}
