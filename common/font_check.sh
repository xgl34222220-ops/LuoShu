#!/system/bin/sh
# LuoShu - 字体文件真实格式与基础兼容性检测
# 只读取文件，不修改字体。

# 同一个字体在一次 shell 进程中通常会连续经过格式、完整性、可变字体和彩色字体检查。
# 缓存前 128 KiB 中出现的 SFNT 表标签，避免每个标签都重新 dd 一遍大字体文件。
FONT_TABLE_CACHE_FILE=""
FONT_TABLE_CACHE_TAGS=""
FONT_TABLE_CACHE_READY="false"

font_magic_hex() {
    dd if="$1" bs=1 count=4 2>/dev/null | od -An -tx1 | tr -d ' \n\r'
}

font_table_token() {
    case "$1" in
        'SVG ') printf '%s\n' 'SVG_' ;;
        *) printf '%s\n' "$1" ;;
    esac
}

font_table_cache_load() {
    _ftc_file="$1"
    FONT_TABLE_CACHE_FILE="$_ftc_file"
    # SFNT 表目录位于文件头部。一次读取后提取洛书关心的全部标签；命令替换只保存
    # 匹配到的 ASCII 标签，不会把字体二进制内容放进 shell 变量。
    FONT_TABLE_CACHE_TAGS=$(
        dd if="$_ftc_file" bs=65536 count=2 2>/dev/null | \
            grep -a -o -E 'cmap|head|maxp|fvar|COLR|CBDT|sbix|SVG ' 2>/dev/null | \
            sed 's/^SVG $/SVG_/' | \
            sort -u 2>/dev/null | \
            tr '\n' '|'
    )
    if [ -n "$FONT_TABLE_CACHE_TAGS" ]; then
        FONT_TABLE_CACHE_READY="true"
    else
        FONT_TABLE_CACHE_READY="false"
    fi
}

font_has_table() {
    _fht_file="$1"
    _fht_tag="$2"
    case "$_fht_tag" in
        cmap|head|maxp|fvar|COLR|CBDT|sbix|'SVG ')
            if [ "$FONT_TABLE_CACHE_READY" = "true" ] && [ "$FONT_TABLE_CACHE_FILE" = "$_fht_file" ]; then
                _fht_token=$(font_table_token "$_fht_tag")
                case "|$FONT_TABLE_CACHE_TAGS" in
                    *"|${_fht_token}|"*) return 0 ;;
                    *) return 1 ;;
                esac
            fi
            ;;
    esac
    # 兼容未知标签或极少数 grep 不支持 -o/-E 的环境。
    dd if="$_fht_file" bs=65536 count=2 2>/dev/null | grep -a -q "$_fht_tag"
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

    font_table_cache_load "$_file"

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

# ---------------------------------------------------------------------------
# 网页字体导入（WOFF/WOFF2）
# font_validate 对网页字体始终按原文案拒绝；导入流程改调 font_prepare_import：
# 网页字体先解包为真实 SFNT，再把解包结果交给 font_validate 做同样的完整检查。
#   font_prepare_import SRC WORKDIR [purpose]
#   成功：FONT_PREPARED_PATH=可直接导入的文件（普通字体即 SRC 本身），
#         FONT_PREPARED_FROM=WOFF/WOFF2（普通字体为空）
#   失败：FONT_CHECK_ERROR 与 font_validate 的原文案一致，FONT_WEB_REASON=转换失败原因
# ---------------------------------------------------------------------------
font_check_run_python() {
    _fcrp_mod="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
    _fcrp_root="$_fcrp_mod/common/python"
    if [ -n "${LUOSHU_IMPORT_PYTHON:-}" ]; then
        "$LUOSHU_IMPORT_PYTHON" "$@"
    elif [ -x "$_fcrp_root/bin/luoshu-python" ]; then
        PYTHONHOME="$_fcrp_root" \
            PYTHONPATH="$_fcrp_root/lib/python3.14:$_fcrp_root/lib/python3.14/site-packages" \
            LD_LIBRARY_PATH="$_fcrp_root/lib:$_fcrp_root/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
            "$_fcrp_root/bin/luoshu-python" "$@"
    else
        return 127
    fi
}

font_json_field() {
    printf '%s' "$1" | sed -n "s/.*\"$2\":\"\([^\"]*\)\".*/\1/p"
}

