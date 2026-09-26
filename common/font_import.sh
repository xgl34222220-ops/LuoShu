#!/system/bin/sh
# 洛书 v2.0.0 - 安全 ZIP 字体包导入
# 只解压字体文件，不执行压缩包中的任何脚本。

IMPORT_MAX_ZIP_BYTES=268435456
IMPORT_MAX_FILES=128
IMPORT_MAX_EXTRACT_BYTES=536870912
USER_IMPORT_DIR="${USER_IMPORT_DIR:-${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/import}"
IMPORT_CACHE_DIR="${IMPORT_CACHE_DIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}/cache/import}"
IMPORT_PROBE="${IMPORT_PROBE:-${MODULE_DIR:-/data/adb/modules/LuoShu}/common/font_import_probe.py}"
IMPORT_PYROOT="${IMPORT_PYROOT:-${MODULE_DIR:-/data/adb/modules/LuoShu}/common/python}"
IMPORT_PYBIN="${IMPORT_PYBIN:-$IMPORT_PYROOT/bin/luoshu-python}"

import_unzip() {
    if command -v unzip >/dev/null 2>&1; then unzip "$@"
    elif command -v busybox >/dev/null 2>&1; then busybox unzip "$@"
    else return 127
    fi
}

import_file_hash() {
    if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" 2>/dev/null | awk '{print $1}'
    elif command -v md5sum >/dev/null 2>&1; then md5sum "$1" 2>/dev/null | awk '{print $1}'
    else wc -c < "$1" 2>/dev/null | tr -d '[:space:]'
    fi
}

# 优先读取字体内部 name / OS/2 / head / fvar 表。Android 使用模块内 Python，
# CI 可通过 LUOSHU_IMPORT_PYTHON=python3 使用宿主 Python。
import_probe_metadata() {
    _probe_file="$1"
    [ -f "$IMPORT_PROBE" ] || return 1
    _probe_output=""
    if [ -n "${LUOSHU_IMPORT_PYTHON:-}" ]; then
        _probe_output=$("$LUOSHU_IMPORT_PYTHON" "$IMPORT_PROBE" "$_probe_file" 2>/dev/null)
    elif [ -x "$IMPORT_PYBIN" ]; then
        _probe_output=$(PYTHONHOME="$IMPORT_PYROOT" \
            PYTHONPATH="$IMPORT_PYROOT/lib/python3.14:$IMPORT_PYROOT/lib/python3.14/site-packages" \
            LD_LIBRARY_PATH="$IMPORT_PYROOT/lib:$IMPORT_PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
            "$IMPORT_PYBIN" "$IMPORT_PROBE" "$_probe_file" 2>/dev/null)
    elif command -v python3 >/dev/null 2>&1; then
        _probe_output=$(python3 "$IMPORT_PROBE" "$_probe_file" 2>/dev/null)
    fi
    case "$_probe_output" in *'|'*'|'*'|'*'|'*) printf '%s
' "$_probe_output"; return 0 ;; esac
    return 1
}

import_safe_basename() {
    _name="$1"
    case "$_name" in ''|*'/'*|*'\\'*|*'..'*) return 1 ;; esac
    printf '%s\n' "$_name"
}

