#!/system/bin/sh
# LuoShu v13.6 Beta1 - ROM font target adapter
set +e

MODULE_DIR="${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
[ -f "$MODULE_DIR/common/db_engine" ] && . "$MODULE_DIR/common/db_engine"

_log_step() {
    if command -v ui_print >/dev/null 2>&1; then ui_print "$1"; else echo "  [洛书] $1"; fi
}

_verify_font_copy() {
    [ -s "$1" ] || return 1
    _sz=$(wc -c < "$1" 2>/dev/null | tr -d '[:space:]')
    case "$_sz" in ''|*[!0-9]*) _sz=0 ;; esac
    [ "$_sz" -ge 1024 ] 2>/dev/null
}

_font_store_reset() {
    _d="$1"
    rm -rf "$_d/.luoshu-font-store" 2>/dev/null || true
    command mkdir -p "$_d/.luoshu-font-store" 2>/dev/null || true
    chmod 0755 "$_d/.luoshu-font-store" 2>/dev/null || true
}

_font_anchor() {
    _src="$1"; _d="$2"; _key="$3"
    _a="$_d/.luoshu-font-store/${_key}.font"
    cp -f "$_src" "$_a" 2>/dev/null || return 1
    chmod 0644 "$_a" 2>/dev/null || true
    printf '%s\n' "$_a"
}

_font_alias() {
    _a="$1"; _d="$2"
    rm -f "$_d" 2>/dev/null || true
    ln "$_a" "$_d" 2>/dev/null || cp -f "$_a" "$_d" 2>/dev/null || return 1
    chmod 0644 "$_d" 2>/dev/null || true
}

link_or_copy_font() {
    _src="$1"; _dst="$2"
    rm -f "$_dst" 2>/dev/null || true
    ln "$_src" "$_dst" 2>/dev/null || cp -f "$_src" "$_dst" 2>/dev/null || return 1
    chmod 0644 "$_dst" 2>/dev/null || true
}

_coloros_extra_names() {
    echo "SysSans-En-Bold SysSans-En-Light SysSans-En-Medium SysSans-En-Thin SysSans-En-Black SysFont-Bold SysFont-Light SysFont-Medium SysFont-Thin SysFont-Black SysFont-Hans-Bold SysFont-Hans-Light SysFont-Hans-Medium SysFont-Hans-Thin SysFont-Hant-Bold SysFont-Hant-Light SysFont-Hant-Medium SysFont-Hant-Thin SysSans-Hant-Bold SysSans-Hant-Light SysSans-Hant-Medium SysSans-Hans-Bold SysSans-Hans-Light SysSans-Hans-Medium SysFont-Static-Bold SysFont-Static-Light SysFont-Static-Medium DINCondensedBold DINPro-Bold DINPro-Medium DINPro-Regular OPPODIN-Bold OPPODIN-Medium OPPODIN-Regular OPPODINCondensed-Bold OPPODINCondensed-Medium OPPODINCondensed-Regular Opposans-En-Regular Opposans-Hans-Regular Opposans-En-Bold Opposans-Hans-Bold Opposans-En-Medium Opposans-Hans-Medium Opposans-En-Light Opposans-Hans-Light OPSans-En-Regular Roboto-Regular Roboto-Medium Roboto-Bold Roboto-Light Roboto-Thin RobotoFlex-Regular RobotoStatic-Regular GoogleSans-Regular GoogleSans-Medium GoogleSans-Bold GoogleSansText-Regular GoogleSansText-Medium GoogleSansText-Bold GoogleSansFlex-Regular SourceSansPro-Regular SourceSansPro-SemiBold SourceSansPro-Bold"
}

get_all_hyperos_files() {
    echo "MiSansVF.ttf MiSansVF_Overlay.ttf MiSansLatinVF.ttf MiSansTCVF.ttf MiSansL3.otf 100.ttf 200.ttf 300.ttf 350.ttf 400.ttf 500.ttf 600.ttf 700.ttf 800.ttf 900.ttf Roboto-Thin.ttf Roboto-ThinItalic.ttf Roboto-ExtraLight.ttf Roboto-ExtraLightItalic.ttf Roboto-Light.ttf Roboto-LightItalic.ttf Roboto-Regular.ttf Roboto-Italic.ttf Roboto-Medium.ttf Roboto-MediumItalic.ttf Roboto-SemiBold.ttf Roboto-SemiBoldItalic.ttf Roboto-Bold.ttf Roboto-BoldItalic.ttf Roboto-ExtraBold.ttf Roboto-ExtraBoldItalic.ttf RobotoFlex-Regular.ttf RobotoStatic-Regular.ttf GoogleSans-Regular.ttf GoogleSans-Medium.ttf GoogleSans-Bold.ttf GoogleSansText-Regular.ttf GoogleSansText-Medium.ttf GoogleSansText-Bold.ttf GoogleSansFlex-Regular.ttf"
}

get_all_generic_files() {
    echo "Roboto-Regular.ttf Roboto-Bold.ttf Roboto-Italic.ttf Roboto-BoldItalic.ttf Roboto-Medium.ttf Roboto-Light.ttf Roboto-Thin.ttf Roboto-Black.ttf GoogleSans-Regular.ttf GoogleSans-Medium.ttf GoogleSans-Bold.ttf GoogleSansText-Regular.ttf GoogleSansText-Medium.ttf GoogleSansText-Bold.ttf GoogleSansFlex-Regular.ttf NotoSans-Regular.ttf DroidSans.ttf DroidSans-Bold.ttf"
}

_rom_exact_target_exists() {
    _f="$1"
    for _r in /system/fonts /system_ext/fonts /product/fonts /my_product/fonts /vendor/fonts; do
        [ -f "$_r/$_f" ] && return 0
    done
    return 1
}

