#!/system/bin/sh
# 在复合任务入队前检查中文、英文和数字角色的基础覆盖。
set +e

MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then
        MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"
    else
        MODDIR="/data/adb/modules/LuoShu"
    fi
fi
MODULE_DIR="$MODDIR"
USER_FONTS_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/fonts"
PYROOT="$MODDIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"
CHECKER="$MODDIR/common/font_role_check.py"
ROLE_CACHE="$MODDIR/cache/font-role-v1"
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"

check_family_role() {
    _family="$1"
    _role="$2"
    _last=''
    for _font in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
                 "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_font" ] || continue
        _detected=$(detect_font_family "$(basename "$_font")")
        [ "$_detected" = "$_family" ] || continue
        _last=$(PYTHONHOME="$PYROOT" \
            PYTHONPATH="$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages" \
            LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
            "$PYBIN" "$CHECKER" "$_font" "$_role" 2>/dev/null)
        [ "$?" -eq 0 ] && { printf '%s\n' "$_last"; return 0; }
    done
    [ -n "$_last" ] || _last='{"status":"error","message":"找不到指定字体族"}'
    printf '%s\n' "$_last"
    return 1
}

[ -x "$PYBIN" ] && [ -f "$CHECKER" ] || {
    printf '{"status":"error","message":"字体角色检查器不可用"}\n'
    exit 1
}
check_family_role "${1:-}" "${2:-}"
