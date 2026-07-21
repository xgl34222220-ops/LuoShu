#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-origin-flyme)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MODULE_DIR="$TMP/module"
MODDIR="$MODULE_DIR"
LUOSHU_PUBLIC_DIR="$TMP/public"
USER_FONTS_DIR="$LUOSHU_PUBLIC_DIR/fonts"
export MODULE_DIR MODDIR LUOSHU_PUBLIC_DIR USER_FONTS_DIR
mkdir -p "$MODULE_DIR/common" "$MODULE_DIR/config" "$MODULE_DIR/system/fonts" "$USER_FONTS_DIR"

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

_log_step() { :; }
. "$ROOT/common/util_functions.sh"
. "$ROOT/common/rom_adapters.sh"
. "$ROOT/common/origin_flyme_global.sh"
set -eu

# OriginOS: exact existing physical slots must be recreated in the same partition. Script-specific
# faces remain untouched even when their filename includes vivoSans.
ORIGIN_REAL="$TMP/origin-real"
LUOSHU_TEST_ROM=originos
LUOSHU_ORIGINOS_SYSTEM_FONTS_ROOT="$ORIGIN_REAL/system/fonts"
LUOSHU_ORIGINOS_SYSTEM_EXT_FONTS_ROOT="$ORIGIN_REAL/system_ext/fonts"
LUOSHU_ORIGINOS_PRODUCT_FONTS_ROOT="$ORIGIN_REAL/product/fonts"
LUOSHU_ORIGINOS_VENDOR_FONTS_ROOT="$ORIGIN_REAL/vendor/fonts"
LUOSHU_ORIGINOS_ODM_FONTS_ROOT="$ORIGIN_REAL/odm/fonts"
LUOSHU_ORIGINOS_OEM_FONTS_ROOT="$ORIGIN_REAL/oem/fonts"
LUOSHU_ORIGINOS_MY_PRODUCT_FONTS_ROOT="$ORIGIN_REAL/my_product/fonts"
LUOSHU_ORIGINOS_PRODUCT_VIVO_FONTS_ROOT="$ORIGIN_REAL/product/vivo/fonts"
LUOSHU_ORIGINOS_SYSTEM_EXT_VIVO_FONTS_ROOT="$ORIGIN_REAL/system_ext/vivo/fonts"
LUOSHU_ORIGINOS_VENDOR_VIVO_FONTS_ROOT="$ORIGIN_REAL/vendor/vivo/fonts"
export LUOSHU_TEST_ROM LUOSHU_ORIGINOS_SYSTEM_FONTS_ROOT LUOSHU_ORIGINOS_SYSTEM_EXT_FONTS_ROOT \
    LUOSHU_ORIGINOS_PRODUCT_FONTS_ROOT LUOSHU_ORIGINOS_VENDOR_FONTS_ROOT \
    LUOSHU_ORIGINOS_ODM_FONTS_ROOT LUOSHU_ORIGINOS_OEM_FONTS_ROOT \
    LUOSHU_ORIGINOS_MY_PRODUCT_FONTS_ROOT LUOSHU_ORIGINOS_PRODUCT_VIVO_FONTS_ROOT \
    LUOSHU_ORIGINOS_SYSTEM_EXT_VIVO_FONTS_ROOT LUOSHU_ORIGINOS_VENDOR_VIVO_FONTS_ROOT
mkdir -p "$LUOSHU_ORIGINOS_SYSTEM_FONTS_ROOT" "$LUOSHU_ORIGINOS_SYSTEM_EXT_FONTS_ROOT" \
    "$LUOSHU_ORIGINOS_PRODUCT_FONTS_ROOT" "$LUOSHU_ORIGINOS_PRODUCT_VIVO_FONTS_ROOT"
touch "$LUOSHU_ORIGINOS_PRODUCT_FONTS_ROOT/vivoSansVF.ttf"
touch "$LUOSHU_ORIGINOS_SYSTEM_EXT_FONTS_ROOT/VivoSans-Medium.ttf"
touch "$LUOSHU_ORIGINOS_SYSTEM_FONTS_ROOT/Roboto-Bold.ttf"
touch "$LUOSHU_ORIGINOS_PRODUCT_FONTS_ROOT/vivoSansThai.ttf"

copy_as_originos "$USER_FONTS_DIR/Demo-Regular.ttf" "$MODULE_DIR/system/fonts" quick Demo
cmp -s "$USER_FONTS_DIR/Demo-Regular.ttf" "$MODULE_DIR/product/fonts/vivoSansVF.ttf"
cmp -s "$USER_FONTS_DIR/Demo-Medium.ttf" "$MODULE_DIR/system_ext/fonts/VivoSans-Medium.ttf"
cmp -s "$USER_FONTS_DIR/Demo-Bold.ttf" "$MODULE_DIR/system/fonts/Roboto-Bold.ttf"
test ! -e "$MODULE_DIR/product/fonts/vivoSansThai.ttf"
grep -q '^originos|product/fonts/vivoSansVF.ttf|' "$MODULE_DIR/config/oem-font-targets.conf"
luoshu_oem_clear_managed_fonts
test ! -e "$MODULE_DIR/product/fonts/vivoSansVF.ttf"
test ! -e "$MODULE_DIR/system_ext/fonts/VivoSans-Medium.ttf"

