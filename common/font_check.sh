#!/system/bin/sh
# LuoShu v13.3 Beta2 - 字体文件真实格式与基础兼容性检测
# 只读取文件，不修改字体。

font_magic_hex() {
    dd if="$1" bs=1 count=4 2>/dev/null | od -An -tx1 | tr -d ' \n\r'
}

font_detect_format() {
    case "$(font_magic_hex "$1")" in
        00010000|74727565|00020000) echo "TTF" ;;
        4f54544f) echo "OTF" ;;
        74746366) echo "TTC" ;;
        774f4646) echo "WOFF" ;;
        774f4632) echo "WOFF2" ;;
        504b0304) echo "ZIP" ;;
        *) echo "UNKNOWN" ;;
    esac
}

font_has_table() {
    grep -a -q "$2" "$1" 2>/dev/null
}

font_validate() {
    _file="$1"
    _purpose="${2:-text}"
    FONT_CHECK_FORMAT="UNKNOWN"
    FONT_CHECK_SIZE=0
    FONT_CHECK_VARIABLE="false"
    FONT_CHECK_COLOR="false"
    FONT_CHECK_WARNING=""
    FONT_CHECK_ERROR=""

    if [ ! -f "$_file" ]; then
        FONT_CHECK_ERROR="字体文件不存在"
        return 1
    fi

    FONT_CHECK_SIZE=$(wc -c < "$_file" 2>/dev/null | tr -d '[:space:]')
    case "$FONT_CHECK_SIZE" in ''|*[!0-9]*) FONT_CHECK_SIZE=0 ;; esac
    if [ "$FONT_CHECK_SIZE" -lt 4096 ]; then
        FONT_CHECK_ERROR="字体文件过小（${FONT_CHECK_SIZE} 字节），可能损坏或不是字体"
        return 1
    fi

    FONT_CHECK_FORMAT=$(font_detect_format "$_file")
    case "$FONT_CHECK_FORMAT" in
        TTF|OTF|TTC) ;;
        WOFF|WOFF2)
            FONT_CHECK_ERROR="检测到网页字体 $FONT_CHECK_FORMAT，不能仅修改扩展名后作为系统字体"
            return 1
            ;;
        ZIP)
            FONT_CHECK_ERROR="检测到 ZIP 压缩包，请先解压出 TTF/OTF/TTC 文件"
            return 1
            ;;
        *)
            FONT_CHECK_ERROR="无法识别真实字体格式（文件头 $(font_magic_hex "$_file")）"
            return 1
            ;;
    esac

    if ! font_has_table "$_file" "cmap"; then
        FONT_CHECK_ERROR="字体缺少 cmap 字符映射表"
        return 1
    fi
    if ! font_has_table "$_file" "head" && [ "$FONT_CHECK_FORMAT" != "TTC" ]; then
        FONT_CHECK_ERROR="字体缺少 head 表，文件可能损坏"
        return 1
    fi
    if ! font_has_table "$_file" "maxp" && [ "$FONT_CHECK_FORMAT" != "TTC" ]; then
        FONT_CHECK_ERROR="字体缺少 maxp 表，文件可能损坏"
        return 1
    fi

    font_has_table "$_file" "fvar" && FONT_CHECK_VARIABLE="true"
    if font_has_table "$_file" "COLR" || font_has_table "$_file" "CBDT" || \
       font_has_table "$_file" "sbix" || font_has_table "$_file" "SVG "; then
        FONT_CHECK_COLOR="true"
    fi

    if [ "$_purpose" = "emoji" ]; then
        if [ "$FONT_CHECK_COLOR" != "true" ]; then
            FONT_CHECK_WARNING="未检测到常见彩色 Emoji 表，可能只显示单色字形"
        fi
    else
        if [ "$FONT_CHECK_FORMAT" = "TTC" ]; then
            FONT_CHECK_WARNING="TTC 字体集合兼容性取决于 ROM，建议优先使用单独的 TTF/OTF"
        fi
    fi
    return 0
}

font_check_json() {
    _file="$1"
    _purpose="${2:-text}"
    if font_validate "$_file" "$_purpose"; then
        printf '{"valid":true,"format":"%s","bytes":%s,"variable":%s,"color":%s,"warning":"%s"}\n' \
            "$FONT_CHECK_FORMAT" "$FONT_CHECK_SIZE" "$FONT_CHECK_VARIABLE" "$FONT_CHECK_COLOR" "$FONT_CHECK_WARNING"
    else
        printf '{"valid":false,"format":"%s","bytes":%s,"variable":%s,"color":%s,"error":"%s"}\n' \
            "$FONT_CHECK_FORMAT" "$FONT_CHECK_SIZE" "$FONT_CHECK_VARIABLE" "$FONT_CHECK_COLOR" "$FONT_CHECK_ERROR"
        return 1
    fi
}

# CLI
if [ "$1" = "--json" ]; then
    font_check_json "$2" "${3:-text}"
elif [ -n "$1" ] && [ -f "$1" ]; then
    if font_validate "$1" "${2:-text}"; then
        echo "状态: 通过"
        echo "真实格式: $FONT_CHECK_FORMAT"
        echo "文件大小: $FONT_CHECK_SIZE bytes"
        echo "可变字体: $FONT_CHECK_VARIABLE"
        echo "彩色字体表: $FONT_CHECK_COLOR"
        [ -n "$FONT_CHECK_WARNING" ] && echo "提示: $FONT_CHECK_WARNING"
    else
        echo "状态: 失败"
        echo "原因: $FONT_CHECK_ERROR"
        exit 1
    fi
fi
