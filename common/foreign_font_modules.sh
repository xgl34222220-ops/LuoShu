#!/system/bin/sh
# 洛书：只读扫描其他 Root 模块里的字体负载，提示可能互相覆盖的字体模块。
# 只读取 /data/adb/modules/*，从不修改、停用或删除其他模块。
# 结果写入 config/foreign-font-modules.conf，供 App 首页和诊断导出读取。
#   foreignFontModules=<逗号分隔的模块 id>
#   foreignFontModuleNames=<id:名称|id:名称>
#   foreignFontModuleCount=<N>
#   fontLoaderPresent=yes|no      FontLoader（JingMatrix）是伴随模块，不算冲突
#   fontLoaderModules=<逗号分隔的模块 id>
set +e

luoshu_foreign_font_lower() {
    printf '%s' "$1" | tr 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' 'abcdefghijklmnopqrstuvwxyz'
}

luoshu_foreign_font_prop() {
    sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

# A glob that matched nothing stays literal; only an existing path counts.
luoshu_foreign_font_any() {
    for _lffa_path in "$@"; do
        [ -e "$_lffa_path" ] && return 0
    done
    return 1
}

luoshu_foreign_font_has_payload() {
    _lffp_dir="$1"
    for _lffp_font in "$_lffp_dir"/system/fonts/*; do
        [ -f "$_lffp_font" ] || continue
        case "$_lffp_font" in
            *.[tT][tT][fF]|*.[tT][tT][cC]|*.[oO][tT][fF]) return 0 ;;
        esac
    done
    luoshu_foreign_font_any "$_lffp_dir"/system/etc/font*.xml && return 0
    luoshu_foreign_font_any \
        "$_lffp_dir/system/product/etc/fonts_customization.xml" \
        "$_lffp_dir/product/etc/fonts_customization.xml" && return 0
    luoshu_foreign_font_any \
        "$_lffp_dir"/system/system_ext/etc/*font*.xml \
        "$_lffp_dir"/system_ext/etc/*font*.xml && return 0
    return 1
}

# FontLoader ships a Zygisk library; its module id/name or library names carry "fontloader".
luoshu_foreign_font_is_fontloader() {
    _lffl_dir="$1"
    _lffl_label="$2"
    [ -d "$_lffl_dir/zygisk" ] || return 1
    case "$(luoshu_foreign_font_lower "$_lffl_label")" in
        *fontloader*|*font-loader*|*font_loader*) return 0 ;;
    esac
    for _lffl_lib in "$_lffl_dir"/zygisk/*; do
        [ -e "$_lffl_lib" ] || continue
        case "$(luoshu_foreign_font_lower "${_lffl_lib##*/}")" in
            *fontloader*) return 0 ;;
        esac
    done
    return 1
}

luoshu_foreign_font_scan() {
    _lffs_root="${LUOSHU_MODULES_ROOT:-/data/adb/modules}"
    _lffs_self="${1:-LuoShu}"
    _lffs_ids=''
    _lffs_names=''
    _lffs_count=0
    _lffs_loaders=''
    for _lffs_dir in "$_lffs_root"/*; do
        [ -d "$_lffs_dir" ] || continue
        _lffs_base="${_lffs_dir##*/}"
        _lffs_id=$(luoshu_foreign_font_prop "$_lffs_dir/module.prop" id)
        [ -n "$_lffs_id" ] || _lffs_id="$_lffs_base"
        case "$_lffs_base" in LuoShu|"$_lffs_self") continue ;; esac
        case "$_lffs_id" in LuoShu|"$_lffs_self") continue ;; esac
        if [ -e "$_lffs_dir/disable" ] || [ -L "$_lffs_dir/disable" ] ||
           [ -e "$_lffs_dir/remove" ] || [ -L "$_lffs_dir/remove" ]; then
            continue
        fi
        # Keep ids list-safe: ids are [A-Za-z0-9._-] by root-manager convention.
        _lffs_id=$(printf '%s' "$_lffs_id" | tr -c 'A-Za-z0-9._-' '_')
        _lffs_name=$(luoshu_foreign_font_prop "$_lffs_dir/module.prop" name |
            tr '|\t' '/ ' | cut -c1-60)
        [ -n "$_lffs_name" ] || _lffs_name="$_lffs_id"
        if luoshu_foreign_font_is_fontloader "$_lffs_dir" "$_lffs_base $_lffs_id $_lffs_name"; then
            _lffs_loaders="${_lffs_loaders:+$_lffs_loaders,}$_lffs_id"
            continue
        fi
        luoshu_foreign_font_has_payload "$_lffs_dir" || continue
        _lffs_ids="${_lffs_ids:+$_lffs_ids,}$_lffs_id"
        _lffs_names="${_lffs_names:+$_lffs_names|}$_lffs_id:$_lffs_name"
        _lffs_count=$((_lffs_count + 1))
    done
    _lffs_loader_state=no
    [ -n "$_lffs_loaders" ] && _lffs_loader_state=yes
    printf 'foreignFontModules=%s\n' "$_lffs_ids"
    printf 'foreignFontModuleNames=%s\n' "$_lffs_names"
    printf 'foreignFontModuleCount=%s\n' "$_lffs_count"
    printf 'fontLoaderPresent=%s\n' "$_lffs_loader_state"
    printf 'fontLoaderModules=%s\n' "$_lffs_loaders"
}

# Writes the record only when it changed, so repeated boots/refreshes cost no flash write.
luoshu_foreign_font_record() {
    _lffr_moddir="$1"
    _lffr_out="$_lffr_moddir/config/foreign-font-modules.conf"
    mkdir -p "$_lffr_moddir/config" 2>/dev/null || return 1
    _lffr_tmp="$_lffr_out.tmp.$$"
    luoshu_foreign_font_scan "${_lffr_moddir##*/}" > "$_lffr_tmp" 2>/dev/null || {
        rm -f "$_lffr_tmp" 2>/dev/null
        return 1
    }
    if [ -f "$_lffr_out" ] && cmp -s "$_lffr_tmp" "$_lffr_out" 2>/dev/null; then
        rm -f "$_lffr_tmp" 2>/dev/null
    else
        mv -f "$_lffr_tmp" "$_lffr_out" 2>/dev/null || { rm -f "$_lffr_tmp"; return 1; }
        chmod 0644 "$_lffr_out" 2>/dev/null || true
    fi
    return 0
}

case "${0##*/}" in
    foreign_font_modules.sh)
        MODDIR="${MODDIR:-}"
        if [ -z "$MODDIR" ]; then
            if [ -f "${0%/*}/../module.prop" ]; then
                MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"
            else
                MODDIR="/data/adb/modules/LuoShu"
            fi
        fi
        case "${1:-scan}" in
            scan)
                luoshu_foreign_font_record "$MODDIR" || exit 1
                cat "$MODDIR/config/foreign-font-modules.conf" 2>/dev/null
                ;;
            print) luoshu_foreign_font_scan "${MODDIR##*/}" ;;
            *) printf 'usage: foreign_font_modules.sh [scan|print]\n' >&2; exit 2 ;;
        esac
        ;;
esac
