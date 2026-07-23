#!/system/bin/sh
# 洛书无 Hook 全局字体覆盖增强层。
# 必须在 rom_adapters.sh 之后 source；这里重新定义 HyperOS 映射和统一 ROM 分发入口。
set +e

_luoshu_hyperos_module_dir() {
    printf '%s\n' "${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
}

_luoshu_font_config_runtime="$(_luoshu_hyperos_module_dir)/common/font_config_runtime.sh"
[ -f "$_luoshu_font_config_runtime" ] && . "$_luoshu_font_config_runtime"
_luoshu_font_config_weights="$(_luoshu_hyperos_module_dir)/common/font_config_weights.sh"
[ -f "$_luoshu_font_config_weights" ] && . "$_luoshu_font_config_weights"

_luoshu_hyperos_root_pairs() {
    _module="$(_luoshu_hyperos_module_dir)"
    printf '%s|%s\n' "${LUOSHU_SYSTEM_FONTS_ROOT:-/system/fonts}" "$_module/system/fonts"
    printf '%s|%s\n' "${LUOSHU_PRODUCT_FONTS_ROOT:-/product/fonts}" "$_module/product/fonts"
    printf '%s|%s\n' "${LUOSHU_SYSTEM_EXT_FONTS_ROOT:-/system_ext/fonts}" "$_module/system_ext/fonts"
    printf '%s|%s\n' "${LUOSHU_MI_EXT_FONTS_ROOT:-/mi_ext/fonts}" "$_module/mi_ext/fonts"
}

_hyperos_core_files() {
    printf '%s\n' 'MiSansVF.ttf MiSansVF_Overlay.ttf MiSansLatinVF.ttf MiSansTCVF.ttf MiSansL3.otf'
}

_hyperos_weight_files() {
    printf '%s\n' '100.ttf 200.ttf 300.ttf 350.ttf 400.ttf 500.ttf 600.ttf 700.ttf 800.ttf 900.ttf'
}

_hyperos_metric_shell_files() {
    printf '%s\n' 'Roboto-Thin.ttf Roboto-ThinItalic.ttf Roboto-ExtraLight.ttf Roboto-ExtraLightItalic.ttf Roboto-Light.ttf Roboto-LightItalic.ttf Roboto-Regular.ttf Roboto-Italic.ttf Roboto-Medium.ttf Roboto-MediumItalic.ttf Roboto-SemiBold.ttf Roboto-SemiBoldItalic.ttf Roboto-Bold.ttf Roboto-BoldItalic.ttf Roboto-ExtraBold.ttf Roboto-ExtraBoldItalic.ttf RobotoFlex-Regular.ttf RobotoStatic-Regular.ttf GoogleSans-Regular.ttf GoogleSans-Medium.ttf GoogleSans-Bold.ttf GoogleSansText-Regular.ttf GoogleSansText-Medium.ttf GoogleSansText-Bold.ttf GoogleSansFlex-Regular.ttf'
}

# Google Play、系统搜索框、安装器和部分 Launcher/设置页面会直接打开这些物理槽。
_hyperos_upright_ui_files() {
    {
        printf '%s\n' 'Roboto-Thin.ttf Roboto-ExtraLight.ttf Roboto-Light.ttf Roboto-Regular.ttf Roboto-Medium.ttf Roboto-SemiBold.ttf Roboto-Bold.ttf Roboto-ExtraBold.ttf Roboto-Black.ttf RobotoFlex-Regular.ttf RobotoStatic-Regular.ttf GoogleSans-Regular.ttf GoogleSans-Medium.ttf GoogleSans-SemiBold.ttf GoogleSans-Bold.ttf GoogleSans-Black.ttf GoogleSansText-Regular.ttf GoogleSansText-Medium.ttf GoogleSansText-SemiBold.ttf GoogleSansText-Bold.ttf GoogleSansText-Black.ttf GoogleSansText-VF.ttf GoogleSansTextVF.ttf GoogleSans-VF.ttf GoogleSansFlex-Regular.ttf'
        while IFS='|' read -r _real _overlay; do
            [ -d "$_real" ] || continue
            for _path in "$_real"/Roboto*.ttf "$_real"/GoogleSans*.ttf; do
                [ -f "$_path" ] || continue
                _name=${_path##*/}
                case "$_name" in *Italic*|*Oblique*|*Mono*|*Emoji*|*Symbol*|*Icon*) continue ;; esac
                printf '%s\n' "$_name"
            done
        done <<EOF_UI_ROOTS
$(_luoshu_hyperos_root_pairs)
EOF_UI_ROOTS
    } | awk 'NF && !seen[$0]++'
}

