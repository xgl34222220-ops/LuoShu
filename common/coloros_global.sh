#!/system/bin/sh
# ColorOS/OPlus partition-aware font mapping.
# Loaded after rom_adapters.sh so it can replace the legacy system-only copy_as_coloros().
set +e

_luoshu_coloros_module_dir() {
    printf '%s\n' "${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
}

# real font directory | matching module overlay directory
_luoshu_coloros_root_pairs() {
    _lcg_module="$(_luoshu_coloros_module_dir)"
    printf '%s|%s/system/fonts\n' "${LUOSHU_COLOROS_SYSTEM_FONTS_ROOT:-${LUOSHU_SYSTEM_FONTS_ROOT:-/system/fonts}}" "$_lcg_module"
    printf '%s|%s/system_ext/fonts\n' "${LUOSHU_COLOROS_SYSTEM_EXT_FONTS_ROOT:-${LUOSHU_SYSTEM_EXT_FONTS_ROOT:-/system_ext/fonts}}" "$_lcg_module"
    printf '%s|%s/product/fonts\n' "${LUOSHU_COLOROS_PRODUCT_FONTS_ROOT:-${LUOSHU_PRODUCT_FONTS_ROOT:-/product/fonts}}" "$_lcg_module"
    printf '%s|%s/vendor/fonts\n' "${LUOSHU_COLOROS_VENDOR_FONTS_ROOT:-/vendor/fonts}" "$_lcg_module"
    printf '%s|%s/odm/fonts\n' "${LUOSHU_COLOROS_ODM_FONTS_ROOT:-/odm/fonts}" "$_lcg_module"
    printf '%s|%s/oem/fonts\n' "${LUOSHU_COLOROS_OEM_FONTS_ROOT:-/oem/fonts}" "$_lcg_module"
    printf '%s|%s/my_product/fonts\n' "${LUOSHU_COLOROS_MY_PRODUCT_FONTS_ROOT:-/my_product/fonts}" "$_lcg_module"
    printf '%s|%s/oplus_product/fonts\n' "${LUOSHU_COLOROS_OPLUS_PRODUCT_FONTS_ROOT:-/oplus_product/fonts}" "$_lcg_module"
    printf '%s|%s/oplus_engineering/fonts\n' "${LUOSHU_COLOROS_OPLUS_ENGINEERING_FONTS_ROOT:-/oplus_engineering/fonts}" "$_lcg_module"
    printf '%s|%s/oplus_version/fonts\n' "${LUOSHU_COLOROS_OPLUS_VERSION_FONTS_ROOT:-/oplus_version/fonts}" "$_lcg_module"
    printf '%s|%s/oplus_region/fonts\n' "${LUOSHU_COLOROS_OPLUS_REGION_FONTS_ROOT:-/oplus_region/fonts}" "$_lcg_module"
}

_coloros_core_files() {
    printf '%s\n' 'SysSans-Hant-Regular.ttf SysSans-Hans-Regular.ttf SysFont-Static-Regular.ttf SysFont-Hant-Regular.ttf SysFont-Hans-Regular.ttf SysFont-Regular.ttf SysSans-En-Regular.ttf'
}

# Google apps commonly request google-sans-text directly. On current ColorOS builds these files are
# normally in /product/fonts, not /system/fonts, so a system-only alias does not affect text fields.
_coloros_google_text_files() {
    printf '%s\n' 'GoogleSansText-Regular.ttf GoogleSansText-Medium.ttf GoogleSansText-SemiBold.ttf GoogleSansText-Bold.ttf GoogleSansText-VF.ttf GoogleSansTextVF.ttf GoogleSans-Regular.ttf GoogleSans-Medium.ttf GoogleSans-SemiBold.ttf GoogleSans-Bold.ttf GoogleSans-VF.ttf GoogleSansFlex-Regular.ttf Roboto-Regular.ttf Roboto-Medium.ttf Roboto-SemiBold.ttf Roboto-Bold.ttf Roboto-Light.ttf Roboto-Thin.ttf Roboto-ExtraLight.ttf Roboto-ExtraBold.ttf Roboto-Black.ttf RobotoFlex-Regular.ttf RobotoStatic-Regular.ttf'
}

