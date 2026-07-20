#!/system/bin/sh
# 洛书原生 App 文件选择器导入桥。
# 只接受 App 私有缓存中的 TTF/OTF/TTC/ZIP；ZIP 继续交由安全字体包导入器处理。
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
FONT_MANAGER="$MODDIR/common/font_manager.sh"
PYROOT="$MODDIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"
FACE_EXTRACTOR="$MODDIR/common/font_extract_faces.py"
HASH_INDEX="$MODDIR/config/import_hash_index.tsv"
MAX_BYTES=268435456

[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/font_check.sh" ] && . "$MODDIR/common/font_check.sh"

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
        /data/data/io.github.xgl34222220.luoshu.debug/cache/native_import/*) return 0 ;;
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
    rm -f "$MODDIR/config/webui_font_list.json" \
          "$MODDIR/config/webui_font_list.key" \
          "$MODDIR/config/native_font_index.json" \
          "$MODDIR/config/native_font_index.key" \
          "$MODDIR/config/recent_fonts.conf" 2>/dev/null || true
}

font_dir_mtime() {
    mkdir -p "$USER_FONTS_DIR" 2>/dev/null || true
    if command -v stat >/dev/null 2>&1; then
        stat -c '%Y' "$USER_FONTS_DIR" 2>/dev/null && return 0
    fi
    if command -v busybox >/dev/null 2>&1; then
        busybox stat -c '%Y' "$USER_FONTS_DIR" 2>/dev/null && return 0
    fi
    printf '0\n'
}

rebuild_hash_index() {
    mkdir -p "$USER_FONTS_DIR" "$MODDIR/config" 2>/dev/null || return 1
    _tmp="$HASH_INDEX.tmp.$$"
    {
        printf '#mtime=%s\n' "$(font_dir_mtime)"
        for _file in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
                     "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
            [ -f "$_file" ] || continue
            _hash=$(file_hash "$_file")
            [ -n "$_hash" ] || continue
            printf '%s\t%s\n' "$_hash" "$_file"
        done
    } > "$_tmp" 2>/dev/null || { rm -f "$_tmp" 2>/dev/null; return 1; }
    mv -f "$_tmp" "$HASH_INDEX" 2>/dev/null || return 1
    chmod 0600 "$HASH_INDEX" 2>/dev/null || true
}

ensure_hash_index() {
    _current=$(font_dir_mtime)
    _saved=$(sed -n 's/^#mtime=//p' "$HASH_INDEX" 2>/dev/null | head -n1)
    if [ ! -f "$HASH_INDEX" ] || [ -z "$_saved" ] || [ "$_saved" != "$_current" ]; then
        rebuild_hash_index
    fi
}

refresh_hash_index_header() {
    [ -f "$HASH_INDEX" ] || return 0
    _tmp="$HASH_INDEX.header.$$"
    {
        printf '#mtime=%s\n' "$(font_dir_mtime)"
        sed '1d' "$HASH_INDEX" 2>/dev/null
    } > "$_tmp" 2>/dev/null && mv -f "$_tmp" "$HASH_INDEX" 2>/dev/null || rm -f "$_tmp" 2>/dev/null
}

find_duplicate() {
    _hash="$1"
    ensure_hash_index >/dev/null 2>&1 || return 1
    _tab=$(printf '\t')
    _entry=$(grep -F "${_hash}${_tab}" "$HASH_INDEX" 2>/dev/null | head -n1)
    [ -n "$_entry" ] || return 1
    _path=${_entry#*"$_tab"}
    [ -f "$_path" ] || { rm -f "$HASH_INDEX" 2>/dev/null; return 1; }
    printf '%s\n' "$_path"
}

record_import_hash() {
    _hash="$1"
    _path="$2"
    ensure_hash_index >/dev/null 2>&1 || rebuild_hash_index >/dev/null 2>&1 || return 0
    printf '%s\t%s\n' "$_hash" "$_path" >> "$HASH_INDEX" 2>/dev/null || return 0
    refresh_hash_index_header
}

extract_collection_faces() {
    _src="$1"
    _display="$2"
    [ -x "$PYBIN" ] && [ -f "$FACE_EXTRACTOR" ] || {
        fail_json "TTC 字体面拆分组件不可用"
        return
    }
    mkdir -p "$USER_FONTS_DIR" 2>/dev/null || { fail_json "无法创建字体目录"; return; }
    _result=$(
        PYTHONHOME="$PYROOT" \
        PYTHONPATH="$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages" \
        LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$PYBIN" "$FACE_EXTRACTOR" \
            --input "$_src" \
            --output-dir "$USER_FONTS_DIR" \
            --label "$(safe_stem "$_display")" 2>/dev/null
    )
    _rc=$?
    _json=$(printf '%s\n' "$_result" | sed -n '/^[[:space:]]*{/p' | tail -n1)
    if [ "$_rc" -eq 0 ] && [ -n "$_json" ]; then
        rm -f "$HASH_INDEX" 2>/dev/null || true
        invalidate_font_cache
        printf '%s\n' "$_json"
    else
        fail_json "TTC 字体面拆分失败"
    fi
}

import_font_file() {
    _src="$1"
    _display="$2"
    _format=""
    if type font_detect_format >/dev/null 2>&1; then
        _format=$(font_detect_format "$_src" 2>/dev/null)
    fi
    case "$_format" in
        TTF) _ext=ttf ;;
        OTF) _ext=otf ;;
        TTC) _ext=ttc ;;
        *) fail_json "文件不是受支持的 TTF、OTF 或 TTC 字体"; return ;;
    esac

    if type font_validate >/dev/null 2>&1 && ! font_validate "$_src" text >/dev/null 2>&1; then
        fail_json "${FONT_CHECK_ERROR:-字体文件校验失败}"
        return
    fi

    if [ "$_format" = TTC ]; then
        extract_collection_faces "$_src" "$_display"
        return
    fi

    _hash=$(file_hash "$_src")
    [ -n "$_hash" ] || { fail_json "无法计算字体 SHA-256"; return; }
    mkdir -p "$USER_FONTS_DIR" 2>/dev/null || { fail_json "无法创建字体目录"; return; }

    _duplicate=$(find_duplicate "$_hash")
    if [ -f "$_duplicate" ]; then
        _family=$(detect_font_family "$(basename "$_duplicate")")
        printf '{"status":"ok","data":{"kind":"font","id":"%s","name":"%s","format":"%s","duplicate":true,"message":"字体已存在，未重复导入"}}\n' \
            "$(json_escape "$_family")" "$(json_escape "$(safe_stem "$_display")")" "$_format"
        return
    fi

    _stem=$(safe_stem "$_display")
    _target="$USER_FONTS_DIR/${_stem}.${_ext}"
    if [ -e "$_target" ]; then
        _target="$USER_FONTS_DIR/${_stem}-$(printf '%s' "$_hash" | cut -c1-10).${_ext}"
    fi
    cp -f "$_src" "$_target" 2>/dev/null || { fail_json "无法复制字体到 /sdcard/LuoShu/fonts"; return; }
    chmod 0644 "$_target" 2>/dev/null || true
    record_import_hash "$_hash" "$_target"
    invalidate_font_cache
    _family=$(detect_font_family "$(basename "$_target")")
    printf '{"status":"ok","data":{"kind":"font","id":"%s","name":"%s","format":"%s","duplicate":false,"message":"字体已导入"}}\n' \
        "$(json_escape "$_family")" "$(json_escape "$_stem")" "$_format"
}

import_zip_file() {
    _src="$1"
    _display="$2"
    command -v unzip >/dev/null 2>&1 || command -v busybox >/dev/null 2>&1 || {
        fail_json "系统缺少 unzip，无法导入字体模块 ZIP"
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
    _result=$(MODDIR="$MODDIR" sh "$FONT_MANAGER" action import_zip "$(basename "$_target")" 2>"$_error_file")
    _rc=$?
    _stderr=$(tail -n 6 "$_error_file" 2>/dev/null | tr '\n\r' '  ')
    rm -f "$_error_file" "$_target" 2>/dev/null || true
    rm -f "$HASH_INDEX" 2>/dev/null || true
    invalidate_font_cache

    _json=$(printf '%s\n' "$_result" | sed -n '/^[[:space:]]*{/p' | tail -n1)
    if [ -n "$_json" ]; then
        printf '%s\n' "$_json"
    else
        _detail=$(printf '%s' "${_stderr:-$_result}" | sed -E 's/[[:space:]]+/ /g; s/^ //; s/ $//' | cut -c1-180)
        [ -n "$_detail" ] || _detail="底层导入器没有返回结果（代码 $_rc）"
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
_ext=$(printf '%s' "${display_name##*.}" | tr '[:upper:]' '[:lower:]')
case "$_ext" in
    ttf|otf|ttc) import_font_file "$source_path" "$display_name" ;;
    zip) import_zip_file "$source_path" "$display_name" ;;
    *) fail_json "仅支持 TTF、OTF、TTC 和字体模块 ZIP" ;;
esac
exit 0
