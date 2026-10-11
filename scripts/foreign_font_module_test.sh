#!/bin/sh
# Other root modules with font payloads must be reported (read-only) so the App can warn.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/scripts/assert.sh"
CASE='外部字体模块检测'

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MODULES="$TMP/adb/modules"
SELF="$MODULES/LuoShu"
mkdir -p "$SELF/common" "$SELF/config" "$SELF/system/fonts" "$SELF/system/etc"
cp "$ROOT/common/foreign_font_modules.sh" "$ROOT/common/module_status.sh" "$SELF/common/"
printf 'id=LuoShu\nname=洛书\ndescription=old\n' > "$SELF/module.prop"
printf 'x' > "$SELF/system/fonts/LuoShu.ttf"
printf '<x/>' > "$SELF/system/etc/fonts.xml"

fake_module() {
    _dir="$MODULES/$1"
    mkdir -p "$_dir"
    printf 'id=%s\nname=%s\n' "$1" "$2" > "$_dir/module.prop"
}

fake_module mfga 'Make Fonts Great Again'
mkdir -p "$MODULES/mfga/system/fonts"
printf 'x' > "$MODULES/mfga/system/fonts/MiSansVF.TTF"
fake_module ufs 'Unicode Font Set | UFS'
mkdir -p "$MODULES/ufs/system/etc"
printf '<x/>' > "$MODULES/ufs/system/etc/font_fallback.xml"
fake_module oemxml 'OEM customization'
mkdir -p "$MODULES/oemxml/product/etc"
printf '<x/>' > "$MODULES/oemxml/product/etc/fonts_customization.xml"
fake_module sysext 'system_ext fonts'
mkdir -p "$MODULES/sysext/system/system_ext/etc"
printf '<x/>' > "$MODULES/sysext/system/system_ext/etc/hyper_fonts.xml"
fake_module disabledfont 'Disabled font'
mkdir -p "$MODULES/disabledfont/system/fonts"
printf 'x' > "$MODULES/disabledfont/system/fonts/A.otf"
touch "$MODULES/disabledfont/disable"
fake_module removedfont 'Removed font'
mkdir -p "$MODULES/removedfont/system/etc"
printf '<x/>' > "$MODULES/removedfont/system/etc/fonts.xml"
touch "$MODULES/removedfont/remove"
fake_module notfont 'Not a font module'
mkdir -p "$MODULES/notfont/system/fonts" "$MODULES/notfont/system/etc"
printf 'x' > "$MODULES/notfont/system/fonts/readme.txt"
printf 'x' > "$MODULES/notfont/system/etc/hosts"
fake_module fontloader 'Font Loader'
mkdir -p "$MODULES/fontloader/zygisk" "$MODULES/fontloader/system/fonts"
printf 'x' > "$MODULES/fontloader/zygisk/arm64-v8a.so"
printf 'x' > "$MODULES/fontloader/system/fonts/Loader.ttf"
fake_module zyg_other 'Some zygisk module'
mkdir -p "$MODULES/zyg_other/zygisk"
printf 'x' > "$MODULES/zyg_other/zygisk/arm64-v8a.so"
# A copied/renamed LuoShu directory is still LuoShu by its module.prop id.
mkdir -p "$MODULES/luoshu_copy/system/fonts"
printf 'id=LuoShu\nname=洛书\n' > "$MODULES/luoshu_copy/module.prop"
printf 'x' > "$MODULES/luoshu_copy/system/fonts/A.ttf"

export LUOSHU_MODULES_ROOT="$MODULES"
OUT=$(MODDIR="$SELF" sh "$SELF/common/foreign_font_modules.sh" scan)
CONF="$SELF/config/foreign-font-modules.conf"
ok test -f "$CONF"
eq "$(sed -n 's/^foreignFontModules=//p' "$CONF")" 'mfga,oemxml,sysext,ufs'
eq "$(sed -n 's/^foreignFontModuleCount=//p' "$CONF")" '4'
eq "$(sed -n 's/^foreignFontModuleNames=//p' "$CONF")" \
    'mfga:Make Fonts Great Again|oemxml:OEM customization|sysext:system_ext fonts|ufs:Unicode Font Set / UFS'
eq "$(sed -n 's/^fontLoaderPresent=//p' "$CONF")" 'yes'
eq "$(sed -n 's/^fontLoaderModules=//p' "$CONF")" 'fontloader'
case "$OUT" in *'foreignFontModules=mfga,oemxml,sysext,ufs'*) ;; *) fail "scan output missing ids: $OUT" ;; esac

# Read-only: other modules are never touched.
ok test -f "$MODULES/mfga/system/fonts/MiSansVF.TTF"
ok test -f "$MODULES/ufs/system/etc/font_fallback.xml"
no test -e "$MODULES/mfga/disable"

# Unchanged result does not rewrite the record.
touch -t 200001010000 "$CONF"
MODDIR="$SELF" sh "$SELF/common/foreign_font_modules.sh" scan >/dev/null
eq "$(find "$CONF" -newer "$SELF/module.prop" | wc -l | tr -d ' ')" '0'

# Service stage refresh path: module_status.sh triggers the scan.
rm -rf "$MODULES/mfga" "$MODULES/ufs" "$MODULES/oemxml" "$MODULES/sysext" "$MODULES/fontloader"
MODDIR="$SELF" sh "$SELF/common/module_status.sh" default >/dev/null
eq "$(sed -n 's/^foreignFontModules=//p' "$CONF")" ''
eq "$(sed -n 's/^foreignFontModuleCount=//p' "$CONF")" '0'
eq "$(sed -n 's/^fontLoaderPresent=//p' "$CONF")" 'no'

# Empty or missing modules root is not an error.
LUOSHU_MODULES_ROOT="$TMP/missing" MODDIR="$SELF" sh "$SELF/common/foreign_font_modules.sh" scan >/dev/null
eq "$(sed -n 's/^foreignFontModuleCount=//p' "$CONF")" '0'

printf 'PASS: %s\n' "$CASE"
