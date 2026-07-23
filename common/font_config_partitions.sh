#!/system/bin/sh
# Extended Android/OEM font-configuration partition map. Source after font_config_runtime.sh.
set +e

_luoshu_font_config_emit_partition() {
    _lfcp_key="$1"
    _lfcp_real_etc="$2"
    _lfcp_overlay_root="$3"
    shift 3
    for _lfcp_name in "$@"; do
        printf '%s/%s|%s/%s|%s/etc/%s|%s/fonts\n' \
            "$_lfcp_key" "$_lfcp_name" \
            "$_lfcp_real_etc" "$_lfcp_name" \
            "$_lfcp_overlay_root" "$_lfcp_name" \
            "$_lfcp_overlay_root"
    done
}

_luoshu_font_config_xml_names() {
    printf '%s\n' 'fonts.xml font_fallback.xml fonts_customization.xml font_customization.xml mi_fonts_customization.xml oplus_fonts_customization.xml oplus_font_customization.xml oppo_fonts_customization.xml coloros_fonts_customization.xml vivo_fonts.xml vivo_fonts_customization.xml vivo_font_customization.xml origin_fonts.xml originos_fonts.xml iqoo_fonts.xml flyme_fonts.xml flyme_fonts_customization.xml flyme_font_customization.xml meizu_fonts.xml meizu_fonts_customization.xml mz_fonts.xml fonts_vendor.xml fonts_overlay.xml'
}

_luoshu_font_config_resolve_etc() {
    _lfcr_root="$1"
    _lfcr_legacy="$2"
    _lfcr_default="$3"
    if [ -n "$_lfcr_root" ]; then
        printf '%s/etc\n' "${_lfcr_root%/}"
    elif [ -n "$_lfcr_legacy" ]; then
        printf '%s\n' "${_lfcr_legacy%/}"
    else
        printf '%s\n' "$_lfcr_default"
    fi
}

_luoshu_font_config_partition_rows() {
    _lfcp_module="$(_luoshu_font_config_module)"
    printf 'system|%s|%s/system\n' "$(_luoshu_font_config_resolve_etc "${LUOSHU_SYSTEM_ROOT:-}" "${LUOSHU_SYSTEM_ETC_ROOT:-}" /system/etc)" "$_lfcp_module"
    printf 'system_ext|%s|%s/system_ext\n' "$(_luoshu_font_config_resolve_etc "${LUOSHU_SYSTEM_EXT_ROOT:-}" "${LUOSHU_SYSTEM_EXT_ETC_ROOT:-}" /system_ext/etc)" "$_lfcp_module"
    printf 'product|%s|%s/product\n' "$(_luoshu_font_config_resolve_etc "${LUOSHU_PRODUCT_ROOT:-}" "${LUOSHU_PRODUCT_ETC_ROOT:-}" /product/etc)" "$_lfcp_module"
    printf 'vendor|%s|%s/vendor\n' "$(_luoshu_font_config_resolve_etc "${LUOSHU_VENDOR_ROOT:-}" "${LUOSHU_VENDOR_ETC_ROOT:-}" /vendor/etc)" "$_lfcp_module"
    printf 'odm|%s|%s/odm\n' "$(_luoshu_font_config_resolve_etc "${LUOSHU_ODM_ROOT:-}" "${LUOSHU_ODM_ETC_ROOT:-}" /odm/etc)" "$_lfcp_module"
    printf 'oem|%s|%s/oem\n' "$(_luoshu_font_config_resolve_etc "${LUOSHU_OEM_ROOT:-}" "${LUOSHU_OEM_ETC_ROOT:-}" /oem/etc)" "$_lfcp_module"
    printf 'my_product|%s|%s/my_product\n' "$(_luoshu_font_config_resolve_etc "${LUOSHU_MY_PRODUCT_ROOT:-}" "${LUOSHU_MY_PRODUCT_ETC_ROOT:-}" /my_product/etc)" "$_lfcp_module"
    printf 'my_engineering|%s|%s/my_engineering\n' "$(_luoshu_font_config_resolve_etc "${LUOSHU_MY_ENGINEERING_ROOT:-}" "${LUOSHU_MY_ENGINEERING_ETC_ROOT:-}" /my_engineering/etc)" "$_lfcp_module"
    printf 'my_company|%s|%s/my_company\n' "$(_luoshu_font_config_resolve_etc "${LUOSHU_MY_COMPANY_ROOT:-}" "${LUOSHU_MY_COMPANY_ETC_ROOT:-}" /my_company/etc)" "$_lfcp_module"
    printf 'my_preload|%s|%s/my_preload\n' "$(_luoshu_font_config_resolve_etc "${LUOSHU_MY_PRELOAD_ROOT:-}" "${LUOSHU_MY_PRELOAD_ETC_ROOT:-}" /my_preload/etc)" "$_lfcp_module"
    printf 'my_region|%s|%s/my_region\n' "$(_luoshu_font_config_resolve_etc "${LUOSHU_MY_REGION_ROOT:-}" "${LUOSHU_MY_REGION_ETC_ROOT:-}" /my_region/etc)" "$_lfcp_module"
    printf 'my_stock|%s|%s/my_stock\n' "$(_luoshu_font_config_resolve_etc "${LUOSHU_MY_STOCK_ROOT:-}" "${LUOSHU_MY_STOCK_ETC_ROOT:-}" /my_stock/etc)" "$_lfcp_module"
    printf 'oplus_product|%s|%s/oplus_product\n' "$(_luoshu_font_config_resolve_etc "${LUOSHU_OPLUS_PRODUCT_ROOT:-}" "${LUOSHU_OPLUS_PRODUCT_ETC_ROOT:-}" /oplus_product/etc)" "$_lfcp_module"
    printf 'oplus_engineering|%s|%s/oplus_engineering\n' "$(_luoshu_font_config_resolve_etc "${LUOSHU_OPLUS_ENGINEERING_ROOT:-}" "${LUOSHU_OPLUS_ENGINEERING_ETC_ROOT:-}" /oplus_engineering/etc)" "$_lfcp_module"
    printf 'oplus_version|%s|%s/oplus_version\n' "$(_luoshu_font_config_resolve_etc "${LUOSHU_OPLUS_VERSION_ROOT:-}" "${LUOSHU_OPLUS_VERSION_ETC_ROOT:-}" /oplus_version/etc)" "$_lfcp_module"
    printf 'oplus_region|%s|%s/oplus_region\n' "$(_luoshu_font_config_resolve_etc "${LUOSHU_OPLUS_REGION_ROOT:-}" "${LUOSHU_OPLUS_REGION_ETC_ROOT:-}" /oplus_region/etc)" "$_lfcp_module"
    printf 'mi_ext|%s|%s/mi_ext\n' "$(_luoshu_font_config_resolve_etc "${LUOSHU_MI_EXT_ROOT:-}" "${LUOSHU_MI_EXT_ETC_ROOT:-}" /mi_ext/etc)" "$_lfcp_module"
    printf 'cust|%s|%s/cust\n' "$(_luoshu_font_config_resolve_etc "${LUOSHU_CUST_ROOT:-}" "${LUOSHU_CUST_ETC_ROOT:-}" /cust/etc)" "$_lfcp_module"
}

