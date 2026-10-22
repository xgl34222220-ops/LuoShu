#!/system/bin/sh
# 洛书 v2.0.0：原生 App 文件选择器导入桥。
# 只接受 App 私有缓存中的 TTF/OTF/TTC/WOFF/WOFF2/ZIP；ZIP 由安全字体包导入器处理，
# WOFF/WOFF2 先由 font_check.sh 转换为真实 SFNT，再按普通字体文件导入。
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
FACE_EXTRACTOR="$MODDIR/common/font_extract_faces.py"
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
    rm -f "$MODDIR/config/native_font_index.json" \
          "$MODDIR/config/native_font_index.key" \

          "$MODDIR/config/recent_fonts.conf" 2>/dev/null || true
}

schedule_font_prewarm() {
    _sfp_family="$1"
    [ -n "$_sfp_family" ] || return 0
    _sfp_switch="$MODDIR/common/legacy_v14_4/font_switch_safe.sh"
    [ -f "$_sfp_switch" ] || return 0
    MODDIR="$MODDIR" LUOSHU_PUBLIC_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}" \
        sh "$_sfp_switch" action prewarm-start "$_sfp_family" >/dev/null 2>&1 || true
    return 0
}

find_duplicate() {
    _source="$1"
    _hash="$2"
    _source_size=$(stat -c %s "$_source" 2>/dev/null)
    case "$_source_size" in ''|*[!0-9]*) _source_size=0 ;; esac
    for _file in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
                 "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_file" ] || continue
        _candidate_size=$(stat -c %s "$_file" 2>/dev/null)
        [ "$_candidate_size" = "$_source_size" ] || continue
        [ "$(file_hash "$_file")" = "$_hash" ] && { printf '%s\n' "$_file"; return 0; }
    done
    return 1
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
        invalidate_font_cache
        printf '%s\n' "$_json"
    else
        # 拆分器给出明确原因（例如集合内全部是位图/彩色字体面）时原样提示。
        _reason=$(printf '%s' "$_json" | sed -n 's/.*"message":"\([^"]*\)".*/\1/p')
        fail_json "TTC/OTC 字体集合无法导入：${_reason:-字体面拆分失败}"
    fi
}

# 彩色 Emoji 字体不能作为全局文字字体；单独保存，供可选 Emoji 槽使用。
import_emoji_file() {
    _src="$1"; _display="$2"; _ext="$3"
    _emoji_dir="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/emoji"
    mkdir -p "$_emoji_dir" 2>/dev/null || { fail_json "无法创建 Emoji 字体目录"; return; }
    _stem=$(safe_stem "$_display")
    _target="$_emoji_dir/${_stem}.${_ext}"
    if [ -e "$_target" ] && ! cmp -s "$_src" "$_target" 2>/dev/null; then
        _hash=$(file_hash "$_src")
        _target="$_emoji_dir/${_stem}-$(printf '%s' "$_hash" | cut -c1-10).${_ext}"
    fi
    cp -f "$_src" "$_target" 2>/dev/null || { fail_json "无法复制 Emoji 字体"; return; }
    chmod 0644 "$_target" 2>/dev/null || true
    printf '{"status":"ok","data":{"kind":"emoji","name":"%s","path":"%s","duplicate":false,"message":"已作为可选 Emoji 字体导入；需在 Emoji 槽中启用后重新应用字体，默认仍使用原厂 Emoji"}}\n' \
        "$(json_escape "$_stem")" "$(json_escape "$_target")"
}

