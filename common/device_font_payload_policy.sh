#!/system/bin/sh
# LuoShu v2.2 foreground runtime policy.
# Never build or normalize large per-slot/per-weight font payloads in the App switch path.
# Reuse is allowed only when the cache was built from the current trusted stock template.
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

_device_font_policy_trusted_template_key() {
    if [ -n "${LUOSHU_TRUSTED_TEMPLATE_KEY:-}" ]; then
        printf '%s\n' "$LUOSHU_TRUSTED_TEMPLATE_KEY"
        return 0
    fi
    _dfpp_module="$(_device_font_policy_module)"
    _dfpp_template_script="$_dfpp_module/common/device_font_template.sh"
    [ -f "$_dfpp_template_script" ] || return 1
    MODDIR="$_dfpp_module" sh "$_dfpp_template_script" trusted >/dev/null 2>&1 || return 1
    _dfpp_key=$(cat "$_dfpp_module/config/device-font-template.key" 2>/dev/null)
    [ -n "$_dfpp_key" ] || return 1
    printf '%s\n' "$_dfpp_key"
}

# Cache ColorOS target discovery by build fingerprint; an OTA invalidates it automatically.
get_all_coloros_files() {
    _dfpp_module="$(_device_font_policy_module)"
    _dfpp_cache="$_dfpp_module/config/coloros-font-targets.cache"
    _dfpp_key="${LUOSHU_COLOROS_CACHE_KEY:-$(getprop ro.build.fingerprint 2>/dev/null)}"
    [ -n "$_dfpp_key" ] || _dfpp_key="$(getprop ro.build.version.incremental 2>/dev/null)"
    [ -n "$_dfpp_key" ] || _dfpp_key=unknown
    _dfpp_cached_key=$(sed -n 's/^key=//p' "$_dfpp_cache" 2>/dev/null | head -n1)
    if [ "$_dfpp_cached_key" = "$_dfpp_key" ] && sed -n '2,$p' "$_dfpp_cache" 2>/dev/null | grep -q .; then
        sed -n '2,$p' "$_dfpp_cache" 2>/dev/null
        return 0
    fi
    _dfpp_tmp="${_dfpp_cache}.tmp.$$"
    mkdir -p "${_dfpp_cache%/*}" 2>/dev/null || true
    {
        printf 'key=%s\n' "$_dfpp_key"
        {
            if type _coloros_core_files >/dev/null 2>&1; then _coloros_core_files; fi
            if type _coloros_google_text_files >/dev/null 2>&1; then _coloros_google_text_files; fi
            if type _coloros_vendor_files >/dev/null 2>&1; then _coloros_vendor_files; fi
            if type _coloros_oem_ui_files >/dev/null 2>&1; then _coloros_oem_ui_files; fi
            if type _coloros_discovered_ui_files >/dev/null 2>&1; then _coloros_discovered_ui_files; fi
        } | tr ' ' '\n' | awk 'NF && !seen[$0]++'
    } > "$_dfpp_tmp" 2>/dev/null || { rm -f "$_dfpp_tmp" 2>/dev/null || true; return 1; }
    mv -f "$_dfpp_tmp" "$_dfpp_cache" 2>/dev/null || { rm -f "$_dfpp_tmp" 2>/dev/null || true; return 1; }
    chmod 0644 "$_dfpp_cache" 2>/dev/null || true
    sed -n '2,$p' "$_dfpp_cache" 2>/dev/null
}

get_all_coloros_names() {
    [ "${LUOSHU_COLOROS_TARGETS_MAPPED:-0}" != 1 ] || return 0
    for _dfpp_file in $(get_all_coloros_files); do
        printf '%s\n' "${_dfpp_file%.ttf}"
    done
}

# Legacy quick mode used wc and Python normalization for every alias. These overrides make
# foreground switching metadata-only: one source inode, stat-based checks and hard-link aliases.
_device_font_fast_size() {
    _dffs_file="$1"
    if command -v stat >/dev/null 2>&1; then
        stat -c '%s' "$_dffs_file" 2>/dev/null && return 0
    fi
    if command -v toybox >/dev/null 2>&1; then
        toybox stat -c '%s' "$_dffs_file" 2>/dev/null && return 0
    fi
    wc -c < "$_dffs_file" 2>/dev/null | tr -d '[:space:]'
}

