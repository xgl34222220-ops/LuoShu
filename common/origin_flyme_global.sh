#!/system/bin/sh
# OriginOS/vivo and Flyme/Meizu font adapters.
# Loaded after the generic, HyperOS and ColorOS adapters so this file owns the final ROM dispatcher.
set +e

_luoshu_oem_module_dir() {
    printf '%s\n' "${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
}

_luoshu_oem_getprop() {
    command -v getprop >/dev/null 2>&1 || return 1
    getprop "$1" 2>/dev/null | tr -d '\r\n'
}

_luoshu_detect_originos() {
    IS_ORIGINOS=false
    ORIGINOS_VERSION=''
    [ "${LUOSHU_TEST_ROM:-}" != originos ] || {
        IS_ORIGINOS=true
        ORIGINOS_VERSION=test
        return 0
    }
    _lod_name=$(_luoshu_oem_getprop ro.vivo.os.name)
    _lod_version=$(_luoshu_oem_getprop ro.vivo.os.version)
    _lod_rom=$(_luoshu_oem_getprop ro.vivo.rom.version)
    _lod_display=$(_luoshu_oem_getprop ro.build.display.id)
    _lod_brand=$(_luoshu_oem_getprop ro.product.brand)
    _lod_manufacturer=$(_luoshu_oem_getprop ro.product.manufacturer)
    case "$_lod_name $_lod_display" in
        *OriginOS*|*originos*) IS_ORIGINOS=true ;;
    esac
    if [ "$IS_ORIGINOS" != true ]; then
        case "$_lod_brand $_lod_manufacturer" in
            *vivo*|*VIVO*|*iQOO*|*IQOO*)
                [ -n "$_lod_version$_lod_rom" ] && IS_ORIGINOS=true
                ;;
        esac
    fi
    ORIGINOS_VERSION="${_lod_version:-${_lod_rom:-${_lod_name:-unknown}}}"
    [ "$IS_ORIGINOS" = true ]
}

_luoshu_detect_flyme() {
    IS_FLYME=false
    FLYME_VERSION=''
    [ "${LUOSHU_TEST_ROM:-}" != flyme ] || {
        IS_FLYME=true
        FLYME_VERSION=test
        return 0
    }
    _lfd_display=$(_luoshu_oem_getprop ro.build.display.id)
    _lfd_version=$(_luoshu_oem_getprop ro.flyme.published)
    _lfd_brand=$(_luoshu_oem_getprop ro.product.brand)
    _lfd_manufacturer=$(_luoshu_oem_getprop ro.product.manufacturer)
    case "$_lfd_display" in
        *Flyme*|*flyme*) IS_FLYME=true ;;
    esac
    if [ "$IS_FLYME" != true ]; then
        case "$_lfd_brand $_lfd_manufacturer" in
            *Meizu*|*MEIZU*|*meizu*) IS_FLYME=true ;;
        esac
    fi
    FLYME_VERSION="${_lfd_display:-${_lfd_version:-unknown}}"
    [ "$IS_FLYME" = true ]
}

_luoshu_oem_detect_rom() {
    if _luoshu_detect_originos; then
        printf 'originos\n'
    elif _luoshu_detect_flyme; then
        printf 'flyme\n'
    else
        printf 'generic\n'
    fi
}

