#!/system/bin/sh
# 为无 Hook XML 配置准备九个确定的静态字重文件。被 source 时只定义函数。
set +e

_luoshu_config_weight_module() {
    printf '%s\n' "${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
}

_luoshu_config_weight_role() {
    case "$1" in
        100) printf 'Thin\n' ;;
        200) printf 'ExtraLight\n' ;;
        300) printf 'Light\n' ;;
        500) printf 'Medium\n' ;;
        600) printf 'SemiBold\n' ;;
        700) printf 'Bold\n' ;;
        800) printf 'ExtraBold\n' ;;
        900) printf 'Black\n' ;;
        *) printf 'Regular\n' ;;
    esac
}

_luoshu_config_weight_library_role() {
    case "$1" in
        100) printf 'thin
' ;;
        200) printf 'extralight
' ;;
        300) printf 'light
' ;;
        500) printf 'medium
' ;;
        600) printf 'semibold
' ;;
        700) printf 'bold
' ;;
        800) printf 'extrabold
' ;;
        900) printf 'black
' ;;
        *) printf 'regular
' ;;
    esac
}

LUOSHU_CONFIG_WEIGHT_CACHE_VERSION="1"

_luoshu_config_weight_cache_root() {
    _lcwc_module="$(_luoshu_config_weight_module)"
    printf '%s/config/font-payload-cache-v%s
' "$_lcwc_module" "$LUOSHU_CONFIG_WEIGHT_CACHE_VERSION"
}

_luoshu_config_fast_size() {
    _lcwfs_file="$1"
    if command -v stat >/dev/null 2>&1; then
        stat -c '%s' "$_lcwfs_file" 2>/dev/null && return 0
    fi
    if command -v toybox >/dev/null 2>&1; then
        toybox stat -c '%s' "$_lcwfs_file" 2>/dev/null && return 0
    fi
    wc -c < "$_lcwfs_file" 2>/dev/null | tr -d '[:space:]'
}

_luoshu_config_source_digest() {
    _lcwsd_source="$1"
    _lcwsd_digest=''
    if type _font_source_digest >/dev/null 2>&1; then
        _lcwsd_digest="$(_font_source_digest "$_lcwsd_source" 2>/dev/null)" || _lcwsd_digest=''
    fi
    if [ -z "$_lcwsd_digest" ] && command -v sha256sum >/dev/null 2>&1; then
        _lcwsd_digest="$(sha256sum "$_lcwsd_source" 2>/dev/null | awk '{print $1}')"
    fi
    if [ -z "$_lcwsd_digest" ] && command -v busybox >/dev/null 2>&1; then
        _lcwsd_digest="$(busybox sha256sum "$_lcwsd_source" 2>/dev/null | awk '{print $1}')"
    fi
    [ -n "$_lcwsd_digest" ] || return 1
    printf '%s
' "$_lcwsd_digest"
}

_luoshu_config_weight_source() {
    _lcw_weight="$1"
    _lcw_family="${2:-}"
    _lcw_hint="${3:-}"
    _lcw_module="$(_luoshu_config_weight_module)"
    _lcw_fonts="$_lcw_module/system/fonts"
    _lcw_role="$(_luoshu_config_weight_role "$_lcw_weight")"

    # Cache/prewarm path: resolve directly from the user's font family instead of first
    # rebuilding ROM aliases. This makes import-time preprocessing independent of the
    # active mount payload and lets a later switch reuse exactly the same 18 artifacts.
    if [ -n "$_lcw_hint" ] && [ -s "$_lcw_hint" ]; then
        if [ -n "$_lcw_family" ] && type get_weight_file >/dev/null 2>&1; then
            _lcw_library_role="$(_luoshu_config_weight_library_role "$_lcw_weight")"
            _lcw_family_source="$(get_weight_file "$_lcw_family" "$_lcw_library_role" 2>/dev/null)"
            if [ -s "$_lcw_family_source" ]; then
                printf '%s
' "$_lcw_family_source"
                return 0
            fi
        fi
        printf '%s
' "$_lcw_hint"
        return 0
    fi

    for _lcw_file in \
        "$_lcw_fonts/.luoshu-font-store/wght-${_lcw_weight}.font" \
        "$_lcw_fonts/${_lcw_weight}.ttf" \
        "$_lcw_fonts/Roboto-${_lcw_role}.ttf" \
        "$_lcw_fonts/GoogleSans-${_lcw_role}.ttf" \
        "$_lcw_fonts/GoogleSansText-${_lcw_role}.ttf" \
        "$_lcw_fonts/SysFont-${_lcw_role}.ttf" \
        "$_lcw_fonts/SysSans-En-${_lcw_role}.ttf" \
        "$_lcw_fonts/Opposans-En-${_lcw_role}.ttf" \
        "$_lcw_fonts/SourceSansPro-${_lcw_role}.ttf" \
        "$_lcw_fonts/NotoSans-${_lcw_role}.ttf"; do
        [ -s "$_lcw_file" ] || continue
        _lcw_size=$(_luoshu_config_fast_size "$_lcw_file")
        case "$_lcw_size" in ''|*[!0-9]*) _lcw_size=0 ;; esac
        [ "$_lcw_size" -ge 1024 ] || continue
        printf '%s