# key | real XML | module overlay XML | font directory referenced by that document
_luoshu_font_config_specs() {
    _lfcp_names="$(_luoshu_font_config_xml_names)"
    while IFS='|' read -r _lfcp_key _lfcp_real_etc _lfcp_overlay; do
        [ -n "$_lfcp_key" ] && [ -n "$_lfcp_real_etc" ] && [ -n "$_lfcp_overlay" ] || continue
        # shellcheck disable=SC2086
        _luoshu_font_config_emit_partition "$_lfcp_key" "$_lfcp_real_etc" "$_lfcp_overlay" $_lfcp_names
    done <<EOF_LUOSHU_PARTITIONS
$(_luoshu_font_config_partition_rows)
EOF_LUOSHU_PARTITIONS
}

# ColorOS uses product/system_ext named families (notably google-sans-text) for some app controls.
_luoshu_coloros_helper="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}/common/coloros_global.sh"
[ -f "$_luoshu_coloros_helper" ] && . "$_luoshu_coloros_helper"

# OriginOS and Flyme use OEM-named families, exact physical slots and (on Flyme) a persistent theme font.
_luoshu_origin_flyme_helper="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}/common/origin_flyme_global.sh"
[ -f "$_luoshu_origin_flyme_helper" ] && . "$_luoshu_origin_flyme_helper"

# font_mix.sh 通过 mount_compat.sh 间接加载本文件。组合 Worker 是独立 shell，不能依赖
# 调用方已经 source 的函数；缺失时在这里补齐运行时与九档准备层，再加载收尾性能修复。
_luoshufp_module="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
if ! type luoshu_payload_validate_current >/dev/null 2>&1; then
    [ -f "$_luoshufp_module/common/font_config_runtime.sh" ] && . "$_luoshufp_module/common/font_config_runtime.sh"
fi
if ! type font_config_prepare_payload_weights >/dev/null 2>&1; then
    [ -f "$_luoshufp_module/common/font_config_weights.sh" ] && . "$_luoshufp_module/common/font_config_weights.sh"
fi
[ -f "$_luoshufp_module/common/font_finalize_hotfix.sh" ] && . "$_luoshufp_module/common/font_finalize_hotfix.sh"

# v2.2 loads after every legacy adapter. Dynamic and transaction guards are sourced
# after the bridge so older compatibility helpers cannot replace them.
[ -f "$_luoshufp_module/common/device_font_payload_bridge.sh" ] && . "$_luoshufp_module/common/device_font_payload_bridge.sh"
[ -f "$_luoshufp_module/common/device_font_dynamic_guard.sh" ] && . "$_luoshufp_module/common/device_font_dynamic_guard.sh"
[ -f "$_luoshufp_module/common/device_font_transaction_guard.sh" ] && . "$_luoshufp_module/common/device_font_transaction_guard.sh"
unset _luoshufp_module