# 网页字体：先在模块私有临时目录转换为 TTF/OTF/TTC 并完整校验，再沿用普通导入流程
# （去重、TTC 拆分、Emoji 分流、元数据探测）。转换失败时返回 font_check.sh 的原因。
import_web_font_file() {
    _iwf_src="$1"
    _iwf_display="$2"
    _iwf_tmp="${LUOSHU_TMP_DIR:-$MODDIR/.luoshu-state/tmp}/native-import-web.$$"
    rm -rf "$_iwf_tmp" 2>/dev/null || true
    mkdir -p "$_iwf_tmp" 2>/dev/null || { fail_json "无法创建网页字体转换目录"; return; }
    FONT_CHECK_CONVERT_DIR="$_iwf_tmp"
    _iwf_rc=0
    font_validate "$_iwf_src" text >/dev/null 2>&1 || _iwf_rc=$?
    FONT_CHECK_CONVERT_DIR=""
    if [ "$_iwf_rc" -ne 0 ] || [ ! -f "${FONT_CHECK_CONVERTED:-}" ]; then
        rm -rf "$_iwf_tmp" 2>/dev/null || true
        fail_json "${FONT_CHECK_ERROR:-网页字体转换失败}"
        return
    fi
    _iwf_converted="$FONT_CHECK_CONVERTED"
    _iwf_stem="${_iwf_display%.*}"
    import_font_file "$_iwf_converted" "${_iwf_stem}.${_iwf_converted##*.}"
    rm -rf "$_iwf_tmp" 2>/dev/null || true
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
        WOFF|WOFF2) import_web_font_file "$_src" "$_display"; return ;;
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

    if [ "${FONT_CHECK_COLOR:-false}" = true ]; then
        import_emoji_file "$_src" "$_display" "$_ext"
        return
    fi

    _hash=$(file_hash "$_src")
    [ -n "$_hash" ] || { fail_json "无法计算字体 SHA-256"; return; }
    mkdir -p "$USER_FONTS_DIR" 2>/dev/null || { fail_json "无法创建字体目录"; return; }

    _duplicate=$(find_duplicate "$_src" "$_hash")
    if [ -f "$_duplicate" ]; then
        _family=$(detect_font_family "$(basename "$_duplicate")")
        schedule_font_prewarm "$_family"
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
    invalidate_font_cache
    _family=$(detect_font_family "$(basename "$_target")")
    _supports_cjk=false
    _probe=$(import_probe_metadata "$_target" 2>/dev/null)
    if [ -n "$_probe" ]; then
        IFS='|' read -r _probe_family _probe_subfamily _probe_weight _probe_italic _probe_variable _probe_supports_cjk <<EOF_RAW_PROBE
$_probe
EOF_RAW_PROBE
        [ "$_probe_supports_cjk" = true ] && _supports_cjk=true
    fi
    {
        printf 'name=%s\n' "$_stem"
        printf 'description=直接导入字体文件\n'
        printf 'supports_cjk=%s\n' "$_supports_cjk"
        printf 'is_variable=%s\n' "${_probe_variable:-false}"
    } > "$USER_FONTS_DIR/${_family}.conf" 2>/dev/null || true
    schedule_font_prewarm "$_family" "$_hash"
    printf '{"status":"ok","data":{"kind":"font","id":"%s","name":"%s","format":"%s","supportsCjk":%s,"duplicate":false,"message":"字体已导入"}}\n' \
        "$(json_escape "$_family")" "$(json_escape "$_stem")" "$_format" "$_supports_cjk"
}

import_zip_file() {
    _src="$1"
    _display="$2"
    command -v unzip >/dev/null 2>&1 || command -v busybox >/dev/null 2>&1 || {
        fail_json "系统缺少 unzip，无法导入字体模块 ZIP"
        return
    }
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

    _error_file="${LUOSHU_TMP_DIR:-$MODDIR/.luoshu-state/tmp}/native-import-zip-error.$$"
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
_ext=$(printf '%s' "${display_name##*.}" | tr '[:upper:]' '[:lower:]')
case "$_ext" in
    ttf|otf|ttc|otc|woff|woff2) import_font_file "$source_path" "$display_name" ;;
    zip) import_zip_file "$source_path" "$display_name" ;;
    *) fail_json "仅支持 TTF、OTF、TTC/OTC、WOFF/WOFF2 和字体 ZIP 压缩包" ;;
esac
exit 0
