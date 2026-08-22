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

_luoshu_config_weight_source() {
    _lcw_weight="$1"
    _lcw_module="$(_luoshu_config_weight_module)"
    _lcw_fonts="$_lcw_module/system/fonts"
    _lcw_role="$(_luoshu_config_weight_role "$_lcw_weight")"

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
        _lcw_size=$(wc -c < "$_lcw_file" 2>/dev/null | tr -d '[:space:]')
        case "$_lcw_size" in ''|*[!0-9]*) _lcw_size=0 ;; esac
        [ "$_lcw_size" -ge 1024 ] || continue
        printf '%s\n' "$_lcw_file"
        return 0
    done

    # A single-weight family remains valid: Android will still select the declared weight while the
    # outline is shared. True multiweight families are picked above whenever the ROM mapping exposes
    # their anchors or named faces.
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
        _lcw_size=$(wc -c < "$_lcw_file" 2>/dev/null | tr -d '[:space:]')
        case "$_lcw_size" in ''|*[!0-9]*) _lcw_size=0 ;; esac
        [ "$_lcw_size" -ge 1024 ] || continue
        printf '%s\n' "$_lcw_file"
        return 0
    done
    return 1
}

_luoshu_config_weight_file_identity() {
    _lcwi_file="$1"
    [ -f "$_lcwi_file" ] || return 1
    if command -v stat >/dev/null 2>&1; then
        stat -c '%d:%i:%s:%Y:%Z' "$_lcwi_file" 2>/dev/null && return 0
    fi
    if command -v toybox >/dev/null 2>&1; then
        toybox stat -c '%d:%i:%s:%Y:%Z' "$_lcwi_file" 2>/dev/null && return 0
    fi
    return 1
}

# The old foreground path rebuilt nine UI faces plus nine monospace faces on every
# switch, even when all inputs were byte-for-byte the same. Build a cheap identity key
# from every selected source face plus the processing engines. A real source/tool update
# changes inode/size/timestamps and invalidates the cache without hashing 20-40 MB files.
_luoshu_config_weights_key() {
    _lcwk_family="${1:-unknown}"
    _lcwk_module="$(_luoshu_config_weight_module)"
    _lcwk_acc="schema=v2|family=$_lcwk_family|normalizer=${LUOSHU_NORMALIZER_VERSION:-unknown}"
    for _lcwk_tool in \
        "$_lcwk_module/common/font_instance.py" \
        "$_lcwk_module/common/font_name_normalize.py"; do
        _lcwk_identity=$(_luoshu_config_weight_file_identity "$_lcwk_tool") || return 1
        _lcwk_acc="$_lcwk_acc|tool=$_lcwk_identity"
    done
    for _lcwk_weight in 100 200 300 400 500 600 700 800 900; do
        _lcwk_source=$(_luoshu_config_weight_source "$_lcwk_weight") || return 1
        _lcwk_identity=$(_luoshu_config_weight_file_identity "$_lcwk_source") || return 1
        _lcwk_acc="$_lcwk_acc|${_lcwk_weight}=$_lcwk_identity"
    done
    if command -v sha256sum >/dev/null 2>&1; then
        printf '%s' "$_lcwk_acc" | sha256sum 2>/dev/null | awk '{print $1}'
    elif command -v toybox >/dev/null 2>&1; then
        printf '%s' "$_lcwk_acc" | toybox sha256sum 2>/dev/null | awk '{print $1}'
    else
        printf '%s' "$_lcwk_acc" | cksum 2>/dev/null | awk '{print $1 ":" $2}'
    fi
}

