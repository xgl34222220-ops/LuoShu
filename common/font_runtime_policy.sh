#!/system/bin/sh
# LuoShu final font runtime policy.
#
# The private payload is the canonical writable tree. The public module partition
# directories are only compatibility views and must never be treated as the source
# of truth because Root implementations may place App shells in another mount
# namespace. This layer also merges the device inventory with ROM critical slots
# and preserves stock fallbacks for scripts the selected font does not contain.
set +e

_lfrp_module() {
    printf '%s\n' "${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
}

_lfrp_payload_root() {
    _lfrp_m="$(_lfrp_module)"
    if [ -d "$_lfrp_m/.luoshu-payload" ]; then
        printf '%s/.luoshu-payload\n' "${_lfrp_m%/}"
    else
        printf '%s\n' "${_lfrp_m%/}"
    fi
}

_lfrp_config_root() {
    printf '%s/config\n' "$(_lfrp_module)"
}

_lfrp_partitions() {
    if type luoshu_private_partitions >/dev/null 2>&1; then
        luoshu_private_partitions
    elif type luoshu_payload_partitions >/dev/null 2>&1; then
        luoshu_payload_partitions
    else
        printf '%s\n' 'system system_ext product vendor odm oem my_product my_engineering my_company my_preload my_region my_stock oplus_product oplus_engineering oplus_version oplus_region mi_ext cust hw_product'
    fi
}

_lfrp_private_helper="$(_lfrp_module)/common/private_payload.sh"
[ -f "$_lfrp_private_helper" ] && . "$_lfrp_private_helper"
unset _lfrp_private_helper

# Re-declare the module-view helper with strict accounting. The old helper returned
# success even when every bind failed, which let switch/boot validation operate on
# empty placeholder directories and later reset the active font to default.
if type _luoshu_private_root >/dev/null 2>&1; then
    luoshu_private_mount_module_view() {
        _lpp_module="${1:-$(_lfrp_module)}"
        _lpp_root=$(_luoshu_private_root "$_lpp_module")
        _lpp_state=$(_luoshu_private_state_root)
        _lpp_list="$_lpp_state/module-view.mounts"
        [ -d "$_lpp_root" ] || return 2
        mkdir -p "$_lpp_state" 2>/dev/null || return 1
        : > "$_lpp_list" 2>/dev/null || return 1
        _lpp_seen=0
        _lpp_failed=0

        for _lpp_part in $(luoshu_private_partitions); do
            _lpp_source="$_lpp_root/$_lpp_part"
            _lpp_target="$_lpp_module/$_lpp_part"
            [ -d "$_lpp_source" ] || continue
            _lpp_seen=$((_lpp_seen + 1))
            mkdir -p "$_lpp_target" 2>/dev/null || {
                _lpp_failed=$((_lpp_failed + 1))
                continue
            }
            if _luoshu_private_is_mountpoint "$_lpp_target"; then
                printf '%s\n' "$_lpp_target" >> "$_lpp_list" 2>/dev/null || true
                continue
            fi
            if _luoshu_private_mount_cmd -o bind "$_lpp_source" "$_lpp_target" >/dev/null 2>&1; then
                printf '%s\n' "$_lpp_target" >> "$_lpp_list" 2>/dev/null || true
            else
                _lpp_failed=$((_lpp_failed + 1))
            fi
        done
        [ "$_lpp_seen" -gt 0 ] && [ "$_lpp_failed" -eq 0 ]
    }
fi

LUOSHU_PRIVATE_VIEW_READY=false
if [ -d "$(_lfrp_module)/.luoshu-payload" ] && type luoshu_private_mount_module_view >/dev/null 2>&1; then
    if luoshu_private_mount_module_view "$(_lfrp_module)" >/dev/null 2>&1; then
        LUOSHU_PRIVATE_VIEW_READY=true
    fi
fi
export LUOSHU_PRIVATE_VIEW_READY

# font_manager.sh defines this before loading mount_compat.sh. Point it at the
# canonical payload so a namespace-local bind failure cannot send writes into the
# empty public placeholder tree.
if [ -n "${SYSTEM_FONTS_DIR:-}" ] && [ -d "$(_lfrp_payload_root)/system" ]; then
    SYSTEM_FONTS_DIR="$(_lfrp_payload_root)/system/fonts"
    mkdir -p "$SYSTEM_FONTS_DIR" 2>/dev/null || true
fi

_lfrp_json_number() {
    _lfrp_json="$1"
    _lfrp_key="$2"
    printf '%s' "$_lfrp_json" | sed -n "s/.*\"${_lfrp_key}\":\([0-9][0-9]*\).*/\1/p" | head -n1
}