font_unwrap_web() {
    _fuw_src="$1"; _fuw_dir="$2"; _fuw_stem="${3:-}"
    FONT_WEB_OUTPUT=""; FONT_WEB_REASON=""
    _fuw_tool="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}/common/font_web_convert.py"
    if [ ! -f "$_fuw_tool" ]; then FONT_WEB_REASON="网页字体转换组件缺失"; return 1; fi
    mkdir -p "$_fuw_dir" 2>/dev/null || { FONT_WEB_REASON="无法创建转换目录"; return 1; }
    if [ -n "$_fuw_stem" ]; then
        _fuw_out=$(font_check_run_python "$_fuw_tool" "$_fuw_src" "$_fuw_dir" --name "$_fuw_stem" 2>/dev/null)
    else
        _fuw_out=$(font_check_run_python "$_fuw_tool" "$_fuw_src" "$_fuw_dir" 2>/dev/null)
    fi
    _fuw_rc=$?
    if [ "$_fuw_rc" -eq 127 ] && [ -z "$_fuw_out" ]; then FONT_WEB_REASON="缺少字体处理运行时"; return 1; fi
    _fuw_out=$(printf '%s\n' "$_fuw_out" | grep '^{' | tail -n 1)
    case "$_fuw_out" in
        '{"ok":true'*)
            FONT_WEB_OUTPUT=$(font_json_field "$_fuw_out" output)
            [ -n "$FONT_WEB_OUTPUT" ] && [ -f "$FONT_WEB_OUTPUT" ] && return 0
            FONT_WEB_OUTPUT=""; FONT_WEB_REASON="转换结果缺失"; return 1 ;;
    esac
    FONT_WEB_REASON=$(font_json_field "$_fuw_out" error)
    [ -n "$FONT_WEB_REASON" ] || FONT_WEB_REASON="转换失败"
    return 1
}

font_prepare_import() {
    _fpi_src="$1"; _fpi_dir="$2"; _fpi_purpose="${3:-text}"
    FONT_PREPARED_PATH=""; FONT_PREPARED_FROM=""; FONT_WEB_REASON=""
    _fpi_fmt=$(font_detect_format "$_fpi_src" 2>/dev/null)
    case "$_fpi_fmt" in
        WOFF|WOFF2) ;;
        *)
            font_validate "$_fpi_src" "$_fpi_purpose" || return 1
            FONT_PREPARED_PATH="$_fpi_src"
            return 0 ;;
    esac
    # 先跑一次 font_validate 拿到原始拒绝文案与大小门槛（过小的文件不尝试转换）。
    font_validate "$_fpi_src" "$_fpi_purpose" && { FONT_PREPARED_PATH="$_fpi_src"; return 0; }
    _fpi_reject="$FONT_CHECK_ERROR"
    case "$FONT_CHECK_FORMAT" in WOFF|WOFF2) ;; *) return 1 ;; esac
    _fpi_name=$(basename "$_fpi_src"); _fpi_name="${_fpi_name%.*}"
    if ! font_unwrap_web "$_fpi_src" "$_fpi_dir" "$_fpi_name"; then
        FONT_CHECK_FORMAT="$_fpi_fmt"
        FONT_CHECK_ERROR="$_fpi_reject"
        return 1
    fi
    if ! font_validate "$FONT_WEB_OUTPUT" "$_fpi_purpose"; then
        FONT_WEB_REASON="转换结果未通过校验：$FONT_CHECK_ERROR"
        rm -f "$FONT_WEB_OUTPUT" 2>/dev/null || true
        FONT_CHECK_FORMAT="$_fpi_fmt"
        FONT_CHECK_ERROR="$_fpi_reject"
        return 1
    fi
    FONT_PREPARED_PATH="$FONT_WEB_OUTPUT"
    FONT_PREPARED_FROM="$_fpi_fmt"
    FONT_CHECK_WARNING="由 $_fpi_fmt 网页字体解包为 $FONT_CHECK_FORMAT${FONT_CHECK_WARNING:+；$FONT_CHECK_WARNING}"
    return 0
}

