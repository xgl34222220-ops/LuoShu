#!/system/bin/sh
# 洛书 v2.0.0：按字体族 ID 返回稳定文件身份与 TTC 字体面详情。
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
INSPECTOR="$MODDIR/common/font_metadata.py"
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"

json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
}

family="${1:-}"
[ -n "$family" ] || { printf '{"status":"error","message":"未指定字体"}\n'; exit 0; }
source_file=""
for file in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
            "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
    [ -f "$file" ] || continue
    detected=$(detect_font_family "$(basename "$file")")
    [ "$detected" = "$family" ] && { source_file="$file"; break; }
done
[ -f "$source_file" ] || {
    printf '{"status":"error","message":"找不到字体：%s"}\n' "$(json_escape "$family")"
    exit 0
}
[ -x "$PYBIN" ] && [ -f "$INSPECTOR" ] || {
    printf '{"status":"error","message":"字体详情分析器不可用"}\n'
    exit 0
}
export PYTHONHOME="$PYROOT"
export PYTHONPATH="$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages"
export LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
"$PYBIN" "$INSPECTOR" "$source_file"
exit 0
