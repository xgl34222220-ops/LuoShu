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

font_config_prepare_payload_weights() {
    _lcw_module="$(_luoshu_config_weight_module)"
    _lcw_fonts="$_lcw_module/system/fonts"
    mkdir -p "$_lcw_fonts" 2>/dev/null || return 1

    _lcw_stage="$_lcw_module/config/font-config-weights.$$"
    rm -rf "$_lcw_stage" 2>/dev/null || true
    mkdir -p "$_lcw_stage" 2>/dev/null || return 1

    for _lcw_weight in 100 200 300 400 500 600 700 800 900; do
        _lcw_source="$(_luoshu_config_weight_source "$_lcw_weight")" || {
            rm -rf "$_lcw_stage" 2>/dev/null || true
            return 1
        }
        _lcw_target="$_lcw_stage/LuoShu-${_lcw_weight}.ttf"
        ln "$_lcw_source" "$_lcw_target" 2>/dev/null || cp -f "$_lcw_source" "$_lcw_target" 2>/dev/null || {
            rm -rf "$_lcw_stage" 2>/dev/null || true
            return 1
        }
        chmod 0644 "$_lcw_target" 2>/dev/null || true
    done

    for _lcw_weight in 100 200 300 400 500 600 700 800 900; do
        _lcw_ready="$_lcw_stage/LuoShu-${_lcw_weight}.ttf"
        _lcw_dest="$_lcw_fonts/LuoShu-${_lcw_weight}.ttf"
        rm -f "$_lcw_dest" 2>/dev/null || true
        mv -f "$_lcw_ready" "$_lcw_dest" 2>/dev/null || {
            rm -rf "$_lcw_stage" 2>/dev/null || true
            return 1
        }
    done
    rmdir "$_lcw_stage" 2>/dev/null || true
    return 0
}

font_config_enable_for_payload() {
    _lcw_family="${1:-unknown}"
    type font_config_generate >/dev/null 2>&1 || return 1
    font_config_prepare_payload_weights || {
        type font_config_disable >/dev/null 2>&1 && font_config_disable
        return 1
    }
    font_config_generate "$_lcw_family"
}
