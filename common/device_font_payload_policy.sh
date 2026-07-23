#!/system/bin/sh
# LuoShu v2.2 runtime policy.
# Synchronous per-slot generation is temporarily disabled because it can take minutes on
# large CJK fonts. Reuse only an already-installed payload for the same font; otherwise
# clear stale v2 files and immediately fall back to the established fast mapping path.
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

    # A payload generated for another font must never remain mounted while legacy mapping
    # applies the new selection.
    if type device_font_payload_clear >/dev/null 2>&1; then
        device_font_payload_clear >/dev/null 2>&1 || true
    fi
    _device_font_policy_log "跳过前台逐槽位重建，字体 $_dfpp_font 使用快速兼容映射"
    return 2
}
