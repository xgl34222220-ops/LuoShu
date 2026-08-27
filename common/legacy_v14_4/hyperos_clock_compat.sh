#!/system/bin/sh
# HyperOS compatibility bridge for the restored v14.4 physical-file runtime.
# v14.4 predates the v2.1.2 HyperOS 3 mi_ext + Mitype/MiClock coverage, so
# re-create those proven physical aliases in the private payload before mount.
# No XML, device-template, provider hook or foreground rebuild is involved.
set +e

_lhcc_module_dir() {
    printf '%s\n' "${LUOSHU_REAL_MODDIR:-${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}}"
}

_lhcc_payload_root() {
    if [ -n "${LUOSHU_HYPEROS_CLOCK_PAYLOAD_ROOT:-}" ]; then
        printf '%s\n' "$LUOSHU_HYPEROS_CLOCK_PAYLOAD_ROOT"
        return 0
    fi
    _lhcc_module="$(_lhcc_module_dir)"
    if [ -d "$_lhcc_module/.luoshu-payload" ]; then
        printf '%s\n' "$_lhcc_module/.luoshu-payload"
    else
        printf '%s\n' "$_lhcc_module"
    fi
}

_lhcc_root_for_part() {
    case "$1" in
        system) printf '%s\n' "${LUOSHU_SYSTEM_FONTS_ROOT:-/system/fonts}" ;;
        system_ext) printf '%s\n' "${LUOSHU_SYSTEM_EXT_FONTS_ROOT:-/system_ext/fonts}" ;;
        product) printf '%s\n' "${LUOSHU_PRODUCT_FONTS_ROOT:-/product/fonts}" ;;
        mi_ext) printf '%s\n' "${LUOSHU_MI_EXT_FONTS_ROOT:-/mi_ext/fonts}" ;;
        vendor) printf '%s\n' "${LUOSHU_VENDOR_FONTS_ROOT:-/vendor/fonts}" ;;
        odm) printf '%s\n' "${LUOSHU_ODM_FONTS_ROOT:-/odm/fonts}" ;;
        oem) printf '%s\n' "${LUOSHU_OEM_FONTS_ROOT:-/oem/fonts}" ;;
        my_product) printf '%s\n' "${LUOSHU_MY_PRODUCT_FONTS_ROOT:-/my_product/fonts}" ;;
        hw_product) printf '%s\n' "${LUOSHU_HW_PRODUCT_FONTS_ROOT:-/hw_product/fonts}" ;;
        cust) printf '%s\n' "${LUOSHU_CUST_FONTS_ROOT:-/cust/fonts}" ;;
        *) return 1 ;;
    esac
}

_lhcc_anchor() {
    _lhcc_payload="$(_lhcc_payload_root)"
    for _lhcc_file in \
        "$_lhcc_payload/system/fonts/MiSansVF.ttf" \
        "$_lhcc_payload/system/fonts/MiSansLatinVF.ttf" \
        "$_lhcc_payload/system/fonts/Roboto-Regular.ttf" \
        "$_lhcc_payload/system/fonts/400.ttf"; do
        [ -s "$_lhcc_file" ] || continue
        printf '%s\n' "$_lhcc_file"
        return 0
    done
    return 1
}

_lhcc_static_names() {
    printf '%s\n' \
        MitypeVF.ttf MitypeMonoVF.ttf MitypeClock.ttf MitypeClock.otf \
        MitypeClockMono.ttf MitypeClockMono.otf \
        MiClock.ttf MiClock.otf MiClockThin.ttf MiClockThin.otf \
        MiClockMono.ttf MiClockMono.otf MiSansClock.ttf MiSansClockVF.ttf \
        AndroidClock.ttf AndroidClock_Highlight.ttf AndroidClock_Solid.ttf Clockopia.ttf
}

_lhcc_names_for_root() {
    _lhcc_real="$1"
    {
        _lhcc_static_names
        [ -d "$_lhcc_real" ] || exit 0
        for _lhcc_path in \
            "$_lhcc_real"/Mitype*.ttf "$_lhcc_real"/Mitype*.otf \
            "$_lhcc_real"/MiClock*.ttf "$_lhcc_real"/MiClock*.otf \
            "$_lhcc_real"/MiSans*Clock*.ttf "$_lhcc_real"/MiSans*Clock*.otf \
            "$_lhcc_real"/AndroidClock*.ttf "$_lhcc_real"/AndroidClock*.otf \
            "$_lhcc_real"/Clockopia.ttf; do
            [ -f "$_lhcc_path" ] || continue
            _lhcc_name=${_lhcc_path##*/}
            case "$_lhcc_name" in *Italic*|*Oblique*|*Emoji*|*Symbol*|*Icon*) continue ;; esac
            printf '%s\n' "$_lhcc_name"
        done
    } | awk 'NF && !seen[$0]++'
}

_lhcc_link_or_copy() {
    _lhcc_source="$1"
    _lhcc_dest="$2"
    rm -f "$_lhcc_dest" 2>/dev/null || true
    ln "$_lhcc_source" "$_lhcc_dest" 2>/dev/null || \
        cp -f "$_lhcc_source" "$_lhcc_dest" 2>/dev/null || return 1
    chmod 0644 "$_lhcc_dest" 2>/dev/null || true
    return 0
}

luoshu_hyperos_clock_payload_ensure() {
    _lhcc_anchor_file="$(_lhcc_anchor)" || return 0
    _lhcc_payload="$(_lhcc_payload_root)"
    _lhcc_count=0

    # The current v14.4 payload already proves this is a selected text font. Only
    # mirror into physical files that really exist on the ROM, so other ROMs no-op.
    for _lhcc_part in system system_ext product mi_ext vendor odm oem my_product hw_product cust; do
        _lhcc_real="$(_lhcc_root_for_part "$_lhcc_part")" || continue
        [ -d "$_lhcc_real" ] || continue
        _lhcc_overlay="$_lhcc_payload/$_lhcc_part/fonts"
        while IFS= read -r _lhcc_name; do
            [ -n "$_lhcc_name" ] || continue
            [ -e "$_lhcc_real/$_lhcc_name" ] || continue
            mkdir -p "$_lhcc_overlay" 2>/dev/null || continue
            if _lhcc_link_or_copy "$_lhcc_anchor_file" "$_lhcc_overlay/$_lhcc_name"; then
                _lhcc_count=$((_lhcc_count + 1))
            fi
        done <<EOF_LHCC_NAMES
$(_lhcc_names_for_root "$_lhcc_real")
EOF_LHCC_NAMES
    done

    _lhcc_module="$(_lhcc_module_dir)"
    if [ "$_lhcc_count" -gt 0 ]; then
        mkdir -p "$_lhcc_module/logs" 2>/dev/null || true
        printf '[%s] HyperOS legacy clock/status slots restored: %s\n' \
            "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" "$_lhcc_count" \
            >> "$_lhcc_module/logs/fontswitch.log" 2>/dev/null || true
    fi
    return 0
}
