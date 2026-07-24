#!/system/bin/sh
# 根据字体能力和当前 wght 判断组合槽位是否仍处于自动多字重状态。

mix_role_weight() {
    case "$1" in
        thin) echo 100 ;; extralight) echo 200 ;; light) echo 300 ;; regular|normal) echo 400 ;;
        medium) echo 500 ;; semibold) echo 600 ;; bold) echo 700 ;; extrabold) echo 800 ;;
        black|heavy) echo 900 ;; *) echo 400 ;;
    esac
}

mix_axis_weight() {
    _spec="$1"
    _value=$(printf '%s' "$_spec" | tr ',' '\n' | sed -n 's/^wght=//p' | head -n1)
    _value=${_value%%.*}
    case "$_value" in ''|*[!0-9]*) _value=400 ;; esac
    [ "$_value" -ge 1 ] 2>/dev/null || _value=1
    [ "$_value" -le 1000 ] 2>/dev/null || _value=1000
    printf '%s\n' "$_value"
}

mix_find_family_source() {
    _family="$1"
    _variable=''
    _regular=''
    _first=''
    for _font in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
                 "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_font" ] || continue
        [ "$(detect_font_family "$(basename "$_font")")" = "$_family" ] || continue
        [ -n "$_first" ] || _first="$_font"
        if is_variable_font "$_font" 2>/dev/null; then
            [ -n "$_variable" ] || _variable="$_font"
            continue
        fi
        if [ "$(detect_font_weight "$(basename "$_font")")" = regular ] && [ -z "$_regular" ]; then
            _regular="$_font"
        fi
    done
    for _candidate in "$_variable" "$_regular" "$_first"; do
        [ -f "$_candidate" ] && { printf '%s\n' "$_candidate"; return 0; }
    done
    return 1
}

# 输出 wght 的 fvar 默认值；没有 wght 轴时输出空字符串。
mix_variable_default_weight() {
    _source="$1"
    _pyroot="${MODDIR:-/data/adb/modules/LuoShu}/common/python"
    _python="$_pyroot/bin/luoshu-python"
    [ -x "$_python" ] || return 0
    PYTHONHOME="$_pyroot" \
    PYTHONPATH="$_pyroot/lib/python3.14:$_pyroot/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$_pyroot/lib:$_pyroot/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$_python" -c 'import sys
from fontTools.ttLib import TTFont
font=TTFont(sys.argv[1], lazy=True)
value=None
if "fvar" in font:
    for axis in font["fvar"].axes:
        if axis.axisTag == "wght":
            value=round(float(axis.defaultValue)); break
if value is not None:
    print(max(1,min(1000,int(value))))' "$_source" 2>/dev/null || true
}

mix_static_default_weight() {
    _family="$1"
    _weights=$(scan_family_weights "$_family" 2>/dev/null)
    case ",$_weights," in *,regular,*) echo 400; return ;; esac
    _first=$(printf '%s' "$_weights" | tr ',' '\n' | sed -n '1p')
    mix_role_weight "$_first"
}

infer_mix_weight_mode() {
    _family="$1"
    _axes="$2"
    _source=$(mix_find_family_source "$_family")
    [ -f "$_source" ] || { echo fixed; return; }
    _current=$(mix_axis_weight "$_axes")
    if is_variable_font "$_source" 2>/dev/null; then
        _default=$(mix_variable_default_weight "$_source")
        [ -n "$_default" ] && [ "$_current" = "$_default" ] && echo auto || echo fixed
        return
    fi

    # 静态多字重家族过去会在默认 400 时被自动展开为 100–900 九个复合文件。
    # 用户只选择了当前字重，却被迫等待整套家族生成；六档静态字体通常要重复执行
    # 六次大体积 CJK 合并。静态字体现在始终按当前所选字重走快速单文件组合。
    # 多个静态字重仍可在界面中逐档选择，但不会再被无提示地扩展成九档任务。
    echo fixed
}
