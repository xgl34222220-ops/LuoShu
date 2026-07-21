#!/bin/sh
set -eu
REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ROOT=$(mktemp -d)
trap 'rm -rf "$ROOT"' EXIT HUP INT TERM

MODULE_DIR="$ROOT/module"
MODDIR="$MODULE_DIR"
USER_FONTS_DIR="$ROOT/user-fonts"
LUOSHU_SYSTEM_FONTS_ROOT="$ROOT/real/system/fonts"
LUOSHU_PRODUCT_FONTS_ROOT="$ROOT/real/product/fonts"
LUOSHU_SYSTEM_EXT_FONTS_ROOT="$ROOT/real/system_ext/fonts"
export MODULE_DIR MODDIR USER_FONTS_DIR LUOSHU_SYSTEM_FONTS_ROOT LUOSHU_PRODUCT_FONTS_ROOT LUOSHU_SYSTEM_EXT_FONTS_ROOT

mkdir -p "$MODULE_DIR/system/fonts" "$MODULE_DIR/product/fonts" "$MODULE_DIR/system_ext/fonts" \
    "$USER_FONTS_DIR" "$LUOSHU_SYSTEM_FONTS_ROOT" "$LUOSHU_PRODUCT_FONTS_ROOT" "$LUOSHU_SYSTEM_EXT_FONTS_ROOT"
printf 'regular-source\n' > "$USER_FONTS_DIR/Demo-Regular.ttf"
printf 'bold-source\n' > "$USER_FONTS_DIR/Demo-Bold.ttf"
printf 'stock-core\n' > "$LUOSHU_PRODUCT_FONTS_ROOT/MiSansVF.ttf"
printf 'stock-overlay\n' > "$LUOSHU_SYSTEM_EXT_FONTS_ROOT/MiSansVF_Overlay.ttf"
printf 'stock-400\n' > "$LUOSHU_SYSTEM_FONTS_ROOT/400.ttf"
printf 'stock-700\n' > "$LUOSHU_PRODUCT_FONTS_ROOT/700.ttf"
printf 'stock-metrics\n' > "$LUOSHU_SYSTEM_FONTS_ROOT/Roboto-Regular.ttf"
printf 'stale-overlay\n' > "$MODULE_DIR/system/fonts/Roboto-Regular.ttf"

_font_store_reset() {
    rm -rf "$1/.luoshu-font-store"
    mkdir -p "$1/.luoshu-font-store"
}
_font_anchor() {
    cp -f "$1" "$2/.luoshu-font-store/$3.font"
    printf '%s\n' "$2/.luoshu-font-store/$3.font"
}
_font_alias() {
    mkdir -p "${2%/*}"
    cp -f "$1" "$2"
}
detect_font_family() {
    _name=${1%.*}
    _name=${_name%-Regular}
    _name=${_name%-Bold}
    printf '%s\n' "$_name"
}
detect_font_weight() {
    case "$1" in *-Bold.*) printf 'bold\n' ;; *) printf 'regular\n' ;; esac
}
is_variable_font() { return 1; }
_log_step() { :; }

. "$REPO_ROOT/common/hyperos_global.sh"
copy_as_hyperos "$USER_FONTS_DIR/Demo-Bold.ttf" "$MODULE_DIR/system/fonts" quick Demo

test "$(cat "$MODULE_DIR/product/fonts/MiSansVF.ttf")" = 'regular-source'
test "$(cat "$MODULE_DIR/system_ext/fonts/MiSansVF_Overlay.ttf")" = 'regular-source'
test "$(cat "$MODULE_DIR/system/fonts/400.ttf")" = 'regular-source'
test "$(cat "$MODULE_DIR/product/fonts/700.ttf")" = 'bold-source'
test ! -e "$MODULE_DIR/system/fonts/MiSansVF.ttf"
test ! -e "$MODULE_DIR/system/fonts/Roboto-Regular.ttf"
test ! -e "$MODULE_DIR/product/fonts/Roboto-Regular.ttf"
test ! -e "$MODULE_DIR/system_ext/fonts/Roboto-Regular.ttf"
printf 'HyperOS global mapping tests passed.\n'

# Keep OEM partition regressions in the always-on source gate.
sh "$REPO_ROOT/scripts/coloros_partition_mapping_test.sh"
sh "$REPO_ROOT/scripts/originos_flyme_mapping_test.sh"
