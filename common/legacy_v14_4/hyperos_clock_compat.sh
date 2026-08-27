#!/system/bin/sh
# HyperOS compatibility bridge for the restored v14.4 physical-file runtime.
# v14.4 predates the later HyperOS 3 physical-slot coverage work. Re-create the
# proven MiSans/Roboto/GoogleSans/NotoSans/Mitype/clock aliases in the private
# payload before self-mount, without entering the v4 template/XML/94% pipeline.
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

_lhcc_is_hyperos() {
    [ "${IS_HYPEROS:-false}" = true ] && return 0
    _lhcc_mios=$(getprop ro.mi.os.version.name 2>/dev/null | tr -d '\r\n')
    _lhcc_miui=$(getprop ro.miui.ui.version.name 2>/dev/null | tr -d '\r\n')
    [ -n "$_lhcc_mios$_lhcc_miui" ]
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

_lhcc_weight_for_name() {
    _lhcc_lower=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
    case "$_lhcc_lower" in
        100.ttf|*thin*) printf '100\n' ;;
        200.ttf|*extralight*|*extra-light*) printf '200\n' ;;
        300.ttf|*light*) printf '300\n' ;;
        350.ttf) printf '350\n' ;;
        500.ttf|*medium*) printf '500\n' ;;
        600.ttf|*semibold*|*semi-bold*|*demibold*) printf '600\n' ;;
        700.ttf|*bold*) printf '700\n' ;;
        800.ttf|*extrabold*|*extra-bold*) printf '800\n' ;;
        900.ttf|*black*|*heavy*) printf '900\n' ;;
        *) printf '400\n' ;;
    esac
}

_lhcc_source_for_name() {
    _lhcc_name="$1"
    _lhcc_payload="$(_lhcc_payload_root)"
    _lhcc_system="$_lhcc_payload/system/fonts"

    # Best source is the exact v14.4-generated alias. This preserves composite
    # CJK/Latin/digit content and any selected weight without rebuilding anything.
    [ -s "$_lhcc_system/$_lhcc_name" ] && {
        printf '%s\n' "$_lhcc_system/$_lhcc_name"
        return 0
    }

    _lhcc_weight=$(_lhcc_weight_for_name "$_lhcc_name")
    for _lhcc_file in \
        "$_lhcc_system/${_lhcc_weight}.ttf" \
        "$_lhcc_system/400.ttf" \
        "$_lhcc_system/Roboto-Regular.ttf" \
        "$_lhcc_system/MiSansLatinVF.ttf" \
        "$_lhcc_system/MiSansVF.ttf"; do
        [ -s "$_lhcc_file" ] || continue
        printf '%s\n' "$_lhcc_file"
        return 0
    done
    return 1
}

_lhcc_static_names() {
    cat <<'EOF_LHCC_STATIC'
MiSansVF.ttf
MiSansVF_Overlay.ttf
MiSansLatinVF.ttf
MiSansTCVF.ttf
MiSansL3.otf
100.ttf
200.ttf
300.ttf
350.ttf
400.ttf
500.ttf
600.ttf
700.ttf
800.ttf
900.ttf
Roboto-Thin.ttf
Roboto-ExtraLight.ttf
Roboto-Light.ttf
Roboto-Regular.ttf
Roboto-Medium.ttf
Roboto-SemiBold.ttf
Roboto-Bold.ttf
Roboto-ExtraBold.ttf
Roboto-Black.ttf
RobotoFlex-Regular.ttf
RobotoStatic-Regular.ttf
GoogleSans-Regular.ttf
GoogleSans-Medium.ttf
GoogleSans-SemiBold.ttf
GoogleSans-Bold.ttf
GoogleSans-Black.ttf
GoogleSansText-Regular.ttf
GoogleSansText-Medium.ttf
GoogleSansText-SemiBold.ttf
GoogleSansText-Bold.ttf
GoogleSansText-Black.ttf
GoogleSansText-VF.ttf
GoogleSansTextVF.ttf
GoogleSans-VF.ttf
GoogleSansFlex-Regular.ttf
NotoSans-Regular.ttf
NotoSans-Medium.ttf
NotoSans-SemiBold.ttf
NotoSans-Bold.ttf
NotoSans-Black.ttf
NotoSansUI-Regular.ttf
NotoSansUI-Medium.ttf
NotoSansUI-Bold.ttf
SourceSansPro-Regular.ttf
SourceSansPro-Medium.ttf
SourceSansPro-SemiBold.ttf
SourceSansPro-Bold.ttf
DroidSans.ttf
MitypeVF.ttf
MitypeMonoVF.ttf
MitypeClock.ttf
MitypeClock.otf
MitypeClockMono.ttf
MitypeClockMono.otf
MiClock.ttf
MiClock.otf
MiClockThin.ttf
MiClockThin.otf
MiClockMono.ttf
MiClockMono.otf
MiSansClock.ttf
MiSansClockVF.ttf
AndroidClock.ttf
AndroidClock_Highlight.ttf
AndroidClock_Solid.ttf
Clockopia.ttf
EOF_LHCC_STATIC
}