' "$_lcw_file"
        return 0
    done

    for _lcw_file in \
        "$_lcw_fonts/.luoshu-font-store/regular.font" \
        "$_lcw_fonts/.luoshu-font-store/mix-composite.font" \
        "$_lcw_fonts/400.ttf" \
        "$_lcw_fonts/Roboto-Regular.ttf" \
        "$_lcw_fonts/GoogleSans-Regular.ttf" \
        "$_lcw_fonts/GoogleSansText-Regular.ttf" \
        "$_lcw_fonts/SysFont-Regular.ttf" \
        "$_lcw_fonts/SysSans-En-Regular.ttf" \
        "$_lcw_fonts/MiSansVF.ttf" \
        "$_lcw_fonts/NotoSansCJK-Regular.ttc" \
        "$_lcw_fonts/NotoSans-Regular.ttf"; do
        [ -s "$_lcw_file" ] || continue
        _lcw_size=$(_luoshu_config_fast_size "$_lcw_file")
        case "$_lcw_size" in ''|*[!0-9]*) _lcw_size=0 ;; esac
        [ "$_lcw_size" -ge 1024 ] || continue
        printf '%s
' "$_lcw_file"
        return 0
    done
    return 1
}

_luoshu_config_normalize_weight() {
    _lcw_source="$1"
    _lcw_output="$2"
    _lcw_weight="$3"
    _lcw_module="$(_luoshu_config_weight_module)"
    _lcw_tool="$_lcw_module/common/font_name_normalize.py"
    _lcw_instance="$_lcw_module/common/font_instance.py"
    _lcw_raw="${_lcw_output}.raw"
    rm -f "$_lcw_output" "$_lcw_raw" 2>/dev/null || true

    # A direct variable-font application must materialize real 100-900 outlines. Merely changing the
    # OS/2 weight metadata leaves every Android weight visually identical and is a major source of
    # inconsistent hierarchy between titles, body text, keyboards and app controls.
    if type is_variable_font >/dev/null 2>&1 && is_variable_font "$_lcw_source" && \
       [ -f "$_lcw_instance" ] && type _luoshu_font_config_exec >/dev/null 2>&1; then
        _luoshu_font_config_exec "$_lcw_instance" --input "$_lcw_source" --output "$_lcw_raw" \
            --role cjk --weight "$_lcw_weight" --axes "wght=$_lcw_weight" >/dev/null 2>&1 || {
            rm -f "$_lcw_raw" "$_lcw_output" 2>/dev/null || true
            return 1
        }
    else
        cp -f "$_lcw_source" "$_lcw_raw" 2>/dev/null || return 1
    fi

    # A TTC may contain locale-specific faces. The generated XML points to one deterministic static
    # face and removes the ROM's old collection index, so carrying a whole TTC under a .ttf name could
    # silently select the wrong language. Until the native backend extracts a requested face, reject
    # TTC for XML and let the already-committed ROM file-slot mapping remain the compatibility path.
    _lcw_magic=$(dd if="$_lcw_raw" bs=4 count=1 2>/dev/null)
    if [ "$_lcw_magic" = ttcf ]; then
        rm -f "$_lcw_raw" "$_lcw_output" 2>/dev/null || true
        return 1
    elif [ -f "$_lcw_tool" ] && type _luoshu_font_config_exec >/dev/null 2>&1; then
        if ! _luoshu_font_config_exec "$_lcw_tool" --input "$_lcw_raw" --output "$_lcw_output" \
            --weight "$_lcw_weight" --family 'LuoShu UI' >/dev/null 2>&1; then
            rm -f "$_lcw_raw" "$_lcw_output" 2>/dev/null || true
            return 1
        fi
        rm -f "$_lcw_raw" 2>/dev/null || true
    else
        rm -f "$_lcw_raw" 2>/dev/null || true
        return 1
    fi
    chmod 0644 "$_lcw_output" 2>/dev/null || true
    _lcw_size=$(_luoshu_config_fast_size "$_lcw_output")
    case "$_lcw_size" in ''|*[!0-9]*) _lcw_size=0 ;; esac
    [ "$_lcw_size" -ge 1024 ]
}