_luoshu_config_weights_ready() {
    _lcwr_module="$(_luoshu_config_weight_module)"
    _lcwr_fonts="$_lcwr_module/system/fonts"
    for _lcwr_weight in 100 200 300 400 500 600 700 800 900; do
        for _lcwr_prefix in LuoShu LuoShuMono; do
            _lcwr_file="$_lcwr_fonts/${_lcwr_prefix}-${_lcwr_weight}.ttf"
            [ -s "$_lcwr_file" ] || return 1
            _lcwr_size=$(wc -c < "$_lcwr_file" 2>/dev/null | tr -d '[:space:]')
            case "$_lcwr_size" in ''|*[!0-9]*) return 1 ;; esac
            [ "$_lcwr_size" -ge 1024 ] || return 1
        done
    done
    return 0
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
    _lcw_size=$(wc -c < "$_lcw_output" 2>/dev/null | tr -d '[:space:]')
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
    _luoshu_font_config_exec "$_lcw_tool" --input "$_lcw_source" --output "$_lcw_output" \
        --weight "$_lcw_weight" --family 'LuoShu Mono' --monospace >/dev/null 2>&1 || return 1
    chmod 0644 "$_lcw_output" 2>/dev/null || true
    _lcw_size=$(wc -c < "$_lcw_output" 2>/dev/null | tr -d '[:space:]')
    case "$_lcw_size" in ''|*[!0-9]*) _lcw_size=0 ;; esac
    [ "$_lcw_size" -ge 1024 ]
}

font_config_prepare_payload_weights() {
    _lcw_module="$(_luoshu_config_weight_module)"
    _lcw_fonts="$_lcw_module/system/fonts"
    mkdir -p "$_lcw_fonts" "$_lcw_module/config" 2>/dev/null || return 1

    _lcw_stage="$_lcw_module/config/font-config-weights.$$"
    rm -rf "$_lcw_stage" 2>/dev/null || true
    mkdir -p "$_lcw_stage" 2>/dev/null || return 1

    for _lcw_weight in 100 200 300 400 500 600 700 800 900; do
        _lcw_source="$(_luoshu_config_weight_source "$_lcw_weight")" || {
            rm -rf "$_lcw_stage" 2>/dev/null || true
            return 1
        }
        _lcw_target="$_lcw_stage/LuoShu-${_lcw_weight}.ttf"
        _lcw_mono="$_lcw_stage/LuoShuMono-${_lcw_weight}.ttf"
        _luoshu_config_normalize_weight "$_lcw_source" "$_lcw_target" "$_lcw_weight" || {
            rm -rf "$_lcw_stage" 2>/dev/null || true
            return 1
        }
        _luoshu_config_make_mono_weight "$_lcw_target" "$_lcw_mono" "$_lcw_weight" || {
            rm -rf "$_lcw_stage" 2>/dev/null || true
            return 1
        }
    done

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
    _lcw_module="$(_luoshu_config_weight_module)"
    _lcw_stamp="$_lcw_module/config/font-config-weights.key"
    _lcw_key="$(_luoshu_config_weights_key "$_lcw_family" 2>/dev/null)"
    _lcw_cached=$(cat "$_lcw_stamp" 2>/dev/null | tr -d '\r\n')
    type font_config_generate >/dev/null 2>&1 || return 1

    if [ -n "$_lcw_key" ] && [ "$_lcw_key" = "$_lcw_cached" ] && _luoshu_config_weights_ready; then
        : # Reuse the complete 18-file payload; skip embedded Python/FontTools work.
    else
        font_config_prepare_payload_weights || {
            rm -f "$_lcw_stamp" 2>/dev/null || true
            type font_config_disable >/dev/null 2>&1 && font_config_disable
            return 1
        }
        _lcw_key="$(_luoshu_config_weights_key "$_lcw_family" 2>/dev/null)"
        if [ -n "$_lcw_key" ]; then
            printf '%s\n' "$_lcw_key" > "${_lcw_stamp}.tmp.$$" 2>/dev/null && \
                mv -f "${_lcw_stamp}.tmp.$$" "$_lcw_stamp" 2>/dev/null || true
            chmod 0644 "$_lcw_stamp" 2>/dev/null || true
        fi
    fi

    font_config_generate "$_lcw_family"
}