# real font directory | matching module overlay directory
_luoshu_originos_root_pairs() {
    _lor_module="$(_luoshu_oem_module_dir)"
    printf '%s|%s/system/fonts\n' "${LUOSHU_ORIGINOS_SYSTEM_FONTS_ROOT:-/system/fonts}" "$_lor_module"
    printf '%s|%s/system_ext/fonts\n' "${LUOSHU_ORIGINOS_SYSTEM_EXT_FONTS_ROOT:-/system_ext/fonts}" "$_lor_module"
    printf '%s|%s/product/fonts\n' "${LUOSHU_ORIGINOS_PRODUCT_FONTS_ROOT:-/product/fonts}" "$_lor_module"
    printf '%s|%s/vendor/fonts\n' "${LUOSHU_ORIGINOS_VENDOR_FONTS_ROOT:-/vendor/fonts}" "$_lor_module"
    printf '%s|%s/odm/fonts\n' "${LUOSHU_ORIGINOS_ODM_FONTS_ROOT:-/odm/fonts}" "$_lor_module"
    printf '%s|%s/oem/fonts\n' "${LUOSHU_ORIGINOS_OEM_FONTS_ROOT:-/oem/fonts}" "$_lor_module"
    printf '%s|%s/my_product/fonts\n' "${LUOSHU_ORIGINOS_MY_PRODUCT_FONTS_ROOT:-/my_product/fonts}" "$_lor_module"
    printf '%s|%s/product/vivo/fonts\n' "${LUOSHU_ORIGINOS_PRODUCT_VIVO_FONTS_ROOT:-/product/vivo/fonts}" "$_lor_module"
    printf '%s|%s/system_ext/vivo/fonts\n' "${LUOSHU_ORIGINOS_SYSTEM_EXT_VIVO_FONTS_ROOT:-/system_ext/vivo/fonts}" "$_lor_module"
    printf '%s|%s/vendor/vivo/fonts\n' "${LUOSHU_ORIGINOS_VENDOR_VIVO_FONTS_ROOT:-/vendor/vivo/fonts}" "$_lor_module"
}

_luoshu_flyme_root_pairs() {
    _lfr_module="$(_luoshu_oem_module_dir)"
    printf '%s|%s/system/fonts\n' "${LUOSHU_FLYME_SYSTEM_FONTS_ROOT:-/system/fonts}" "$_lfr_module"
    printf '%s|%s/system_ext/fonts\n' "${LUOSHU_FLYME_SYSTEM_EXT_FONTS_ROOT:-/system_ext/fonts}" "$_lfr_module"
    printf '%s|%s/product/fonts\n' "${LUOSHU_FLYME_PRODUCT_FONTS_ROOT:-/product/fonts}" "$_lfr_module"
    printf '%s|%s/vendor/fonts\n' "${LUOSHU_FLYME_VENDOR_FONTS_ROOT:-/vendor/fonts}" "$_lfr_module"
    printf '%s|%s/odm/fonts\n' "${LUOSHU_FLYME_ODM_FONTS_ROOT:-/odm/fonts}" "$_lfr_module"
    printf '%s|%s/oem/fonts\n' "${LUOSHU_FLYME_OEM_FONTS_ROOT:-/oem/fonts}" "$_lfr_module"
    printf '%s|%s/my_product/fonts\n' "${LUOSHU_FLYME_MY_PRODUCT_FONTS_ROOT:-/my_product/fonts}" "$_lfr_module"
}

_luoshu_oem_root_pairs() {
    case "$1" in
        originos) _luoshu_originos_root_pairs ;;
        flyme) _luoshu_flyme_root_pairs ;;
        *) return 1 ;;
    esac
}

_luoshu_oem_file_role() {
    _lofr_lower=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
    case "$_lofr_lower" in
        *-100.*|*_100.*|*thin*) printf 'thin\n' ;;
        *-200.*|*_200.*|*extralight*|*extra-light*) printf 'extralight\n' ;;
        *-300.*|*_300.*|*light*) printf 'light\n' ;;
        *-500.*|*_500.*|*medium*) printf 'medium\n' ;;
        *-600.*|*_600.*|*semibold*|*semi-bold*|*demibold*) printf 'semibold\n' ;;
        *-800.*|*_800.*|*extrabold*|*extra-bold*) printf 'extrabold\n' ;;
        *-900.*|*_900.*|*black*|*heavy*) printf 'black\n' ;;
        *-700.*|*_700.*|*bold*) printf 'bold\n' ;;
        *) printf 'regular\n' ;;
    esac
}

_luoshu_oem_protected_filename() {
    _lop_lower=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
    case "$_lop_lower" in
        *emoji*|*symbol*|*icon*|*material*|*dingbat*|*clock*|*mono*|*serif*|*math*|*music*|*braille*|*barcode*|*qrcode*|*fallback*|*legacy*|*thai*|*arabic*|*devanagari*|*bengali*|*tamil*|*telugu*|*kannada*|*malayalam*|*hebrew*|*khmer*|*lao*|*tibetan*|*myanmar*|*japanese*|*korean*) return 0 ;;
    esac
    return 1
}

