#!/bin/sh
# The safe switch core uses the legacy ColorOS mapper. ColorOS 16 digit/Latin
# slots (OplusOSUI, OplusSans, extended Roboto/Google weights, .otf stock files)
# must be aliased, while italic/serif/mono/code/emoji/clock/script faces and
# collections stay stock. Weight-named slots take the matching family weight.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/scripts/assert.sh"
CASE='ColorOS 旧映射器数字/英文覆盖'
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-legacy-coloros)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

STOCK="$TMP/stock"
DEST="$TMP/stage/system/fonts"
USER_FONTS_DIR="$TMP/public/fonts"
MODULE_DIR="$TMP/module"
LUOSHU_LEGACY_STOCK_ROOT="$STOCK"
export USER_FONTS_DIR MODULE_DIR LUOSHU_LEGACY_STOCK_ROOT
mkdir -p "$STOCK/system/fonts" "$STOCK/product/fonts" "$STOCK/my_product/fonts" "$STOCK/my_stock/fonts" \
    "$DEST" "$USER_FONTS_DIR" "$MODULE_DIR/config"

make_font() {
    { printf '%s\n' "$2"; dd if=/dev/zero bs=2048 count=1 2>/dev/null; } > "$1"
}
make_font "$USER_FONTS_DIR/Demo-Regular.ttf" regular-source
make_font "$USER_FONTS_DIR/Demo-Bold.ttf" bold-source
make_font "$USER_FONTS_DIR/Demo-Thin.ttf" thin-source

for name in SysSans-En-Regular.ttf SysFont-Regular.ttf SysSans-En-Bold.ttf OplusOSUI-Regular.ttf \
            OplusOSUI-XThin.ttf OplusSans-Bold.ttf Roboto-SemiBold.ttf SysFont-Myanmar.ttf \
            Roboto-Italic.ttf RobotoMono-Regular.ttf GoogleSansCode-Regular.ttf Oplus-Serif.ttf \
            NotoColorEmoji.ttf SysSans-Clock-Regular.ttf; do
    make_font "$STOCK/system/fonts/$name" "stock-$name"
done
make_font "$STOCK/product/fonts/GoogleSansText-SemiBold.ttf" stock
make_font "$STOCK/my_product/fonts/SysSans-Hans-Regular.otf" stock
make_font "$STOCK/system/fonts/SysFont-Hant-Regular.ttc" stock
# Discovered OTA rename in a legacy root, and an OEM-only partition that the
# inventory completion (not this mapper) owns.
make_font "$STOCK/system/fonts/SysSans-En-Display-Regular.ttf" stock
make_font "$STOCK/my_stock/fonts/OplusOSUI-Medium.ttf" stock

(
    set +eu
    . "$ROOT/common/legacy_v14_4/util_functions.sh" >/dev/null 2>&1
    . "$ROOT/common/legacy_v14_4/rom_adapters.sh"
    # util_functions.sh resets the public font directory to /sdcard.
    USER_FONTS_DIR="$TMP/public/fonts"
    IS_COLOROS=true IS_HYPEROS=false
    apply_font_by_rom "$USER_FONTS_DIR/Demo-Regular.ttf" "$DEST" quick Demo > "$TMP/log" 2>&1
) || { cat "$TMP/log" >&2; fail "copy_as_coloros 返回失败"; }

for name in SysSans-En-Regular.ttf SysFont-Regular.ttf OplusOSUI-Regular.ttf GoogleSansText-SemiBold.ttf \
            SysSans-Hans-Regular.otf SysSans-En-Display-Regular.ttf; do
    [ -f "$DEST/$name" ] || { cat "$TMP/log"; fail "缺少数字/英文槽位 $name"; }
    cmp -s "$DEST/$name" "$USER_FONTS_DIR/Demo-Regular.ttf" || fail "$name 未使用常规字重"
done
for name in SysSans-En-Bold.ttf OplusSans-Bold.ttf; do
    cmp -s "$DEST/$name" "$USER_FONTS_DIR/Demo-Bold.ttf" || fail "$name 未使用粗体字重"
done
cmp -s "$DEST/OplusOSUI-XThin.ttf" "$USER_FONTS_DIR/Demo-Thin.ttf" || fail "OplusOSUI-XThin 未使用细体字重"
# No SemiBold in the family: regular, never a missing slot.
cmp -s "$DEST/Roboto-SemiBold.ttf" "$USER_FONTS_DIR/Demo-Regular.ttf" || fail "缺失字重未回退常规"

for name in SysFont-Myanmar.ttf Roboto-Italic.ttf RobotoMono-Regular.ttf GoogleSansCode-Regular.ttf \
            Oplus-Serif.ttf NotoColorEmoji.ttf SysSans-Clock-Regular.ttf SysFont-Hant-Regular.ttc \
            SysFont-Hant-Regular.ttf SysSans-Hans-Regular.ttf OplusOSUI-Medium.ttf; do
    [ ! -e "$DEST/$name" ] || fail "不应替换或新建 $name"
done
grep -q '已覆盖 3 个 ColorOS 基础字体文件' "$TMP/log" || { cat "$TMP/log"; fail "基础槽位计数异常"; }
printf '%s\n' "ColorOS legacy digit/Latin coverage tests passed."