_verify_font_copy() {
    _dfvf_file="$1"
    [ -s "$_dfvf_file" ] || return 1
    _dfvf_size=$(_device_font_fast_size "$_dfvf_file")
    case "$_dfvf_size" in ''|*[!0-9]*) return 1 ;; esac
    [ "$_dfvf_size" -ge 1024 ]
}

_font_anchor() {
    _dffa_src="$1"
    _dffa_dest="$2"
    _dffa_key="$3"
    _dffa_anchor="$_dffa_dest/.luoshu-font-store/${_dffa_key}.font"
    mkdir -p "$_dffa_dest/.luoshu-font-store" 2>/dev/null || return 1
    rm -f "$_dffa_anchor" 2>/dev/null || true
    ln "$_dffa_src" "$_dffa_anchor" 2>/dev/null || cp -f "$_dffa_src" "$_dffa_anchor" 2>/dev/null || return 1
    chmod 0644 "$_dffa_anchor" 2>/dev/null || true
    printf '%s\n' "$_dffa_anchor"
}

_device_font_fast_alias_roots() {
    _dffar_anchor="$1"
    _dffar_file="$2"
    _dffar_module="$(_device_font_policy_module)"
    _dffar_count=0
    while IFS='|' read -r _dffar_real _dffar_overlay; do
        [ -e "$_dffar_real/$_dffar_file" ] || continue
        mkdir -p "$_dffar_overlay" 2>/dev/null || continue
        rm -f "$_dffar_overlay/$_dffar_file" 2>/dev/null || true
        if ln "$_dffar_anchor" "$_dffar_overlay/$_dffar_file" 2>/dev/null || \
           cp -f "$_dffar_anchor" "$_dffar_overlay/$_dffar_file" 2>/dev/null; then
            chmod 0644 "$_dffar_overlay/$_dffar_file" 2>/dev/null || true
            _dffar_count=$((_dffar_count + 1))
        fi
    done <<EOF_DFFAR_ROOTS
/system/fonts|$_dffar_module/system/fonts
/system_ext/fonts|$_dffar_module/system_ext/fonts
/product/fonts|$_dffar_module/product/fonts
/mi_ext/fonts|$_dffar_module/mi_ext/fonts
/my_product/fonts|$_dffar_module/my_product/fonts
/vendor/fonts|$_dffar_module/vendor/fonts
EOF_DFFAR_ROOTS
    printf '%s\n' "$_dffar_count"
}

_device_font_fast_map() {
    _dffm_src="$1"
    _dffm_family="$2"
    _dffm_module="$(_device_font_policy_module)"
    _dffm_dest="$_dffm_module/system/fonts"
    mkdir -p "$_dffm_dest" 2>/dev/null || return 1

    _dffm_preserve="${LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE:-0}"
    LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE=1
    export LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE
    type font_config_disable >/dev/null 2>&1 && font_config_disable >/dev/null 2>&1 || true
    LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE="$_dffm_preserve"
    export LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE

    type _font_store_reset >/dev/null 2>&1 && _font_store_reset "$_dffm_dest"
    _dffm_anchor=$(_font_anchor "$_dffm_src" "$_dffm_dest" regular) || return 1
    _dffm_total=0

    if [ "${IS_HYPEROS:-false}" = true ]; then
        _dffm_files=$(get_all_hyperos_files)
    elif [ "${IS_COLOROS:-false}" = true ]; then
        _dffm_files=$(get_all_coloros_files)
    elif type get_all_generic_files >/dev/null 2>&1; then
        _dffm_files=$(get_all_generic_files)
    else
        _dffm_files='Roboto-Regular.ttf Roboto-Medium.ttf Roboto-Bold.ttf NotoSans-Regular.ttf'
    fi

    for _dffm_file in $_dffm_files; do
        _dffm_added=$(_device_font_fast_alias_roots "$_dffm_anchor" "$_dffm_file")
        case "$_dffm_added" in ''|*[!0-9]*) _dffm_added=0 ;; esac
        _dffm_total=$((_dffm_total + _dffm_added))
    done

    if [ "$_dffm_total" -eq 0 ]; then
        for _dffm_file in MiSansVF.ttf Roboto-Regular.ttf NotoSans-Regular.ttf; do
            rm -f "$_dffm_dest/$_dffm_file" 2>/dev/null || true
            ln "$_dffm_anchor" "$_dffm_dest/$_dffm_file" 2>/dev/null || \
                cp -f "$_dffm_anchor" "$_dffm_dest/$_dffm_file" 2>/dev/null || continue
            chmod 0644 "$_dffm_dest/$_dffm_file" 2>/dev/null || true
            _dffm_total=$((_dffm_total + 1))
            break
        done
    fi

    for _dffm_weight in 100 200 300 400 500 600 700 800 900; do
        for _dffm_prefix in LuoShu LuoShuMono; do
            _dffm_out="$_dffm_dest/${_dffm_prefix}-${_dffm_weight}.ttf"
            rm -f "$_dffm_out" 2>/dev/null || true
            ln "$_dffm_anchor" "$_dffm_out" 2>/dev/null || cp -f "$_dffm_anchor" "$_dffm_out" 2>/dev/null || return 1
            chmod 0644 "$_dffm_out" 2>/dev/null || true
        done
    done

    _device_font_policy_log "前台快速映射完成：font=$_dffm_family aliases=$_dffm_total"
    return 0
}

