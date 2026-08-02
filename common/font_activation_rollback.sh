#!/system/bin/sh
# Consume a hard activation failure before any LuoShu font payload is mounted.
# The current boot is left untouched; the next boot starts from the ROM font tree.
set +e

_luar_module() {
    printf '%s\n' "${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
}

_luar_partitions() {
    if type luoshu_private_partitions >/dev/null 2>&1; then
        luoshu_private_partitions
    else
        printf '%s\n' 'system system_ext product vendor odm oem my_product my_engineering my_company my_preload my_region my_stock oplus_product oplus_engineering oplus_version oplus_region mi_ext cust hw_product'
    fi
}

_luar_clear_partition_fonts() {
    _luar_module_dir="$1"
    for _luar_partition in $(_luar_partitions); do
        _luar_fonts="$_luar_module_dir/$_luar_partition/fonts"
        [ -d "$_luar_fonts" ] || continue
        find "$_luar_fonts" -maxdepth 1 -type f \
            \( -iname '*.ttf' -o -iname '*.otf' -o -iname '*.ttc' -o -name '*.font' \) \
            -delete 2>/dev/null || {
                for _luar_file in "$_luar_fonts"/*; do
                    [ -f "$_luar_file" ] || continue
                    case "$_luar_file" in *.ttf|*.TTF|*.otf|*.OTF|*.ttc|*.TTC|*.font) rm -f "$_luar_file" ;; esac
                done
            }
        rm -rf "$_luar_fonts/.luoshu-font-store" 2>/dev/null || true
    done
}

_luar_clear_generated_xml() {
    _luar_module_dir="$1"
    for _luar_partition in $(_luar_partitions); do
        _luar_etc="$_luar_module_dir/$_luar_partition/etc"
        [ -d "$_luar_etc" ] || continue
        rm -f "$_luar_etc/.luoshu-data-fonts-config.xml" 2>/dev/null || true
        for _luar_xml in "$_luar_etc"/*.xml; do
            [ -f "$_luar_xml" ] || continue
            if grep -q 'LuoShuSlot-\|LuoShuAutoMix\|luoshu-slot' "$_luar_xml" 2>/dev/null; then
                rm -f "$_luar_xml" 2>/dev/null || true
            fi
        done
    done
}

luoshu_activation_rollback_pending() {
    _luar_module_dir="$(_luar_module)"
    [ -s "$_luar_module_dir/config/font-activation-rollback.conf" ]
}

luoshu_activation_rollback_apply() {
    _luar_module_dir="$(_luar_module)"
    _luar_flag="$_luar_module_dir/config/font-activation-rollback.conf"
    [ -s "$_luar_flag" ] || return 2
    _luar_reason=$(sed -n 's/^reason=//p' "$_luar_flag" 2>/dev/null | head -n1 | tr -d '\r\n')
    _luar_font=$(sed -n 's/^font=//p' "$_luar_flag" 2>/dev/null | head -n1 | tr -d '\r\n')
    [ -n "$_luar_reason" ] || _luar_reason=hard-activation-failure
    [ -n "$_luar_font" ] || _luar_font=unknown

    [ -f "$_luar_module_dir/common/device_font_payload_runtime.sh" ] && \
        . "$_luar_module_dir/common/device_font_payload_runtime.sh"
    type device_font_payload_clear >/dev/null 2>&1 && device_font_payload_clear >/dev/null 2>&1 || true

    [ -f "$_luar_module_dir/common/font_config_runtime.sh" ] && \
        . "$_luar_module_dir/common/font_config_runtime.sh"
    type font_config_disable >/dev/null 2>&1 && font_config_disable >/dev/null 2>&1 || true

    _luar_clear_partition_fonts "$_luar_module_dir"
    _luar_clear_generated_xml "$_luar_module_dir"

    if [ -f "$_luar_module_dir/common/font_provider_cache.sh" ]; then
        . "$_luar_module_dir/common/font_provider_cache.sh"
        type luoshu_provider_cache_restore >/dev/null 2>&1 && \
            luoshu_provider_cache_restore >/dev/null 2>&1 || true
    fi

    mkdir -p "$_luar_module_dir/config" "$_luar_module_dir/logs" 2>/dev/null || true
    printf 'default\n' > "$_luar_module_dir/config/active_font.conf" 2>/dev/null || return 1
    rm -f \
        "$_luar_module_dir/config/font_mix.conf" \
        "$_luar_module_dir/config/axes_mix.conf" \
        "$_luar_module_dir/config/text_reboot_required.conf" \
        "$_luar_module_dir/config/font-payload-schema.conf" \
        "$_luar_module_dir/config/font-payload-manifest.conf" \
        "$_luar_module_dir/config/font-payload-boot.conf" \
        "$_luar_module_dir/config/self-mount.conf" \
        "$_luar_module_dir/config/self-mount-required.conf" \
        "$_luar_module_dir/config/device-font-engine.conf" \
        "$_luar_module_dir/config/device-font-installed.conf" \
        "$_luar_module_dir/config/device-font-dynamic-mount.conf" \
        "$_luar_module_dir/config/device-font-load-verification.conf" \
        "$_luar_module_dir/config/device-font-load-verification.json" \
        "$_luar_module_dir/config/device-font-manager-dump.txt" \
        "$_luar_module_dir/config/device-font-mount-evidence.txt" 2>/dev/null || true

    {
        printf 'state=restored-default\n'
        printf 'font=%s\n' "$_luar_font"
        printf 'reason=%s\n' "$_luar_reason"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_luar_module_dir/config/font-activation-rollback-last.conf" 2>/dev/null || true
    rm -f "$_luar_flag" 2>/dev/null || true
    chmod 0644 "$_luar_module_dir/config/active_font.conf" \
        "$_luar_module_dir/config/font-activation-rollback-last.conf" 2>/dev/null || true
    printf '[%s] [ACTIVATION-ROLLBACK] restored default font=%s reason=%s\n' \
        "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$_luar_font" "$_luar_reason" \
        >> "$_luar_module_dir/logs/fontswitch.log" 2>/dev/null || true
    return 0
}

if [ "${0##*/}" = font_activation_rollback.sh ]; then
    case "${1:-apply}" in
        pending) luoshu_activation_rollback_pending ;;
        apply) luoshu_activation_rollback_apply ;;
        *) printf 'usage: %s {pending|apply}\n' "$0" >&2; exit 2 ;;
    esac
fi