# Structural validity and script coverage are separate questions. A Latin-only
# font is valid, but it must never replace a CJK slot. Accept usable partial fonts,
# record their capabilities, and let the mapper keep stock fallbacks for the rest.
font_validate_global() {
    _lfrp_font="$1"
    type font_validate >/dev/null 2>&1 || {
        FONT_CHECK_ERROR='字体验证器不可用'
        return 127
    }
    font_validate "$_lfrp_font" text || return 1

    _lfrp_m="$(_lfrp_module)"
    _lfrp_python="$_lfrp_m/common/python/bin/luoshu-python"
    _lfrp_checker="$_lfrp_m/common/font_coverage.py"
    [ -x "$_lfrp_python" ] && [ -f "$_lfrp_checker" ] || {
        FONT_CHECK_ERROR='字形覆盖分析器不可用'
        return 1
    }
    _lfrp_pyroot="$_lfrp_m/common/python"
    _lfrp_result=$(PYTHONHOME="$_lfrp_pyroot" \
        PYTHONPATH="$_lfrp_pyroot/lib/python3.14:$_lfrp_pyroot/lib/python3.14/site-packages" \
        LD_LIBRARY_PATH="$_lfrp_pyroot/lib:$_lfrp_pyroot/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$_lfrp_python" "$_lfrp_checker" "$_lfrp_font" 2>/dev/null)
    [ -n "$_lfrp_result" ] || {
        FONT_CHECK_ERROR='字形覆盖分析失败'
        return 1
    }

    _lfrp_han=$(_lfrp_json_number "$_lfrp_result" coreHan)
    _lfrp_cjk=$(_lfrp_json_number "$_lfrp_result" cjk)
    _lfrp_latin=$(_lfrp_json_number "$_lfrp_result" latin)
    _lfrp_digits=$(_lfrp_json_number "$_lfrp_result" digits)
    _lfrp_punct=$(_lfrp_json_number "$_lfrp_result" punctuation)
    case "$_lfrp_han" in ''|*[!0-9]*) _lfrp_han=0 ;; esac
    case "$_lfrp_cjk" in ''|*[!0-9]*) _lfrp_cjk=0 ;; esac
    case "$_lfrp_latin" in ''|*[!0-9]*) _lfrp_latin=0 ;; esac
    case "$_lfrp_digits" in ''|*[!0-9]*) _lfrp_digits=0 ;; esac
    case "$_lfrp_punct" in ''|*[!0-9]*) _lfrp_punct=0 ;; esac

    LUOSHU_FONT_HAS_CJK=false
    LUOSHU_FONT_HAS_LATIN=false
    LUOSHU_FONT_HAS_MIXED=false
    [ "$_lfrp_han" -ge 6000 ] && [ "$_lfrp_cjk" -ge 95 ] && LUOSHU_FONT_HAS_CJK=true
    # HyperOS splits CJK, Latin and numeric UI glyphs across independent physical slots.
    # Punctuation coverage varies wildly between otherwise complete CJK fonts, so using it as a
    # hard gate left Roboto/MiSansLatin/100-900 on the stock font even though A-Z/a-z/0-9 were
    # present. Keep punctuation in the diagnostic, but let usable letters + all digits drive the
    # Latin slot decision.
    [ "$_lfrp_latin" -ge 90 ] && [ "$_lfrp_digits" -eq 100 ] && LUOSHU_FONT_HAS_LATIN=true
    [ "$LUOSHU_FONT_HAS_CJK" = true ] && [ "$LUOSHU_FONT_HAS_LATIN" = true ] && \
        LUOSHU_FONT_HAS_MIXED=true
    export LUOSHU_FONT_HAS_CJK LUOSHU_FONT_HAS_LATIN LUOSHU_FONT_HAS_MIXED

    FONT_CHECK_COVERAGE="核心汉字 ${_lfrp_han} 个、中文 ${_lfrp_cjk}%、英文 ${_lfrp_latin}%、数字 ${_lfrp_digits}%、标点 ${_lfrp_punct}%"
    case "$LUOSHU_FONT_HAS_CJK:$LUOSHU_FONT_HAS_LATIN" in
        true:true)
            FONT_CHECK_WARNING="${FONT_CHECK_WARNING:+$FONT_CHECK_WARNING；}字形覆盖完整"
            [ "$_lfrp_punct" -ge 75 ] || \
                FONT_CHECK_WARNING="${FONT_CHECK_WARNING}；部分标点将由系统回退字体补齐"
            ;;
        true:false)
            FONT_CHECK_WARNING="${FONT_CHECK_WARNING:+$FONT_CHECK_WARNING；}字体缺少完整英文或数字，洛书将只替换中文槽位并保留系统英文"
            ;;
        false:true)
            FONT_CHECK_WARNING="${FONT_CHECK_WARNING:+$FONT_CHECK_WARNING；}字体缺少完整中文，洛书将只替换英文数字槽位并保留系统中文"
            ;;
        *)
            FONT_CHECK_ERROR="$FONT_CHECK_COVERAGE；字体既不具备可用中文覆盖，也不具备完整英文数字覆盖"
            return 1
            ;;
    esac
    FONT_CHECK_ERROR=''
    return 0
}

# Capability-aware cache entries restore the exact CJK/Latin slot policy. The first validation of
# a changed font still performs the complete coverage analysis; later switches reuse it by file
# identity without opening the font in Python again.
luoshu_font_validate_global_cached() {
    _lfrp_font="$1"
    LUOSHU_FONT_VALIDATION_CACHE_HIT=false
    export LUOSHU_FONT_VALIDATION_CACHE_HIT
    if type luoshu_font_validation_is_preflight >/dev/null 2>&1 && \
       luoshu_font_validation_is_preflight && \
       type luoshu_font_validation_fast_preflight >/dev/null 2>&1; then
        luoshu_font_validation_fast_preflight "$_lfrp_font"
        return $?
    fi
    if type luoshu_font_validation_cache_restore >/dev/null 2>&1 && \
       luoshu_font_validation_cache_restore "$_lfrp_font"; then
        return 0
    fi
    font_validate_global "$_lfrp_font" || return $?
    type luoshu_font_validation_cache_store >/dev/null 2>&1 && \
        luoshu_font_validation_cache_store "$_lfrp_font" >/dev/null 2>&1 || true
    return 0
}

