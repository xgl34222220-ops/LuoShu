#!/system/bin/sh
# Complete a staged LuoShu payload with the same HyperOS physical UI targets used by
# the current mapper. This helper never writes the live payload; callers pass an
# isolated next-boot/staging root.
set +e

PAYLOAD_ROOT="${1:-${LUOSHU_HYPEROS_STAGE_ROOT:-}}"
[ -n "$PAYLOAD_ROOT" ] || exit 2

REALMOD="${LUOSHU_REAL_MODDIR:-}"
if [ -z "$REALMOD" ]; then
    _self_dir=$(CDPATH= cd -- "${0%/*}" 2>/dev/null && pwd)
    REALMOD=$(CDPATH= cd -- "$_self_dir/.." 2>/dev/null && pwd)
fi
[ -f "$REALMOD/module.prop" ] || exit 2

MODULE_DIR="$REALMOD"
MODDIR="$REALMOD"
USER_FONTS_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/fonts"
export MODULE_DIR MODDIR USER_FONTS_DIR

[ -f "$REALMOD/common/util_functions.sh" ] && . "$REALMOD/common/util_functions.sh"
[ -f "$REALMOD/common/rom_adapters.sh" ] && . "$REALMOD/common/rom_adapters.sh"
[ -f "$REALMOD/common/hyperos_global.sh" ] && . "$REALMOD/common/hyperos_global.sh"

type _hyperos_core_files >/dev/null 2>&1 || exit 2
type _hyperos_weight_files >/dev/null 2>&1 || exit 2
type _hyperos_upright_ui_files >/dev/null 2>&1 || exit 2
type _hyperos_clock_ui_files >/dev/null 2>&1 || exit 2

stage_font_dir="$PAYLOAD_ROOT/system/fonts"
[ -d "$stage_font_dir" ] || exit 1

pick_anchor() {
    _name="$1"
    _weight=400
    if type _hyperos_file_weight >/dev/null 2>&1; then
        _weight=$(_hyperos_file_weight "$_name")
    else
        case "$_name" in
            100.ttf) _weight=100 ;; 200.ttf) _weight=200 ;; 300.ttf) _weight=300 ;;
            500.ttf) _weight=500 ;; 600.ttf) _weight=600 ;; 700.ttf) _weight=700 ;;
            800.ttf) _weight=800 ;; 900.ttf) _weight=900 ;; *) _weight=400 ;;
        esac
    fi
    for _candidate in \
        "$stage_font_dir/LuoShu-${_weight}.ttf" \
        "$stage_font_dir/.luoshu-font-store/wght-${_weight}.font" \
        "$stage_font_dir/.luoshu-font-store/compact-wght-${_weight}.font" \
        "$stage_font_dir/.luoshu-font-store/mix-composite.font" \
        "$stage_font_dir/.luoshu-font-store/regular.font" \
        "$stage_font_dir/.luoshu-font-store/compact-regular.font" \
        "$stage_font_dir/400.ttf" \
        "$stage_font_dir/MiSansVF.ttf" \
        "$stage_font_dir/Roboto-Regular.ttf"; do
        [ -s "$_candidate" ] || continue
        printf '%s\n' "$_candidate"
        return 0
    done
    find "$stage_font_dir" -maxdepth 2 -type f \( -iname '*.ttf' -o -iname '*.otf' \) -print -quit 2>/dev/null
}

link_font() {
    _source="$1"
    _dest="$2"
    [ -s "$_source" ] || return 1
    mkdir -p "${_dest%/*}" 2>/dev/null || return 1
    rm -f "$_dest" 2>/dev/null || true
    ln "$_source" "$_dest" 2>/dev/null || cp -f "$_source" "$_dest" 2>/dev/null || return 1
    chmod 0644 "$_dest" 2>/dev/null || true
    return 0
}

all_targets() {
    {
        _hyperos_core_files
        _hyperos_weight_files
        _hyperos_upright_ui_files
        _hyperos_clock_ui_files
    } | tr ' ' '\n' | awk 'NF && !seen[$0]++'
}

mapped=0
while IFS= read -r _file; do
    [ -n "$_file" ] || continue
    _anchor=$(pick_anchor "$_file")
    [ -s "$_anchor" ] || continue
    while IFS='|' read -r _part _real_root; do
        [ -e "$_real_root/$_file" ] || continue
        _dest="$PAYLOAD_ROOT/$_part/fonts/$_file"
        if link_font "$_anchor" "$_dest"; then
            mapped=$((mapped + 1))
        fi
    done <<'EOF_PARTS'
system|/system/fonts
system_ext|/system_ext/fonts
product|/product/fonts
mi_ext|/mi_ext/fonts
vendor|/vendor/fonts
odm|/odm/fonts
oem|/oem/fonts
my_product|/my_product/fonts
hw_product|/hw_product/fonts
cust|/cust/fonts
EOF_PARTS
done <<EOF_TARGETS
$(all_targets)
EOF_TARGETS

# HyperOS itself always carries MiSansVF in /system/fonts. Keep a deterministic core
# fallback for test environments where the stock root is not mounted.
if [ ! -s "$PAYLOAD_ROOT/system/fonts/MiSansVF.ttf" ]; then
    _anchor=$(pick_anchor MiSansVF.ttf)
    [ ! -s "$_anchor" ] || { link_font "$_anchor" "$PAYLOAD_ROOT/system/fonts/MiSansVF.ttf" && mapped=$((mapped + 1)); }
fi

printf 'mapped=%s\n' "$mapped"
[ "$mapped" -gt 0 ] 2>/dev/null