_luoshu_config_make_mono_weight() {
    _lcw_source="$1"
    _lcw_output="$2"
    _lcw_weight="$3"
    _lcw_module="$(_luoshu_config_weight_module)"
    _lcw_tool="$_lcw_module/common/font_name_normalize.py"
    [ -f "$_lcw_tool" ] && type _luoshu_font_config_exec >/dev/null 2>&1 || return 1
    rm -f "$_lcw_output" 2>/dev/null || true
    _luoshu_font_config_exec "$_lcw_tool" --input "$_lcw_source" --output "$_lcw_output"         --weight "$_lcw_weight" --family 'LuoShu Mono' --monospace >/dev/null 2>&1 || return 1
    chmod 0644 "$_lcw_output" 2>/dev/null || true
    _lcw_size=$(_luoshu_config_fast_size "$_lcw_output")
    case "$_lcw_size" in ''|*[!0-9]*) _lcw_size=0 ;; esac
    [ "$_lcw_size" -ge 1024 ]
}

_luoshu_config_weight_cache_key() {
    _lcwk_family="${1:-}"
    _lcwk_hint="${2:-}"
    _lcwk_module="$(_luoshu_config_weight_module)"
    _lcwk_tmp="${CONFIG_DIR:-$_lcwk_module/config}/.font-payload-key.$$"
    mkdir -p "${_lcwk_tmp%/*}" 2>/dev/null || return 1
    : > "$_lcwk_tmp" 2>/dev/null || return 1
    printf 'schema=%s\n' "$LUOSHU_CONFIG_WEIGHT_CACHE_VERSION" >> "$_lcwk_tmp"
    for _lcwk_weight in 100 200 300 400 500 600 700 800 900; do
        _lcwk_source="$(_luoshu_config_weight_source "$_lcwk_weight" "$_lcwk_family" "$_lcwk_hint")" || {
            rm -f "$_lcwk_tmp" 2>/dev/null || true
            return 1
        }
        _lcwk_digest="$(_luoshu_config_source_digest "$_lcwk_source")" || {
            rm -f "$_lcwk_tmp" 2>/dev/null || true
            return 1
        }
        _lcwk_size=$(_luoshu_config_fast_size "$_lcwk_source")
        printf '%s|%s|%s\n' "$_lcwk_weight" "$_lcwk_digest" "${_lcwk_size:-0}" >> "$_lcwk_tmp"
    done
    if command -v sha256sum >/dev/null 2>&1; then
        _lcwk_key=$(sha256sum "$_lcwk_tmp" 2>/dev/null | awk '{print $1}')
    elif command -v busybox >/dev/null 2>&1; then
        _lcwk_key=$(busybox sha256sum "$_lcwk_tmp" 2>/dev/null | awk '{print $1}')
    else
        _lcwk_key=''
    fi
    rm -f "$_lcwk_tmp" 2>/dev/null || true
    [ -n "$_lcwk_key" ] || return 1
    printf '%s\n' "$_lcwk_key"
}

_luoshu_config_weight_cache_dir() {
    _lcwcd_key="$1"
    printf '%s/%s\n' "$(_luoshu_config_weight_cache_root)" "$_lcwcd_key"
}

