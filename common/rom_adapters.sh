#!/system/bin/sh
# LuoShu ROM adapters. Weight-specific aliases are created only for real font-defined weights.
set +e

_verify_font_copy() {
    _f="$1"; [ -s "$_f" ] || return 1
    _size=$(wc -c <"$_f" 2>/dev/null | tr -d '[:space:]'); case "$_size" in ''|*[!0-9]*) _size=0 ;; esac
    [ "$_size" -ge 1024 ] 2>/dev/null
}
_font_store_reset() {
    _dest="$1"; rm -rf "$_dest/.luoshu-font-store" 2>/dev/null || true
    mkdir -p "$_dest/.luoshu-font-store" 2>/dev/null || true; chmod 0755 "$_dest/.luoshu-font-store" 2>/dev/null || true
}
_font_anchor() {
    _src="$1"; _dest="$2"; _key="$3"; _anchor="$_dest/.luoshu-font-store/${_key}.font"
    cp -f "$_src" "$_anchor" 2>/dev/null || return 1; chmod 0644 "$_anchor" 2>/dev/null || true; printf '%s\n' "$_anchor"
}
_font_alias() {
    _anchor="$1"; _dest="$2"; rm -f "$_dest" 2>/dev/null || true
    ln "$_anchor" "$_dest" 2>/dev/null || cp -f "$_anchor" "$_dest" 2>/dev/null || return 1
    chmod 0644 "$_dest" 2>/dev/null || true
}
link_or_copy_font() {
    _src="$1"; _dest="$2"; rm -f "$_dest" 2>/dev/null || true
    ln "$_src" "$_dest" 2>/dev/null || cp -f "$_src" "$_dest" 2>/dev/null || return 1
    chmod 0644 "$_dest" 2>/dev/null || true
}
_rom_exact_target_exists() {
    _file="$1"
    for _root in /system/fonts /system_ext/fonts /product/fonts /my_product/fonts /vendor/fonts; do [ -e "$_root/$_file" ] && return 0; done
    return 1
}
_alias_if_target() {
    _anchor="$1"; _dest_dir="$2"; _name="$3"
    _rom_exact_target_exists "$_name" || return 0
    _font_alias "$_anchor" "$_dest_dir/$_name"
}

if ! type get_all_coloros_names >/dev/null 2>&1; then
    get_all_coloros_names() {
        echo "SysSans-Hant-Regular SysSans-Hans-Regular SysFont-Static-Regular SysFont-Myanmar SysFont-Hant-Regular SysFont-Hans-Regular SysFont-Regular SysSans-En-Regular SysSans-En-Thin SysSans-En-Light SysSans-En-Medium SysSans-En-SemiBold SysSans-En-Bold SysSans-En-Black SysFont-Thin SysFont-Light SysFont-Medium SysFont-SemiBold SysFont-Bold SysFont-Black SysFont-Hans-Thin SysFont-Hans-Light SysFont-Hans-Medium SysFont-Hans-SemiBold SysFont-Hans-Bold SysFont-Hans-Black SysFont-Hant-Thin SysFont-Hant-Light SysFont-Hant-Medium SysFont-Hant-SemiBold SysFont-Hant-Bold SysFont-Hant-Black Roboto-Thin Roboto-ExtraLight Roboto-Light Roboto-Regular Roboto-Medium Roboto-SemiBold Roboto-Bold Roboto-ExtraBold Roboto-Black GoogleSans-Regular GoogleSans-Medium GoogleSans-Bold GoogleSansText-Regular GoogleSansText-Medium GoogleSansText-Bold"
    }
fi
get_all_hyperos_files() {
    echo "MiSansVF.ttf MiSansVF_Overlay.ttf MiSansLatinVF.ttf MiSansTCVF.ttf MiSansL3.otf 100.ttf 200.ttf 300.ttf 350.ttf 400.ttf 500.ttf 600.ttf 700.ttf 800.ttf 900.ttf Roboto-Thin.ttf Roboto-ExtraLight.ttf Roboto-Light.ttf Roboto-Regular.ttf Roboto-Medium.ttf Roboto-SemiBold.ttf Roboto-Bold.ttf Roboto-ExtraBold.ttf Roboto-Black.ttf RobotoFlex-Regular.ttf RobotoStatic-Regular.ttf GoogleSans-Regular.ttf GoogleSans-Medium.ttf GoogleSans-Bold.ttf GoogleSansText-Regular.ttf GoogleSansText-Medium.ttf GoogleSansText-Bold.ttf GoogleSansFlex-Regular.ttf"
}
get_all_generic_files() {
    echo "Roboto-Thin.ttf Roboto-ExtraLight.ttf Roboto-Light.ttf Roboto-Regular.ttf Roboto-Medium.ttf Roboto-SemiBold.ttf Roboto-Bold.ttf Roboto-ExtraBold.ttf Roboto-Black.ttf GoogleSans-Regular.ttf GoogleSans-Medium.ttf GoogleSans-Bold.ttf GoogleSansText-Regular.ttf GoogleSansText-Medium.ttf GoogleSansText-Bold.ttf NotoSans-Regular.ttf DroidSans.ttf DroidSans-Bold.ttf"
}