# HyperOS 时钟、控制中心和部分管理页会绕过默认 family，直接读取 Mitype/MiClock 等槽。
_hyperos_clock_ui_files() {
    {
        printf '%s\n' 'MitypeVF.ttf MitypeMonoVF.ttf MitypeClock.ttf MitypeClock.otf MitypeClockMono.ttf MitypeClockMono.otf MiClock.ttf MiClock.otf MiClockThin.ttf MiClockThin.otf MiClockMono.ttf MiClockMono.otf MiSansClock.ttf MiSansClockVF.ttf AndroidClock.ttf AndroidClock_Highlight.ttf AndroidClock_Solid.ttf Clockopia.ttf'
        while IFS='|' read -r _real _overlay; do
            [ -d "$_real" ] || continue
            for _path in "$_real"/Mitype*.ttf "$_real"/Mitype*.otf \
                         "$_real"/MiClock*.ttf "$_real"/MiClock*.otf \
                         "$_real"/MiSans*Clock*.ttf "$_real"/MiSans*Clock*.otf \
                         "$_real"/AndroidClock*.ttf "$_real"/Clockopia.ttf; do
                [ -f "$_path" ] || continue
                _name=${_path##*/}
                case "$_name" in *Italic*|*Oblique*|*Emoji*|*Symbol*|*Icon*) continue ;; esac
                printf '%s\n' "$_name"
            done
        done <<EOF_CLOCK_ROOTS
$(_luoshu_hyperos_root_pairs)
EOF_CLOCK_ROOTS
    } | awk 'NF && !seen[$0]++'
}

get_all_hyperos_files() {
    printf '%s %s %s %s %s\n' "$(_hyperos_core_files)" "$(_hyperos_weight_files)" \
        "$(_hyperos_metric_shell_files)" "$(_hyperos_upright_ui_files)" "$(_hyperos_clock_ui_files)"
}

_hyperos_remove_overlay_file() {
    _file="$1"
    _module="$(_luoshu_hyperos_module_dir)"
    rm -f "$_module/system/fonts/$_file" "$_module/product/fonts/$_file" \
        "$_module/system_ext/fonts/$_file" "$_module/mi_ext/fonts/$_file" 2>/dev/null || true
}

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
    _regular=''; _variable=''; _medium=''; _first=''
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
    _family="$1"; _role="$2"
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
        100) printf 'thin\n' ;; 200) printf 'extralight\n' ;; 300) printf 'light\n' ;;
        500) printf 'medium\n' ;; 600) printf 'semibold\n' ;; 700) printf 'bold\n' ;;
        800) printf 'extrabold\n' ;; 900) printf 'black\n' ;; *) printf 'regular\n' ;;
    esac
}

_hyperos_file_weight() {
    _name=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
    case "$_name" in
        *extrabold*|*extra-bold*) printf '800\n' ;; *semibold*|*semi-bold*|*demibold*) printf '600\n' ;;
        *extralight*|*extra-light*) printf '200\n' ;; *medium*) printf '500\n' ;;
        *black*|*heavy*) printf '900\n' ;; *bold*) printf '700\n' ;; *light*) printf '300\n' ;;
        *thin*) printf '100\n' ;; *) printf '400\n' ;;
    esac
}

