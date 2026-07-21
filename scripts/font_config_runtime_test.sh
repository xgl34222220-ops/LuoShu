#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MOD="$TMP/module"
SYSTEM_ETC="$TMP/real/system/etc"
PRODUCT_ETC="$TMP/real/product/etc"
SYSTEM_EXT_ETC="$TMP/real/system_ext/etc"
mkdir -p "$MOD/common" "$MOD/config" "$MOD/system/fonts" \
    "$SYSTEM_ETC" "$PRODUCT_ETC" "$SYSTEM_EXT_ETC"
cp -f "$ROOT/common/font_config_overlay.py" "$MOD/common/font_config_overlay.py"
cp -f "$ROOT/common/font_config_runtime.sh" "$MOD/common/font_config_runtime.sh"

cat > "$SYSTEM_ETC/fonts.xml" <<'XML'
<familyset>
  <family name="sans-serif">
    <font weight="400">Roboto-Regular.ttf</font>
    <font weight="700">Roboto-Bold.ttf</font>
  </family>
  <family name="serif"><font weight="400">NotoSerif-Regular.ttf</font></family>
</familyset>
XML
cat > "$SYSTEM_ETC/font_fallback.xml" <<'XML'
<familyset>
  <family name="sans-serif-condensed"><font weight="400">RobotoCondensed-Regular.ttf</font></family>
  <family lang="und-Arab"><font weight="400">NotoNaskhArabic-Regular.ttf</font></family>
</familyset>
XML
cat > "$PRODUCT_ETC/mi_fonts_customization.xml" <<'XML'
<familyset>
  <family name="misans"><font weight="500">MiSansVF.ttf</font></family>
  <family name="mitype-clock"><font weight="400">Mitype2019.ttf</font></family>
</familyset>
XML
cat > "$SYSTEM_EXT_ETC/fonts_customization.xml" <<'XML'
<familyset>
  <family name="google-sans"><font weight="400">GoogleSans-Regular.ttf</font></family>
  <family name="material-icons"><font weight="400">MaterialIcons.ttf</font></family>
</familyset>
XML

for weight in 100 200 300 400 500 600 700 800 900; do
    dd if=/dev/zero of="$MOD/system/fonts/LuoShu-${weight}.ttf" bs=2048 count=1 2>/dev/null
    chmod 0644 "$MOD/system/fonts/LuoShu-${weight}.ttf"
done

export MODDIR="$MOD"
export MODULE_DIR="$MOD"
export CONFIG_DIR="$MOD/config"
export LUOSHU_PYTHON=python3
export LUOSHU_SYSTEM_ETC_ROOT="$SYSTEM_ETC"
export LUOSHU_PRODUCT_ETC_ROOT="$PRODUCT_ETC"
export LUOSHU_SYSTEM_EXT_ETC_ROOT="$SYSTEM_EXT_ETC"
. "$MOD/common/font_config_runtime.sh"
set -eu

font_config_generate DemoFamily

test -s "$MOD/system/etc/fonts.xml"
test -s "$MOD/system/etc/font_fallback.xml"
test -s "$MOD/product/etc/mi_fonts_customization.xml"
test -s "$MOD/system_ext/etc/fonts_customization.xml"
grep -q 'LuoShu-400.ttf' "$MOD/system/etc/fonts.xml"
grep -q 'LuoShu-700.ttf' "$MOD/system/etc/fonts.xml"
grep -q 'NotoSerif-Regular.ttf' "$MOD/system/etc/fonts.xml"
grep -q 'LuoShu-500.ttf' "$MOD/product/etc/mi_fonts_customization.xml"
grep -q 'Mitype2019.ttf' "$MOD/product/etc/mi_fonts_customization.xml"
grep -q 'LuoShu-400.ttf' "$MOD/system_ext/etc/fonts_customization.xml"
grep -q 'MaterialIcons.ttf' "$MOD/system_ext/etc/fonts_customization.xml"

test -s "$MOD/config/font-config-source/system/fonts.xml"
test -s "$MOD/config/font-config-source/product/mi_fonts_customization.xml"
test -s "$MOD/config/font-config-source/system_ext/fonts_customization.xml"
for weight in 100 200 300 400 500 600 700 800 900; do
    test -s "$MOD/product/fonts/LuoShu-${weight}.ttf"
    test -s "$MOD/system_ext/fonts/LuoShu-${weight}.ttf"
done

# A missing or truncated referenced font must disable every generated XML before boot.
: > "$MOD/product/fonts/LuoShu-500.ttf"
if font_config_boot_guard DemoFamily; then
    echo 'boot guard unexpectedly accepted a truncated generated font' >&2
    exit 1
fi
test ! -e "$MOD/system/etc/fonts.xml"
test ! -e "$MOD/product/etc/mi_fonts_customization.xml"
test ! -e "$MOD/system_ext/etc/fonts_customization.xml"

# Regeneration repairs partition aliases from the validated system weight set.
font_config_generate DemoFamily
test -s "$MOD/product/fonts/LuoShu-500.ttf"
font_config_disable
test ! -e "$MOD/system/etc/fonts.xml"
test ! -e "$MOD/product/etc/mi_fonts_customization.xml"
test ! -e "$MOD/system_ext/etc/fonts_customization.xml"
test ! -e "$MOD/system/fonts/LuoShu-400.ttf"
test ! -e "$MOD/product/fonts/LuoShu-400.ttf"
test ! -e "$MOD/system_ext/fonts/LuoShu-400.ttf"

printf 'Font configuration runtime tests passed.\n'
