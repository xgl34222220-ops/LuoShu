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
}

_hyperos_core_files() {
    printf '%s\n' 'MiSansVF.ttf MiSansVF_Overlay.ttf MiSansLatinVF.ttf MiSansTCVF.ttf MiSansL3.otf'
}

_hyperos_weight_files() {
    printf '%s\n' '100.ttf 200.ttf 300.ttf 350.ttf 400.ttf 500.ttf 600.ttf 700.ttf 800.ttf 900.ttf'
}

_hyperos_app_font_files() {
    printf '%s\n' 'Roboto-Thin.ttf Roboto-ThinItalic.ttf Roboto-ExtraLight.ttf Roboto-ExtraLightItalic.ttf Roboto-Light.ttf Roboto-LightItalic.ttf Roboto-Regular.ttf Roboto-Italic.ttf Roboto-Medium.ttf Roboto-MediumItalic.ttf Roboto-SemiBold.ttf Roboto-SemiBoldItalic.ttf Roboto-Bold.ttf Roboto-BoldItalic.ttf Roboto-ExtraBold.ttf Roboto-ExtraBoldItalic.ttf RobotoFlex-Regular.ttf RobotoStatic-Regular.ttf GoogleSans-Regular.ttf GoogleSans-Medium.ttf GoogleSans-Bold.ttf GoogleSansText-Regular.ttf GoogleSansText-Medium.ttf GoogleSansText-Bold.ttf GoogleSansFlex-Regular.ttf'
}

# 返回完整清理清单。每次提交先清除旧分区负载，再按 ROM 中的真实路径重建。
get_all_hyperos_files() {
    printf '%s %s %s\n' "$(_hyperos_core_files)" "$(_hyperos_weight_files)" "$(_hyperos_app_font_files)"
}

_hyperos_remove_overlay_file() {
    _file="$1"
    _module="$(_luoshu_hyperos_module_dir)"
    rm -f "$_module/system/fonts/$_file" "$_module/product/fonts/$_file" \
        "$_module/system_ext/fonts/$_file" 2>/dev/null || true
}

# 把一个字体锚点写到 ROM 中该文件真实存在的分区；输出成功目标数量。
_hyperos_alias_existing_targets() {
    _anchor="$1"
    _file="$2"
    _count=0
    while IFS='|' read -r _real _overlay; do
        [ -n "$_real" ] && [ -n "$_overlay" ] || continue
        [ -e "$_real/$_file" ] || continue
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

# HyperOS 3 的 framework、系统 App 与 Google App 并不只走 MiSans：
# 部分组件会直接请求 Roboto/GoogleSans。这里只覆盖 ROM 中真实存在的目标，
# 并按 100~900 字重锚点映射，避免全部退化成 Regular。
copy_as_hyperos() {
    src="$1"
    dest_dir="$2"
    mode="${3:-full}"
    font_family="${4:-}"
    _module="$(_luoshu_hyperos_module_dir)"
    [ -n "$font_family" ] || font_family=$(detect_font_family "$(basename "$src")")
    regular="$(_hyperos_pick_regular_source "$font_family" "$src")" || return 1

    mkdir -p "$_module/system/fonts" "$_module/product/fonts" "$_module/system_ext/fonts" 2>/dev/null || true
    for _file in $(get_all_hyperos_files); do _hyperos_remove_overlay_file "$_file"; done
    _font_store_reset "$_module/system/fonts"
    regular_anchor=$(_font_anchor "$regular" "$_module/system/fonts" regular) || return 1

    _log_step '  正在应用用户字体（HyperOS 全局映射）...'
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
        _anchor=$(_hyperos_weight_anchor "$regular" "$font_family" "$_weight" "$_module/system/fonts")
        [ -s "$_anchor" ] || _anchor="$regular_anchor"
        _added=$(_hyperos_alias_existing_targets "$_anchor" "$_file")
        case "$_added" in ''|*[!0-9]*) _added=0 ;; esac
        weight_count=$((weight_count + _added))
    done

    app_count=0
    for _file in $(_hyperos_app_font_files); do
        _weight=$(_hyperos_app_font_weight "$_file")
        _anchor="$_module/system/fonts/.luoshu-font-store/wght-${_weight}.font"
        [ -s "$_anchor" ] || _anchor="$regular_anchor"
        _added=$(_hyperos_alias_existing_targets "$_anchor" "$_file")
        case "$_added" in ''|*[!0-9]*) _added=0 ;; esac
        app_count=$((app_count + _added))
    done

    _log_step "  已按真实分区覆盖 $core_count 个 MiSans 核心目标、$weight_count 个数字字重目标"
    _log_step "  已按真实字重覆盖 $app_count 个 Roboto/GoogleSans 应用字体目标"
    return 0
}
