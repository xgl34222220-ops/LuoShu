#!/system/bin/sh
# LuoShu v2.2 foreground runtime policy.
# Never build or normalize large per-slot/per-weight font payloads in the App switch path.
# Reuse a verified cache for the same font; otherwise keep the ROM physical-slot mapping
# that was already prepared by the adapter and remove stale XML/device payload state.
set +e

_device_font_policy_module() {
    printf '%s\n' "${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
}

_device_font_policy_log() {
    _dfpp_module="$(_device_font_policy_module)"
    mkdir -p "$_dfpp_module/logs" 2>/dev/null || true
    printf '[%s] [POLICY] %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$*" \
        >> "$_dfpp_module/logs/device-font-payload.log" 2>/dev/null || true
}

# ColorOS target discovery used to rescan every font directory several times during one
# switch. System partition filenames only change after an OTA, so cache the deduplicated
# target list by build fingerprint. The explicit environment key keeps fixtures deterministic.
get_all_coloros_files() {
    _dfpp_module="$(_device_font_policy_module)"
    _dfpp_cache="$_dfpp_module/config/coloros-font-targets.cache"
    _dfpp_key="${LUOSHU_COLOROS_CACHE_KEY:-$(getprop ro.build.fingerprint 2>/dev/null)}"
    [ -n "$_dfpp_key" ] || _dfpp_key="$(getprop ro.build.version.incremental 2>/dev/null)"
    [ -n "$_dfpp_key" ] || _dfpp_key=unknown
    _dfpp_cached_key=$(sed -n 's/^key=//p' "$_dfpp_cache" 2>/dev/null | head -n1)
    if [ "$_dfpp_cached_key" = "$_dfpp_key" ] && sed -n '2,$p' "$_dfpp_cache" 2>/dev/null | grep -q .; then
        sed -n '2,$p' "$_dfpp_cache" 2>/dev/null
        return 0
    fi

    _dfpp_tmp="${_dfpp_cache}.tmp.$$"
    mkdir -p "${_dfpp_cache%/*}" 2>/dev/null || true
    {
        printf 'key=%s\n' "$_dfpp_key"
        {
            if type _coloros_core_files >/dev/null 2>&1; then _coloros_core_files; fi
            if type _coloros_google_text_files >/dev/null 2>&1; then _coloros_google_text_files; fi
            if type _coloros_vendor_files >/dev/null 2>&1; then _coloros_vendor_files; fi
            if type _coloros_oem_ui_files >/dev/null 2>&1; then _coloros_oem_ui_files; fi
            if type _coloros_discovered_ui_files >/dev/null 2>&1; then _coloros_discovered_ui_files; fi
        } | tr ' ' '\n' | awk 'NF && !seen[$0]++'
    } > "$_dfpp_tmp" 2>/dev/null || {
        rm -f "$_dfpp_tmp" 2>/dev/null || true
        return 1
    }
    mv -f "$_dfpp_tmp" "$_dfpp_cache" 2>/dev/null || {
        rm -f "$_dfpp_tmp" 2>/dev/null || true
        return 1
    }
    chmod 0644 "$_dfpp_cache" 2>/dev/null || true
    sed -n '2,$p' "$_dfpp_cache" 2>/dev/null
}

# font_manager.sh contains an old post-adapter compatibility loop that copies the same
# ColorOS aliases to system_ext/product again. The partition-aware adapter has already
# handled every real target before font_config_enable_for_payload is called, so suppress
# only that second pass while leaving the initial cleanup list intact.
get_all_coloros_names() {
    [ "${LUOSHU_COLOROS_TARGETS_MAPPED:-0}" != 1 ] || return 0
    for _dfpp_file in $(get_all_coloros_files); do
        printf '%s\n' "${_dfpp_file%.ttf}"
    done
}

# Return 0 only when an already-installed payload belongs to this exact font and still
# passes its manifest validation. Return 2 for a normal cache miss so the caller can use
# the fast physical-slot path. A stale payload for another font is removed first.
device_font_payload_build_install() {
    _dfpp_font="${1:-custom}"
    _dfpp_module="$(_device_font_policy_module)"
    _dfpp_state="$_dfpp_module/config/device-font-engine.conf"
    _dfpp_installed_state=$(sed -n 's/^state=//p' "$_dfpp_state" 2>/dev/null | head -n1)
    _dfpp_installed_font=$(sed -n 's/^font=//p' "$_dfpp_state" 2>/dev/null | head -n1)

    if [ "$_dfpp_installed_state" = installed ] && [ "$_dfpp_installed_font" = "$_dfpp_font" ]; then
        if type device_font_payload_validate_installed >/dev/null 2>&1 && device_font_payload_validate_installed; then
            _device_font_policy_log "复用已验证的设备字体缓存：$_dfpp_font"
            return 0
        fi
    fi

    if type device_font_payload_clear >/dev/null 2>&1; then
        device_font_payload_clear >/dev/null 2>&1 || true
    fi
    _device_font_policy_log "设备缓存未命中：$_dfpp_font"
    return 2
}

# This overrides the bridge function after all adapters have loaded. The old order called
# font_config_prepare_payload_weights first, causing 9 UI + 9 Mono full-font rewrites even
# when the device engine was going to be skipped. Cache eligibility is now checked first.
font_config_enable_for_payload() {
    _dfpp_family="${1:-unknown}"
    LUOSHU_DEVICE_PAYLOAD_RESULT='preparing'

    device_font_payload_build_install "$_dfpp_family"
    _dfpp_rc=$?
    case "$_dfpp_rc" in
        0)
            LUOSHU_DEVICE_PAYLOAD_RESULT='device'
            [ "${IS_COLOROS:-false}" != true ] || LUOSHU_COLOROS_TARGETS_MAPPED=1
            export LUOSHU_COLOROS_TARGETS_MAPPED
            return 0
            ;;
        1)
            LUOSHU_DEVICE_PAYLOAD_RESULT='device-failed'
            return 1
            ;;
    esac

    # Preserve the physical files that copy_as_* just prepared, while removing stale v2,
    # dynamic-target and XML overlay state from the previous font. Most importantly, do
    # not call font_config_prepare_payload_weights or font_config_generate here.
    _dfpp_preserve="${LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE:-0}"
    LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE=1
    export LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE
    if type font_config_disable >/dev/null 2>&1; then
        font_config_disable >/dev/null 2>&1 || true
    fi
    LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE="$_dfpp_preserve"
    export LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE

    [ "${IS_COLOROS:-false}" != true ] || LUOSHU_COLOROS_TARGETS_MAPPED=1
    export LUOSHU_COLOROS_TARGETS_MAPPED
    LUOSHU_DEVICE_PAYLOAD_RESULT='slot-only'
    _device_font_policy_log "前台跳过九字重、逐槽位重建和重复 ColorOS 别名同步：$_dfpp_family"
    return 0
}