_weight_number() { font_role_number "$1" 2>/dev/null || echo 400; }
_weight_suffix() {
    _n="$1"
    if [ "$_n" -le 149 ] 2>/dev/null; then echo Thin
    elif [ "$_n" -le 249 ] 2>/dev/null; then echo ExtraLight
    elif [ "$_n" -le 349 ] 2>/dev/null; then echo Light
    elif [ "$_n" -le 449 ] 2>/dev/null; then echo Regular
    elif [ "$_n" -le 549 ] 2>/dev/null; then echo Medium
    elif [ "$_n" -le 649 ] 2>/dev/null; then echo SemiBold
    elif [ "$_n" -le 749 ] 2>/dev/null; then echo Bold
    elif [ "$_n" -le 849 ] 2>/dev/null; then echo ExtraBold
    else echo Black; fi
}
_family_weights_or_source() {
    _family="$1"; _src="$2"
    if [ -n "$_family" ] && type family_weight_numbers >/dev/null 2>&1; then family_weight_numbers "$_family"
    elif type font_weight_numbers_for_file >/dev/null 2>&1; then font_weight_numbers_for_file "$_src"
    else echo 400; fi
}
_source_for_weight() {
    _family="$1"; _src="$2"; _weight="$3"
    if [ -n "$_family" ] && type family_file_for_weight >/dev/null 2>&1; then
        _selected=$(family_file_for_weight "$_family" "$_weight"); [ -f "$_selected" ] && { printf '%s\n' "$_selected"; return; }
    fi
    printf '%s\n' "$_src"
}
_default_source() {
    _family="$1"; _src="$2"; _selected=$(_source_for_weight "$_family" "$_src" 400)
    [ -f "$_selected" ] && printf '%s\n' "$_selected" || printf '%s\n' "$_src"
}

_coloros_regular_targets() {
    echo "SysSans-Hant-Regular.ttf SysSans-Hans-Regular.ttf SysFont-Static-Regular.ttf SysFont-Myanmar.ttf SysFont-Hant-Regular.ttf SysFont-Hans-Regular.ttf SysFont-Regular.ttf SysSans-En-Regular.ttf Roboto-Regular.ttf RobotoFlex-Regular.ttf RobotoStatic-Regular.ttf GoogleSans-Regular.ttf GoogleSansText-Regular.ttf GoogleSansFlex-Regular.ttf DINPro-Regular.ttf OPPODIN-Regular.ttf OPPODINCondensed-Regular.ttf Opposans-En-Regular.ttf Opposans-Hans-Regular.ttf OPSans-En-Regular.ttf"
}
_coloros_weight_targets() {
    _suffix="$1"
    echo "SysSans-Hant-${_suffix}.ttf SysSans-Hans-${_suffix}.ttf SysFont-Static-${_suffix}.ttf SysFont-Hant-${_suffix}.ttf SysFont-Hans-${_suffix}.ttf SysFont-${_suffix}.ttf SysSans-En-${_suffix}.ttf Roboto-${_suffix}.ttf GoogleSans-${_suffix}.ttf GoogleSansText-${_suffix}.ttf Opposans-En-${_suffix}.ttf Opposans-Hans-${_suffix}.ttf"
}

copy_as_coloros() {
    _src="$1"; _dest="$2"; _mode="${3:-full}"; _family="${4:-}"
    mkdir -p "$_dest" 2>/dev/null || return 1
    for _name in $(get_all_coloros_names); do rm -f "$_dest/${_name}.ttf" 2>/dev/null || true; done
    _font_store_reset "$_dest"
    _default=$(_default_source "$_family" "$_src"); _regular=$(_font_anchor "$_default" "$_dest" default) || return 1
    _count=0
    for _target in $(_coloros_regular_targets); do _alias_if_target "$_regular" "$_dest" "$_target" && [ -e "$_dest/$_target" ] && _count=$((_count + 1)); done
    _weights=$(_family_weights_or_source "$_family" "$_src"); _oldifs="$IFS"; IFS=','
    for _weight in $_weights; do
        IFS="$_oldifs"; case "$_weight" in ''|*[!0-9]*) IFS=','; continue ;; esac
        _source=$(_source_for_weight "$_family" "$_src" "$_weight"); [ -f "$_source" ] || { IFS=','; continue; }
        _suffix=$(_weight_suffix "$_weight"); [ "$_suffix" = Regular ] && { IFS=','; continue; }
        _anchor=$(_font_anchor "$_source" "$_dest" "w$_weight") || { IFS=','; continue; }
        for _target in $(_coloros_weight_targets "$_suffix"); do _alias_if_target "$_anchor" "$_dest" "$_target" || true; done
        IFS=','
    done
    IFS="$_oldifs"
    [ "$_count" -gt 0 ] 2>/dev/null || _font_alias "$_regular" "$_dest/SysFont-Regular.ttf"
    return 0
}

