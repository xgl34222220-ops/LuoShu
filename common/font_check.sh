#!/system/bin/sh
# LuoShu font validation and real metadata bootstrap.
set +e

MODULE_DIR="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"

font_magic_hex() { dd if="$1" bs=1 count=4 2>/dev/null | od -An -tx1 | tr -d ' \n\r'; }
font_detect_format() {
    case "$(font_magic_hex "$1")" in
        00010000|74727565|00020000) echo TTF ;; 4f54544f) echo OTF ;; 74746366) echo TTC ;;
        774f4646) echo WOFF ;; 774f4632) echo WOFF2 ;; 504b0304) echo ZIP ;; *) echo UNKNOWN ;;
    esac
}
font_has_table() { dd if="$1" bs=65536 count=2 2>/dev/null | grep -a -q "$2"; }

font_validate() {
    _file="$1"; _purpose="${2:-text}"
    FONT_CHECK_FORMAT=UNKNOWN; FONT_CHECK_SIZE=0; FONT_CHECK_VARIABLE=false; FONT_CHECK_COLOR=false
    FONT_CHECK_WARNING=""; FONT_CHECK_ERROR=""
    [ -f "$_file" ] || { FONT_CHECK_ERROR="字体文件不存在"; return 1; }
    FONT_CHECK_SIZE=$(wc -c <"$_file" 2>/dev/null | tr -d '[:space:]'); case "$FONT_CHECK_SIZE" in ''|*[!0-9]*) FONT_CHECK_SIZE=0 ;; esac
    [ "$FONT_CHECK_SIZE" -ge 4096 ] 2>/dev/null || { FONT_CHECK_ERROR="字体文件过小（${FONT_CHECK_SIZE} 字节），可能损坏或不是字体"; return 1; }
    FONT_CHECK_FORMAT=$(font_detect_format "$_file")
    case "$FONT_CHECK_FORMAT" in
        TTF|OTF|TTC) ;;
        WOFF|WOFF2) FONT_CHECK_ERROR="检测到网页字体 $FONT_CHECK_FORMAT，不能直接作为系统字体"; return 1 ;;
        ZIP) FONT_CHECK_ERROR="检测到 ZIP 压缩包，请使用字体模块导入功能"; return 1 ;;
        *) FONT_CHECK_ERROR="无法识别真实字体格式（文件头 $(font_magic_hex "$_file")）"; return 1 ;;
    esac
    font_has_table "$_file" cmap || { FONT_CHECK_ERROR="字体缺少 cmap 字符映射表"; return 1; }
    if [ "$FONT_CHECK_FORMAT" != TTC ]; then
        font_has_table "$_file" head || { FONT_CHECK_ERROR="字体缺少 head 表，文件可能损坏"; return 1; }
        font_has_table "$_file" maxp || { FONT_CHECK_ERROR="字体缺少 maxp 表，文件可能损坏"; return 1; }
    fi
    font_has_table "$_file" fvar && FONT_CHECK_VARIABLE=true
    if font_has_table "$_file" COLR || font_has_table "$_file" CBDT || font_has_table "$_file" sbix || font_has_table "$_file" 'SVG '; then FONT_CHECK_COLOR=true; fi
    if [ "$_purpose" = emoji ]; then
        [ "$FONT_CHECK_COLOR" = true ] || FONT_CHECK_WARNING="未检测到常见彩色 Emoji 表，可能只显示单色字形"
    elif [ "$FONT_CHECK_FORMAT" = TTC ]; then
        FONT_CHECK_WARNING="TTC 字体集合兼容性取决于 ROM"
    fi
    return 0
}

font_validate_global() {
    _file="$1"; font_validate "$_file" text || return 1
    _python="$MODULE_DIR/common/python/bin/luoshu-python"; _checker="$MODULE_DIR/common/font_coverage.py"; FONT_CHECK_COVERAGE=""
    if [ ! -x "$_python" ] || [ ! -f "$_checker" ]; then
        FONT_CHECK_WARNING="${FONT_CHECK_WARNING:+$FONT_CHECK_WARNING；}未运行字形覆盖门禁"; return 0
    fi
    _pyroot="$MODULE_DIR/common/python"
    FONT_CHECK_COVERAGE=$(PYTHONHOME="$_pyroot" PYTHONPATH="$_pyroot/lib/python3.14:$_pyroot/lib/python3.14/site-packages" \
        LD_LIBRARY_PATH="$_pyroot/lib:$_pyroot/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$_python" "$_checker" --brief "$_file" 2>/dev/null)
    _rc=$?
    if [ "$_rc" -ne 0 ]; then
        [ -n "$FONT_CHECK_COVERAGE" ] || FONT_CHECK_COVERAGE="字体缺少全局替换所需字形"
        FONT_CHECK_ERROR="$FONT_CHECK_COVERAGE；请改用复合字体功能或更完整的字体"; return 1
    fi
    return 0
}

font_check_json() {
    _file="$1"; _purpose="${2:-text}"
    if font_validate "$_file" "$_purpose"; then
        printf '{"valid":true,"format":"%s","bytes":%s,"variable":%s,"color":%s,"warning":"%s"}\n' \
            "$FONT_CHECK_FORMAT" "$FONT_CHECK_SIZE" "$FONT_CHECK_VARIABLE" "$FONT_CHECK_COLOR" "$FONT_CHECK_WARNING"
    else
        printf '{"valid":false,"format":"%s","bytes":%s,"variable":%s,"color":%s,"error":"%s"}\n' \
            "$FONT_CHECK_FORMAT" "$FONT_CHECK_SIZE" "$FONT_CHECK_VARIABLE" "$FONT_CHECK_COLOR" "$FONT_CHECK_ERROR"; return 1
    fi
}

# This is intentionally loaded after util_functions.sh so metadata-aware functions replace filename guessing.
[ -f "$MODULE_DIR/common/font_metadata_runtime.sh" ] && . "$MODULE_DIR/common/font_metadata_runtime.sh"

if [ "$1" = --json ]; then
    font_check_json "$2" "${3:-text}"
elif [ -n "$1" ] && [ -f "$1" ]; then
    if font_validate "$1" "${2:-text}"; then
        echo "状态: 通过"; echo "真实格式: $FONT_CHECK_FORMAT"; echo "文件大小: $FONT_CHECK_SIZE bytes"
        echo "可变字体: $FONT_CHECK_VARIABLE"; echo "彩色字体表: $FONT_CHECK_COLOR"
        [ -n "$FONT_CHECK_WARNING" ] && echo "提示: $FONT_CHECK_WARNING"
    else echo "状态: 失败"; echo "原因: $FONT_CHECK_ERROR"; return 1 2>/dev/null || exit 1; fi
fi