_luoshu_oem_candidate_filename() {
    _loc_rom="$1"
    _loc_file="$2"
    _loc_lower=$(printf '%s' "$_loc_file" | tr '[:upper:]' '[:lower:]')
    case "$_loc_lower" in *.ttf|*.otf|*.ttc) ;; *) return 1 ;; esac
    _luoshu_oem_protected_filename "$_loc_file" && return 1
    case "$_loc_rom:$_loc_lower" in
        originos:*vivosans*|originos:*vivo-sans*|originos:*originsans*|originos:*origin-sans*|originos:*iqoosans*|originos:*iqoo-sans*) return 0 ;;
        flyme:*flymefont*|flyme:*flymesans*|flyme:*flyme-sans*|flyme:*meizusans*|flyme:*meizu-sans*|flyme:*mflyme*) return 0 ;;
    esac
    case "$_loc_lower" in
        roboto-regular.ttf|roboto-medium.ttf|roboto-semibold.ttf|roboto-bold.ttf|roboto-light.ttf|roboto-thin.ttf|roboto-extralight.ttf|roboto-extrabold.ttf|roboto-black.ttf|robotoflex-regular.ttf|robotostatic-regular.ttf|googlesans-regular.ttf|googlesans-medium.ttf|googlesans-semibold.ttf|googlesans-bold.ttf|googlesanstext-regular.ttf|googlesanstext-medium.ttf|googlesanstext-semibold.ttf|googlesanstext-bold.ttf|googlesansflex-regular.ttf|notosans-regular.ttf) return 0 ;;
    esac
    return 1
}

_luoshu_oem_pick_regular_source() {
    _lops_family="$1"
    _lops_fallback="$2"
    if type get_weight_file >/dev/null 2>&1; then
        _lops_regular=$(get_weight_file "$_lops_family" regular 2>/dev/null)
        [ -f "$_lops_regular" ] && { printf '%s\n' "$_lops_regular"; return 0; }
        _lops_variable=$(get_weight_file "$_lops_family" variable 2>/dev/null)
        [ -f "$_lops_variable" ] && { printf '%s\n' "$_lops_variable"; return 0; }
    fi
    [ -f "$_lops_fallback" ] && { printf '%s\n' "$_lops_fallback"; return 0; }
    return 1
}

_luoshu_oem_anchor_for_file() {
    _loaf_regular_anchor="$1"
    _loaf_family="$2"
    _loaf_store="$3"
    _loaf_file="$4"
    _loaf_role=$(_luoshu_oem_file_role "$_loaf_file")
    [ "$_loaf_role" != regular ] || { printf '%s\n' "$_loaf_regular_anchor"; return 0; }
    if type get_weight_file >/dev/null 2>&1; then
        _loaf_source=$(get_weight_file "$_loaf_family" "$_loaf_role" 2>/dev/null)
        if [ -f "$_loaf_source" ]; then
            _loaf_anchor="$_loaf_store/.luoshu-font-store/${_loaf_role}.font"
            if [ ! -s "$_loaf_anchor" ]; then
                _loaf_anchor=$(_font_anchor "$_loaf_source" "$_loaf_store" "$_loaf_role") || {
                    printf '%s\n' "$_loaf_regular_anchor"
                    return 0
                }
            fi
            printf '%s\n' "$_loaf_anchor"
            return 0
        fi
    fi
    printf '%s\n' "$_loaf_regular_anchor"
}