# Override the ROM dispatcher after all OEM adapters have been sourced. Quick mode never enters
# compact normalization, variable-font instancing or per-weight generation.
apply_font_by_rom() {
    _dfabr_src="$1"
    _dfabr_dest="$2"
    _dfabr_mode="${3:-full}"
    _dfabr_family="${4:-}"
    [ -n "$_dfabr_family" ] || _dfabr_family=$(detect_font_family "$(basename "$_dfabr_src")")

    if [ "$_dfabr_mode" = quick ]; then
        _device_font_fast_map "$_dfabr_src" "$_dfabr_family" || return 1
        if type font_config_enable_for_payload >/dev/null 2>&1; then
            font_config_enable_for_payload "$_dfabr_family" || return 1
        fi
        return 0
    fi

    if [ "${IS_HYPEROS:-false}" = true ]; then
        copy_as_hyperos "$_dfabr_src" "$_dfabr_dest" "$_dfabr_mode" "$_dfabr_family"
    elif [ "${IS_COLOROS:-false}" = true ]; then
        copy_as_coloros "$_dfabr_src" "$_dfabr_dest" "$_dfabr_mode" "$_dfabr_family"
    else
        copy_as_generic "$_dfabr_src" "$_dfabr_dest" "$_dfabr_mode"
    fi
}

