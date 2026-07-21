#!/system/bin/sh
# 洛书 HyperOS 全局字体覆盖增强层。
# 必须在 rom_adapters.sh 之后 source；这里重新定义 HyperOS 映射函数。
set +e

_luoshu_hyperos_module_dir() {
    printf '%s\n' "${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
}

_luoshu_hyperos_root_pairs() {
    _module="$(_luoshu_hyperos_module_dir)"
    printf '%s|%s\n' "${LUOSHU_SYSTEM_FONTS_ROOT:-/system/fonts}" "$_module/system/fonts"
    printf '%s|%s\n' "${LUOSHU_PRODUCT_FONTS_ROOT:-/product/fonts}" "$_module/product/fonts"
    printf '%s|%s\n' "${LUOSHU_SYSTEM_EXT_FONTS_ROOT:-/system_ext/fonts}" "$_module/system_ext/fonts"
    printf '%s|%s\n' "${LUOSHU_VENDOR_FONTS_ROOT:-/vendor/fonts}" "$_module/vendor/fonts"
    printf '%s|%s\n' "${LUOSHU_MY_PRODUCT_FONTS_ROOT:-/my_product/fonts}" "$_module/my_product/fonts"
}

_hyperos_font_xmls() {
    if [ -n "${LUOSHU_FONT_XMLS:-}" ]; then
        printf '%s\n' $LUOSHU_FONT_XMLS
        return 0
    fi
    printf '%s\n' \
        /system/etc/fonts.xml \
        /system/etc/font_fallback.xml \
        /product/etc/fonts_customization.xml \
        /product/etc/fonts.xml \
        /system_ext/etc/fonts_customization.xml \
        /system_ext/etc/fonts.xml \
        /vendor/etc/fonts_customization.xml \
        /vendor/etc/fonts.xml \
        /my_product/etc/fonts_customization.xml \
        /my_product/etc/fonts.xml
}