luoshu_oem_clear_managed_fonts() {
    _locm_module="$(_luoshu_oem_module_dir)"
    _locm_manifest="$_locm_module/config/oem-font-targets.conf"
    [ -f "$_locm_manifest" ] || return 0
    while IFS='|' read -r _locm_rom _locm_rel _locm_real; do
        case "$_locm_rel" in
            system/fonts/*|system_ext/fonts/*|product/fonts/*|vendor/fonts/*|odm/fonts/*|oem/fonts/*|my_product/fonts/*|product/vivo/fonts/*|system_ext/vivo/fonts/*|vendor/vivo/fonts/*)
                rm -f "$_locm_module/$_locm_rel" 2>/dev/null || true
                ;;
        esac
    done < "$_locm_manifest"
    rm -f "$_locm_manifest" 2>/dev/null || true
}

_luoshu_oem_copy_existing_slots() {
    _loce_rom="$1"
    _loce_src="$2"
    _loce_family="$3"
    _loce_module="$(_luoshu_oem_module_dir)"
    _loce_config="$_loce_module/config"
    _loce_store="$_loce_module/system/fonts"
    _loce_manifest_tmp="$_loce_config/oem-font-targets.conf.tmp.$$"
    mkdir -p "$_loce_store" "$_loce_config" 2>/dev/null || return 1
    luoshu_oem_clear_managed_fonts
    _font_store_reset "$_loce_store"
    _loce_regular=$(_luoshu_oem_pick_regular_source "$_loce_family" "$_loce_src") || return 1
    _loce_regular_anchor=$(_font_anchor "$_loce_regular" "$_loce_store" regular) || return 1
    : > "$_loce_manifest_tmp" 2>/dev/null || return 1
    _loce_count=0
    while IFS='|' read -r _loce_real_root _loce_overlay_root; do
        [ -d "$_loce_real_root" ] || continue
        for _loce_real_file in "$_loce_real_root"/*; do
            [ -f "$_loce_real_file" ] || continue
            _loce_name=$(basename "$_loce_real_file")
            _luoshu_oem_candidate_filename "$_loce_rom" "$_loce_name" || continue
            _loce_anchor=$(_luoshu_oem_anchor_for_file "$_loce_regular_anchor" "$_loce_family" "$_loce_store" "$_loce_name")
            [ -s "$_loce_anchor" ] || continue
            case "$_loce_name" in
                *.ttc|*.TTC)
                    _loce_magic=$(dd if="$_loce_anchor" bs=4 count=1 2>/dev/null)
                    [ "$_loce_magic" = ttcf ] || continue
                    ;;
            esac
            mkdir -p "$_loce_overlay_root" 2>/dev/null || continue
            _loce_dest="$_loce_overlay_root/$_loce_name"
            rm -f "$_loce_dest" 2>/dev/null || true
            if _font_alias "$_loce_anchor" "$_loce_dest"; then
                _loce_size=$(wc -c < "$_loce_dest" 2>/dev/null | tr -d '[:space:]')
                case "$_loce_size" in ''|*[!0-9]*) _loce_size=0 ;; esac
                if [ "$_loce_size" -ge 1024 ]; then
                    _loce_rel="${_loce_dest#$_loce_module/}"
                    printf '%s|%s|%s\n' "$_loce_rom" "$_loce_rel" "$_loce_real_file" >> "$_loce_manifest_tmp"
                    _loce_count=$((_loce_count + 1))
                else
                    rm -f "$_loce_dest" 2>/dev/null || true
                fi
            fi
        done
    done <<EOF_LUOSHU_OEM_ROOTS
$(_luoshu_oem_root_pairs "$_loce_rom")
EOF_LUOSHU_OEM_ROOTS
    mv -f "$_loce_manifest_tmp" "$_loce_config/oem-font-targets.conf" 2>/dev/null || return 1
    chmod 0644 "$_loce_config/oem-font-targets.conf" 2>/dev/null || true
    LUOSHU_OEM_SLOT_COUNT="$_loce_count"
    export LUOSHU_OEM_SLOT_COUNT
    [ "$_loce_count" -gt 0 ]
}

_luoshu_flyme_data_root() {
    printf '%s\n' "${LUOSHU_FLYME_DATA_FONT_ROOT:-/data/customizecenter/font}"
}

luoshu_flyme_pending_clear() {
    _lfpc_module="$(_luoshu_oem_module_dir)"
    rm -rf "$_lfpc_module/config/flyme-data-stage" 2>/dev/null || true
    rm -f "$_lfpc_module/config/flyme-data-pending.conf" 2>/dev/null || true
}

_luoshu_flyme_prepare_data_apply() {
    _lfpa_source="$1"
    _lfpa_module="$(_luoshu_oem_module_dir)"
    _lfpa_root="$(_luoshu_flyme_data_root)"
    [ -d "$_lfpa_root" ] || return 2
    [ -f "$_lfpa_source" ] || return 1
    _lfpa_size=$(wc -c < "$_lfpa_source" 2>/dev/null | tr -d '[:space:]')
    case "$_lfpa_size" in ''|*[!0-9]*) _lfpa_size=0 ;; esac
    [ "$_lfpa_size" -ge 1024 ] || return 1
    luoshu_flyme_pending_clear
    mkdir -p "$_lfpa_module/config/flyme-data-stage" 2>/dev/null || return 1
    cp -f "$_lfpa_source" "$_lfpa_module/config/flyme-data-stage/flymeFont.ttf" 2>/dev/null || return 1
    chmod 0444 "$_lfpa_module/config/flyme-data-stage/flymeFont.ttf" 2>/dev/null || true
    {
        printf 'action=apply\n'
        printf 'root=%s\n' "$_lfpa_root"
    } > "$_lfpa_module/config/flyme-data-pending.conf" 2>/dev/null || return 1
    chmod 0600 "$_lfpa_module/config/flyme-data-pending.conf" 2>/dev/null || true
    return 0
}

_luoshu_flyme_prepare_data_restore() {
    _lfpr_module="$(_luoshu_oem_module_dir)"
    _lfpr_state="$_lfpr_module/config/flyme-data-original/state.conf"
    [ -f "$_lfpr_state" ] || return 0
    luoshu_flyme_pending_clear
    {
        printf 'action=restore\n'
        printf 'root=%s\n' "$(_luoshu_flyme_data_root)"
    } > "$_lfpr_module/config/flyme-data-pending.conf" 2>/dev/null || return 1
    chmod 0600 "$_lfpr_module/config/flyme-data-pending.conf" 2>/dev/null || true
}

_luoshu_flyme_capture_original() {
    _lfco_root="$1"
    _lfco_module="$(_luoshu_oem_module_dir)"
    _lfco_dir="$_lfco_module/config/flyme-data-original"
    _lfco_state="$_lfco_dir/state.conf"
    [ -f "$_lfco_state" ] && return 0
    mkdir -p "$_lfco_dir" 2>/dev/null || return 1
    if [ -f "$_lfco_root/flymeFont.ttf" ]; then
        cp -fp "$_lfco_root/flymeFont.ttf" "$_lfco_dir/flymeFont.ttf" 2>/dev/null || return 1
        printf 'original=present\n' > "$_lfco_state" 2>/dev/null || return 1
    else
        printf 'original=absent\n' > "$_lfco_state" 2>/dev/null || return 1
    fi
    chmod 0600 "$_lfco_state" "$_lfco_dir/flymeFont.ttf" 2>/dev/null || true
}

_luoshu_flyme_atomic_install() {
    _lfai_source="$1"
    _lfai_target="$2"
    _lfai_mode="$3"
    mkdir -p "${_lfai_target%/*}" 2>/dev/null || return 1
    _lfai_temp="${_lfai_target}.luoshu.$$"
    rm -f "$_lfai_temp" 2>/dev/null || true
    cp -f "$_lfai_source" "$_lfai_temp" 2>/dev/null || return 1
    chmod "$_lfai_mode" "$_lfai_temp" 2>/dev/null || true
    _lfai_size=$(wc -c < "$_lfai_temp" 2>/dev/null | tr -d '[:space:]')
    case "$_lfai_size" in ''|*[!0-9]*) _lfai_size=0 ;; esac
    [ "$_lfai_size" -ge 1024 ] || { rm -f "$_lfai_temp"; return 1; }
    mv -f "$_lfai_temp" "$_lfai_target" 2>/dev/null
}

luoshu_flyme_pending_apply() {
    _lfpp_module="$(_luoshu_oem_module_dir)"
    _lfpp_pending="$_lfpp_module/config/flyme-data-pending.conf"
    [ -f "$_lfpp_pending" ] || return 0
    _lfpp_action=$(sed -n 's/^action=//p' "$_lfpp_pending" 2>/dev/null | head -n1)
    _lfpp_root=$(sed -n 's/^root=//p' "$_lfpp_pending" 2>/dev/null | head -n1)
    [ -n "$_lfpp_root" ] || return 1
    _lfpp_target="$_lfpp_root/flymeFont.ttf"
    case "$_lfpp_action" in
        apply)
            _lfpp_stage="$_lfpp_module/config/flyme-data-stage/flymeFont.ttf"
            [ -s "$_lfpp_stage" ] || return 1
            _luoshu_flyme_capture_original "$_lfpp_root" || return 1
            _luoshu_flyme_atomic_install "$_lfpp_stage" "$_lfpp_target" 0444 || return 1
            ;;
        restore)
            _lfpp_state="$_lfpp_module/config/flyme-data-original/state.conf"
            _lfpp_original=$(sed -n 's/^original=//p' "$_lfpp_state" 2>/dev/null | head -n1)
            case "$_lfpp_original" in
                present)
                    _luoshu_flyme_atomic_install "$_lfpp_module/config/flyme-data-original/flymeFont.ttf" "$_lfpp_target" 0444 || return 1
                    ;;
                absent) rm -f "$_lfpp_target" 2>/dev/null || return 1 ;;
                *) return 1 ;;
            esac
            rm -rf "$_lfpp_module/config/flyme-data-original" 2>/dev/null || true
            ;;
        *) return 1 ;;
    esac
    luoshu_flyme_pending_clear
    return 0
}

copy_as_originos() {
    _lao_src="$1"
    _lao_family="${4:-}"
    [ -n "$_lao_family" ] || _lao_family=$(detect_font_family "$(basename "$_lao_src")")
    _luoshu_oem_copy_existing_slots originos "$_lao_src" "$_lao_family"
}

copy_as_flyme() {
    _laf_src="$1"
    _laf_family="${4:-}"
    [ -n "$_laf_family" ] || _laf_family=$(detect_font_family "$(basename "$_laf_src")")
    _laf_regular=$(_luoshu_oem_pick_regular_source "$_laf_family" "$_laf_src") || return 1
    _luoshu_oem_copy_existing_slots flyme "$_laf_src" "$_laf_family"
    _laf_slots=$?
    _luoshu_flyme_prepare_data_apply "$_laf_regular"
    _laf_data=$?
    [ "$_laf_slots" -eq 0 ] || [ "$_laf_data" -eq 0 ]
}

# Keep OEM file-slot mappings when XML generation merely falls back. Explicit reset/default still
# clears the OEM manifest and schedules Flyme's persistent theme slot for restoration.
font_config_disable() {
    if [ "${LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE:-0}" != 1 ]; then
        luoshu_oem_clear_managed_fonts
        _luoshu_detect_flyme >/dev/null 2>&1 && _luoshu_flyme_prepare_data_restore >/dev/null 2>&1 || true
    fi
    type luoshu_dynamic_targets_clear >/dev/null 2>&1 && luoshu_dynamic_targets_clear
    type _luoshu_font_config_disable_base >/dev/null 2>&1 && _luoshu_font_config_disable_base
}

# The Flyme /data slot is applied only after payload validation and boot-state arming. If any earlier
# step fails, the normal transaction abort removes the pending file and leaves /data untouched.
luoshu_payload_transaction_abort() {
    luoshu_flyme_pending_clear
    _lpta_had=0
    if [ -n "${LUOSHU_PAYLOAD_TXN:-}" ]; then
        _lpta_had=1
        luoshu_payload_transaction_rollback
    fi
    if [ "$_lpta_had" -eq 1 ] && type luoshu_sync_mount_payload >/dev/null 2>&1; then
        luoshu_sync_mount_payload >/dev/null 2>&1 ||
            type _luoshu_safety_log >/dev/null 2>&1 && _luoshu_safety_log ERROR '本地旧字体已恢复，但元模块旧负载回写失败；开机守卫将撤销覆盖'
    fi
}

luoshu_payload_transaction_commit() {
    _lptc_active="$1"
    [ -n "${LUOSHU_PAYLOAD_TXN:-}" ] && [ -d "$LUOSHU_PAYLOAD_TXN" ] || return 1
    if [ "$_lptc_active" != default ]; then
        luoshu_payload_validate_current "$_lptc_active" || return 1
    fi
    luoshu_payload_arm "$_lptc_active" || return 1
    luoshu_flyme_pending_apply || return 1
    rm -rf "$LUOSHU_PAYLOAD_TXN" 2>/dev/null || true
    LUOSHU_PAYLOAD_TXN=''
    return 0
}

# Boot failure must restore Flyme's persistent theme slot as well as systemless partition payloads.
luoshu_payload_quarantine() {
    _lpq_module="$(_luoshu_safety_module)"
    _lpq_config="$(_luoshu_safety_config)"
    _lpq_fail=$(cat "$_lpq_config/font-boot-failures" 2>/dev/null)
    case "$_lpq_fail" in ''|*[!0-9]*) _lpq_fail=0 ;; esac
    _lpq_fail=$((_lpq_fail + 1))
    printf '%s\n' "$_lpq_fail" > "$_lpq_config/font-boot-failures" 2>/dev/null || true

    luoshu_oem_clear_managed_fonts
    if _luoshu_detect_flyme >/dev/null 2>&1; then
        _luoshu_flyme_prepare_data_restore >/dev/null 2>&1 || true
        luoshu_flyme_pending_apply >/dev/null 2>&1 || true
    fi
    for _lpq_part in $(_luoshu_payload_parts); do
        rm -rf "$_lpq_module/$_lpq_part/fonts" 2>/dev/null || true
        _lpq_etc="$_lpq_module/$_lpq_part/etc"
        [ -d "$_lpq_etc" ] || continue
        for _lpq_xml in "$_lpq_etc"/*.xml; do
            [ -f "$_lpq_xml" ] || continue
            grep -q 'LuoShu-' "$_lpq_xml" 2>/dev/null && rm -f "$_lpq_xml" 2>/dev/null || true
        done
    done
    if type luoshu_meta_content_roots >/dev/null 2>&1; then
        for _lpq_root in $(luoshu_meta_content_roots); do
            [ -d "$_lpq_root" ] || continue
            for _lpq_part in $(_luoshu_payload_parts); do
                rm -rf "$_lpq_root/$_lpq_part/fonts" 2>/dev/null || true
                _lpq_etc="$_lpq_root/$_lpq_part/etc"
                [ -d "$_lpq_etc" ] || continue
                for _lpq_xml in "$_lpq_etc"/*.xml; do
                    [ -f "$_lpq_xml" ] || continue
                    grep -q 'LuoShu-' "$_lpq_xml" 2>/dev/null && rm -f "$_lpq_xml" 2>/dev/null || true
                done
            done
        done
    fi
    printf 'default\n' > "$_lpq_config/active_font.conf" 2>/dev/null || true
    rm -f "$_lpq_config/font-payload-boot.conf" "$_lpq_config/font-payload-manifest.conf" \
          "$_lpq_config/font-target-aliases.conf" "$_lpq_config/font-target-coverage.conf" \
          "$_lpq_config/font-config-overlay.conf" "$_lpq_config/oem-font-targets.conf" 2>/dev/null || true
    [ "$_lpq_fail" -lt 2 ] || touch "$_lpq_module/disable" 2>/dev/null || true
    type _luoshu_safety_log >/dev/null 2>&1 && _luoshu_safety_log ERROR "检测到上次字体负载未完成开机，已撤销全部字体覆盖（failure=$_lpq_fail）"
}

# Final dispatcher. OriginOS/Flyme detection is self-contained, so existing callers do not need to
# know new global flags. XML rewriting remains the second layer after exact physical file-slot mapping.
apply_font_by_rom() {
    _lafr_src="$1"
    _lafr_dest="$2"
    _lafr_mode="${3:-full}"
    _lafr_family="${4:-}"
    [ -n "$_lafr_family" ] || _lafr_family=$(detect_font_family "$(basename "$_lafr_src")")

    if [ "${IS_HYPEROS:-false}" = true ]; then
        copy_as_hyperos "$_lafr_src" "$_lafr_dest" "$_lafr_mode" "$_lafr_family"
        return $?
    elif [ "${IS_COLOROS:-false}" = true ]; then
        copy_as_coloros "$_lafr_src" "$_lafr_dest" "$_lafr_mode" "$_lafr_family" || return $?
    elif _luoshu_detect_originos; then
        copy_as_originos "$_lafr_src" "$_lafr_dest" "$_lafr_mode" "$_lafr_family" || return $?
    elif _luoshu_detect_flyme; then
        copy_as_flyme "$_lafr_src" "$_lafr_dest" "$_lafr_mode" "$_lafr_family" || return $?
    else
        copy_as_generic "$_lafr_src" "$_lafr_dest" "$_lafr_mode" || return $?
    fi

    if type font_config_enable_for_payload >/dev/null 2>&1; then
        LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE=1
        export LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE
        if font_config_enable_for_payload "$_lafr_family"; then
            type _log_step >/dev/null 2>&1 && _log_step '  系统与 OEM 字体 XML 已事务生成（无 Hook）'
        else
            type _log_step >/dev/null 2>&1 && _log_step '  设备没有可安全启用的字体 XML，继续使用真机文件槽映射'
        fi
        LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE=0
        export LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE
    fi
    return 0
}