_weight_from_name() {
    case "$1" in
        100.ttf|*Thin*|*XThin*) echo thin ;;
        200.ttf|*ExtraLight*) echo light ;;
        300.ttf|*Light*) echo light ;;
        500.ttf|*Medium*) echo medium ;;
        600.ttf|*SemiBold*) echo semibold ;;
        700.ttf|*Bold*|*CondensedBold*) echo bold ;;
        800.ttf|*ExtraBold*) echo black ;;
        900.ttf|*Black*) echo black ;;
        *) echo regular ;;
    esac
}

_source_for_target() {
    _regular="$1"; _family="$2"; _target="$3"
    _w=$(_weight_from_name "$_target")
    if [ "$_w" != regular ] && [ -n "$_family" ] && type get_weight_file >/dev/null 2>&1; then
        _candidate=$(get_weight_file "$_family" "$_w" 2>/dev/null)
        [ -s "$_candidate" ] && { printf '%s\n' "$_candidate"; return 0; }
    fi
    printf '%s\n' "$_regular"
}

_db_add_existing() {
    _src="$1"; _file="$2"; _include_data="${3:-0}"
    for _root in /system/fonts /system_ext/fonts /product/fonts /my_product/fonts /vendor/fonts; do
        [ -f "$_root/$_file" ] && luoshu_db_add "$_src" "$_root/$_file"
    done
    if [ "$_include_data" = 1 ] && [ -f "/data/fonts/$_file" ]; then
        luoshu_db_add "$_src" "/data/fonts/$_file"
    fi
}

_prepare_db_coloros() {
    _regular="$1"; _family="$2"
    _names="$(get_all_coloros_names 2>/dev/null) $(_coloros_extra_names)"
    for _name in $_names; do
        _file="${_name}.ttf"
        _src=$(_source_for_target "$_regular" "$_family" "$_file")
        _db_add_existing "$_src" "$_file" 1
    done
}

_prepare_db_hyperos() {
    _regular="$1"; _family="$2"
    for _file in $(get_all_hyperos_files); do
        case "$_file" in MiSansVF.ttf|MiSansVF_Overlay.ttf|MiSansLatinVF.ttf|MiSansTCVF.ttf|MiSansL3.otf) _src="$_regular" ;; *) _src=$(_source_for_target "$_regular" "$_family" "$_file") ;; esac
        _db_add_existing "$_src" "$_file" 0
    done
}

_prepare_db_generic() {
    _regular="$1"; _family="$2"
    for _file in $(get_all_generic_files); do
        _src=$(_source_for_target "$_regular" "$_family" "$_file")
        _db_add_existing "$_src" "$_file" 0
    done
}

_prepare_db_font() {
    _src="$1"; _family="$2"
    luoshu_db_begin || return 1
    if [ "$IS_HYPEROS" = true ]; then
        _prepare_db_hyperos "$_src" "$_family"
    elif [ "$IS_COLOROS" = true ]; then
        _prepare_db_coloros "$_src" "$_family"
    else
        _prepare_db_generic "$_src" "$_family"
    fi
    luoshu_db_finish
}

_copy_module_targets() {
    _src="$1"; _dest="$2"; _family="$3"; _files="$4"
    command mkdir -p "$_dest" 2>/dev/null || return 1
    _font_store_reset "$_dest"
    _count=0
    for _file in $_files; do
        _rom_exact_target_exists "$_file" || continue
        _selected=$(_source_for_target "$_src" "$_family" "$_file")
        _key=$(_weight_from_name "$_file")
        _anchor="$_dest/.luoshu-font-store/${_key}.font"
        if [ ! -s "$_anchor" ]; then
            cp -f "$_selected" "$_anchor" 2>/dev/null || continue
            chmod 0644 "$_anchor" 2>/dev/null || true
        fi
        _font_alias "$_anchor" "$_dest/$_file" && _count=$((_count + 1))
    done
    _log_step "已准备 $_count 个系统字体目标"
    [ "$_count" -gt 0 ]
}

copy_as_coloros() {
    _src="$1"; _dest="$2"; _family="$4"
    _files=""
    for _n in $(get_all_coloros_names 2>/dev/null) $(_coloros_extra_names); do _files="$_files ${_n}.ttf"; done
    _copy_module_targets "$_src" "$_dest" "$_family" "$_files"
}

copy_as_hyperos() { _copy_module_targets "$1" "$2" "$4" "$(get_all_hyperos_files)"; }
copy_as_generic() { _copy_module_targets "$1" "$2" "$4" "$(get_all_generic_files)"; }

apply_font_by_rom() {
    _src="$1"; _dest="$2"; _mode="${3:-full}"; _family="$4"
    if type luoshu_db_use_direct >/dev/null 2>&1 && luoshu_db_use_direct; then
        rm -rf "$_dest/.luoshu-font-store" 2>/dev/null || true
        for _f in "$_dest"/*.ttf "$_dest"/*.otf "$_dest"/*.ttc; do [ -f "$_f" ] && rm -f "$_f" 2>/dev/null || true; done
        _prepare_db_font "$_src" "$_family" || return 1
        _log_step "兼容环境已启用 DB 模式：不生成批量系统字体副本"
        return 0
    fi
    if [ "$IS_HYPEROS" = true ]; then
        copy_as_hyperos "$_src" "$_dest" "$_mode" "$_family"
    elif [ "$IS_COLOROS" = true ]; then
        copy_as_coloros "$_src" "$_dest" "$_mode" "$_family"
    else
        copy_as_generic "$_src" "$_dest" "$_mode" "$_family"
    fi
}
