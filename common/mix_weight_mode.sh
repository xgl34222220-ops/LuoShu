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
    _variable=''; _regular=''; _first=''
    for _font in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
                 "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_font" ] || continue
        [ "$(detect_font_family "$(basename "$_font")")" = "$_family" ] || continue
        [ -n "$_first" ] || _first="$_font"
        if is_variable_font "$_font" 2>/dev/null; then
            [ -n "$_variable" ] || _variable="$_font"
            continue
        fi
        if [ "$(detect_font_weight "$(basename "$_font")")" = regular ]; then
            [ -n "$_regular" ] || _regular="$_font"
        fi
    done
    for _candidate in "$_variable" "$_regular" "$_first"; do
        [ -f "$_candidate" ] && { printf '%s\n' "$_candidate"; return 0; }
    done
    return 1
}

mix_variable_default_weight() {
    _source="$1"
    _pyroot="${MODDIR:-/data/adb/modules/LuoShu}/common/python"
    _python="$_pyroot/bin/luoshu-python"
    [ -x "$_python" ] || { echo 400; return; }
    PYTHONHOME="$_pyroot" \
    PYTHONPATH="$_pyroot/lib/python3.14:$_pyroot/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$_pyroot/lib:$_pyroot/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$_python" -c 'import sys
from fontTools.ttLib import TTFont
font=TTFont(sys.argv[1], lazy=True)
value=400
if "fvar" in font:
    for axis in font["fvar"].axes:
        if axis.axisTag == "wght":
            value=round(float(axis.defaultValue)); break
print(max(1,min(1000,int(value))))' "$_source" 2>/dev/null || echo 400
}

mix_static_default_weight() {
    _family="$1"
    _weights=$(scan_family_weights "$_family" 2>/dev/null)
    case ",$_weights," in *,regular,*) echo 400; return ;; esac
    _first=$(printf '%s' "$_weights" | tr ',' '\n' | sed -n '1p')
    mix_role_weight "$_first"
}

infer_mix_weight_mode() {
    _family="$1"; _axes="$2"
    _source=$(mix_find_family_source "$_family")
    [ -f "$_source" ] || { echo fixed; return; }
    _current=$(mix_axis_weight "$_axes")
    if is_variable_font "$_source" 2>/dev/null; then
        _default=$(mix_variable_default_weight "$_source")
        [ "$_current" = "$_default" ] && echo auto || echo fixed
        return
    fi
    _weights=$(scan_family_weights "$_family" 2>/dev/null)
    _count=$(printf '%s' "$_weights" | tr ',' '\n' | grep -c . 2>/dev/null)
    case "$_count" in ''|*[!0-9]*) _count=0 ;; esac
    [ "$_count" -ge 2 ] 2>/dev/null || { echo fixed; return; }
    _default=$(mix_static_default_weight "$_family")
    [ "$_current" = "$_default" ] && echo auto || echo fixed
}
