#!/system/bin/sh
# 洛书 v13.4 Beta2 Hotfix6 - 安全 ZIP 字体包导入
# 只解压字体文件，不执行压缩包中的任何脚本。

IMPORT_MAX_ZIP_BYTES=268435456
IMPORT_MAX_FILES=128
IMPORT_MAX_EXTRACT_BYTES=536870912
USER_IMPORT_DIR="${USER_IMPORT_DIR:-${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/import}"
IMPORT_CACHE_DIR="${IMPORT_CACHE_DIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}/cache/import}"

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

# 为导入后的字体族写显示元数据。字体文件名用于稳定识别，WebUI 名称则使用原模块中文名。
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

import_is_emoji_name() {
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
        *extralight*|*ultralight*|*light*|*-w2.*|*_w2.*|*-200.*|*_200.*) echo light ;;
        *regular*|*book*|*normal*|*-w3.*|*_w3.*|*-300.*|*_300.*|*-400.*|*_400.*) echo regular ;;
        *medium*|*-w4.*|*_w4.*|*-500.*|*_500.*) echo medium ;;
        *semibold*|*demibold*|*-w5.*|*_w5.*|*-600.*|*_600.*) echo semibold ;;
        *extrabold*|*ultrabold*|*bold*|*-w6.*|*_w6.*|*-700.*|*_700.*) echo bold ;;
        *black*|*heavy*|*-w7.*|*_w7.*|*-w8.*|*_w8.*|*-w9.*|*_w9.*|*-800.*|*_800.*|*-900.*|*_900.*) echo black ;;
        *) echo regular ;;
    esac
}

import_weight_label() {
    case "$1" in
        thin) echo Thin ;; light) echo Light ;; regular) echo Regular ;; medium) echo Medium ;;
        semibold) echo SemiBold ;; bold) echo Bold ;; black) echo Black ;; *) echo Regular ;;
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