_hyperos_config_targets() {
    _module="$(_luoshu_hyperos_module_dir)"
    _script="$_module/common/font_config_targets.py"
    [ -f "$_script" ] || return 0
    _python="${LUOSHU_PYTHON:-$_module/common/python/bin/luoshu-python}"
    if [ ! -x "$_python" ]; then
        _python=$(command -v python3 2>/dev/null)
    fi
    [ -n "$_python" ] && [ -x "$_python" ] || return 0
    _xmls=''
    for _xml in $(_hyperos_font_xmls); do
        [ -f "$_xml" ] && _xmls="$_xmls $_xml"
    done
    [ -n "$_xmls" ] || return 0

    case "$_python" in
        "$_module"/common/python/*)
            _pyroot="$_module/common/python"
            PYTHONHOME="$_pyroot" \
            PYTHONPATH="$_pyroot/lib/python3.14:$_pyroot/lib/python3.14/site-packages" \
            LD_LIBRARY_PATH="$_pyroot/lib:$_pyroot/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
                "$_python" "$_script" $_xmls 2>/dev/null
            ;;
        *)
            "$_python" "$_script" $_xmls 2>/dev/null
            ;;
    esac
}

_hyperos_dynamic_state_file() {
    _module="$(_luoshu_hyperos_module_dir)"
    printf '%s\n' "$_module/config/hyperos_dynamic_targets.conf"
}

_hyperos_core_files() {
    printf '%s\n' 'MiSansVF.ttf MiSansVF_Overlay.ttf MiSansLatinVF.ttf MiSansTCVF.ttf MiSansL3.otf'
}

_hyperos_weight_files() {
    printf '%s\n' '100.ttf 200.ttf 300.ttf 350.ttf 400.ttf 500.ttf 600.ttf 700.ttf 800.ttf 900.ttf'
}

_hyperos_app_font_files() {
    printf '%s\n' 'Roboto-Thin.ttf Roboto-ThinItalic.ttf Roboto-ExtraLight.ttf Roboto-ExtraLightItalic.ttf Roboto-Light.ttf Roboto-LightItalic.ttf Roboto-Regular.ttf Roboto-Italic.ttf Roboto-Medium.ttf Roboto-MediumItalic.ttf Roboto-SemiBold.ttf Roboto-SemiBoldItalic.ttf Roboto-Bold.ttf Roboto-BoldItalic.ttf Roboto-ExtraBold.ttf Roboto-ExtraBoldItalic.ttf RobotoFlex-Regular.ttf RobotoStatic-Regular.ttf GoogleSans-Regular.ttf GoogleSans-Medium.ttf GoogleSans-Bold.ttf GoogleSansText-Regular.ttf GoogleSansText-Medium.ttf GoogleSansText-Bold.ttf GoogleSansFlex-Regular.ttf SourceSansPro-Regular.ttf SourceSansPro-SemiBold.ttf SourceSansPro-Bold.ttf'
}

# 保留旧门禁和外部脚本使用的函数名；这些槽现在会按真实字重参与映射。
_hyperos_metric_shell_files() {
    _hyperos_app_font_files
}

# 返回完整清理清单，包括上次从本机 XML 动态发现的目标。
get_all_hyperos_files() {
    printf '%s %s %s ' "$(_hyperos_core_files)" "$(_hyperos_weight_files)" "$(_hyperos_app_font_files)"
    _state="$(_hyperos_dynamic_state_file)"
    [ -f "$_state" ] && tr '\n' ' ' < "$_state" 2>/dev/null
    _hyperos_config_targets | while IFS='|' read -r _file _weight _family; do
        [ -n "$_file" ] && printf '%s ' "$_file"
    done
    printf '\n'
}

_hyperos_remove_overlay_file() {
    _file="$1"
    while IFS='|' read -r _real _overlay; do
        [ -n "$_overlay" ] || continue
        rm -f "$_overlay/$_file" 2>/dev/null || true
    done <<EOF_PAIRS
$(_luoshu_hyperos_root_pairs)
EOF_PAIRS
}

# 把一个字体锚点写到 ROM 中该文件真实存在的分区；输出成功目标数量。
_hyperos_alias_existing_targets() {
    _anchor="$1"
    _file="$2"
    _count=0
    while IFS='|' read -r _real _overlay; do
        [ -n "$_real" ] && [ -n "$_overlay" ] || continue
        { [ -e "$_real/$_file" ] || [ -L "$_real/$_file" ]; } || continue
        mkdir -p "$_overlay" 2>/dev/null || continue
        if _font_alias "$_anchor" "$_overlay/$_file"; then
            _count=$((_count + 1))
        fi
    done <<EOF_PAIRS
$(_luoshu_hyperos_root_pairs)
EOF_PAIRS
    printf '%s\n' "$_count"
}

_hyperos_pick_regular_source() {
    _family="$1"
    _fallback="$2"
    _regular=''
    _variable=''
    _medium=''
    _first=''
    for _file in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
                 "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_file" ] || continue
        [ "$(detect_font_family "$(basename "$_file")")" = "$_family" ] || continue
        [ -n "$_first" ] || _first="$_file"
        _weight=$(detect_font_weight "$(basename "$_file")")
        case "$_weight" in
            regular) [ -n "$_regular" ] || _regular="$_file" ;;
            variable) [ -n "$_variable" ] || _variable="$_file" ;;
            medium) [ -n "$_medium" ] || _medium="$_file" ;;
        esac
    done
    for _candidate in "$_regular" "$_variable" "$_medium" "$_first" "$_fallback"; do
        [ -f "$_candidate" ] && { printf '%s\n' "$_candidate"; return 0; }
    done
    return 1
}

_hyperos_exact_weight_source() {
    _family="$1"
    _role="$2"
    for _file in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
                 "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_file" ] || continue
        [ "$(detect_font_family "$(basename "$_file")")" = "$_family" ] || continue
        [ "$(detect_font_weight "$(basename "$_file")")" = "$_role" ] || continue
        printf '%s\n' "$_file"
        return 0
    done
    return 1
}

_hyperos_weight_role() {
    case "$1" in
        100) printf 'thin\n' ;;
        200) printf 'extralight\n' ;;
        300) printf 'light\n' ;;
        500) printf 'medium\n' ;;
        600) printf 'semibold\n' ;;
        700) printf 'bold\n' ;;
        800) printf 'extrabold\n' ;;
        900) printf 'black\n' ;;
        *) printf 'regular\n' ;;
    esac
}

_hyperos_app_font_weight() {
    case "$1" in
        *ExtraBold*) printf '800\n' ;;
        *ExtraLight*) printf '200\n' ;;
        *SemiBold*) printf '600\n' ;;
        *Thin*) printf '100\n' ;;
        *Light*) printf '300\n' ;;
        *Medium*) printf '500\n' ;;
        *Bold*) printf '700\n' ;;
        *) printf '400\n' ;;
    esac
}

_hyperos_nearest_weight() {
    _weight="$1"
    case "$_weight" in ''|*[!0-9]*) _weight=400 ;; esac
    if [ "$_weight" -lt 150 ]; then printf '100\n'
    elif [ "$_weight" -lt 250 ]; then printf '200\n'
    elif [ "$_weight" -lt 350 ]; then printf '300\n'
    elif [ "$_weight" -lt 450 ]; then printf '400\n'
    elif [ "$_weight" -lt 550 ]; then printf '500\n'
    elif [ "$_weight" -lt 650 ]; then printf '600\n'
    elif [ "$_weight" -lt 750 ]; then printf '700\n'
    elif [ "$_weight" -lt 850 ]; then printf '800\n'
    else printf '900\n'
    fi
}

_hyperos_materialize_variable_weight() {
    _source="$1"
    _output="$2"
    _weight="$3"
    _module="$(_luoshu_hyperos_module_dir)"
    _pyroot="$_module/common/python"
    _python="$_pyroot/bin/luoshu-python"
    _instancer="$_module/common/font_instance.py"
    [ -x "$_python" ] && [ -f "$_instancer" ] || return 1
    PYTHONHOME="$_pyroot" \
    PYTHONPATH="$_pyroot/lib/python3.14:$_pyroot/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$_pyroot/lib:$_pyroot/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$_python" "$_instancer" --input "$_source" --output "$_output" \
        --role cjk --weight "$_weight" --axes "wght=$_weight" >/dev/null 2>&1
}

_hyperos_weight_anchor() {
    _regular="$1"
    _family="$2"
    _weight="$3"
    _dest_dir="$4"
    _role="$(_hyperos_weight_role "$_weight")"
    _source="$(_hyperos_exact_weight_source "$_family" "$_role")"
    [ -f "$_source" ] || _source="$_regular"

    if type is_variable_font >/dev/null 2>&1 && is_variable_font "$_source"; then
        _output="$_dest_dir/.luoshu-font-store/wght-${_weight}.font"
        rm -f "$_output" 2>/dev/null || true
        if _hyperos_materialize_variable_weight "$_source" "$_output" "$_weight" && [ -s "$_output" ]; then
            chmod 0644 "$_output" 2>/dev/null || true
            printf '%s\n' "$_output"
            return 0
        fi
    fi
    _font_anchor "$_source" "$_dest_dir" "wght-${_weight}"
}

_hyperos_anchor_for_weight() {
    _module="$1"
    _regular_anchor="$2"
    _weight="$(_hyperos_nearest_weight "$3")"
    _anchor="$_module/system/fonts/.luoshu-font-store/wght-${_weight}.font"
    [ -s "$_anchor" ] || _anchor="$_regular_anchor"
    printf '%s\n' "$_anchor"
}

# HyperOS 3 的 framework、系统 App 与 Google App 并不只走固定 MiSans 文件名。
# 本实现同时覆盖固定兼容槽，以及当前设备 fonts.xml / fonts_customization.xml 中
# 真正注册的 UI 字体文件；Emoji、符号、等宽、衬线与时钟专用字体始终排除。
copy_as_hyperos() {
    src="$1"
    dest_dir="$2"
    mode="${3:-full}"
    font_family="${4:-}"
    _module="$(_luoshu_hyperos_module_dir)"
    [ -n "$font_family" ] || font_family=$(detect_font_family "$(basename "$src")")
    regular="$(_hyperos_pick_regular_source "$font_family" "$src")" || return 1

    while IFS='|' read -r _real _overlay; do
        [ -n "$_overlay" ] && mkdir -p "$_overlay" 2>/dev/null || true
    done <<EOF_PAIRS
$(_luoshu_hyperos_root_pairs)
EOF_PAIRS
    mkdir -p "$_module/config" 2>/dev/null || true

    for _file in $(get_all_hyperos_files); do _hyperos_remove_overlay_file "$_file"; done
    _font_store_reset "$_module/system/fonts"
    regular_anchor=$(_font_anchor "$regular" "$_module/system/fonts" regular) || return 1

    # 预先生成完整字重锚点，供数字槽、Roboto/GoogleSans 和 XML 动态槽共用。
    for _weight in 100 200 300 400 500 600 700 800 900; do
        _anchor=$(_hyperos_weight_anchor "$regular" "$font_family" "$_weight" "$_module/system/fonts")
        [ -s "$_anchor" ] || true
    done

    _log_step '  正在应用用户字体（HyperOS 全局动态映射）...'
    core_count=0
    for _file in $(_hyperos_core_files); do
        _added=$(_hyperos_alias_existing_targets "$regular_anchor" "$_file")
        case "$_added" in ''|*[!0-9]*) _added=0 ;; esac
        core_count=$((core_count + _added))
    done

    # 极少数旧 MIUI 设备没有可探测的 MiSans 路径时，保留一个最小兼容目标。
    if [ "$core_count" -eq 0 ]; then
        if _font_alias "$regular_anchor" "$_module/system/fonts/MiSansVF.ttf"; then
            core_count=1
        fi
    fi

    weight_count=0
    for _file in $(_hyperos_weight_files); do
        _weight=${_file%.ttf}
        _anchor=$(_hyperos_anchor_for_weight "$_module" "$regular_anchor" "$_weight")
        _added=$(_hyperos_alias_existing_targets "$_anchor" "$_file")
        case "$_added" in ''|*[!0-9]*) _added=0 ;; esac
        weight_count=$((weight_count + _added))
    done

    app_count=0
    for _file in $(_hyperos_app_font_files); do
        _weight=$(_hyperos_app_font_weight "$_file")
        _anchor=$(_hyperos_anchor_for_weight "$_module" "$regular_anchor" "$_weight")
        _added=$(_hyperos_alias_existing_targets "$_anchor" "$_file")
        case "$_added" in ''|*[!0-9]*) _added=0 ;; esac
        app_count=$((app_count + _added))
    done

    dynamic_count=0
    _state="$(_hyperos_dynamic_state_file)"
    _state_tmp="${_state}.tmp.$$"
    : > "$_state_tmp"
    _hyperos_config_targets | while IFS='|' read -r _file _weight _family; do
        [ -n "$_file" ] || continue
        _anchor=$(_hyperos_anchor_for_weight "$_module" "$regular_anchor" "$_weight")
        _added=$(_hyperos_alias_existing_targets "$_anchor" "$_file")
        case "$_added" in ''|*[!0-9]*) _added=0 ;; esac
        if [ "$_added" -gt 0 ]; then
            printf '%s\n' "$_file" >> "$_state_tmp"
            printf '%s\n' "$_added" >> "$_state_tmp.count"
        fi
    done
    if [ -f "$_state_tmp.count" ]; then
        dynamic_count=$(awk '{ total += $1 } END { print total + 0 }' "$_state_tmp.count" 2>/dev/null)
    fi
    sort -u "$_state_tmp" > "$_state" 2>/dev/null || mv -f "$_state_tmp" "$_state" 2>/dev/null || true
    rm -f "$_state_tmp" "$_state_tmp.count" 2>/dev/null || true
    chmod 0644 "$_state" 2>/dev/null || true

    _log_step "  已覆盖 $core_count 个 MiSans 核心目标、$weight_count 个数字字重目标"
    _log_step "  已覆盖 $app_count 个固定应用字体目标、$dynamic_count 个本机 XML 动态目标"
    return 0
}
