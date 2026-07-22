#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-coloros-consistency)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MODULE="$TMP/module"
PUBLIC="$TMP/public"
REAL_SYSTEM="$TMP/real-system"
REAL_PRODUCT="$TMP/real-product"
mkdir -p "$MODULE/common" "$MODULE/system/fonts" "$PUBLIC/fonts" "$REAL_SYSTEM" "$REAL_PRODUCT"
cp "$ROOT/common/util_functions.sh" "$MODULE/common/util_functions.sh"
cp "$ROOT/common/rom_adapters.sh" "$MODULE/common/rom_adapters.sh"
cp "$ROOT/common/coloros_global.sh" "$MODULE/common/coloros_global.sh"

python3 - "$PUBLIC/fonts/Demo-Regular.ttf" "$PUBLIC/fonts/Demo-Thin.ttf" "$PUBLIC/fonts/Demo-SemiBold.ttf" <<'PY'
from pathlib import Path
import sys
for index, name in enumerate(sys.argv[1:], 1):
    Path(name).write_bytes((f'font-{index}-'.encode() * 700)[:5000])
PY
for name in OplusOSUI-XThin.ttf OplusSans-SemiBold.ttf GoogleSansText-Regular.ttf Oplus-Serif.ttf Roboto-Italic.ttf; do
    : > "$REAL_PRODUCT/$name"
done

MODULE_DIR="$MODULE"
LUOSHU_PUBLIC_DIR="$PUBLIC"
USER_FONTS_DIR="$PUBLIC/fonts"
. "$MODULE/common/util_functions.sh"
. "$MODULE/common/rom_adapters.sh"
LUOSHU_COLOROS_SYSTEM_FONTS_ROOT="$REAL_SYSTEM"
LUOSHU_COLOROS_PRODUCT_FONTS_ROOT="$REAL_PRODUCT"
LUOSHU_COLOROS_SYSTEM_EXT_FONTS_ROOT="$TMP/none-system-ext"
LUOSHU_COLOROS_VENDOR_FONTS_ROOT="$TMP/none-vendor"
LUOSHU_COLOROS_ODM_FONTS_ROOT="$TMP/none-odm"
LUOSHU_COLOROS_OEM_FONTS_ROOT="$TMP/none-oem"
LUOSHU_COLOROS_MY_PRODUCT_FONTS_ROOT="$TMP/none-my-product"
LUOSHU_COLOROS_OPLUS_PRODUCT_FONTS_ROOT="$TMP/none-oplus-product"
LUOSHU_COLOROS_OPLUS_ENGINEERING_FONTS_ROOT="$TMP/none-oplus-engineering"
LUOSHU_COLOROS_OPLUS_VERSION_FONTS_ROOT="$TMP/none-oplus-version"
LUOSHU_COLOROS_OPLUS_REGION_FONTS_ROOT="$TMP/none-oplus-region"
. "$MODULE/common/coloros_global.sh"

copy_as_coloros "$PUBLIC/fonts/Demo-Regular.ttf" "$MODULE/system/fonts" quick Demo
cmp -s "$PUBLIC/fonts/Demo-Thin.ttf" "$MODULE/product/fonts/OplusOSUI-XThin.ttf"
cmp -s "$PUBLIC/fonts/Demo-SemiBold.ttf" "$MODULE/product/fonts/OplusSans-SemiBold.ttf"
cmp -s "$PUBLIC/fonts/Demo-Regular.ttf" "$MODULE/product/fonts/GoogleSansText-Regular.ttf"
test ! -e "$MODULE/product/fonts/Oplus-Serif.ttf"
test ! -e "$MODULE/product/fonts/Roboto-Italic.ttf"
echo 'ColorOS consistency mapping passed.'
