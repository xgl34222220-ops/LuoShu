#!/system/bin/sh
# Extended Android/OEM font-configuration partition map. Source after font_config_runtime.sh.
set +e

_luoshu_font_config_emit_partition() {
    _lfcp_key="$1"
    _lfcp_real_root="$2"
    _lfcp_overlay_root="$3"
    shift 3
    for _lfcp_name in "$@"; do
        printf '%s/%s|%s/etc/%s|%s/etc/%s|%s/fonts\n' \
            "$_lfcp_key" "$_lfcp_name" \
            "$_lfcp_real_root" "$_lfcp_name" \
            "$_lfcp_overlay_root" "$_lfcp_name" \
            "$_lfcp_overlay_root"
    done
}

_luoshu_font_config_xml_names() {
    printf '%s\n' 'fonts.xml font_fallback.xml fonts_customization.xml font_customization.xml mi_fonts_customization.xml oplus_fonts_customization.xml oplus_font_customization.xml oppo_fonts_customization.xml coloros_fonts_customization.xml fonts_vendor.xml fonts_overlay.xml'
}

_luoshu_font_config_partition_rows() {
    _lfcp_module="$(_luoshu_font_config_module)"
    printf 'system|%s|%s/system\n' "${LUOSHU_SYSTEM_ROOT:-/system}" "$_lfcp_module"
    printf 'system_ext|%s|%s/system_ext\n' "${LUOSHU_SYSTEM_EXT_ROOT:-/system_ext}" "$_lfcp_module"
    printf 'product|%s|%s/product\n' "${LUOSHU_PRODUCT_ROOT:-/product}" "$_lfcp_module"
    printf 'vendor|%s|%s/vendor\n' "${LUOSHU_VENDOR_ROOT:-/vendor}" "$_lfcp_module"
    printf 'odm|%s|%s/odm\n' "${LUOSHU_ODM_ROOT:-/odm}" "$_lfcp_module"
    printf 'oem|%s|%s/oem\n' "${LUOSHU_OEM_ROOT:-/oem}" "$_lfcp_module"
    printf 'my_product|%s|%s/my_product\n' "${LUOSHU_MY_PRODUCT_ROOT:-/my_product}" "$_lfcp_module"
    printf 'my_engineering|%s|%s/my_engineering\n' "${LUOSHU_MY_ENGINEERING_ROOT:-/my_engineering}" "$_lfcp_module"
    printf 'my_company|%s|%s/my_company\n' "${LUOSHU_MY_COMPANY_ROOT:-/my_company}" "$_lfcp_module"
    printf 'my_preload|%s|%s/my_preload\n' "${LUOSHU_MY_PRELOAD_ROOT:-/my_preload}" "$_lfcp_module"
    printf 'my_region|%s|%s/my_region\n' "${LUOSHU_MY_REGION_ROOT:-/my_region}" "$_lfcp_module"
    printf 'my_stock|%s|%s/my_stock\n' "${LUOSHU_MY_STOCK_ROOT:-/my_stock}" "$_lfcp_module"
    printf 'oplus_product|%s|%s/oplus_product\n' "${LUOSHU_OPLUS_PRODUCT_ROOT:-/oplus_product}" "$_lfcp_module"
    printf 'oplus_engineering|%s|%s/oplus_engineering\n' "${LUOSHU_OPLUS_ENGINEERING_ROOT:-/oplus_engineering}" "$_lfcp_module"
    printf 'oplus_version|%s|%s/oplus_version\n' "${LUOSHU_OPLUS_VERSION_ROOT:-/oplus_version}" "$_lfcp_module"
    printf 'oplus_region|%s|%s/oplus_region\n' "${LUOSHU_OPLUS_REGION_ROOT:-/oplus_region}" "$_lfcp_module"
    printf 'mi_ext|%s|%s/mi_ext\n' "${LUOSHU_MI_EXT_ROOT:-/mi_ext}" "$_lfcp_module"
    printf 'cust|%s|%s/cust\n' "${LUOSHU_CUST_ROOT:-/cust}" "$_lfcp_module"
}

# key | real XML | module overlay XML | font directory referenced by that document
_luoshu_font_config_specs() {
    _lfcp_names="$(_luoshu_font_config_xml_names)"
    while IFS='|' read -r _lfcp_key _lfcp_real _lfcp_overlay; do
        [ -n "$_lfcp_key" ] && [ -n "$_lfcp_real" ] && [ -n "$_lfcp_overlay" ] || continue
        # Emit every known file name. Runtime consumers skip absent real documents; this keeps tests
        # deterministic while allowing new OEM partitions without another ROM-specific code path.
        # shellcheck disable=SC2086
        _luoshu_font_config_emit_partition "$_lfcp_key" "$_lfcp_real" "$_lfcp_overlay" $_lfcp_names
    done <<EOF_LUOSHU_PARTITIONS
$(_luoshu_font_config_partition_rows)
EOF_LUOSHU_PARTITIONS
}
