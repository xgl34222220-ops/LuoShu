#!/system/bin/sh
# Extended Android/OEM font-configuration partition map. Source after font_config_runtime.sh.
set +e

# key | real XML | module overlay XML | font directory referenced by the generated document
_luoshu_font_config_specs() {
    _lfc_module="$(_luoshu_font_config_module)"
    _lfc_system_etc="${LUOSHU_SYSTEM_ETC_ROOT:-/system/etc}"
    _lfc_product_etc="${LUOSHU_PRODUCT_ETC_ROOT:-/product/etc}"
    _lfc_system_ext_etc="${LUOSHU_SYSTEM_EXT_ETC_ROOT:-/system_ext/etc}"
    _lfc_my_product_etc="${LUOSHU_MY_PRODUCT_ETC_ROOT:-/my_product/etc}"
    _lfc_vendor_etc="${LUOSHU_VENDOR_ETC_ROOT:-/vendor/etc}"
    _lfc_odm_etc="${LUOSHU_ODM_ETC_ROOT:-/odm/etc}"

    _luoshu_font_config_emit_partition system "$_lfc_system_etc" "$_lfc_module/system" \
        fonts.xml font_fallback.xml
    _luoshu_font_config_emit_partition product "$_lfc_product_etc" "$_lfc_module/product" \
        fonts.xml font_fallback.xml fonts_customization.xml font_customization.xml \
        mi_fonts_customization.xml
    _luoshu_font_config_emit_partition system_ext "$_lfc_system_ext_etc" "$_lfc_module/system_ext" \
        fonts.xml font_fallback.xml fonts_customization.xml font_customization.xml
    _luoshu_font_config_emit_partition my_product "$_lfc_my_product_etc" "$_lfc_module/my_product" \
        fonts.xml font_fallback.xml fonts_customization.xml font_customization.xml \
        oplus_fonts_customization.xml oplus_font_customization.xml
    _luoshu_font_config_emit_partition vendor "$_lfc_vendor_etc" "$_lfc_module/vendor" \
        fonts.xml font_fallback.xml fonts_customization.xml font_customization.xml
    _luoshu_font_config_emit_partition odm "$_lfc_odm_etc" "$_lfc_module/odm" \
        fonts.xml font_fallback.xml fonts_customization.xml font_customization.xml
}

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
