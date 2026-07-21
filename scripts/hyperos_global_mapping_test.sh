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
LUOSHU_FONT_XMLS="$ROOT/fonts.xml"
LUOSHU_PYTHON=$(command -v python3)
export MODULE_DIR MODDIR USER_FONTS_DIR LUOSHU_SYSTEM_FONTS_ROOT LUOSHU_PRODUCT_FONTS_ROOT LUOSHU_SYSTEM_EXT_FONTS_ROOT LUOSHU_FONT_XMLS LUOSHU_PYTHON

mkdir -p "$MODULE_DIR/system/fonts" "$MODULE_DIR/product/fonts" "$MODULE_DIR/system_ext/fonts" \
    "$MODULE_DIR/common" "$MODULE_DIR/config" \
    "$USER_FONTS_DIR" "$LUOSHU_SYSTEM_FONTS_ROOT" "$LUOSHU_PRODUCT_FONTS_ROOT" "$LUOSHU_SYSTEM_EXT_FONTS_ROOT"
cp "$REPO_ROOT/common/font_config_targets.py" "$MODULE_DIR/common/font_config_targets.py"

printf 'regular-source\n' > "$USER_FONTS_DIR/Demo-Regular.ttf"
printf 'medium-source\n' > "$USER_FONTS_DIR/Demo-Medium.ttf"
printf 'bold-source\n' > "$USER_FONTS_DIR/Demo-Bold.ttf"
printf 'stock-core\n' > "$LUOSHU_PRODUCT_FONTS_ROOT/MiSansVF.ttf"
printf 'stock-overlay\n' > "$LUOSHU_SYSTEM_EXT_FONTS_ROOT/MiSansVF_Overlay.ttf"
printf 'stock-400\n' > "$LUOSHU_SYSTEM_FONTS_ROOT/400.ttf"
printf 'stock-700\n' > "$LUOSHU_PRODUCT_FONTS_ROOT/700.ttf"
printf 'stock-roboto\n' > "$LUOSHU_SYSTEM_FONTS_ROOT/Roboto-Regular.ttf"
printf 'stock-medium\n' > "$LUOSHU_PRODUCT_FONTS_ROOT/Roboto-Medium.ttf"
printf 'stock-google-bold\n' > "$LUOSHU_SYSTEM_EXT_FONTS_ROOT/GoogleSans-Bold.ttf"
printf 'stock-dynamic-regular\n' > "$LUOSHU_SYSTEM_FONTS_ROOT/ActualSansVF.ttf"
printf 'stock-dynamic-medium\n' > "$LUOSHU_PRODUCT_FONTS_ROOT/ActualSans-Medium.ttf"
printf 'stock-source-bold\n' > "$LUOSHU_SYSTEM_EXT_FONTS_ROOT/SourceSansPro-Bold.ttf"
printf 'stock-serif\n' > "$LUOSHU_SYSTEM_FONTS_ROOT/NotoSerif-Regular.ttf"
printf 'stale-overlay\n' > "$MODULE_DIR/system/fonts/Roboto-Regular.ttf"

cat > "$LUOSHU_FONT_XMLS" <<'EOF_XML'
<?xml version="1.0" encoding="utf-8"?>
<familyset>
  <family name="sans-serif">
    <font weight="400">ActualSansVF.ttf<axis tag="wght" stylevalue="400"/></font>
    <font weight="500">ActualSans-Medium.ttf</font>
  </family>
  <family name="source-sans-pro">
    <font weight="700">SourceSansPro-Bold.ttf</font>
  </family>
  <family name="serif">
    <font weight="400">NotoSerif-Regular.ttf</font>
  </family>
</familyset>
EOF_XML

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
    _name=${_name%-Medium}
    _name=${_name%-Bold}
    printf '%s\n' "$_name"
}
detect_font_weight() {
    case "$1" in
        *-Bold.*) printf 'bold\n' ;;
        *-Medium.*) printf 'medium\n' ;;
        *) printf 'regular\n' ;;
    esac
}
is_variable_font() { return 1; }
_log_step() { :; }

. "$REPO_ROOT/common/hyperos_global.sh"
copy_as_hyperos "$USER_FONTS_DIR/Demo-Bold.ttf" "$MODULE_DIR/system/fonts" quick Demo

test "$(cat "$MODULE_DIR/product/fonts/MiSansVF.ttf")" = 'regular-source'
test "$(cat "$MODULE_DIR/system_ext/fonts/MiSansVF_Overlay.ttf")" = 'regular-source'
test "$(cat "$MODULE_DIR/system/fonts/400.ttf")" = 'regular-source'
test "$(cat "$MODULE_DIR/product/fonts/700.ttf")" = 'bold-source'
test "$(cat "$MODULE_DIR/system/fonts/Roboto-Regular.ttf")" = 'regular-source'
test "$(cat "$MODULE_DIR/product/fonts/Roboto-Medium.ttf")" = 'medium-source'
test "$(cat "$MODULE_DIR/system_ext/fonts/GoogleSans-Bold.ttf")" = 'bold-source'
test "$(cat "$MODULE_DIR/system/fonts/ActualSansVF.ttf")" = 'regular-source'
test "$(cat "$MODULE_DIR/product/fonts/ActualSans-Medium.ttf")" = 'medium-source'
test "$(cat "$MODULE_DIR/system_ext/fonts/SourceSansPro-Bold.ttf")" = 'bold-source'
test ! -e "$MODULE_DIR/system/fonts/NotoSerif-Regular.ttf"
grep -qx 'ActualSansVF.ttf' "$MODULE_DIR/config/hyperos_dynamic_targets.conf"
grep -qx 'ActualSans-Medium.ttf' "$MODULE_DIR/config/hyperos_dynamic_targets.conf"
grep -qx 'SourceSansPro-Bold.ttf' "$MODULE_DIR/config/hyperos_dynamic_targets.conf"
test ! -e "$MODULE_DIR/system/fonts/MiSansVF.ttf"
test ! -e "$MODULE_DIR/product/fonts/Roboto-Regular.ttf"
test ! -e "$MODULE_DIR/system_ext/fonts/Roboto-Regular.ttf"

sh "$REPO_ROOT/scripts/play_font_bridge_test.sh"
printf 'HyperOS global mapping tests passed.\n'