_lfrp_target_kind() {
    _lfrp_name=$(printf '%s' "${1##*/}" | tr '[:upper:]' '[:lower:]')
    case "$_lfrp_name" in
        [1-9]00.ttf|350.ttf|*mitype*|*miclock*|*misansclock*|androidclock*|clockopia*)
            # Xiaomi hard-codes these UI/clock/number files outside the normal Android family
            # graph. They are Latin/digit presentation slots even when their filename contains
            # "Mono"; protecting them was the reason many HyperOS pages kept stock digits.
            printf 'latin\n'
            ;;
        *emoji*|*symbol*|*icon*|*math*|*music*|*serif*|*mono*|\
        *myanmar*|*arabic*|*thai*|*tibetan*|*devanagari*|*khmer*|*lao*|\
        *hebrew*|*korean*|*japanese*)
            printf 'protected\n'
            ;;
        *hans*|*hant*|*cjk*|*misanstcvf*|*misansl3*|*notosanssc*|*notosanstc*)
            printf 'cjk\n'
            ;;
        *latin*|*sys*sans-en*|*oppo*sans-en*|*opposans-en*|*opsans-en*|\
        roboto*|google*sans*|sourcesans*|din*|oppodin*)
            printf 'latin\n'
            ;;
        *)
            printf 'mixed\n'
            ;;
    esac
}

_lfrp_target_allowed() {
    _lfrp_kind=$(_lfrp_target_kind "$1")
    _lfrp_has_cjk="${LUOSHU_FONT_HAS_CJK:-true}"
    _lfrp_has_latin="${LUOSHU_FONT_HAS_LATIN:-true}"
    _lfrp_has_mixed="${LUOSHU_FONT_HAS_MIXED:-true}"
    case "$_lfrp_kind" in
        protected) return 1 ;;
        cjk) [ "$_lfrp_has_cjk" = true ] ;;
        latin) [ "$_lfrp_has_latin" = true ] ;;
        *) [ "$_lfrp_has_mixed" = true ] ;;
    esac
}

_lfrp_visible_font_dirs() {
    _lfrp_part="$1"
    case "$_lfrp_part" in
        system)
            [ -d /system/fonts ] && printf '/system/fonts\n'
            ;;
        *)
            [ -d "/$_lfrp_part/fonts" ] && printf '/%s/fonts\n' "$_lfrp_part"
            [ -d "/system/$_lfrp_part/fonts" ] && printf '/system/%s/fonts\n' "$_lfrp_part"
            ;;
    esac
}

_lfrp_payload_font_dir() {
    printf '%s/%s/fonts\n' "$(_lfrp_payload_root)" "$1"
}

_device_font_inventory_target() {
    _lfrp_logical="$1"
    for _lfrp_part in $(_lfrp_partitions); do
        _lfrp_prefix="/${_lfrp_part}/fonts/"
        case "$_lfrp_logical" in
            "$_lfrp_prefix"*)
                printf '%s/%s/fonts/%s\n' "$(_lfrp_payload_root)" "$_lfrp_part" "${_lfrp_logical#$_lfrp_prefix}"
                return 0
                ;;
        esac
    done
    return 1
}

_lfrp_target_manifest() {
    printf '%s/font-runtime-targets.conf\n' "$(_lfrp_config_root)"
}

_lfrp_record_target() {
    _lfrp_target="$1"
    _lfrp_root="$(_lfrp_payload_root)/"
    case "$_lfrp_target" in "$_lfrp_root"*) ;; *) return 1 ;; esac
    _lfrp_rel=${_lfrp_target#$_lfrp_root}
    _lfrp_manifest=$(_lfrp_target_manifest)
    mkdir -p "${_lfrp_manifest%/*}" 2>/dev/null || return 1
    grep -Fxq "$_lfrp_rel" "$_lfrp_manifest" 2>/dev/null || printf '%s\n' "$_lfrp_rel" >> "$_lfrp_manifest"
}

_lfrp_alias_existing_targets() {
    _lfrp_anchor="$1"
    _lfrp_file="$2"
    _lfrp_count=0
    _lfrp_target_allowed "$_lfrp_file" || {
        printf '0\n'
        return 0
    }
    for _lfrp_part in $(_lfrp_partitions); do
        _lfrp_found=0
        for _lfrp_visible in $(_lfrp_visible_font_dirs "$_lfrp_part"); do
            [ -e "$_lfrp_visible/$_lfrp_file" ] || continue
            _lfrp_found=1
            break
        done
        [ "$_lfrp_found" -eq 1 ] || continue
        _lfrp_dest=$(_lfrp_payload_font_dir "$_lfrp_part")/$_lfrp_file
        mkdir -p "${_lfrp_dest%/*}" 2>/dev/null || continue
        if _font_alias "$_lfrp_anchor" "$_lfrp_dest" && _verify_font_copy "$_lfrp_dest"; then
            _lfrp_record_target "$_lfrp_dest" >/dev/null 2>&1 || true
            _lfrp_count=$((_lfrp_count + 1))
        fi
    done
    printf '%s\n' "$_lfrp_count"
}