# Keep the safety contract, but use stat for font aliases instead of reading the same inode dozens
# of times through wc. XML structure validation remains unchanged.
luoshu_payload_validate_current() {
    _lpv_active="${1:-unknown}"
    _lpv_module="$(_luoshu_safety_module)"
    _lpv_config="$(_luoshu_safety_config)"
    [ "$_lpv_active" != default ] || return 0
    _lpv_fonts=0
    for _lpv_part in $(_luoshu_payload_parts); do
        _lpv_dir="$_lpv_module/$_lpv_part/fonts"
        [ -d "$_lpv_dir" ] || continue
        for _lpv_file in "$_lpv_dir"/*.ttf "$_lpv_dir"/*.otf "$_lpv_dir"/*.ttc; do
            [ -f "$_lpv_file" ] || continue
            _lpv_size=$(_device_font_fast_size "$_lpv_file")
            case "$_lpv_size" in ''|*[!0-9]*) _lpv_size=0 ;; esac
            [ "$_lpv_size" -ge 1024 ] || return 1
            _lpv_fonts=$((_lpv_fonts + 1))
        done
    done
    [ "$_lpv_fonts" -gt 0 ] || return 1

    _lpv_targets=$(sed -n 's/^targets=//p' "$_lpv_config/font-target-coverage.conf" 2>/dev/null | head -n1)
    _lpv_mapped=$(sed -n 's/^mapped=//p' "$_lpv_config/font-target-coverage.conf" 2>/dev/null | head -n1)
    case "$_lpv_targets" in ''|*[!0-9]*) _lpv_targets=0 ;; esac
    case "$_lpv_mapped" in ''|*[!0-9]*) _lpv_mapped=0 ;; esac
    [ "$_lpv_targets" -eq "$_lpv_mapped" ] || return 1

    while IFS='|' read -r _lpv_key _lpv_real _lpv_overlay _lpv_font_dir; do
        [ -f "$_lpv_overlay" ] || continue
        grep -Eq 'LuoShu(Mono)?-[1-9][0-9][0-9]\.ttf' "$_lpv_overlay" 2>/dev/null || continue
        _luoshu_font_config_validate "$_lpv_overlay" "$_lpv_font_dir" || return 1
    done <<EOF_LUOSHU_VALIDATE
$(_luoshu_font_config_specs)
EOF_LUOSHU_VALIDATE
    LUOSHU_PAYLOAD_VALIDATED_ACTIVE="$_lpv_active"
    return 0
}

# Return 0 when the active aligned tree is valid or a persistent ready cache can be
# activated through hard links. A normal miss returns 2 and never performs font generation.
device_font_payload_build_install() {
    _dfpp_font="${1:-custom}"
    _dfpp_module="$(_device_font_policy_module)"
    _dfpp_state="$_dfpp_module/config/device-font-engine.conf"
    _dfpp_installed_state=$(sed -n 's/^state=//p' "$_dfpp_state" 2>/dev/null | head -n1)
    _dfpp_installed_font=$(sed -n 's/^font=//p' "$_dfpp_state" 2>/dev/null | head -n1)
    _dfpp_installed_template=$(sed -n 's/^templateKey=//p' "$_dfpp_state" 2>/dev/null | head -n1)
    _dfpp_template_key=$(_device_font_policy_trusted_template_key 2>/dev/null)

    if [ -n "$_dfpp_template_key" ] && \
       [ "$_dfpp_installed_state" = installed ] && \
       [ "$_dfpp_installed_font" = "$_dfpp_font" ] && \
       [ "$_dfpp_installed_template" = "$_dfpp_template_key" ]; then
        if type device_font_payload_validate_installed >/dev/null 2>&1 && device_font_payload_validate_installed; then
            _device_font_policy_log "复用已激活的可信设备字体：$_dfpp_font"
            return 0
        fi
    fi

    if [ -n "$_dfpp_template_key" ] && type device_font_cache_activate >/dev/null 2>&1; then
        device_font_cache_activate "$_dfpp_font"
        _dfpp_cache_rc=$?
        case "$_dfpp_cache_rc" in
            0)
                _device_font_policy_log "已从持久缓存快速激活设备对齐字体：$_dfpp_font"
                return 0
                ;;
            1)
                _device_font_policy_log "持久缓存存在但激活失败：$_dfpp_font"
                return 1
                ;;
        esac
    fi

    if type device_font_payload_clear >/dev/null 2>&1; then
        device_font_payload_clear >/dev/null 2>&1 || true
    fi
    if [ -z "$_dfpp_template_key" ]; then
        _device_font_policy_log "设备对齐暂不可用：需要在系统默认字体状态重启一次建立原厂模板"
    elif [ -n "$_dfpp_installed_template" ] && [ "$_dfpp_installed_template" != "$_dfpp_template_key" ]; then
        _device_font_policy_log "设备缓存已过期：模板指纹变化"
    else
        _device_font_policy_log "设备缓存未命中：$_dfpp_font"
    fi
    return 2
}

font_config_enable_for_payload() {
    _dfpp_family="${1:-unknown}"
    LUOSHU_DEVICE_PAYLOAD_RESULT='preparing'

    device_font_payload_build_install "$_dfpp_family"
    _dfpp_rc=$?
    case "$_dfpp_rc" in
        0)
            LUOSHU_DEVICE_PAYLOAD_RESULT='device'
            [ "${IS_COLOROS:-false}" != true ] || LUOSHU_COLOROS_TARGETS_MAPPED=1
            export LUOSHU_COLOROS_TARGETS_MAPPED
            return 0
            ;;
        1)
            LUOSHU_DEVICE_PAYLOAD_RESULT='device-failed'
            return 1
            ;;
    esac

    # Keep the physical ROM aliases prepared by the quick mapper and remove only stale v2/XML state.
    _dfpp_preserve="${LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE:-0}"
    LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE=1
    export LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE
    if type font_config_disable >/dev/null 2>&1; then
        font_config_disable >/dev/null 2>&1 || true
    fi
    LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE="$_dfpp_preserve"
    export LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE

    # Scheduling is metadata-only. The expensive builder runs after the foreground transaction.
    if type device_font_cache_schedule >/dev/null 2>&1; then
        device_font_cache_schedule "$_dfpp_family" >/dev/null 2>&1 || true
    fi
    [ "${IS_COLOROS:-false}" != true ] || LUOSHU_COLOROS_TARGETS_MAPPED=1
    export LUOSHU_COLOROS_TARGETS_MAPPED
    LUOSHU_DEVICE_PAYLOAD_RESULT='slot-only'
    _device_font_policy_log "前台已完成常量时间物理槽映射；后台对齐缓存按条件安排：$_dfpp_family"
    return 0
}