_luoshu_config_weight_cache_valid() {
    _lcwcv_dir="$1"
    [ -f "$_lcwcv_dir/.complete" ] || return 1
    grep -qx "schema=$LUOSHU_CONFIG_WEIGHT_CACHE_VERSION" "$_lcwcv_dir/.complete" 2>/dev/null || return 1
    for _lcwcv_weight in 100 200 300 400 500 600 700 800 900; do
        for _lcwcv_prefix in LuoShu LuoShuMono; do
            _lcwcv_file="$_lcwcv_dir/${_lcwcv_prefix}-${_lcwcv_weight}.ttf"
            [ -s "$_lcwcv_file" ] || return 1
            _lcwcv_size=$(_luoshu_config_fast_size "$_lcwcv_file")
            case "$_lcwcv_size" in ''|*[!0-9]*) return 1 ;; esac
            [ "$_lcwcv_size" -ge 1024 ] || return 1
        done
    done
    return 0
}

_luoshu_config_weight_active_clear() {
    _lcwac_module="$(_luoshu_config_weight_module)"
    _lcwac_fonts="$_lcwac_module/system/fonts"
    for _lcwac_weight in 100 200 300 400 500 600 700 800 900; do
        rm -f "$_lcwac_fonts/LuoShu-${_lcwac_weight}.ttf" \
              "$_lcwac_fonts/LuoShuMono-${_lcwac_weight}.ttf" 2>/dev/null || true
    done
}

_luoshu_config_weight_cache_restore() {
    _lcwcr_dir="$1"
    _lcwcr_module="$(_luoshu_config_weight_module)"
    _lcwcr_fonts="$_lcwcr_module/system/fonts"
    _luoshu_config_weight_cache_valid "$_lcwcr_dir" || return 1
    mkdir -p "$_lcwcr_fonts" "${CONFIG_DIR:-$_lcwcr_module/config}" 2>/dev/null || return 1
    _lcwcr_stage="${CONFIG_DIR:-$_lcwcr_module/config}/font-config-cache-restore.$$"
    rm -rf "$_lcwcr_stage" 2>/dev/null || true
    mkdir -p "$_lcwcr_stage" 2>/dev/null || return 1
    for _lcwcr_weight in 100 200 300 400 500 600 700 800 900; do
        for _lcwcr_prefix in LuoShu LuoShuMono; do
            _lcwcr_source="$_lcwcr_dir/${_lcwcr_prefix}-${_lcwcr_weight}.ttf"
            _lcwcr_ready="$_lcwcr_stage/${_lcwcr_prefix}-${_lcwcr_weight}.ttf"
            ln "$_lcwcr_source" "$_lcwcr_ready" 2>/dev/null || cp -f "$_lcwcr_source" "$_lcwcr_ready" 2>/dev/null || {
                rm -rf "$_lcwcr_stage" 2>/dev/null || true
                return 1
            }
            chmod 0644 "$_lcwcr_ready" 2>/dev/null || true
        done
    done
    for _lcwcr_weight in 100 200 300 400 500 600 700 800 900; do
        for _lcwcr_prefix in LuoShu LuoShuMono; do
            _lcwcr_ready="$_lcwcr_stage/${_lcwcr_prefix}-${_lcwcr_weight}.ttf"
            _lcwcr_dest="$_lcwcr_fonts/${_lcwcr_prefix}-${_lcwcr_weight}.ttf"
            rm -f "$_lcwcr_dest" 2>/dev/null || true
            mv -f "$_lcwcr_ready" "$_lcwcr_dest" 2>/dev/null || {
                rm -rf "$_lcwcr_stage" 2>/dev/null || true
                _luoshu_config_weight_active_clear
                return 1
            }
        done
    done
    rmdir "$_lcwcr_stage" 2>/dev/null || true
    touch "$_lcwcr_dir/.complete" 2>/dev/null || true
    return 0
}