# Clear the complete generated font tree, not just a static filename list. The
# private tree contains only LuoShu overlays, so removing it reveals every stock
# fallback and prevents an old full-font switch from leaking tofu-producing aliases
# into a later partial-font switch.
clear_managed_text_fonts() {
    _lfrp_root=$(_lfrp_payload_root)
    for _lfrp_part in $(_lfrp_partitions); do
        rm -rf "$_lfrp_root/$_lfrp_part/fonts" 2>/dev/null || true
    done
    mkdir -p "$_lfrp_root/system/fonts" 2>/dev/null || true
    rm -f "$(_lfrp_target_manifest)" 2>/dev/null || true
    type font_config_disable >/dev/null 2>&1 && font_config_disable
}

_copy_as_inventory() {
    _lfrp_src="$1"
    _lfrp_mode="${3:-full}"
    _lfrp_family="${4:-}"
    _lfrp_entries=$(_device_font_inventory_entries) || {
        LUOSHU_INVENTORY_MAPPED_COUNT=0
        return 2
    }
    [ -n "$_lfrp_entries" ] || {
        LUOSHU_INVENTORY_MAPPED_COUNT=0
        return 2
    }
    _lfrp_system_fonts=$(_lfrp_payload_font_dir system)
    mkdir -p "$_lfrp_system_fonts" 2>/dev/null || return 1
    [ -d "$_lfrp_system_fonts/.luoshu-font-store" ] || _font_store_reset "$_lfrp_system_fonts"
    _lfrp_regular=$(_font_anchor "$_lfrp_src" "$_lfrp_system_fonts" regular) || return 1
    _lfrp_count=0
    _lfrp_bad=0
    _lfrp_tab=$(printf '\t')
    while IFS="$_lfrp_tab" read -r _lfrp_logical _lfrp_name _lfrp_partition _lfrp_format _lfrp_weight _lfrp_style _lfrp_source; do
        [ -n "$_lfrp_logical" ] && [ -n "$_lfrp_name" ] || continue
        _lfrp_target_allowed "$_lfrp_name" || continue
        _lfrp_target=$(_device_font_inventory_target "$_lfrp_logical") || continue
        mkdir -p "${_lfrp_target%/*}" 2>/dev/null || continue
        _lfrp_anchor="$_lfrp_regular"
        if [ "$_lfrp_mode" != quick ] && [ "$_lfrp_weight" != 400 ] && \
           type _device_font_inventory_anchor >/dev/null 2>&1; then
            _lfrp_anchor=$(_device_font_inventory_anchor "$_lfrp_src" "$_lfrp_system_fonts" \
                "$_lfrp_family" "$_lfrp_mode" "$_lfrp_weight") || _lfrp_anchor="$_lfrp_regular"
        fi
        if _font_alias "$_lfrp_anchor" "$_lfrp_target" && _verify_font_copy "$_lfrp_target"; then
            _lfrp_record_target "$_lfrp_target" >/dev/null 2>&1 || true
            _lfrp_count=$((_lfrp_count + 1))
        else
            _lfrp_bad=$((_lfrp_bad + 1))
        fi
    done <<EOF_LUOSHU_RUNTIME_INVENTORY
$_lfrp_entries
EOF_LUOSHU_RUNTIME_INVENTORY
    LUOSHU_INVENTORY_MAPPED_COUNT="$_lfrp_count"
    export LUOSHU_INVENTORY_MAPPED_COUNT
    [ "$_lfrp_count" -gt 0 ] || return 2
    _log_step "  已按设备原厂清单覆盖 $_lfrp_count 个真实槽位"
    [ "$_lfrp_bad" -eq 0 ] || _log_step "  ⚠ $_lfrp_bad 个原厂槽位写入失败"
    return 0
}

_lfrp_static_files() {
    if [ "${IS_HYPEROS:-false}" = true ]; then
        get_all_hyperos_files
    elif [ "${IS_COLOROS:-false}" = true ]; then
        for _lfrp_name in $(get_all_coloros_names); do printf '%s.ttf\n' "$_lfrp_name"; done
    else
        get_all_generic_files
    fi
}

