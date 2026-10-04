#!/system/bin/sh
# LuoShu Phase 3 source-font profile bridge.
# Read-only for source fonts: writes only cached JSON under the module config directory.
set +e

MODDIR="${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
MODULE_DIR="$MODDIR"
USER_FONTS_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/fonts"
PROFILE_DIR="$MODDIR/config/source-font-profiles"
PYROOT="$MODDIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"
ANALYZER="$MODDIR/common/font_source_profile.py"
CONVERTER="$MODDIR/common/font_web_convert.py"

[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"

_profile_exec() {
    if [ -n "${LUOSHU_PYTHON:-}" ]; then
        "$LUOSHU_PYTHON" "$@"
        return $?
    fi
    [ -x "$PYBIN" ] || return 127
    PYTHONHOME="$PYROOT" \
    PYTHONPATH="$MODDIR/common:$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$PYBIN" "$@"
}

_profile_family_key() {
    _pfk_family="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        printf "%s" "$_pfk_family" | sha256sum | awk '{print substr($1,1,24)}'
    elif command -v busybox >/dev/null 2>&1; then
        printf "%s" "$_pfk_family" | busybox sha256sum | awk '{print substr($1,1,24)}'
    else
        printf "%s" "$_pfk_family" | cksum | awk '{print $1 "-" $2}'
    fi
}

_profile_output_for_family() {
    _pof_key=$(_profile_family_key "$1") || return 1
    printf "%s/%s.json\n" "$PROFILE_DIR" "$_pof_key"
}

_profile_safe_family() {
    case "$1" in
        ''|*/*) return 1 ;;
    esac
    return 0
}

# Universal composite (mix) switches keep their role assignment here; the
# whole pipeline uses the family key "mix" while this bridge expands it.
COMPOSITE_CONF="$MODDIR/config/universal-composite.conf"

_profile_conf_value() {
    sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

# Prints matching font files of one family, one per line.
_profile_family_files() {
    _pff_family="$1"
    for _pff_file in \
        "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc "$USER_FONTS_DIR"/*.otc \
        "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC "$USER_FONTS_DIR"/*.OTC \
        "$USER_FONTS_DIR"/*.woff "$USER_FONTS_DIR"/*.woff2 "$USER_FONTS_DIR"/*.WOFF "$USER_FONTS_DIR"/*.WOFF2; do
        [ -f "$_pff_file" ] || continue
        if type detect_font_family >/dev/null 2>&1; then
            _pff_detected=$(detect_font_family "$(basename "$_pff_file")")
        else
            _pff_detected="${_pff_file##*/}"
            _pff_detected="${_pff_detected%.*}"
        fi
        [ "$_pff_detected" = "$_pff_family" ] && printf '%s\n' "$_pff_file"
    done
}

_profile_composite() {
    [ -s "$COMPOSITE_CONF" ] || {
        printf '{"status":"error","message":"组合字体设置缺失"}\n'
        return 1
    }
    mkdir -p "$PROFILE_DIR" 2>/dev/null || {
        printf '{"status":"error","message":"无法创建源字体 Profile 缓存"}\n'
        return 1
    }
    _pc_output=$(_profile_output_for_family mix) || return 1
    set -- "$ANALYZER" --output "$_pc_output"
    for _pc_role in cjk latin digit; do
        _pc_family=$(_profile_conf_value "$COMPOSITE_CONF" "$_pc_role")
        _profile_safe_family "$_pc_family" || {
            printf '{"status":"error","message":"组合字体 ID 无效"}\n'
            return 1
        }
        _pc_files=$(_profile_family_files "$_pc_family")
        [ -n "$_pc_files" ] || {
            printf '{"status":"error","message":"找不到组合字体家族：%s"}\n' "$_pc_family"
            return 1
        }
        while IFS= read -r _pc_file; do
            [ -n "$_pc_file" ] && set -- "$@" --role-font "$_pc_role:$_pc_file"
        done <<EOF_PC_FILES
$_pc_files
EOF_PC_FILES
        set -- "$@" \
            --role-mode "$_pc_role=$(_profile_conf_value "$COMPOSITE_CONF" "${_pc_role}Mode")" \
            --role-axes "$_pc_role=$(_profile_conf_value "$COMPOSITE_CONF" "${_pc_role}Axes")"
    done
    _profile_exec "$@"
}

_profile_family() {
    _pf_family="$1"
    if [ "$_pf_family" = mix ]; then
        _profile_composite
        return $?
    fi
    _profile_safe_family "$_pf_family" || {
        printf '{"status":"error","message":"字体 ID 无效"}\n'
        return 1
    }
    [ -f "$ANALYZER" ] || {
        printf '{"status":"error","message":"源字体分析器不可用"}\n'
        return 1
    }
    mkdir -p "$PROFILE_DIR" 2>/dev/null || {
        printf '{"status":"error","message":"无法创建源字体 Profile 缓存"}\n'
        return 1
    }
    _pf_output=$(_profile_output_for_family "$_pf_family") || return 1
    set -- "$ANALYZER" --output "$_pf_output"
    _pf_count=0
    for _pf_file in \
        "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc "$USER_FONTS_DIR"/*.otc \
        "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC "$USER_FONTS_DIR"/*.OTC \
        "$USER_FONTS_DIR"/*.woff "$USER_FONTS_DIR"/*.woff2 "$USER_FONTS_DIR"/*.WOFF "$USER_FONTS_DIR"/*.WOFF2; do
        [ -f "$_pf_file" ] || continue
        if type detect_font_family >/dev/null 2>&1; then
            _pf_detected=$(detect_font_family "$(basename "$_pf_file")")
        else
            _pf_detected="${_pf_file##*/}"
            _pf_detected="${_pf_detected%.*}"
        fi
        [ "$_pf_detected" = "$_pf_family" ] || continue
        set -- "$@" --font "$_pf_file"
        _pf_count=$((_pf_count + 1))
    done
    if [ "$_pf_count" -le 0 ]; then
        printf '{"status":"error","message":"找不到字体家族"}\n'
        return 1
    fi
    _profile_exec "$@"
}

_profile_validate_family() {
    _pvf_output=$(_profile_output_for_family "$1") || return 1
    [ -s "$_pvf_output" ] || {
        printf '{"status":"error","message":"源字体 Profile 尚未生成"}\n'
        return 1
    }
    _profile_exec "$ANALYZER" --validate "$_pvf_output"
}

_profile_convert_web() {
    _pcw_name="$1"
    case "$_pcw_name" in
        ''|*/*|*..*) printf '{"status":"error","message":"文件名无效"}\n'; return 1 ;;
    esac
    _pcw_source="$USER_FONTS_DIR/$_pcw_name"
    [ -f "$_pcw_source" ] || {
        printf '{"status":"error","message":"找不到网页字体"}\n'
        return 1
    }
    [ -f "$CONVERTER" ] || {
        printf '{"status":"error","message":"网页字体转换器不可用"}\n'
        return 1
    }
    _profile_exec "$CONVERTER" --input "$_pcw_source" --output-dir "$USER_FONTS_DIR"
}

case "${1:-family}" in
    family|refresh)
        _profile_family "${2:-}"
        ;;
    validate)
        _profile_validate_family "${2:-}"
        ;;
    path)
        _profile_output_for_family "${2:-}"
        ;;
    convert-web)
        _profile_convert_web "${2:-}"
        ;;
    *)
        echo "Usage: $0 {family|refresh|validate|path|convert-web} <font-family-or-file>" >&2
        exit 2
        ;;
esac