_luoshu_config_weight_cache_store() {
    _lcwcs_stage="$1"
    _lcwcs_key="$2"
    [ -d "$_lcwcs_stage" ] && [ -n "$_lcwcs_key" ] || return 1
    _lcwcs_root="$(_luoshu_config_weight_cache_root)"
    _lcwcs_dir="$(_luoshu_config_weight_cache_dir "$_lcwcs_key")"
    if _luoshu_config_weight_cache_valid "$_lcwcs_dir"; then
        return 0
    fi
    mkdir -p "$_lcwcs_root" 2>/dev/null || return 1
    _lcwcs_tmp="${_lcwcs_dir}.tmp.$$"
    rm -rf "$_lcwcs_tmp" 2>/dev/null || true
    mkdir -p "$_lcwcs_tmp" 2>/dev/null || return 1
    for _lcwcs_weight in 100 200 300 400 500 600 700 800 900; do
        for _lcwcs_prefix in LuoShu LuoShuMono; do
            _lcwcs_source="$_lcwcs_stage/${_lcwcs_prefix}-${_lcwcs_weight}.ttf"
            _lcwcs_dest="$_lcwcs_tmp/${_lcwcs_prefix}-${_lcwcs_weight}.ttf"
            [ -s "$_lcwcs_source" ] || { rm -rf "$_lcwcs_tmp"; return 1; }
            ln "$_lcwcs_source" "$_lcwcs_dest" 2>/dev/null || cp -f "$_lcwcs_source" "$_lcwcs_dest" 2>/dev/null || {
                rm -rf "$_lcwcs_tmp" 2>/dev/null || true
                return 1
            }
            chmod 0644 "$_lcwcs_dest" 2>/dev/null || true
        done
    done
    printf 'schema=%s\nkey=%s\n' "$LUOSHU_CONFIG_WEIGHT_CACHE_VERSION" "$_lcwcs_key" > "$_lcwcs_tmp/.complete" 2>/dev/null || {
        rm -rf "$_lcwcs_tmp" 2>/dev/null || true
        return 1
    }
    chmod 0644 "$_lcwcs_tmp/.complete" 2>/dev/null || true
    rm -rf "$_lcwcs_dir" 2>/dev/null || true
    mv -f "$_lcwcs_tmp" "$_lcwcs_dir" 2>/dev/null || {
        rm -rf "$_lcwcs_tmp" 2>/dev/null || true
        return 1
    }
    _luoshu_config_weight_cache_prune >/dev/null 2>&1 || true
    return 0
}

LUOSHU_CONFIG_WEIGHT_CACHE_MAX_ENTRIES="${LUOSHU_CONFIG_WEIGHT_CACHE_MAX_ENTRIES:-3}"

