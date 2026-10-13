#!/system/bin/sh
# 字体能力层（Shell 侧）：按字体内部 OS/2 字重、样式名与 fvar 轴为 100–900 槽位生成锚点。
# source 时只定义函数，不执行任何操作。真正的判断全部在 common/font_capability.py：
#   - 可变字体缺某个静态字重时按 wght 轴实例化，而不是把默认实例复用到所有字重；
#   - 静态字体族按 usWeightClass + 样式名映射，缺档就近映射而不是全部落到 Regular；
#   - TTC/OTC 按字体面索引取用，不把整个集合写进单字体槽位；
#   - 斜体只服务斜体槽，正体槽不会拿到斜体（用户无斜体时斜体槽保持原厂）。
# 任何一步不可用（无 Python、无字体族文件、复合任务）时返回非 0，调用方沿用原有映射。

luoshu_cap_module() {
    printf '%s\n' "${LUOSHU_REAL_MODDIR:-${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}}"
}

luoshu_cap_exec() {
    _lce_module=$(luoshu_cap_module)
    _lce_tool="$_lce_module/common/font_capability.py"
    [ -f "$_lce_tool" ] || return 127
    if [ -n "${LUOSHU_CAPABILITY_PYTHON:-}" ]; then
        PYTHONPATH="$_lce_module/common${PYTHONPATH:+:$PYTHONPATH}" \
            "$LUOSHU_CAPABILITY_PYTHON" "$_lce_tool" "$@"
        return $?
    fi
    _lce_root="$_lce_module/common/python"
    _lce_bin="$_lce_root/bin/luoshu-python"
    [ -x "$_lce_bin" ] || return 127
    PYTHONHOME="$_lce_root" \
    PYTHONPATH="$_lce_module/common:$_lce_root/lib/python3.14:$_lce_root/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$_lce_root/lib:$_lce_root/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$_lce_bin" "$_lce_tool" "$@"
}

# 与 font_capability.weight_from_name 一致：ExtraBold/UltraLight/SemiBold 先于 Bold/Light，
# Highlight 不是 Light。未声明字重时输出 400。
luoshu_cap_slot_weight() {
    _lcsw_name=${1##*/}
    _lcsw_stem=${_lcsw_name%.*}
    case "$_lcsw_stem" in
        100|200|300|350|400|500|600|700|800|900) printf '%s\n' "$_lcsw_stem"; return 0 ;;
    esac
    _lcsw_lower=$(printf '%s' "$_lcsw_stem" | tr '[:upper:]' '[:lower:]' | tr -d ' _-')
    case "$_lcsw_lower" in
        *extrablack*|*ultrablack*) printf '900\n' ;;
        *extrabold*|*ultrabold*) printf '800\n' ;;
        *semibold*|*demibold*) printf '600\n' ;;
        *extralight*|*ultralight*) printf '200\n' ;;
        *extrathin*|*ultrathin*|*xthin*|*hairline*) printf '100\n' ;;
        *black*|*heavy*) printf '900\n' ;;
        *bold*) printf '700\n' ;;
        *medium*) printf '500\n' ;;
        *highlight*) printf '400\n' ;;
        *light*) printf '300\n' ;;
        *thin*) printf '100\n' ;;
        *) printf '400\n' ;;
    esac
}

# 声明为可变字体的 ROM 槽位（MiSansVF、GoogleSans-VF、RobotoFlex…）保留 fvar 轴，
# 不能换成单一静态实例。
luoshu_cap_is_variable_slot() {
    case "${1##*/}" in
        *VF.*|*VF_*|*VF-*|*-VF*|*_VF*|*Variable*|*Flex*) return 0 ;;
    esac
    return 1
}

luoshu_cap_is_italic_slot() {
    case "${1##*/}" in *[Ii]talic*|*[Oo]blique*) return 0 ;; esac
    return 1
}

luoshu_cap_is_emoji_slot() {
    case "${1##*/}" in *[Ee]moji*|*EMOJI*) return 0 ;; esac
    return 1
}

# 字体族文件（同一 detect_font_family 结果），逐行输出完整路径。
luoshu_cap_family_files() {
    _lcff_family="$1"
    [ -n "$_lcff_family" ] && [ -d "${USER_FONTS_DIR:-}" ] || return 1
    type detect_font_family >/dev/null 2>&1 || return 1
    for _lcff_file in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc "$USER_FONTS_DIR"/*.otc \
                      "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC "$USER_FONTS_DIR"/*.OTC; do
        [ -f "$_lcff_file" ] || continue
        [ "$(detect_font_family "${_lcff_file##*/}")" = "$_lcff_family" ] || continue
        printf '%s\n' "$_lcff_file"
    done
}

# luoshu_cap_anchors <store> <family> <weights> <prefix> [italic] [fallback-file] [variable-anchor]
# 输出 "weight|file|mode"；失败或没有可用字体面时返回非 0。
luoshu_cap_anchors() {
    _lca2_store="$1"; _lca2_family="$2"; _lca2_weights="$3"; _lca2_prefix="$4"
    _lca2_italic="${5:-}"; _lca2_fallback="${6:-}"; _lca2_variable="${7-variable.font}"
    [ -z "${LUOSHU_MIX_REQUEST_ID:-}" ] || return 1
    [ "${LUOSHU_CAPABILITY_DISABLE:-0}" = 1 ] && return 1
    [ -n "$_lca2_store" ] || return 1
    _lca2_list=$(luoshu_cap_family_files "$_lca2_family" 2>/dev/null)
    [ -n "$_lca2_list" ] || _lca2_list="$_lca2_fallback"
    [ -n "$_lca2_list" ] || return 1
    set --
    while IFS= read -r _lca2_file; do
        [ -f "$_lca2_file" ] && set -- "$@" "$_lca2_file"
    done <<EOF_LCA2
$_lca2_list
EOF_LCA2
    [ "$#" -gt 0 ] || return 1
    if [ "$_lca2_italic" = italic ]; then
        luoshu_cap_exec anchors --store "$_lca2_store" --prefix "$_lca2_prefix" --italic \
            --weights "$_lca2_weights" "$@" 2>/dev/null
    else
        luoshu_cap_exec anchors --store "$_lca2_store" --prefix "$_lca2_prefix" \
            --weights "$_lca2_weights" --variable-anchor "$_lca2_variable" "$@" 2>/dev/null
    fi
}

luoshu_cap_weight_anchors() {
    luoshu_cap_anchors "$1" "$2" "${3:-100,200,300,400,500,600,700,800,900}" wght- '' "${4:-}"
}

luoshu_cap_italic_anchors() {
    luoshu_cap_anchors "$1" "$2" "${3:-100,200,300,400,500,600,700,800,900}" italic-wght- italic "${4:-}"
}

# 字体集合（.ttc/.otc）不能整份写进单字体槽位。
luoshu_cap_is_collection() {
    [ "$(dd if="$1" bs=4 count=1 2>/dev/null)" = ttcf ]
}