# Flyme: system slots are systemless, while /data/customizecenter/font/flymeFont.ttf is changed only
# at transaction commit. Default restore must put the exact original file back.
FLYME_REAL="$TMP/flyme-real"
FLYME_DATA="$TMP/data/customizecenter/font"
LUOSHU_TEST_ROM=flyme
LUOSHU_FLYME_SYSTEM_FONTS_ROOT="$FLYME_REAL/system/fonts"
LUOSHU_FLYME_SYSTEM_EXT_FONTS_ROOT="$FLYME_REAL/system_ext/fonts"
LUOSHU_FLYME_PRODUCT_FONTS_ROOT="$FLYME_REAL/product/fonts"
LUOSHU_FLYME_VENDOR_FONTS_ROOT="$FLYME_REAL/vendor/fonts"
LUOSHU_FLYME_ODM_FONTS_ROOT="$FLYME_REAL/odm/fonts"
LUOSHU_FLYME_OEM_FONTS_ROOT="$FLYME_REAL/oem/fonts"
LUOSHU_FLYME_MY_PRODUCT_FONTS_ROOT="$FLYME_REAL/my_product/fonts"
LUOSHU_FLYME_DATA_FONT_ROOT="$FLYME_DATA"
export LUOSHU_TEST_ROM LUOSHU_FLYME_SYSTEM_FONTS_ROOT LUOSHU_FLYME_SYSTEM_EXT_FONTS_ROOT \
    LUOSHU_FLYME_PRODUCT_FONTS_ROOT LUOSHU_FLYME_VENDOR_FONTS_ROOT LUOSHU_FLYME_ODM_FONTS_ROOT \
    LUOSHU_FLYME_OEM_FONTS_ROOT LUOSHU_FLYME_MY_PRODUCT_FONTS_ROOT LUOSHU_FLYME_DATA_FONT_ROOT
mkdir -p "$LUOSHU_FLYME_SYSTEM_FONTS_ROOT" "$LUOSHU_FLYME_PRODUCT_FONTS_ROOT" "$FLYME_DATA"
touch "$LUOSHU_FLYME_SYSTEM_FONTS_ROOT/FlymeSans-Regular.ttf"
touch "$LUOSHU_FLYME_PRODUCT_FONTS_ROOT/MeizuSans-Bold.ttf"
make_font Original-Flyme-Regular.ttf original-flyme-source
cp -f "$USER_FONTS_DIR/Original-Flyme-Regular.ttf" "$FLYME_DATA/flymeFont.ttf"

copy_as_flyme "$USER_FONTS_DIR/Demo-Regular.ttf" "$MODULE_DIR/system/fonts" quick Demo
test -f "$MODULE_DIR/config/flyme-data-pending.conf"
cmp -s "$USER_FONTS_DIR/Original-Flyme-Regular.ttf" "$FLYME_DATA/flymeFont.ttf"
cmp -s "$USER_FONTS_DIR/Demo-Regular.ttf" "$MODULE_DIR/system/fonts/FlymeSans-Regular.ttf"
cmp -s "$USER_FONTS_DIR/Demo-Bold.ttf" "$MODULE_DIR/product/fonts/MeizuSans-Bold.ttf"

luoshu_payload_validate_current() { return 0; }
luoshu_payload_arm() { return 0; }
luoshu_payload_transaction_rollback() {
    rm -rf "$LUOSHU_PAYLOAD_TXN" 2>/dev/null || true
    LUOSHU_PAYLOAD_TXN=''
}
LUOSHU_PAYLOAD_TXN="$TMP/txn-apply"
mkdir -p "$LUOSHU_PAYLOAD_TXN"
luoshu_payload_transaction_commit Demo
cmp -s "$USER_FONTS_DIR/Demo-Regular.ttf" "$FLYME_DATA/flymeFont.ttf"
test -f "$MODULE_DIR/config/flyme-data-original/state.conf"
test ! -f "$MODULE_DIR/config/flyme-data-pending.conf"

_luoshu_flyme_prepare_data_restore
LUOSHU_PAYLOAD_TXN="$TMP/txn-restore"
mkdir -p "$LUOSHU_PAYLOAD_TXN"
luoshu_payload_transaction_commit default
cmp -s "$USER_FONTS_DIR/Original-Flyme-Regular.ttf" "$FLYME_DATA/flymeFont.ttf"
test ! -d "$MODULE_DIR/config/flyme-data-original"

# Aborting before commit must not modify the persistent Flyme slot.
copy_as_flyme "$USER_FONTS_DIR/Demo-Regular.ttf" "$MODULE_DIR/system/fonts" quick Demo
LUOSHU_PAYLOAD_TXN="$TMP/txn-abort"
mkdir -p "$LUOSHU_PAYLOAD_TXN"
luoshu_payload_transaction_abort
cmp -s "$USER_FONTS_DIR/Original-Flyme-Regular.ttf" "$FLYME_DATA/flymeFont.ttf"
test ! -f "$MODULE_DIR/config/flyme-data-pending.conf"

printf 'OriginOS and Flyme font adapter tests passed.\n'