_hyperos_regular_targets() {
    echo "MiSansVF.ttf MiSansVF_Overlay.ttf MiSansLatinVF.ttf MiSansTCVF.ttf MiSansL3.otf Roboto-Regular.ttf RobotoFlex-Regular.ttf RobotoStatic-Regular.ttf GoogleSans-Regular.ttf GoogleSansText-Regular.ttf GoogleSansFlex-Regular.ttf"
}
_hyperos_named_targets() {
    _suffix="$1"; echo "Roboto-${_suffix}.ttf GoogleSans-${_suffix}.ttf GoogleSansText-${_suffix}.ttf"
}
copy_as_hyperos() {
    _src="$1"; _dest="$2"; _mode="${3:-full}"; _family="${4:-}"
    mkdir -p "$_dest" 2>/dev/null || return 1
    for _name in $(get_all_hyperos_files); do rm -f "$_dest/$_name" 2>/dev/null || true; done
    _font_store_reset "$_dest"
    _default=$(_default_source "$_family" "$_src"); _regular=$(_font_anchor "$_default" "$_dest" default) || return 1
    _count=0
    for _target in $(_hyperos_regular_targets); do _alias_if_target "$_regular" "$_dest" "$_target" && [ -e "$_dest/$_target" ] && _count=$((_count + 1)); done
    _weights=$(_family_weights_or_source "$_family" "$_src"); _oldifs="$IFS"; IFS=','
    for _weight in $_weights; do
        IFS="$_oldifs"; case "$_weight" in ''|*[!0-9]*) IFS=','; continue ;; esac
        _source=$(_source_for_weight "$_family" "$_src" "$_weight"); [ -f "$_source" ] || { IFS=','; continue; }
        _anchor=$(_font_anchor "$_source" "$_dest" "w$_weight") || { IFS=','; continue; }
        _numeric="${_weight}.ttf"; _alias_if_target "$_anchor" "$_dest" "$_numeric" || true
        _suffix=$(_weight_suffix "$_weight")
        for _target in $(_hyperos_named_targets "$_suffix"); do _alias_if_target "$_anchor" "$_dest" "$_target" || true; done
        IFS=','
    done
    IFS="$_oldifs"
    [ "$_count" -gt 0 ] 2>/dev/null || _font_alias "$_regular" "$_dest/Roboto-Regular.ttf"
    return 0
}

_generic_regular_targets() { echo "Roboto-Regular.ttf GoogleSans-Regular.ttf GoogleSansText-Regular.ttf NotoSans-Regular.ttf DroidSans.ttf"; }
_generic_weight_targets() {
    _suffix="$1"
    case "$_suffix" in
        Bold) echo "Roboto-Bold.ttf GoogleSans-Bold.ttf GoogleSansText-Bold.ttf DroidSans-Bold.ttf" ;;
        *) echo "Roboto-${_suffix}.ttf GoogleSans-${_suffix}.ttf GoogleSansText-${_suffix}.ttf" ;;
    esac
}
copy_as_generic() {
    _src="$1"; _dest="$2"; _mode="${3:-full}"; _family="${4:-}"
    mkdir -p "$_dest" 2>/dev/null || return 1
    for _name in $(get_all_generic_files); do rm -f "$_dest/$_name" 2>/dev/null || true; done
    _font_store_reset "$_dest"
    _default=$(_default_source "$_family" "$_src"); _regular=$(_font_anchor "$_default" "$_dest" default) || return 1
    _count=0
    for _target in $(_generic_regular_targets); do _alias_if_target "$_regular" "$_dest" "$_target" && [ -e "$_dest/$_target" ] && _count=$((_count + 1)); done
    _weights=$(_family_weights_or_source "$_family" "$_src"); _oldifs="$IFS"; IFS=','
    for _weight in $_weights; do
        IFS="$_oldifs"; case "$_weight" in ''|*[!0-9]*) IFS=','; continue ;; esac
        _suffix=$(_weight_suffix "$_weight"); [ "$_suffix" = Regular ] && { IFS=','; continue; }
        _source=$(_source_for_weight "$_family" "$_src" "$_weight"); [ -f "$_source" ] || { IFS=','; continue; }
        _anchor=$(_font_anchor "$_source" "$_dest" "w$_weight") || { IFS=','; continue; }
        for _target in $(_generic_weight_targets "$_suffix"); do _alias_if_target "$_anchor" "$_dest" "$_target" || true; done
        IFS=','
    done
    IFS="$_oldifs"
    [ "$_count" -gt 0 ] 2>/dev/null || _font_alias "$_regular" "$_dest/Roboto-Regular.ttf"
    return 0
}

apply_font_by_rom() {
    _src="$1"; _dest="$2"; _mode="${3:-full}"; _family="${4:-}"
    if [ "$IS_HYPEROS" = true ]; then copy_as_hyperos "$_src" "$_dest" "$_mode" "$_family"
    elif [ "$IS_COLOROS" = true ]; then copy_as_coloros "$_src" "$_dest" "$_mode" "$_family"
    else copy_as_generic "$_src" "$_dest" "$_mode" "$_family"; fi
}
