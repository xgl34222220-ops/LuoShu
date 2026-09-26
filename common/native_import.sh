#!/system/bin/sh
# 洛书 v2.0.0：原生 App 文件选择器导入桥。
# 只接受 App 私有缓存中的文件；真实格式由内容识别，模块脚本不会执行。
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
USER_IMPORT_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/import"
PYROOT="$MODDIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"
MAX_BYTES=268435456

[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/font_check.sh" ] && . "$MODDIR/common/font_check.sh"
[ -f "$MODDIR/common/font_import.sh" ] && . "$MODDIR/common/font_import.sh"
[ -f "$MODDIR/common/font_import_compat.sh" ] && . "$MODDIR/common/font_import_compat.sh"

json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
}

fail_json() {
    printf '{"status":"error","message":"%s"}\n' "$(json_escape "$1")"
    return 1
}

trusted_source() {
    case "$1" in
        /data/user/0/io.github.xgl34222220.luoshu/cache/native_import/*|\
        /data/data/io.github.xgl34222220.luoshu/cache/native_import/*|\
        /data/user/0/io.github.xgl34222220.luoshu.debug/cache/native_import/*|\
        /data/data/io.github.xgl34222220.luoshu.debug/cache/native_import/*|\
        /data/user/0/io.github.xgl34222220.luoshu.preview/cache/native_import/*|\
        /data/data/io.github.xgl34222220.luoshu.preview/cache/native_import/*) return 0 ;;
    esac
    return 1
}

file_hash() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" 2>/dev/null | awk '{print $1}'
    elif command -v busybox >/dev/null 2>&1; then
        busybox sha256sum "$1" 2>/dev/null | awk '{print $1}'
    else
        return 1
    fi
}

safe_stem() {
    _name=$(basename "$1" 2>/dev/null)
    _name="${_name%.*}"
    _name=$(printf '%s' "$_name" | tr -d '\r\n' | sed -E '
        s/[[:cntrl:]]//g;
        s#[\\/:*?"<>|]+#-#g;
        s/[[:space:]]+/ /g;
        s/^[ .-]+//;
        s/[ .-]+$//')
    _name=$(printf '%s' "$_name" | cut -c1-80)
    [ -n "$_name" ] || _name="ImportedFont"
    printf '%s\n' "$_name"
}

invalidate_font_cache() {
    rm -f "$MODDIR/config/native_font_index.json" \
          "$MODDIR/config/native_font_index.key" \
          "$MODDIR/config/recent_fonts.conf" 2>/dev/null || true
}

import_font_file() {
    mkdir -p "$IMPORT_CACHE_DIR" "$USER_FONTS_DIR" 2>/dev/null || { fail_json "无法创建导入目录"; return; }
    _result=$(import_run_engine --input "$1" --output-dir "$USER_FONTS_DIR" --label "$2")
    _rc=$?
    if [ "$_rc" -eq 0 ]; then invalidate_font_cache; fi
    [ -n "$_result" ] && printf '%s\n' "$_result" || fail_json "字体导入没有返回结果"
}

import_zip_file() {
    _src="$1"
    _display="$2"
    type import_zip_package >/dev/null 2>&1 || {
        fail_json "安全字体模块导入器不可用"
        return
    }
    mkdir -p "$USER_IMPORT_DIR" 2>/dev/null || { fail_json "无法创建导入目录"; return; }
    _hash=$(file_hash "$_src")
    [ -n "$_hash" ] || { fail_json "无法计算 ZIP SHA-256"; return; }
    _stem=$(safe_stem "$_display")
    _target="$USER_IMPORT_DIR/${_stem}.zip"
    [ ! -e "$_target" ] || _target="$USER_IMPORT_DIR/${_stem}-$(printf '%s' "$_hash" | cut -c1-10).zip"
    cp -f "$_src" "$_target" 2>/dev/null || { fail_json "无法复制 ZIP 到安全导入目录"; return; }
    chmod 0644 "$_target" 2>/dev/null || true

    _error_file="$MODDIR/cache/native-import-zip-error.$$"
    mkdir -p "${_error_file%/*}" 2>/dev/null || true
    _result=$(import_zip_package "$(basename "$_target")" 2>"$_error_file")
    _rc=$?
    _stderr=$(tail -n 6 "$_error_file" 2>/dev/null | tr '\n\r' '  ')
    rm -f "$_error_file" "$_target" 2>/dev/null || true
    invalidate_font_cache

    _json=$(printf '%s\n' "$_result" | sed -n '/^[[:space:]]*{/p' | tail -n1)
    if [ -n "$_json" ]; then
        printf '%s\n' "$_json"
    else
        _detail=$(printf '%s' "${_stderr:-$_result}" | sed -E 's/[[:space:]]+/ /g; s/^ //; s/ $//' | cut -c1-180)
        [ -n "$_detail" ] || _detail="安全导入器没有返回结果（代码 $_rc）"
        fail_json "字体模块 ZIP 导入失败：$_detail"
    fi
}

source_path="${1:-}"
display_name="${2:-}"
[ -n "$source_path" ] || { fail_json "未指定待导入文件"; exit 0; }
trusted_source "$source_path" || { fail_json "导入来源目录不受信任"; exit 0; }
[ -f "$source_path" ] || { fail_json "待导入文件不存在"; exit 0; }
_bytes=$(wc -c < "$source_path" 2>/dev/null | tr -d '[:space:]')
case "$_bytes" in ''|*[!0-9]*) _bytes=0 ;; esac
[ "$_bytes" -gt 0 ] && [ "$_bytes" -le "$MAX_BYTES" ] || { fail_json "文件为空或超过 256 MB 限制"; exit 0; }
[ -n "$display_name" ] || display_name=$(basename "$source_path")
case "$(font_detect_format "$source_path")" in
    ZIP) import_zip_file "$source_path" "$display_name" ;;
    *) import_font_file "$source_path" "$display_name" ;;
esac
exit 0