_coloros_vendor_files() {
    printf '%s\n' 'SysSans-En-Bold.ttf SysSans-En-Light.ttf SysSans-En-Medium.ttf SysSans-En-Thin.ttf SysSans-En-Black.ttf SysFont-Bold.ttf SysFont-Light.ttf SysFont-Medium.ttf SysFont-Thin.ttf SysFont-Black.ttf SysFont-Hans-Bold.ttf SysFont-Hans-Light.ttf SysFont-Hans-Medium.ttf SysFont-Hans-Thin.ttf SysFont-Hant-Bold.ttf SysFont-Hant-Light.ttf SysFont-Hant-Medium.ttf SysFont-Hant-Thin.ttf SysSans-Hant-Bold.ttf SysSans-Hant-Light.ttf SysSans-Hant-Medium.ttf SysSans-Hans-Bold.ttf SysSans-Hans-Light.ttf SysSans-Hans-Medium.ttf SysFont-Static-Bold.ttf SysFont-Static-Light.ttf SysFont-Static-Medium.ttf DINCondensedBold.ttf DINPro-Bold.ttf DINPro-Medium.ttf DINPro-Regular.ttf OPPODIN-Bold.ttf OPPODIN-Medium.ttf OPPODIN-Regular.ttf OPPODINCondensed-Bold.ttf OPPODINCondensed-Medium.ttf OPPODINCondensed-Regular.ttf Opposans-En-Regular.ttf Opposans-Hans-Regular.ttf Opposans-En-Bold.ttf Opposans-Hans-Bold.ttf Opposans-En-Medium.ttf Opposans-Hans-Medium.ttf Opposans-En-Light.ttf Opposans-Hans-Light.ttf OPSans-En-Regular.ttf OplusSans-Regular.ttf OplusSans-Medium.ttf OplusSans-Bold.ttf SourceSansPro-Regular.ttf SourceSansPro-SemiBold.ttf SourceSansPro-Bold.ttf'
}

get_all_coloros_files() {
    printf '%s %s %s\n' "$(_coloros_core_files)" "$(_coloros_google_text_files)" "$(_coloros_vendor_files)"
}

# Legacy callers use names without the .ttf suffix.
get_all_coloros_names() {
    for _lcg_file in $(get_all_coloros_files); do
        printf '%s\n' "${_lcg_file%.ttf}"
    done
}

_coloros_file_role() {
    _lcg_lower=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
    case "$_lcg_lower" in
        *extrabold*|*extra-bold*) printf 'extrabold\n' ;;
        *semibold*|*semi-bold*|*demibold*) printf 'semibold\n' ;;
        *extralight*|*extra-light*) printf 'extralight\n' ;;
        *medium*) printf 'medium\n' ;;
        *black*|*heavy*) printf 'black\n' ;;
        *bold*) printf 'bold\n' ;;
        *light*) printf 'light\n' ;;
        *thin*) printf 'thin\n' ;;
        *) printf 'regular\n' ;;
    esac
}

_coloros_pick_regular_source() {
    _lcg_family="$1"
    _lcg_fallback="$2"
    if type get_weight_file >/dev/null 2>&1; then
        _lcg_regular=$(get_weight_file "$_lcg_family" regular)
        [ -f "$_lcg_regular" ] && { printf '%s\n' "$_lcg_regular"; return 0; }
    fi
    [ -f "$_lcg_fallback" ] && { printf '%s\n' "$_lcg_fallback"; return 0; }
    return 1
}

_coloros_remove_overlay_file() {
    _lcg_file="$1"
    while IFS='|' read -r _lcg_real _lcg_overlay; do
        [ -n "$_lcg_overlay" ] || continue
        rm -f "$_lcg_overlay/$_lcg_file" 2>/dev/null || true
    done <<EOF_LUOSHU_COLOROS_ROOTS
$(_luoshu_coloros_root_pairs)
EOF_LUOSHU_COLOROS_ROOTS
}

_coloros_alias_existing_targets() {
    _lcg_anchor="$1"
    _lcg_file="$2"
    _lcg_count=0
    while IFS='|' read -r _lcg_real _lcg_overlay; do
        [ -n "$_lcg_real" ] && [ -n "$_lcg_overlay" ] || continue
        [ -e "$_lcg_real/$_lcg_file" ] || continue
        mkdir -p "$_lcg_overlay" 2>/dev/null || continue
        if _font_alias "$_lcg_anchor" "$_lcg_overlay/$_lcg_file"; then
            if type _verify_font_copy >/dev/null 2>&1; then
                _verify_font_copy "$_lcg_overlay/$_lcg_file" || continue
            fi
            _lcg_count=$((_lcg_count + 1))
        fi
    done <<EOF_LUOSHU_COLOROS_ROOTS
$(_luoshu_coloros_root_pairs)
EOF_LUOSHU_COLOROS_ROOTS
    printf '%s\n' "$_lcg_count"
}

