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
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"

MESSAGE_ONLY=false
[ "${3:-}" != --message ] || MESSAGE_ONLY=true
json_escape() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r\t' '   '; }
fail_result() {
    if [ "$MESSAGE_ONLY" = true ]; then
        printf '%s\n' "$2"
    else
        printf '{"status":"error","reason":"%s","message":"%s"}\n' "$1" "$(json_escape "$2")"
    fi
}

check_family_role() {
    _family="$1"
    _role="$2"
    _last=''
    _last_rc=1
    for _font in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
                 "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_font" ] || continue
        _detected=$(detect_font_family "$(basename "$_font")")
        [ "$_detected" = "$_family" ] || continue
        if [ "$MESSAGE_ONLY" = true ]; then set -- --message; else set --; fi
        _last=$(PYTHONHOME="$PYROOT" \
            PYTHONPATH="$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages" \
            LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
            "$PYBIN" "$CHECKER" "$_font" "$_role" "$@" 2>&1)
        _last_rc=$?
        [ "$_last_rc" -eq 0 ] && { printf '%s\n' "$_last"; return 0; }
        # Exit 2 means a successfully read cmap with missing required glyphs.
        # Loader/import/permission errors must remain read errors, never a missing-font verdict.
        if [ "$MESSAGE_ONLY" != true ]; then
            case "$_last" in
                '{"status":"error",'*) ;;
                *) _last=$(fail_result runtime_failed "字体检查器运行失败：${_last:-退出码 $_last_rc}"); _last_rc=1 ;;
            esac
        elif [ "$_last_rc" -ne 2 ]; then
            case "$_last" in
                字体读取失败：*) ;;
                *) _last="字体检查器运行失败：${_last:-退出码 $_last_rc}" ;;
            esac
            _last_rc=1
        fi
    done
    if [ -z "$_last" ]; then
        fail_result source_not_found "找不到指定字体族：$_family"
        return 1
    fi
    printf '%s\n' "$_last"
    return "$_last_rc"
}

case "${2:-}" in cjk|latin|digit) ;; *) fail_result invalid_role '未指定有效的字体角色'; exit 1 ;; esac
[ -x "$PYBIN" ] && [ -f "$CHECKER" ] || {
    fail_result runtime_unavailable '字体角色检查器不可用'
    exit 1
}
check_family_role "${1:-}" "${2:-}"
