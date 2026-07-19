#!/system/bin/sh
# 洛书 v14.3 Alpha1.5：按字体族定位真实源文件并输出字形覆盖诊断。
set +e

MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then
        MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"
    else
        MODDIR="/data/adb/modules/LuoShu"
    fi
fi

USER_FONTS_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/fonts"
PYROOT="$MODDIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"
ANALYZER="$MODDIR/common/font_coverage_info.py"

[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"

json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
}

fail_json() {
    printf '{"status":"error","message":"%s"}\n' "$(json_escape "$1")"
    exit 1
}

family="${1:-}"
[ -n "$family" ] || fail_json "未指定字体族"
[ -x "$PYBIN" ] && [ -f "$ANALYZER" ] || fail_json "字体覆盖诊断组件不可用"

source_file=""
if type get_weight_file >/dev/null 2>&1; then
    source_file="$(get_weight_file "$family" regular 2>/dev/null)"
    [ -f "$source_file" ] || source_file="$(get_weight_file "$family" medium 2>/dev/null)"
    [ -f "$source_file" ] || source_file="$(get_weight_file "$family" bold 2>/dev/null)"
fi

if [ ! -f "$source_file" ]; then
    for candidate in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
                     "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$candidate" ] || continue
        if type detect_font_family >/dev/null 2>&1; then
            detected="$(detect_font_family "$(basename "$candidate")")"
        else
            detected="$(basename "$candidate")"
            detected="${detected%.*}"
        fi
        [ "$detected" = "$family" ] || continue
        source_file="$candidate"
        break
    done
fi

[ -f "$source_file" ] || fail_json "找不到字体族对应的真实文件"

export PYTHONHOME="$PYROOT"
export PYTHONPATH="$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages"
export LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$PYBIN" "$ANALYZER" "$source_file"