# Inventory and static OEM anchors are complementary. The old early return meant a
# partial XML inventory could suppress HyperOS' hidden MiSansVF or ColorOS' OEM
# partition files, producing a successful switch that rebooted into the stock font.
apply_font_by_rom() {
    _lfrp_src="$1"
    _lfrp_mode="${3:-full}"
    _lfrp_family="${4:-}"
    _lfrp_system_fonts=$(_lfrp_payload_font_dir system)
    mkdir -p "$_lfrp_system_fonts" 2>/dev/null || return 1
    _font_store_reset "$_lfrp_system_fonts"
    _lfrp_regular=$(_font_anchor "$_lfrp_src" "$_lfrp_system_fonts" regular) || return 1

    LUOSHU_INVENTORY_MAPPED_COUNT=0
    _copy_as_inventory "$_lfrp_src" "$_lfrp_system_fonts" "$_lfrp_mode" "$_lfrp_family" >/dev/null 2>&1 || true
    _lfrp_inventory=${LUOSHU_INVENTORY_MAPPED_COUNT:-0}
    case "$_lfrp_inventory" in ''|*[!0-9]*) _lfrp_inventory=0 ;; esac

    _lfrp_static=0
    for _lfrp_file in $(_lfrp_static_files); do
        _lfrp_added=$(_lfrp_alias_existing_targets "$_lfrp_regular" "$_lfrp_file")
        case "$_lfrp_added" in ''|*[!0-9]*) _lfrp_added=0 ;; esac
        _lfrp_static=$((_lfrp_static + _lfrp_added))
    done
    _lfrp_total=$((_lfrp_inventory + _lfrp_static))
    [ "$_lfrp_total" -gt 0 ] || {
        _log_step '  没有找到与当前 ROM 对应的真实字体槽位，已拒绝伪成功'
        return 1
    }
    LUOSHU_MAPPED_TARGET_COUNT="$_lfrp_total"
    export LUOSHU_MAPPED_TARGET_COUNT
    _log_step "  字体槽位已合并映射：原厂清单 $_lfrp_inventory / ROM 关键槽位 $_lfrp_static"
    case "${LUOSHU_FONT_HAS_CJK:-true}:${LUOSHU_FONT_HAS_LATIN:-true}" in
        false:true) _log_step '  当前字体缺少完整中文：中文继续使用系统字体，避免方框' ;;
        true:false) _log_step '  当前字体缺少完整英文数字：英文数字继续使用系统字体' ;;
    esac
    return 0
}

# Every payload reader/writer below resolves partition files against the canonical
# private tree. Configuration and transaction state stay under module/config.
luoshu_used_partitions() {
    _lfrp_root="${1:-$(_lfrp_payload_root)}"
    for _lfrp_part in $(_lfrp_partitions); do
        [ -d "$_lfrp_root/$_lfrp_part" ] || continue
        find "$_lfrp_root/$_lfrp_part" -type f -print -quit 2>/dev/null | grep -q . && printf '%s\n' "$_lfrp_part"
    done
}

luoshu_payload_validate_current() {
    _lfrp_active="${1:-unknown}"
    [ "$_lfrp_active" != default ] || {
        LUOSHU_PAYLOAD_VALIDATED_ACTIVE=default
        return 0
    }
    _lfrp_root=$(_lfrp_payload_root)
    _lfrp_fonts=0
    for _lfrp_part in $(_lfrp_partitions); do
        _lfrp_dir="$_lfrp_root/$_lfrp_part/fonts"
        [ -d "$_lfrp_dir" ] || continue
        for _lfrp_file in "$_lfrp_dir"/*.ttf "$_lfrp_dir"/*.otf "$_lfrp_dir"/*.ttc "$_lfrp_dir"/*.font; do
            [ -f "$_lfrp_file" ] || continue
            _lfrp_size=$(_luoshu_filesize "$_lfrp_file")
            case "$_lfrp_size" in ''|*[!0-9]*) return 1 ;; esac
            [ "$_lfrp_size" -ge 1024 ] || return 1
            _lfrp_fonts=$((_lfrp_fonts + 1))
        done
    done
    [ "$_lfrp_fonts" -gt 0 ] || return 1
    LUOSHU_PAYLOAD_VALIDATED_ACTIVE="$_lfrp_active"
    return 0
}

luoshu_payload_build_manifest() {
    _lfrp_root=$(_lfrp_payload_root)
    _lfrp_config=$(_lfrp_config_root)
    _lfrp_tmp="$_lfrp_config/font-payload-manifest.conf.tmp.$$"
    _lfrp_checksum_cache="$_lfrp_config/.font-payload-checksums.$$"
    mkdir -p "$_lfrp_config" 2>/dev/null || return 1
    : > "$_lfrp_tmp" 2>/dev/null || return 1
    : > "$_lfrp_checksum_cache" 2>/dev/null || { rm -f "$_lfrp_tmp" 2>/dev/null; return 1; }
    for _lfrp_part in $(_lfrp_partitions); do
        _lfrp_fonts="$_lfrp_root/$_lfrp_part/fonts"
        if [ -d "$_lfrp_fonts" ]; then
            find "$_lfrp_fonts" -type f 2>/dev/null | while IFS= read -r _lfrp_file; do
                case "$_lfrp_file" in *.ttf|*.otf|*.ttc|*.font|*.TTF|*.OTF|*.TTC) ;; *) continue ;; esac
                _lfrp_rel=${_lfrp_file#$_lfrp_root/}
                if type _luoshu_cached_checksum >/dev/null 2>&1; then
                    _lfrp_sum=$(_luoshu_cached_checksum "$_lfrp_file" "$_lfrp_checksum_cache")
                else
                    _lfrp_sum=$(_luoshu_checksum "$_lfrp_file")
                fi
                [ -n "$_lfrp_sum" ] && printf '%s|%s\n' "$_lfrp_rel" "$_lfrp_sum"
            done >> "$_lfrp_tmp"
        fi
        _lfrp_etc="$_lfrp_root/$_lfrp_part/etc"
        if [ -d "$_lfrp_etc" ]; then
            find "$_lfrp_etc" -maxdepth 1 -type f -name '*.xml' 2>/dev/null | while IFS= read -r _lfrp_file; do
                case "${_lfrp_file##*/}" in
                    .luoshu-data-fonts-config.xml) ;;
                    *) grep -Eq 'LuoShu(Mono)?-|LuoShuSlot-' "$_lfrp_file" 2>/dev/null || continue ;;
                esac
                _lfrp_rel=${_lfrp_file#$_lfrp_root/}
                if type _luoshu_cached_checksum >/dev/null 2>&1; then
                    _lfrp_sum=$(_luoshu_cached_checksum "$_lfrp_file" "$_lfrp_checksum_cache")
                else
                    _lfrp_sum=$(_luoshu_checksum "$_lfrp_file")
                fi
                [ -n "$_lfrp_sum" ] && printf '%s|%s\n' "$_lfrp_rel" "$_lfrp_sum"
            done >> "$_lfrp_tmp"
        fi
    done
    rm -f "$_lfrp_checksum_cache" 2>/dev/null || true
    [ -s "$_lfrp_tmp" ] || {
        rm -f "$_lfrp_tmp" 2>/dev/null || true
        return 1
    }
    mv -f "$_lfrp_tmp" "$_lfrp_config/font-payload-manifest.conf" 2>/dev/null || return 1
    chmod 0644 "$_lfrp_config/font-payload-manifest.conf" 2>/dev/null || true
}

