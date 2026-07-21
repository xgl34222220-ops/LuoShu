#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-coloros)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MODULE_DIR="$TMP/module"
MODDIR="$MODULE_DIR"
USER_FONTS_DIR="$TMP/user-fonts"
LUOSHU_COLOROS_SYSTEM_FONTS_ROOT="$TMP/real/system/fonts"
LUOSHU_COLOROS_SYSTEM_EXT_FONTS_ROOT="$TMP/real/system_ext/fonts"
LUOSHU_COLOROS_PRODUCT_FONTS_ROOT="$TMP/real/product/fonts"
LUOSHU_COLOROS_MY_PRODUCT_FONTS_ROOT="$TMP/real/my_product/fonts"
export MODULE_DIR MODDIR USER_FONTS_DIR \
    LUOSHU_COLOROS_SYSTEM_FONTS_ROOT LUOSHU_COLOROS_SYSTEM_EXT_FONTS_ROOT \
    LUOSHU_COLOROS_PRODUCT_FONTS_ROOT LUOSHU_COLOROS_MY_PRODUCT_FONTS_ROOT

mkdir -p "$MODULE_DIR/common" "$MODULE_DIR/system/fonts" "$USER_FONTS_DIR" \
    "$LUOSHU_COLOROS_SYSTEM_FONTS_ROOT" "$LUOSHU_COLOROS_SYSTEM_EXT_FONTS_ROOT" \
    "$LUOSHU_COLOROS_PRODUCT_FONTS_ROOT" "$LUOSHU_COLOROS_MY_PRODUCT_FONTS_ROOT"
cp "$ROOT/common/coloros_global.sh" "$MODULE_DIR/common/coloros_global.sh"

make_font() {
    _name="$1"
    _marker="$2"
    {
        printf '%s\n' "$_marker"
        dd if=/dev/zero bs=2048 count=1 2>/dev/null
    } > "$USER_FONTS_DIR/$_name"
}

make_font Demo-Regular.ttf regular-source
make_font Demo-Medium.ttf medium-source
make_font Demo-Bold.ttf bold-source

# Simulate the physical ColorOS layout: Google input families live in product, while the normal
# system family and other OEM faces can be spread across system_ext and my_product.
touch "$LUOSHU_COLOROS_SYSTEM_FONTS_ROOT/SysFont-Regular.ttf"
touch "$LUOSHU_COLOROS_PRODUCT_FONTS_ROOT/GoogleSansText-Regular.ttf"
touch "$LUOSHU_COLOROS_PRODUCT_FONTS_ROOT/GoogleSansText-Medium.ttf"
touch "$LUOSHU_COLOROS_PRODUCT_FONTS_ROOT/GoogleSansText-Bold.ttf"
touch "$LUOSHU_COLOROS_PRODUCT_FONTS_ROOT/GoogleSansText-VF.ttf"
touch "$LUOSHU_COLOROS_SYSTEM_EXT_FONTS_ROOT/Roboto-Medium.ttf"
touch "$LUOSHU_COLOROS_MY_PRODUCT_FONTS_ROOT/Opposans-En-Bold.ttf"

_log_step() { :; }
_luoshu_font_config_module() { printf '%s\n' "$MODULE_DIR"; }
. "$ROOT/common/util_functions.sh"
. "$ROOT/common/rom_adapters.sh"
. "$ROOT/common/font_config_partitions.sh"

type get_all_coloros_names >/dev/null 2>&1
type copy_as_coloros >/dev/null 2>&1
copy_as_coloros "$USER_FONTS_DIR/Demo-Regular.ttf" "$MODULE_DIR/system/fonts" quick Demo

cmp -s "$USER_FONTS_DIR/Demo-Regular.ttf" "$MODULE_DIR/system/fonts/SysFont-Regular.ttf"
cmp -s "$USER_FONTS_DIR/Demo-Regular.ttf" "$MODULE_DIR/product/fonts/GoogleSansText-Regular.ttf"
cmp -s "$USER_FONTS_DIR/Demo-Medium.ttf" "$MODULE_DIR/product/fonts/GoogleSansText-Medium.ttf"
cmp -s "$USER_FONTS_DIR/Demo-Bold.ttf" "$MODULE_DIR/product/fonts/GoogleSansText-Bold.ttf"
cmp -s "$USER_FONTS_DIR/Demo-Regular.ttf" "$MODULE_DIR/product/fonts/GoogleSansText-VF.ttf"
cmp -s "$USER_FONTS_DIR/Demo-Medium.ttf" "$MODULE_DIR/system_ext/fonts/Roboto-Medium.ttf"
cmp -s "$USER_FONTS_DIR/Demo-Bold.ttf" "$MODULE_DIR/my_product/fonts/Opposans-En-Bold.ttf"

# A product-only slot must not be misplaced into system/fonts; that was the regression that left
# Google Play text fields on the stock GoogleSansText family.
test ! -e "$MODULE_DIR/system/fonts/GoogleSansText-Regular.ttf"
get_all_coloros_names | grep -qx 'GoogleSansText-Regular'
get_all_coloros_names | grep -qx 'SysFont-Regular'

printf 'ColorOS Play input partition mapping tests passed.\n'