_lhcc_safe_dynamic_name() {
    _lhcc_name="$1"
    case "$_lhcc_name" in
        *Italic*|*Oblique*|*Emoji*|*Symbol*|*Icon*|*Serif*) return 1 ;;
        *Arabic*|*Hebrew*|*Thai*|*Devanagari*|*Bengali*|*Tamil*|*Telugu*|*Malayalam*|*Gujarati*|*Gurmukhi*|*Kannada*|*Khmer*|*Lao*|*Tibetan*|*Myanmar*) return 1 ;;
    esac
    case "$_lhcc_name" in
        MiSansVF.ttf|MiSansVF_Overlay.ttf|MiSansLatinVF.ttf|MiSansTCVF.ttf|MiSansL3.otf|\
        [1-9]00.ttf|350.ttf|\
        Roboto*.ttf|Roboto*.otf|GoogleSans*.ttf|GoogleSans*.otf|\
        NotoSans-Regular.ttf|NotoSans-Medium.ttf|NotoSans-SemiBold.ttf|NotoSans-Bold.ttf|NotoSans-Black.ttf|\
        NotoSansUI-Regular.ttf|NotoSansUI-Medium.ttf|NotoSansUI-Bold.ttf|\
        SourceSansPro*.ttf|SourceSansPro*.otf|DroidSans.ttf|\
        Mitype*.ttf|Mitype*.otf|MiClock*.ttf|MiClock*.otf|\
        MiSans*Clock*.ttf|MiSans*Clock*.otf|AndroidClock*.ttf|AndroidClock*.otf|Clockopia.ttf|\
        MiLanPro*.ttf|MiLanPro*.otf|XiaomiSans*.ttf|XiaomiSans*.otf)
            return 0
            ;;
    esac
    return 1
}

_lhcc_names_for_root() {
    _lhcc_real="$1"
    {
        _lhcc_static_names
        [ -d "$_lhcc_real" ] || exit 0
        for _lhcc_path in "$_lhcc_real"/*; do
            [ -f "$_lhcc_path" ] || continue
            _lhcc_name=${_lhcc_path##*/}
            _lhcc_safe_dynamic_name "$_lhcc_name" || continue
            printf '%s\n' "$_lhcc_name"
        done
    } | awk 'NF && !seen[$0]++'
}

_lhcc_link_or_copy() {
    _lhcc_source="$1"
    _lhcc_dest="$2"
    [ "$_lhcc_source" = "$_lhcc_dest" ] && return 0
    rm -f "$_lhcc_dest" 2>/dev/null || true
    ln "$_lhcc_source" "$_lhcc_dest" 2>/dev/null || \
        cp -f "$_lhcc_source" "$_lhcc_dest" 2>/dev/null || return 1
    chmod 0644 "$_lhcc_dest" 2>/dev/null || true
    return 0
}

luoshu_hyperos_clock_payload_ensure() {
    _lhcc_is_hyperos || return 0
    _lhcc_payload="$(_lhcc_payload_root)"
    [ -d "$_lhcc_payload/system/fonts" ] || return 0
    _lhcc_count=0
    _lhcc_parts=0

    # Mirror only names that exist on this exact ROM. The source always comes from
    # the already-built v14.4 payload, so this is fast and cannot re-enter the v4
    # template/slot builder/validation path that previously stalled at 94%.
    for _lhcc_part in system system_ext product mi_ext vendor odm oem my_product hw_product cust; do
        _lhcc_real="$(_lhcc_root_for_part "$_lhcc_part")" || continue
        [ -d "$_lhcc_real" ] || continue
        _lhcc_overlay="$_lhcc_payload/$_lhcc_part/fonts"
        _lhcc_part_count=0
        while IFS= read -r _lhcc_name; do
            [ -n "$_lhcc_name" ] || continue
            [ -e "$_lhcc_real/$_lhcc_name" ] || continue
            _lhcc_source="$(_lhcc_source_for_name "$_lhcc_name")" || continue
            mkdir -p "$_lhcc_overlay" 2>/dev/null || continue
            if _lhcc_link_or_copy "$_lhcc_source" "$_lhcc_overlay/$_lhcc_name"; then
                _lhcc_count=$((_lhcc_count + 1))
                _lhcc_part_count=$((_lhcc_part_count + 1))
            fi
        done <<EOF_LHCC_NAMES
$(_lhcc_names_for_root "$_lhcc_real")
EOF_LHCC_NAMES
        [ "$_lhcc_part_count" -gt 0 ] 2>/dev/null && _lhcc_parts=$((_lhcc_parts + 1))
    done

    _lhcc_module="$(_lhcc_module_dir)"
    if [ "$_lhcc_count" -gt 0 ]; then
        mkdir -p "$_lhcc_module/logs" 2>/dev/null || true
        printf '[%s] HyperOS legacy physical UI slots restored: %s targets / %s partitions\n' \
            "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" "$_lhcc_count" "$_lhcc_parts" \
            >> "$_lhcc_module/logs/fontswitch.log" 2>/dev/null || true
    fi
    return 0
}

# New semantic name for callers/tests; keep the old function as compatibility API.
luoshu_hyperos_legacy_payload_ensure() {
    luoshu_hyperos_clock_payload_ensure "$@"
}