# 对 HyperOS 物理槽使用固定 0.98/0.30 em 行框。禁止按字体极端轮廓扩大 hhea/typo，
# 避免 QQ 回复栏偏移、年龄标签裁切以及酷安标题与热度重叠。
_hyperos_compact_normalize() {
    _source="$1"; _output="$2"
    _module="$(_luoshu_hyperos_module_dir)"
    _pyroot="$_module/common/python"
    _python="$_pyroot/bin/luoshu-python"
    [ -x "$_python" ] && [ -f "$_module/common/font_metrics_normalize.py" ] || return 1
    PYTHONHOME="$_pyroot" \
    PYTHONPATH="$_module/common:$_pyroot/lib/python3.14:$_pyroot/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$_pyroot/lib:$_pyroot/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$_python" - "$_source" "$_output" <<'PY_COMPACT' >/dev/null 2>&1
import sys
from pathlib import Path
import font_metrics_normalize as metrics
metrics.TYPO_ASCENDER_RATIO = 0.98
metrics.TYPO_DESCENDER_RATIO = 0.30
metrics.WIN_ASCENT_CAP_RATIO = 0.98
metrics.WIN_DESCENT_CAP_RATIO = 0.35
metrics.HHEA_ASCENT_CAP_RATIO = 0.98
metrics.HHEA_DESCENT_CAP_RATIO = 0.30
metrics._outline_extremes = lambda font: None
metrics.normalize_path(Path(sys.argv[1]), Path(sys.argv[2]))
PY_COMPACT
}

_hyperos_compact_anchor() {
    _source="$1"; _dest_dir="$2"; _key="$3"
    _output="$_dest_dir/.luoshu-font-store/compact-${_key}.font"
    if [ -s "$_output" ]; then
        printf '%s\n' "$_output"
        return 0
    fi
    rm -f "$_output" 2>/dev/null || true
    if _hyperos_compact_normalize "$_source" "$_output" && [ -s "$_output" ]; then
        chmod 0644 "$_output" 2>/dev/null || true
        printf '%s\n' "$_output"
        return 0
    fi
    _font_anchor "$_source" "$_dest_dir" "$_key"
}

_hyperos_materialize_variable_weight() {
    _source="$1"; _output="$2"; _weight="$3"
    [ -s "$_output" ] && return 0
    _module="$(_luoshu_hyperos_module_dir)"
    _pyroot="$_module/common/python"; _python="$_pyroot/bin/luoshu-python"
    _instancer="$_module/common/font_instance.py"; _raw="${_output}.raw"
    [ -x "$_python" ] && [ -f "$_instancer" ] || return 1
    rm -f "$_raw" "$_output" 2>/dev/null || true
    PYTHONHOME="$_pyroot" \
    PYTHONPATH="$_pyroot/lib/python3.14:$_pyroot/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$_pyroot/lib:$_pyroot/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$_python" "$_instancer" --input "$_source" --output "$_raw" \
        --role cjk --weight "$_weight" --axes "wght=$_weight" >/dev/null 2>&1 || return 1
    _hyperos_compact_normalize "$_raw" "$_output"
    _rc=$?
    rm -f "$_raw" 2>/dev/null || true
    return "$_rc"
}

_hyperos_weight_anchor() {
    _regular="$1"; _family="$2"; _weight="$3"; _dest_dir="$4"
    _role="$(_hyperos_weight_role "$_weight")"
    _source="$(_hyperos_exact_weight_source "$_family" "$_role")"
    [ -f "$_source" ] || _source="$_regular"
    if type is_variable_font >/dev/null 2>&1 && is_variable_font "$_source"; then
        _output="$_dest_dir/.luoshu-font-store/compact-wght-${_weight}.font"
        if _hyperos_materialize_variable_weight "$_source" "$_output" "$_weight" && [ -s "$_output" ]; then
            chmod 0644 "$_output" 2>/dev/null || true
            printf '%s\n' "$_output"
            return 0
        fi
    fi
    _hyperos_compact_anchor "$_source" "$_dest_dir" "wght-${_weight}"
}

_hyperos_is_config_weight() {
    case "$1" in 100|200|300|400|500|600|700|800|900) return 0 ;; *) return 1 ;; esac
}