_luoshu_config_weight_cache_prune() {
    _lcwcp_root="$(_luoshu_config_weight_cache_root)"
    _lcwcp_max="$LUOSHU_CONFIG_WEIGHT_CACHE_MAX_ENTRIES"
    case "$_lcwcp_max" in ''|*[!0-9]*) _lcwcp_max=3 ;; esac
    [ "$_lcwcp_max" -ge 1 ] 2>/dev/null || _lcwcp_max=1
    [ -d "$_lcwcp_root" ] || return 0
    _lcwcp_count=0
    for _lcwcp_dir in $(ls -1dt "$_lcwcp_root"/* 2>/dev/null); do
        [ -d "$_lcwcp_dir" ] || continue
        _lcwcp_count=$((_lcwcp_count + 1))
        [ "$_lcwcp_count" -le "$_lcwcp_max" ] && continue
        rm -rf "$_lcwcp_dir" 2>/dev/null || true
    done
    return 0
}

_luoshu_config_link_font() {
    _lcwlf_source="$1"
    _lcwlf_dest="$2"
    rm -f "$_lcwlf_dest" 2>/dev/null || true
    ln "$_lcwlf_source" "$_lcwlf_dest" 2>/dev/null || cp -f "$_lcwlf_source" "$_lcwlf_dest" 2>/dev/null || return 1
    chmod 0644 "$_lcwlf_dest" 2>/dev/null || true
    _lcwlf_size=$(_luoshu_config_fast_size "$_lcwlf_dest")
    case "$_lcwlf_size" in ''|*[!0-9]*) return 1 ;; esac
    [ "$_lcwlf_size" -ge 1024 ]
}

_luoshu_config_build_weight_stage() {
    _lcwbs_stage="$1"
    _lcwbs_family="${2:-}"
    _lcwbs_hint="${3:-}"
    rm -rf "$_lcwbs_stage" 2>/dev/null || true
    mkdir -p "$_lcwbs_stage" 2>/dev/null || return 1
    for _lcwbs_weight in 100 200 300 400 500 600 700 800 900; do
        _lcwbs_source="$(_luoshu_config_weight_source "$_lcwbs_weight" "$_lcwbs_family" "$_lcwbs_hint")" || {
            rm -rf "$_lcwbs_stage" 2>/dev/null || true
            return 1
        }
        _lcwbs_target="$_lcwbs_stage/LuoShu-${_lcwbs_weight}.ttf"
        _luoshu_config_normalize_weight "$_lcwbs_source" "$_lcwbs_target" "$_lcwbs_weight" || {
            rm -rf "$_lcwbs_stage" 2>/dev/null || true
            return 1
        }
    done

    # Monospace only needs one normalized outline. Android selects the declared XML weight;
    # the eight aliases can safely share the 400 file, matching the existing finalizer.
    _lcwbs_mono400="$_lcwbs_stage/LuoShuMono-400.ttf"
    _luoshu_config_make_mono_weight "$_lcwbs_stage/LuoShu-400.ttf" "$_lcwbs_mono400" 400 || {
        rm -rf "$_lcwbs_stage" 2>/dev/null || true
        return 1
    }
    for _lcwbs_weight in 100 200 300 500 600 700 800 900; do
        _luoshu_config_link_font "$_lcwbs_mono400" "$_lcwbs_stage/LuoShuMono-${_lcwbs_weight}.ttf" || {
            rm -rf "$_lcwbs_stage" 2>/dev/null || true
            return 1
        }
    done
    return 0
}

font_config_prewarm_payload_weights() {
    _lcwp_family="${1:-}"
    _lcwp_hint="${2:-}"
    [ -n "$_lcwp_hint" ] && [ -s "$_lcwp_hint" ] || return 1
    _lcwp_module="$(_luoshu_config_weight_module)"
    _lcwp_key="$(_luoshu_config_weight_cache_key "$_lcwp_family" "$_lcwp_hint")" || return 1
    _lcwp_cache="$(_luoshu_config_weight_cache_dir "$_lcwp_key")"
    _luoshu_config_weight_cache_valid "$_lcwp_cache" && return 0
    _lcwp_stage="${CONFIG_DIR:-$_lcwp_module/config}/font-config-prewarm.$$"
    _luoshu_config_build_weight_stage "$_lcwp_stage" "$_lcwp_family" "$_lcwp_hint" || return 1
    _luoshu_config_weight_cache_store "$_lcwp_stage" "$_lcwp_key"
    _lcwp_rc=$?
    rm -rf "$_lcwp_stage" 2>/dev/null || true
    return "$_lcwp_rc"
}

font_config_prepare_payload_weights() {
    _lcw_family="${1:-}"
    _lcw_hint="${2:-}"
    _lcw_module="$(_luoshu_config_weight_module)"
    _lcw_fonts="$_lcw_module/system/fonts"
    mkdir -p "$_lcw_fonts" "$_lcw_module/config" 2>/dev/null || return 1

    _lcw_key="$(_luoshu_config_weight_cache_key "$_lcw_family" "$_lcw_hint" 2>/dev/null || true)"
    if [ -n "$_lcw_key" ]; then
        _lcw_cache="$(_luoshu_config_weight_cache_dir "$_lcw_key")"
        if _luoshu_config_weight_cache_restore "$_lcw_cache"; then
            return 0
        fi
    fi

    _lcw_stage="$_lcw_module/config/font-config-weights.$$"
    _luoshu_config_build_weight_stage "$_lcw_stage" "$_lcw_family" "$_lcw_hint" || return 1

    if [ -n "$_lcw_key" ]; then
        _luoshu_config_weight_cache_store "$_lcw_stage" "$_lcw_key" >/dev/null 2>&1 || true
    fi

    for _lcw_weight in 100 200 300 400 500 600 700 800 900; do
        for _lcw_prefix in LuoShu LuoShuMono; do
            _lcw_ready="$_lcw_stage/${_lcw_prefix}-${_lcw_weight}.ttf"
            _lcw_dest="$_lcw_fonts/${_lcw_prefix}-${_lcw_weight}.ttf"
            rm -f "$_lcw_dest" 2>/dev/null || true
            mv -f "$_lcw_ready" "$_lcw_dest" 2>/dev/null || {
                rm -rf "$_lcw_stage" 2>/dev/null || true
                return 1
            }
        done
    done
    rmdir "$_lcw_stage" 2>/dev/null || true
    return 0
}

font_config_enable_for_payload() {
    _lcw_family="${1:-unknown}"
    _lcw_hint="${2:-}"
    type font_config_generate >/dev/null 2>&1 || return 1
    font_config_prepare_payload_weights "$_lcw_family" "$_lcw_hint" || {
        type font_config_disable >/dev/null 2>&1 && font_config_disable
        return 1
    }
    font_config_generate "$_lcw_family"
}