# 用作“全局字体”前额外检查常用中文、英文、数字和标点。这个门禁只读取
# cmap，不修改字体；复合字体的中文/英文/数字分槽校验仍由复合引擎负责。
font_validate_global() {
    _file="$1"
    font_validate "$_file" text || return 1
    _module="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
    _python="$_module/common/python/bin/luoshu-python"
    _checker="$_module/common/font_coverage.py"
    FONT_CHECK_COVERAGE=""
    if [ ! -x "$_python" ] || [ ! -f "$_checker" ]; then
        FONT_CHECK_WARNING="${FONT_CHECK_WARNING:+$FONT_CHECK_WARNING；}未运行字形覆盖门禁"
        return 0
    fi
    _pyroot="$_module/common/python"
    FONT_CHECK_COVERAGE=$(PYTHONHOME="$_pyroot" \
        PYTHONPATH="$_pyroot/lib/python3.14:$_pyroot/lib/python3.14/site-packages" \
        LD_LIBRARY_PATH="$_pyroot/lib:$_pyroot/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$_python" "$_checker" --brief "$_file" 2>/dev/null)
    _coverage_code=$?
    if [ "$_coverage_code" -ne 0 ]; then
        [ -n "$FONT_CHECK_COVERAGE" ] || FONT_CHECK_COVERAGE="字体缺少全局替换所需字形"
        FONT_CHECK_ERROR="$FONT_CHECK_COVERAGE；请改用复合字体功能或更完整的字体"
        return 1
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

font_check_cli() {
    # 网页字体在临时目录解包后检查，结束即删除；普通字体走原逻辑。
    _fcc_target="${1:-}"; [ "$_fcc_target" = "--json" ] && _fcc_target="${2:-}"
    _fcc_work=""
    if [ -n "$_fcc_target" ] && [ -f "$_fcc_target" ]; then
        case "$(font_detect_format "$_fcc_target")" in
            WOFF|WOFF2)
                _fcc_work=$(mktemp -d "${TMPDIR:-/data/local/tmp}/luoshu-webfont.XXXXXX" 2>/dev/null || mktemp -d 2>/dev/null) || _fcc_work=""
                ;;
        esac
    fi
    if [ -n "$_fcc_work" ]; then
        font_check_cli_web "$@"; _fcc_rc=$?
        rm -rf "$_fcc_work" 2>/dev/null || true
        return "$_fcc_rc"
    fi
    font_check_cli_plain "$@"
}

font_check_cli_web() {
    if [ "${1:-}" = "--json" ]; then
        if font_prepare_import "${2:-}" "$_fcc_work" "${3:-text}"; then
            printf '{"valid":true,"format":"%s","source":"%s","bytes":%s,"variable":%s,"color":%s,"warning":"%s"}\n' \
                "$FONT_CHECK_FORMAT" "$FONT_PREPARED_FROM" "$FONT_CHECK_SIZE" "$FONT_CHECK_VARIABLE" "$FONT_CHECK_COLOR" "$FONT_CHECK_WARNING"
            return 0
        fi
        printf '{"valid":false,"format":"%s","bytes":%s,"variable":%s,"color":%s,"error":"%s","reason":"%s"}\n' \
            "$FONT_CHECK_FORMAT" "$FONT_CHECK_SIZE" "$FONT_CHECK_VARIABLE" "$FONT_CHECK_COLOR" "$FONT_CHECK_ERROR" "$FONT_WEB_REASON"
        return 1
    fi
    if font_prepare_import "$1" "$_fcc_work" "${2:-text}"; then
        echo "状态: 通过"
        echo "原始格式: $FONT_PREPARED_FROM"
        echo "真实格式: $FONT_CHECK_FORMAT"
        echo "文件大小: $FONT_CHECK_SIZE bytes"
        echo "可变字体: $FONT_CHECK_VARIABLE"
        echo "彩色字体表: $FONT_CHECK_COLOR"
        [ -n "$FONT_CHECK_WARNING" ] && echo "提示: $FONT_CHECK_WARNING"
        return 0
    fi
    echo "状态: 失败"
    echo "原因: $FONT_CHECK_ERROR"
    [ -n "$FONT_WEB_REASON" ] && echo "转换: $FONT_WEB_REASON"
    return 1
}

font_check_cli_plain() {
    if [ "${1:-}" = "--json" ]; then
        font_check_json "${2:-}" "${3:-text}"
    elif [ -n "${1:-}" ] && [ -f "${1:-}" ]; then
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
            return 1
        fi
    fi
}

# 只有直接执行 font_check.sh 时才进入 CLI。被 font_manager/native_import 等脚本
# source 时，必须只定义函数，不能消费父脚本的位置参数，更不能 exit 父进程。
case "${0##*/}" in
    font_check.sh)
        if [ -z "${MODULE_DIR:-${MODDIR:-}}" ]; then
            MODULE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." 2>/dev/null && pwd)
        fi
        font_check_cli "$@"
        ;;
esac