copy_as_hyperos() {
    src="$1"; dest_dir="$2"; mode="${3:-full}"; font_family="${4:-}"
    _module="$(_luoshu_hyperos_module_dir)"
    [ -n "$font_family" ] || font_family=$(detect_font_family "$(basename "$src")")
    regular="$(_hyperos_pick_regular_source "$font_family" "$src")" || return 1

    mkdir -p "$_module/system/fonts" "$_module/product/fonts" "$_module/system_ext/fonts" "$_module/mi_ext/fonts" 2>/dev/null || true
    # 先清除旧版生成的 XML/动态目标，再写入新的物理槽；禁止在映射完成后清理，
    # 否则旧 manifest 可能把刚生成的 Roboto/GoogleSans 目标一并删除。
    type font_config_disable >/dev/null 2>&1 && font_config_disable >/dev/null 2>&1 || true
    for _file in $(get_all_hyperos_files); do _hyperos_remove_overlay_file "$_file"; done
    _font_store_reset "$_module/system/fonts"
    regular_anchor=$(_hyperos_compact_anchor "$regular" "$_module/system/fonts" regular) || return 1

    _log_step '  正在应用用户字体（HyperOS 紧凑控件与完整物理槽映射）...'
    core_count=0
    for _file in $(_hyperos_core_files); do
        _added=$(_hyperos_alias_existing_targets "$regular_anchor" "$_file")
        case "$_added" in ''|*[!0-9]*) _added=0 ;; esac
        core_count=$((core_count + _added))
    done
    if [ "$core_count" -eq 0 ]; then
        _font_alias "$regular_anchor" "$_module/system/fonts/MiSansVF.ttf" && core_count=1
    fi

    weight_count=0; config_weight_count=0
    for _file in $(_hyperos_weight_files); do
        _weight=${_file%.ttf}
        _anchor=$(_hyperos_weight_anchor "$regular" "$font_family" "$_weight" "$_module/system/fonts")
        [ -s "$_anchor" ] || _anchor="$regular_anchor"
        _added=$(_hyperos_alias_existing_targets "$_anchor" "$_file")
        case "$_added" in ''|*[!0-9]*) _added=0 ;; esac
        weight_count=$((weight_count + _added))
        if _hyperos_is_config_weight "$_weight" && _font_alias "$_anchor" "$_module/system/fonts/LuoShu-${_weight}.ttf"; then
            config_weight_count=$((config_weight_count + 1))
        fi
    done

    ui_slot_count=0
    for _file in $(_hyperos_upright_ui_files); do
        _weight=$(_hyperos_file_weight "$_file")
        _anchor=$(_hyperos_weight_anchor "$regular" "$font_family" "$_weight" "$_module/system/fonts")
        [ -s "$_anchor" ] || _anchor="$regular_anchor"
        _added=$(_hyperos_alias_existing_targets "$_anchor" "$_file")
        case "$_added" in ''|*[!0-9]*) _added=0 ;; esac
        ui_slot_count=$((ui_slot_count + _added))
    done

    clock_slot_count=0
    for _file in $(_hyperos_clock_ui_files); do
        _weight=$(_hyperos_file_weight "$_file")
        _anchor=$(_hyperos_weight_anchor "$regular" "$font_family" "$_weight" "$_module/system/fonts")
        [ -s "$_anchor" ] || _anchor="$regular_anchor"
        _added=$(_hyperos_alias_existing_targets "$_anchor" "$_file")
        case "$_added" in ''|*[!0-9]*) _added=0 ;; esac
        clock_slot_count=$((clock_slot_count + _added))
    done

    # HyperOS 的 XML family 经常只是度量外壳。这里保留 ROM XML，避免再次用旧度量
    # 覆盖紧凑物理槽；MiSans、Roboto、GoogleSans、Mitype 与时钟槽已完整映射。
    _log_step "  已覆盖 $core_count 个 MiSans 核心、$weight_count 个数字字重、$ui_slot_count 个 Google/Roboto、$clock_slot_count 个时钟/Mitype 目标"
    _log_step '  已启用固定紧凑行框，QQ/酷安/标签控件不再随字体极端轮廓漂移'
    return 0
}

apply_font_by_rom() {
    src="$1"; dest_dir="$2"; mode="${3:-full}"; font_family="${4:-}"
    [ -n "$font_family" ] || font_family=$(detect_font_family "$(basename "$src")")
    if [ "${IS_HYPEROS:-false}" = true ]; then
        copy_as_hyperos "$src" "$dest_dir" "$mode" "$font_family"
        return $?
    elif [ "${IS_COLOROS:-false}" = true ]; then
        copy_as_coloros "$src" "$dest_dir" "$mode" "$font_family" || return $?
    else
        copy_as_generic "$src" "$dest_dir" "$mode" || return $?
    fi
    if type font_config_enable_for_payload >/dev/null 2>&1; then
        font_config_enable_for_payload "$font_family" || _log_step '  设备没有可安全启用的字体 XML，继续使用文件槽映射'
    fi
    return 0
}