find_import_zip() {
    _wanted=$(import_safe_basename "$1") || return 1
    for _zip in "$USER_IMPORT_DIR"/*.zip "$USER_IMPORT_DIR"/*.ZIP; do
        [ -f "$_zip" ] || continue
        [ "$(basename "$_zip")" = "$_wanted" ] && { printf '%s\n' "$_zip"; return 0; }
    done
    return 1
}

import_package_label() {
    _base="$1"
    _base=$(printf '%s' "$_base" | tr -d '\r\n' | sed -E '
        s/[[:cntrl:]]//g;
        s#[\\/:*?"<>|]+#-#g;
        s/[[:space:]_]+/-/g;
        s/-+/-/g;
        s/^[.-]+//;
        s/[.-]+$//')
    _base=$(printf '%s' "$_base" | cut -c1-64)
    [ -n "$_base" ] || _base="ImportedFont"
    printf '%s\n' "$_base"
}

# 从 ZIP 内的 module.prop 读取模块元数据。优先根目录，也兼容外面多套一层目录。
import_zip_module_prop() {
    _zip="$1"; _listing_text="$2"
    _prop=$(import_unzip -p "$_zip" module.prop 2>/dev/null | tr -d '\r')
    if [ -z "$_prop" ]; then
        _prop_path=$(printf '%s\n' "$_listing_text" | awk 'tolower($NF) ~ /(^|\/)module\.prop$/ {print $NF; exit}')
        [ -n "$_prop_path" ] && _prop=$(import_unzip -p "$_zip" "$_prop_path" 2>/dev/null | tr -d '\r')
    fi
    printf '%s\n' "$_prop"
}

import_prop_value() {
    _text="$1"; _key="$2"
    printf '%s\n' "$_text" | sed -n "s/^${_key}=//p" | head -n1 | tr -d '\r\n' | sed -E 's/[[:cntrl:]]//g; s/^[[:space:]]+//; s/[[:space:]]+$//'
}

# 为导入后的字体族写显示元数据。字体文件名用于稳定识别，App 显示名称则使用原模块中文名。
import_write_font_config() {
    _font_id="$1"; _display_name="$2"; _zip_name="$3"; _version="$4"; _author="$5"; _supports_cjk="$6"; _variable="$7"
    [ -n "$_font_id" ] || return 1
    _cfg="$USER_FONTS_DIR/${_font_id}.conf"
    _display_name=$(printf '%s' "$_display_name" | tr -d '\r\n')
    _version=$(printf '%s' "$_version" | tr -d '\r\n')
    _author=$(printf '%s' "$_author" | tr -d '\r\n')
    {
        printf 'name=%s\n' "$_display_name"
        printf 'description=从字体模块 %s 导入\n' "${_zip_name%.*}"
        printf 'version=%s\n' "${_version:-未知}"
        printf 'author=%s\n' "${_author:-未知}"
        printf 'supports_cjk=%s\n' "$_supports_cjk"
        printf 'is_variable=%s\n' "$_variable"
    } > "$_cfg" 2>/dev/null || return 1
    chmod 0644 "$_cfg" 2>/dev/null || true
}

import_is_icon_name() {
    _lower=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
    case "$_lower" in *icon*|*symbol*|*material*|*awesome*|*glyph*|*dingbat*|*weather*|*fontello*|*emptyfont*) return 0 ;; esac
    return 1
}

import_is_color_font_name() {
    _lower=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
    case "$_lower" in *emoji*|*emojione*|*twemoji*|*noto-color*) return 0 ;; esac
    return 1
}

import_is_italic_name() {
    _lower=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
    case "$_lower" in *italic*|*oblique*) return 0 ;; esac
    return 1
}

# 专用于导入包的字体族归一化：支持 ASCH-w1…w9 这类模块命名。
import_detect_family() {
    _stem="${1%.*}"
    _stem=$(printf '%s' "$_stem" | sed -E '
        s/[-_](thin|extralight|ultralight|light|regular|book|normal|medium|semibold|demibold|bold|extrabold|ultrabold|black|heavy)$//I;
        s/[-_]w([1-9]|[1-9]00)$//I;
        s/[-_](100|200|300|400|500|600|700|800|900)$//;
        s/[-_]+$//')
    [ -n "$_stem" ] || _stem="ImportedFont"
    printf '%s\n' "$_stem"
}

# 名称仅作为预筛选信号；最终仍会在字体详情页做 cmap 覆盖检测。
import_name_class() {
    _lower=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
    case "$_lower" in
        *hans*|*simplified*|*zh-cn*|*zh_cn*|*chinese*|*cjk-sc*|*cjk_sc*|*gb18030*|*as-ch*|asch-*|*sysfont-hans*|*syssans-hans*) echo cjk; return ;;
        *hant*|*traditional*|*zh-tw*|*zh_tw*|*cjk-tc*|*cjk_tc*|*tcvf*) echo cjk_traditional; return ;;
        *cjk*|*han*|*jk*|*jp*|*japanese*|*korean*) echo east_asian; return ;;
        *latin*|*arabic*|*as-en*|asen-*|*opsans-en*|*syssans-en*|*roboto*|*droidsans*) echo latin; return ;;
    esac
    echo neutral
}

import_weight_role() {
    _lower=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
    case "$_lower" in
        *thin*|*-w1.*|*_w1.*|*-100.*|*_100.*) echo thin ;;
        *extralight*|*ultralight*|*extra-light*|*ultra-light*|*-w2.*|*_w2.*|*-200.*|*_200.*) echo extralight ;;
        *light*|*-w3.*|*_w3.*|*-300.*|*_300.*) echo light ;;
        *regular*|*book*|*normal*|*-w4.*|*_w4.*|*-400.*|*_400.*) echo regular ;;
        *medium*|*-w5.*|*_w5.*|*-500.*|*_500.*) echo medium ;;
        *semibold*|*demibold*|*-w6.*|*_w6.*|*-600.*|*_600.*) echo semibold ;;
        *extrabold*|*ultrabold*|*extra-bold*|*ultra-bold*|*-w8.*|*_w8.*|*-800.*|*_800.*) echo extrabold ;;
        *bold*|*-w7.*|*_w7.*|*-700.*|*_700.*) echo bold ;;
        *black*|*heavy*|*-w9.*|*_w9.*|*-900.*|*_900.*) echo black ;;
        *) echo regular ;;
    esac
}

import_weight_role_from_class() {
    _weight="$1"; _fallback="$2"
    case "$_weight" in ''|*[!0-9]*) import_weight_role "$_fallback"; return ;; esac
    if [ "$_weight" -lt 150 ]; then echo thin
    elif [ "$_weight" -lt 250 ]; then echo extralight
    elif [ "$_weight" -lt 350 ]; then echo light
    elif [ "$_weight" -lt 450 ]; then echo regular
    elif [ "$_weight" -lt 550 ]; then echo medium
    elif [ "$_weight" -lt 650 ]; then echo semibold
    elif [ "$_weight" -lt 750 ]; then echo bold
    elif [ "$_weight" -lt 850 ]; then echo extrabold
    else echo black
    fi
}

import_weight_label() {
    case "$1" in
        thin) echo Thin ;; extralight) echo ExtraLight ;; light) echo Light ;;
        regular) echo Regular ;; medium) echo Medium ;; semibold) echo SemiBold ;;
        bold) echo Bold ;; extrabold) echo ExtraBold ;; black) echo Black ;; *) echo Regular ;;
    esac
}

import_real_extension() {
    _fmt=$(font_detect_format "$1" 2>/dev/null)
    case "$_fmt" in TTF) echo ttf ;; OTF) echo otf ;; TTC) echo ttc ;; *) echo "${1##*.}" ;; esac
}

import_copy_unique() {
    _src="$1"; _dest_dir="$2"; _dest_name="$3"
    mkdir -p "$_dest_dir" 2>/dev/null || return 1
    _stem="${_dest_name%.*}"; _ext="${_dest_name##*.}"; _target="$_dest_dir/$_dest_name"; _n=2
    while [ -e "$_target" ]; do
        _old_size=$(wc -c < "$_target" 2>/dev/null | tr -d '[:space:]')
        _new_size=$(wc -c < "$_src" 2>/dev/null | tr -d '[:space:]')
        if [ "$_old_size" = "$_new_size" ] && cmp -s "$_target" "$_src" 2>/dev/null; then
            printf '%s\n' "$_target"; return 0
        fi
        _target="$_dest_dir/${_stem}-import${_n}.${_ext}"; _n=$((_n + 1))
    done
    cp -f "$_src" "$_target" 2>/dev/null || return 1
    chmod 0644 "$_target" 2>/dev/null || true
    printf '%s\n' "$_target"
}

import_list_json() {
    mkdir -p "$USER_IMPORT_DIR" 2>/dev/null || true
    _first=true
    printf '{"status":"ok","data":{"path":"%s","packages":[' "$(json_escape "$USER_IMPORT_DIR")"
    for _zip in "$USER_IMPORT_DIR"/*.zip "$USER_IMPORT_DIR"/*.ZIP; do
        [ -f "$_zip" ] || continue
        _base=$(basename "$_zip"); _bytes=$(wc -c < "$_zip" 2>/dev/null | tr -d '[:space:]')
        case "$_bytes" in ''|*[!0-9]*) _bytes=0 ;; esac
        _date=$(stat -c '%y' "$_zip" 2>/dev/null | cut -c1-16)
        _prop=$(import_unzip -p "$_zip" module.prop 2>/dev/null | tr -d '\r')
        if [ -z "$_prop" ]; then
            _zip_listing=$(import_unzip -l "$_zip" 2>/dev/null)
            _prop=$(import_zip_module_prop "$_zip" "$_zip_listing")
        fi
        _module_name=$(import_prop_value "$_prop" name)
        [ -n "$_module_name" ] || _module_name="${_base%.*}"
        [ "$_first" = true ] || printf ','
        printf '{"id":"%s","name":"%s","fileName":"%s","size":"%s","bytes":%s,"date":"%s"}' \
            "$(json_escape "$_base")" "$(json_escape "$_module_name")" "$(json_escape "${_base%.*}")" "$(format_filesize "$_bytes")" "$_bytes" "$(json_escape "$_date")"
        _first=false
    done
    printf ']}}\n'
}

# One Python process reads every archive member by magic, retains all families,
# extracts TTC/OTC faces and converts web fonts before publishing validated SFNT.
import_run_engine() {
    _engine="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}/common/font_import_engine.py"
    if [ -n "${LUOSHU_IMPORT_PYTHON:-}" ]; then
        "$LUOSHU_IMPORT_PYTHON" "$_engine" "$@"
    elif [ -x "$IMPORT_PYBIN" ]; then
        TMPDIR="${IMPORT_CACHE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}/cache/import}" \
        PYTHONHOME="$IMPORT_PYROOT" \
        PYTHONPATH="$IMPORT_PYROOT/lib/python3.14:$IMPORT_PYROOT/lib/python3.14/site-packages" \
        LD_LIBRARY_PATH="$IMPORT_PYROOT/lib:$IMPORT_PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
            "$IMPORT_PYBIN" "$_engine" "$@"
    elif command -v python3 >/dev/null 2>&1; then
        python3 "$_engine" "$@"
    else
        printf '{"status":"error","message":"字体导入运行时不可用"}\n'
        return 1
    fi
}

import_zip_package() {
    _zip=$(find_import_zip "$1") || { printf '{"status":"error","message":"未找到指定 ZIP 字体包"}\n'; return 0; }
    mkdir -p "$IMPORT_CACHE_DIR" "$USER_FONTS_DIR" 2>/dev/null || return 1
    import_run_engine --input "$_zip" --output-dir "$USER_FONTS_DIR" --label "$(basename "$_zip")"
}