import_zip_package() {
    _zip=$(find_import_zip "$1") || { printf '{"status":"error","message":"未找到指定 ZIP 字体包"}\n'; return 0; }
    _zip_name=$(basename "$_zip")
    _zip_bytes=$(wc -c < "$_zip" 2>/dev/null | tr -d '[:space:]')
    case "$_zip_bytes" in ''|*[!0-9]*) _zip_bytes=0 ;; esac
    if [ "$_zip_bytes" -le 0 ] || [ "$_zip_bytes" -gt "$IMPORT_MAX_ZIP_BYTES" ]; then
        printf '{"status":"error","message":"ZIP 大小异常或超过 256 MB 限制"}\n'; return 0
    fi
    if ! command -v unzip >/dev/null 2>&1 && ! command -v busybox >/dev/null 2>&1; then
        printf '{"status":"error","message":"系统缺少 unzip，无法导入字体包"}\n'; return 0
    fi

    _listing=$(import_unzip -l "$_zip" 2>/dev/null)

    # 直接采用原模块 module.prop 的 name= 作为 WebUI 显示名称。
    _module_prop=$(import_zip_module_prop "$_zip" "$_listing")
    _module_name=$(import_prop_value "$_module_prop" name)
    _module_version=$(import_prop_value "$_module_prop" version)
    _module_author=$(import_prop_value "$_module_prop" author)
    [ -n "$_module_name" ] || _module_name="${_zip_name%.*}"
    _display_name="$_module_name"
    _package_label=$(import_package_label "$_display_name")
    _declared=$(printf '%s\n' "$_listing" | awk 'BEGIN{n=0;s=0} $1 ~ /^[0-9]+$/ && tolower($0) ~ /\.(ttf|otf|ttc)([[:space:]]|$)/ {n++; s+=$1} END{printf "%d %d",n,s}')
    set -- $_declared; _declared_count=${1:-0}; _declared_bytes=${2:-0}
    case "$_declared_count" in ''|*[!0-9]*) _declared_count=0 ;; esac
    case "$_declared_bytes" in ''|*[!0-9]*) _declared_bytes=0 ;; esac
    if [ "$_declared_count" -le 0 ]; then printf '{"status":"error","message":"ZIP 中没有找到 TTF / OTF / TTC 字体"}\n'; return 0; fi
    if [ "$_declared_count" -gt "$IMPORT_MAX_FILES" ] || [ "$_declared_bytes" -gt "$IMPORT_MAX_EXTRACT_BYTES" ]; then
        printf '{"status":"error","message":"字体包内容过多（最多 128 个字体、解压后 512 MB）"}\n'; return 0
    fi

    _tmp="$IMPORT_CACHE_DIR/$(date +%s)-$$"
    rm -rf "$_tmp" 2>/dev/null || true
    mkdir -p "$_tmp" "$USER_FONTS_DIR" "$USER_EMOJI_DIR" 2>/dev/null || { printf '{"status":"error","message":"无法创建导入临时目录"}\n'; return 0; }
    for _pat in '*.ttf' '*.otf' '*.ttc' '*.TTF' '*.OTF' '*.TTC'; do
        import_unzip -j -o "$_zip" "$_pat" -d "$_tmp" >/dev/null 2>&1 || true
    done
    find "$_tmp" -type l -exec rm -f {} \; 2>/dev/null || true

    _manifest="$_tmp/.manifest"; : > "$_manifest"
    _valid=0; _invalid=0; _ignored=0
    for _f in "$_tmp"/*; do
        [ -f "$_f" ] || continue
        _base=$(basename "$_f")
        case "$_base" in *'|'*) _ignored=$((_ignored + 1)); continue ;; esac
        if import_is_icon_name "$_base"; then _ignored=$((_ignored + 1)); continue; fi
        if ! font_validate "$_f" text 2>/dev/null; then _invalid=$((_invalid + 1)); continue; fi
        _valid=$((_valid + 1))
        _family=$(import_detect_family "$_base")
        _variable="$FONT_CHECK_VARIABLE"; _kind=text
        if import_is_emoji_name "$_base" || [ "$FONT_CHECK_COLOR" = true ]; then _kind=emoji; fi
        _size=$(wc -c < "$_f" 2>/dev/null | tr -d '[:space:]'); case "$_size" in ''|*[!0-9]*) _size=0 ;; esac
        _class=$(import_name_class "$_base"); _role=$(import_weight_role "$_base")
        printf '%s|%s|%s|%s|%s|%s|%s|%s\n' "$_family" "$_variable" "$_kind" "$_size" "$_base" "$_f" "$_class" "$_role" >> "$_manifest"
    done

    if [ "$_valid" -le 0 ]; then rm -rf "$_tmp"; printf '{"status":"error","message":"没有字体通过真实格式检测"}\n'; return 0; fi

    # 预选主文字字体：中文名称、字体族完整度和文件体积优先；VF 仅加分，不再无条件压过中文静态字重。
    _best_score=-999999; _best_path=""; _best_family=""; _best_variable=false; _best_name=""; _best_class=neutral; _best_role=regular; _best_size=0
    while IFS='|' read -r _family _variable _kind _size _base _path _class _role; do
        [ "$_kind" = text ] || continue
        import_is_italic_name "$_base" && continue
        _family_count=$(awk -F'|' -v f="$_family" '$1==f && $3=="text"{n++} END{print n+0}' "$_manifest")
        _mb=$((_size / 1048576)); [ "$_mb" -gt 64 ] && _mb=64
        _score=$((_mb * 120 + _family_count * 260))
        case "$_class" in cjk) _score=$((_score + 7000)) ;; cjk_traditional) _score=$((_score + 4500)) ;; east_asian) _score=$((_score + 2500)) ;; latin) if [ "$_size" -lt 6291456 ]; then _score=$((_score - 5000)); else _score=$((_score - 1000)); fi ;; esac
        [ "$_variable" = true ] && _score=$((_score + 1500))
        case "$_role" in regular) _score=$((_score + 1400)) ;; medium) _score=$((_score + 900)) ;; semibold) _score=$((_score + 550)) ;; bold) _score=$((_score + 300)) ;; thin) _score=$((_score - 150)) ;; esac
        if [ "$_size" -lt 1048576 ]; then _score=$((_score - 5000)); elif [ "$_size" -lt 3145728 ]; then _score=$((_score - 2500)); elif [ "$_size" -lt 6291456 ]; then _score=$((_score - 800)); fi
        if [ "$_score" -gt "$_best_score" ]; then
            _best_score=$_score; _best_path=$_path; _best_family=$_family; _best_variable=$_variable; _best_name=$_base; _best_class=$_class; _best_role=$_role; _best_size=$_size
        fi
    done < "$_manifest"

    if [ ! -f "$_best_path" ]; then rm -rf "$_tmp"; printf '{"status":"error","message":"字体包中只有 Emoji 或图标字体，没有可用文字字体"}\n'; return 0; fi

    _family_count=$(awk -F'|' -v f="$_best_family" '$1==f && $3=="text"{n++} END{print n+0}' "$_manifest")
    _imported_text=0; _imported_emoji=0; _mode=single; _target_name=""

    if [ "$_best_variable" = true ]; then
        _mode=variable; _ext=$(import_real_extension "$_best_path"); _target_name="${_package_label}-Variable.${_ext}"
        _copied=$(import_copy_unique "$_best_path" "$USER_FONTS_DIR" "$_target_name") && { _target_name=$(basename "$_copied"); _imported_text=1; }
    elif [ "$_family_count" -ge 2 ]; then
        _mode=family
        while IFS='|' read -r _family _variable _kind _size _base _path _class _role; do
            [ "$_kind" = text ] || continue; [ "$_family" = "$_best_family" ] || continue
            import_is_italic_name "$_base" && continue
            _label=$(import_weight_label "$_role"); _ext=$(import_real_extension "$_path"); _name="${_package_label}-${_label}.${_ext}"
            _copied=$(import_copy_unique "$_path" "$USER_FONTS_DIR" "$_name") || continue
            _imported_text=$((_imported_text + 1))
            if [ "$_role" = regular ] && [ -z "$_target_name" ]; then _target_name=$(basename "$_copied"); fi
            [ "$_path" = "$_best_path" ] && [ -z "$_target_name" ] && _target_name=$(basename "$_copied")
        done < "$_manifest"
        [ -n "$_target_name" ] || _target_name="${_package_label}-Regular.ttf"
    else
        # 单文件模块若存在多个系统别名，只对最终候选做 cmp，不再对全部文件反复 SHA-256。
        _same=0
        while IFS='|' read -r _family _variable _kind _size _base _path _class _role; do
            [ "$_kind" = text ] || continue; [ "$_size" = "$_best_size" ] || continue
            cmp -s "$_best_path" "$_path" 2>/dev/null && _same=$((_same + 1))
        done < "$_manifest"
        [ "$_same" -ge 2 ] && _mode=deduplicated
        _ext=$(import_real_extension "$_best_path"); _target_name="${_package_label}-Regular.${_ext}"
        _copied=$(import_copy_unique "$_best_path" "$USER_FONTS_DIR" "$_target_name") && { _target_name=$(basename "$_copied"); _imported_text=1; }
    fi

    _emoji_best=""; _emoji_size=0; _emoji_name=""
    while IFS='|' read -r _family _variable _kind _size _base _path _class _role; do
        [ "$_kind" = emoji ] || continue
        if [ "$_size" -gt "$_emoji_size" ]; then _emoji_best=$_path; _emoji_size=$_size; _emoji_name=$_base; fi
    done < "$_manifest"
    if [ -f "$_emoji_best" ]; then
        _emoji_ext=$(import_real_extension "$_emoji_best"); _emoji_stem="${_emoji_name%.*}"
        import_copy_unique "$_emoji_best" "$USER_EMOJI_DIR" "${_emoji_stem}.${_emoji_ext}" >/dev/null && _imported_emoji=1
    fi

    if [ "$_imported_text" -gt 0 ]; then
        _font_id=$(detect_font_family "$_target_name")
        case "$_best_class" in cjk|cjk_traditional|east_asian) _supports_cjk=true ;; *) _supports_cjk=false ;; esac
        import_write_font_config "$_font_id" "$_display_name" "$_zip_name" "$_module_version" "$_module_author" "$_supports_cjk" "$_best_variable" || true
    fi

    rm -f "$CONFIG_DIR/webui_font_list.key" "$CONFIG_DIR/webui_font_list.json" 2>/dev/null || true
    rm -rf "$_tmp" 2>/dev/null || true
    if [ "$_imported_text" -le 0 ]; then printf '{"status":"error","message":"字体复制失败，请检查存储空间和目录权限"}\n'; return 0; fi

    case "$_best_class" in cjk) _reason="检测到简体中文主字体" ;; cjk_traditional) _reason="检测到繁体中文主字体" ;; east_asian) _reason="检测到东亚文字字体" ;; latin) _reason="未找到明确中文命名，已按覆盖候选规则选择" ;; *) _reason="已按字体族完整度与文件体积选择" ;; esac
    _message="已导入：$_display_name"
    printf '{"status":"ok","data":{"package":"%s","displayName":"%s","selected":"%s","source":"%s","family":"%s","mode":"%s","reason":"%s","familyFiles":%d,"importedText":%d,"importedEmoji":%d,"valid":%d,"invalid":%d,"ignored":%d,"message":"%s"}}\n' \
        "$(json_escape "$_zip_name")" "$(json_escape "$_display_name")" "$(json_escape "$_target_name")" "$(json_escape "$_best_name")" "$(json_escape "$_best_family")" "$(json_escape "$_mode")" "$(json_escape "$_reason")" \
        "$_family_count" "$_imported_text" "$_imported_emoji" "$_valid" "$_invalid" "$_ignored" "$(json_escape "$_message")"
}