_coloros_anchor_for_file() {
    _lcg_regular_anchor="$1"
    _lcg_family="$2"
    _lcg_weights="$3"
    _lcg_store="$4"
    _lcg_file="$5"
    _lcg_role=$(_coloros_file_role "$_lcg_file")
    [ "$_lcg_role" != regular ] || { printf '%s\n' "$_lcg_regular_anchor"; return 0; }
    case ",$_lcg_weights," in
        *",$_lcg_role,"*)
            _lcg_source=$(get_weight_file "$_lcg_family" "$_lcg_role" 2>/dev/null)
            if [ -f "$_lcg_source" ]; then
                _lcg_anchor="$_lcg_store/.luoshu-font-store/${_lcg_role}.font"
                if [ ! -s "$_lcg_anchor" ]; then
                    _lcg_anchor=$(_font_anchor "$_lcg_source" "$_lcg_store" "$_lcg_role") || {
                        printf '%s\n' "$_lcg_regular_anchor"
                        return 0
                    }
                fi
                printf '%s\n' "$_lcg_anchor"
                return 0
            fi
            ;;
    esac
    printf '%s\n' "$_lcg_regular_anchor"
}

copy_as_coloros() {
    _lcg_src="$1"
    _lcg_dest_dir="$2"
    _lcg_mode="${3:-full}"
    _lcg_family="${4:-}"
    _lcg_module="$(_luoshu_coloros_module_dir)"
    [ -n "$_lcg_family" ] || _lcg_family=$(detect_font_family "$(basename "$_lcg_src")")
    _lcg_regular=$(_coloros_pick_regular_source "$_lcg_family" "$_lcg_src") || return 1

    mkdir -p "$_lcg_module/system/fonts" 2>/dev/null || return 1
    for _lcg_file in $(get_all_coloros_files); do _coloros_remove_overlay_file "$_lcg_file"; done
    _font_store_reset "$_lcg_module/system/fonts"
    _lcg_regular_anchor=$(_font_anchor "$_lcg_regular" "$_lcg_module/system/fonts" regular) || return 1
    _lcg_weights=''
    if type scan_family_weights >/dev/null 2>&1; then
        _lcg_weights=$(scan_family_weights "$_lcg_family")
    fi

    _lcg_total=0
    _lcg_google=0
    _lcg_core=0
    for _lcg_file in $(get_all_coloros_files); do
        _lcg_anchor=$(_coloros_anchor_for_file "$_lcg_regular_anchor" "$_lcg_family" "$_lcg_weights" "$_lcg_module/system/fonts" "$_lcg_file")
        _lcg_added=$(_coloros_alias_existing_targets "$_lcg_anchor" "$_lcg_file")
        case "$_lcg_added" in ''|*[!0-9]*) _lcg_added=0 ;; esac
        _lcg_total=$((_lcg_total + _lcg_added))
        case "$_lcg_file" in
            GoogleSans*|Roboto*) _lcg_google=$((_lcg_google + _lcg_added)) ;;
            SysFont*|SysSans*) _lcg_core=$((_lcg_core + _lcg_added)) ;;
        esac
    done

    # Old or heavily trimmed ColorOS builds may hide every real path from the installer namespace.
    # Keep a minimal system mapping rather than silently producing an empty payload.
    if [ "$_lcg_total" -eq 0 ]; then
        for _lcg_file in SysFont-Regular.ttf SysSans-En-Regular.ttf Roboto-Regular.ttf GoogleSansText-Regular.ttf; do
            if _font_alias "$_lcg_regular_anchor" "$_lcg_dest_dir/$_lcg_file"; then
                _lcg_total=$((_lcg_total + 1))
            fi
        done
    fi

    if type _log_step >/dev/null 2>&1; then
        _log_step "  ColorOS 已按真实分区覆盖 $_lcg_total 个字体目标（系统族=$_lcg_core，Google 输入族=$_lcg_google）"
    fi
    [ "$_lcg_total" -gt 0 ]
}