luoshu_payload_validate_manifest_full() {
    _lfrp_root=$(_lfrp_payload_root)
    _lfrp_manifest="$(_lfrp_config_root)/font-payload-manifest.conf"
    [ -s "$_lfrp_manifest" ] || return 1
    _lfrp_seen=0
    while IFS='|' read -r _lfrp_rel _lfrp_sum _lfrp_size; do
        case "$_lfrp_rel" in */fonts/*|*/etc/*.xml) ;; *) return 1 ;; esac
        _lfrp_file="$_lfrp_root/$_lfrp_rel"
        [ -f "$_lfrp_file" ] || return 1
        _lfrp_now=$(_luoshu_checksum "$_lfrp_file")
        [ "$_lfrp_now" = "$_lfrp_sum|$_lfrp_size" ] || return 1
        _lfrp_seen=$((_lfrp_seen + 1))
    done < "$_lfrp_manifest"
    [ "$_lfrp_seen" -gt 0 ]
}

luoshu_payload_validate_manifest_fast() {
    _lfrp_root=$(_lfrp_payload_root)
    _lfrp_manifest="$(_lfrp_config_root)/font-payload-manifest.conf"
    [ -s "$_lfrp_manifest" ] || return 1
    _lfrp_seen=0
    while IFS='|' read -r _lfrp_rel _lfrp_sum _lfrp_size; do
        case "$_lfrp_size" in ''|*[!0-9]*) return 1 ;; esac
        _lfrp_file="$_lfrp_root/$_lfrp_rel"
        [ -f "$_lfrp_file" ] || return 1
        case "$_lfrp_rel" in
            */fonts/*)
                _lfrp_now=$(_luoshu_filesize "$_lfrp_file")
                case "$_lfrp_now" in ''|*[!0-9]*) return 1 ;; esac
                [ "$_lfrp_now" -ge 1024 ] && [ "$_lfrp_now" = "$_lfrp_size" ] || return 1
                ;;
            */etc/*.xml)
                _lfrp_now=$(_luoshu_checksum "$_lfrp_file")
                [ "$_lfrp_now" = "$_lfrp_sum|$_lfrp_size" ] || return 1
                ;;
            *) return 1 ;;
        esac
        _lfrp_seen=$((_lfrp_seen + 1))
    done < "$_lfrp_manifest"
    [ "$_lfrp_seen" -gt 0 ]
}

LUOSHU_PAYLOAD_TXN=''
luoshu_payload_transaction_begin() {
    [ -z "$LUOSHU_PAYLOAD_TXN" ] || return 1
    LUOSHU_PAYLOAD_VALIDATED_ACTIVE=''
    _lfrp_root=$(_lfrp_payload_root)
    _lfrp_config=$(_lfrp_config_root)
    LUOSHU_PAYLOAD_TXN="$_lfrp_config/.payload-transaction.$$"
    rm -rf "$LUOSHU_PAYLOAD_TXN" 2>/dev/null || true
    mkdir -p "$LUOSHU_PAYLOAD_TXN/payload" "$LUOSHU_PAYLOAD_TXN/config" 2>/dev/null || {
        LUOSHU_PAYLOAD_TXN=''
        return 1
    }
    : > "$LUOSHU_PAYLOAD_TXN/paths" 2>/dev/null || return 1
    for _lfrp_part in $(_lfrp_partitions); do
        for _lfrp_sub in fonts etc; do
            _lfrp_rel="$_lfrp_part/$_lfrp_sub"
            _lfrp_src="$_lfrp_root/$_lfrp_rel"
            if [ -d "$_lfrp_src" ]; then
                mkdir -p "$LUOSHU_PAYLOAD_TXN/payload/$_lfrp_part" 2>/dev/null || return 1
                cp -al "$_lfrp_src" "$LUOSHU_PAYLOAD_TXN/payload/$_lfrp_rel" 2>/dev/null || \
                cp -af "$_lfrp_src" "$LUOSHU_PAYLOAD_TXN/payload/$_lfrp_rel" 2>/dev/null || return 1
                printf 'payload|present|%s\n' "$_lfrp_rel" >> "$LUOSHU_PAYLOAD_TXN/paths"
            else
                printf 'payload|absent|%s\n' "$_lfrp_rel" >> "$LUOSHU_PAYLOAD_TXN/paths"
            fi
        done
    done
    for _lfrp_name in active_font.conf font_mix.conf font-config-overlay.conf font-target-aliases.conf font-target-coverage.conf font-runtime-targets.conf font-payload-manifest.conf font-payload-boot.conf font-payload-schema.conf text_reboot_required.conf; do
        if [ -f "$_lfrp_config/$_lfrp_name" ]; then
            cp -fp "$_lfrp_config/$_lfrp_name" "$LUOSHU_PAYLOAD_TXN/config/$_lfrp_name" 2>/dev/null || return 1
            printf 'config|present|%s\n' "$_lfrp_name" >> "$LUOSHU_PAYLOAD_TXN/paths"
        else
            printf 'config|absent|%s\n' "$_lfrp_name" >> "$LUOSHU_PAYLOAD_TXN/paths"
        fi
    done
    return 0
}

luoshu_payload_transaction_rollback() {
    [ -n "$LUOSHU_PAYLOAD_TXN" ] && [ -d "$LUOSHU_PAYLOAD_TXN" ] || {
        LUOSHU_PAYLOAD_TXN=''
        return 0
    }
    _lfrp_root=$(_lfrp_payload_root)
    _lfrp_config=$(_lfrp_config_root)
    while IFS='|' read -r _lfrp_kind _lfrp_state _lfrp_rel; do
        case "$_lfrp_kind" in
            payload)
                rm -rf "$_lfrp_root/$_lfrp_rel" 2>/dev/null || true
                if [ "$_lfrp_state" = present ] && [ -d "$LUOSHU_PAYLOAD_TXN/payload/$_lfrp_rel" ]; then
                    mkdir -p "${_lfrp_root}/${_lfrp_rel%/*}" 2>/dev/null || true
                    cp -af "$LUOSHU_PAYLOAD_TXN/payload/$_lfrp_rel" "$_lfrp_root/$_lfrp_rel" 2>/dev/null || true
                fi
                ;;
            config)
                rm -f "$_lfrp_config/$_lfrp_rel" 2>/dev/null || true
                if [ "$_lfrp_state" = present ] && [ -f "$LUOSHU_PAYLOAD_TXN/config/$_lfrp_rel" ]; then
                    cp -fp "$LUOSHU_PAYLOAD_TXN/config/$_lfrp_rel" "$_lfrp_config/$_lfrp_rel" 2>/dev/null || true
                fi
                ;;
        esac
    done < "$LUOSHU_PAYLOAD_TXN/paths"
    rm -rf "$LUOSHU_PAYLOAD_TXN" 2>/dev/null || true
    LUOSHU_PAYLOAD_TXN=''
    type luoshu_private_mount_module_view >/dev/null 2>&1 && \
        luoshu_private_mount_module_view "$(_lfrp_module)" >/dev/null 2>&1 || true
}

luoshu_payload_transaction_abort() {
    _lfrp_had=0
    [ -z "$LUOSHU_PAYLOAD_TXN" ] || _lfrp_had=1
    luoshu_payload_transaction_rollback
    if [ "$_lfrp_had" -eq 1 ] && type luoshu_sync_mount_payload >/dev/null 2>&1; then
        luoshu_sync_mount_payload >/dev/null 2>&1 || true
    fi
}

luoshu_payload_transaction_commit() {
    _lfrp_active="$1"
    [ -n "$LUOSHU_PAYLOAD_TXN" ] && [ -d "$LUOSHU_PAYLOAD_TXN" ] || return 1
    if [ "$_lfrp_active" != default ] && [ "${LUOSHU_PAYLOAD_VALIDATED_ACTIVE:-}" != "$_lfrp_active" ]; then
        luoshu_payload_validate_current "$_lfrp_active" || return 1
    fi
    luoshu_payload_arm "$_lfrp_active" || return 1
    rm -rf "$LUOSHU_PAYLOAD_TXN" 2>/dev/null || true
    LUOSHU_PAYLOAD_TXN=''
    return 0
}

luoshu_payload_quarantine() {
    _lfrp_root=$(_lfrp_payload_root)
    _lfrp_config=$(_lfrp_config_root)
    _lfrp_fail=$(cat "$_lfrp_config/font-boot-failures" 2>/dev/null)
    case "$_lfrp_fail" in ''|*[!0-9]*) _lfrp_fail=0 ;; esac
    _lfrp_fail=$((_lfrp_fail + 1))
    printf '%s\n' "$_lfrp_fail" > "$_lfrp_config/font-boot-failures" 2>/dev/null || true
    for _lfrp_part in $(_lfrp_partitions); do
        rm -rf "$_lfrp_root/$_lfrp_part/fonts" 2>/dev/null || true
        _lfrp_etc="$_lfrp_root/$_lfrp_part/etc"
        [ -d "$_lfrp_etc" ] || continue
        for _lfrp_xml in "$_lfrp_etc"/*.xml; do
            [ -f "$_lfrp_xml" ] || continue
            grep -Eq 'LuoShu(Mono)?-' "$_lfrp_xml" 2>/dev/null && rm -f "$_lfrp_xml" 2>/dev/null || true
        done
    done
    mkdir -p "$_lfrp_root/system/fonts" 2>/dev/null || true
    printf 'default\n' > "$_lfrp_config/active_font.conf" 2>/dev/null || true
    rm -f "$_lfrp_config/font-payload-boot.conf" "$_lfrp_config/font-payload-manifest.conf" \
        "$_lfrp_config/font-payload-schema.conf" "$_lfrp_config/font-payload-rebuild-pending.conf" \
        "$_lfrp_config/font-target-aliases.conf" "$_lfrp_config/font-target-coverage.conf" \
        "$_lfrp_config/font-runtime-targets.conf" "$_lfrp_config/font-config-overlay.conf" 2>/dev/null || true
    {
        printf 'state=quarantined\n'
        printf 'failures=%s\n' "$_lfrp_fail"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_lfrp_config/font-payload-quarantine.conf" 2>/dev/null || true
    _luoshu_safety_log ERROR "字体负载无法通过真实启动校验，已撤销覆盖（failure=$_lfrp_fail）"
}

# Self-mount reads the private tree directly. It no longer depends on a bind view
# created in another mount namespace, which is the main reason only some users
# rebooted into the ROM default font.
luoshu_self_mount_ensure() {
    _lsme_module=$(_luoshu_self_module)
    _lsme_payload=$(_lfrp_payload_root)
    _lsme_active=$(head -n1 "$_lsme_module/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_lsme_active" ] || _lsme_active=default

    rm -f "$_lsme_module/skip_mount" "$_lsme_module/skip_mountify" \
        "$_lsme_module/mount_error" 2>/dev/null || true
    if [ "$_lsme_active" = default ]; then
        _luoshu_self_state_write idle none '' ''
        return 0
    fi
    if _luoshu_system_probe_visible; then
        _luoshu_self_state_write mounted external-mount system ''
        _luoshu_self_log 'Root 管理器已挂载洛书负载，跳过重复自挂载'
        return 0
    fi

    _lsme_mounted=''
    _lsme_failed=''
    _lsme_overlay_count=0
    _lsme_bind_count=0
    _lsme_system_fonts_ok=0
    _lsme_state_root=$(_luoshu_self_state_root)
    _lsme_bind_list="$_lsme_state_root/binds.$$"
    _lsme_mount_list="$_lsme_state_root/mounts.list"
    mkdir -p "$_lsme_state_root" 2>/dev/null || true
    : > "$_lsme_mount_list" 2>/dev/null || true

    for _lsme_partition in $(_lfrp_partitions); do
        _lsme_root=$(_luoshu_partition_root "$_lsme_partition") || continue
        for _lsme_subdir in fonts etc; do
            _lsme_upper="$_lsme_payload/$_lsme_partition/$_lsme_subdir"
            _lsme_target="$_lsme_root/$_lsme_subdir"
            [ -d "$_lsme_upper" ] && find "$_lsme_upper" -type f -print -quit 2>/dev/null | grep -q . || continue
            if _luoshu_overlay_mount_dir "$_lsme_upper" "$_lsme_target" \
                "${_lsme_partition}-${_lsme_subdir}"; then
                _lsme_overlay_count=$((_lsme_overlay_count + 1))
                _lsme_mounted="${_lsme_mounted}${_lsme_mounted:+,}${_lsme_partition}/${_lsme_subdir}"
                printf '%s\n' "$_lsme_target" >> "$_lsme_mount_list" 2>/dev/null || true
                [ "$_lsme_partition/$_lsme_subdir" = system/fonts ] && _lsme_system_fonts_ok=1
                continue
            fi
            if [ "$_lsme_subdir" = fonts ] && \
               _luoshu_bind_existing_fonts "$_lsme_upper" "$_lsme_target" "$_lsme_bind_list"; then
                _lsme_bind_count=$((_lsme_bind_count + 1))
                cat "$_lsme_bind_list" >> "$_lsme_mount_list" 2>/dev/null || true
                _lsme_mounted="${_lsme_mounted}${_lsme_mounted:+,}${_lsme_partition}/${_lsme_subdir}:bind"
                [ "$_lsme_partition/$_lsme_subdir" = system/fonts ] && _lsme_system_fonts_ok=1
            else
                _lsme_failed="${_lsme_failed}${_lsme_failed:+,}${_lsme_partition}/${_lsme_subdir}"
            fi
        done
    done
    rm -f "$_lsme_bind_list" 2>/dev/null || true

    if [ "$_lsme_system_fonts_ok" -ne 1 ]; then
        _luoshu_self_state_write failed none "$_lsme_mounted" "${_lsme_failed:-system/fonts}"
        _luoshu_self_log "自挂载失败：私有 system/fonts 未进入系统；failed=$_lsme_failed"
        return 1
    fi
    if [ -z "$_lsme_failed" ] && [ "$_lsme_bind_count" -eq 0 ]; then
        _luoshu_self_state_write mounted self-overlay "$_lsme_mounted" ''
        _luoshu_self_log "私有字体负载 OverlayFS 自挂载成功：$_lsme_mounted"
    else
        _luoshu_self_state_write degraded self-overlay-bind "$_lsme_mounted" "$_lsme_failed"
        _luoshu_self_log "私有字体负载降级接管：mounted=$_lsme_mounted failed=$_lsme_failed"
    fi
    return 0
}
