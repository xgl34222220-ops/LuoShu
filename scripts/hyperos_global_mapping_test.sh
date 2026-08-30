#!/bin/sh
set -eu
REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$REPO_ROOT/scripts/assert.sh"
ROOT=$(mktemp -d)
trap 'rm -rf "$ROOT"' EXIT HUP INT TERM

MODULE_DIR="$ROOT/module"
MODDIR="$MODULE_DIR"
LUOSHU_PUBLIC_DIR="$ROOT/public"
USER_FONTS_DIR="$LUOSHU_PUBLIC_DIR/fonts"
LUOSHU_SYSTEM_FONTS_ROOT="$ROOT/real/system/fonts"
LUOSHU_PRODUCT_FONTS_ROOT="$ROOT/real/product/fonts"
LUOSHU_SYSTEM_EXT_FONTS_ROOT="$ROOT/real/system_ext/fonts"
LUOSHU_MI_EXT_FONTS_ROOT="$ROOT/real/mi_ext/fonts"
LUOSHU_ODM_FONTS_ROOT="$ROOT/real/odm/fonts"
LUOSHU_CUST_FONTS_ROOT="$ROOT/real/cust/fonts"
export MODULE_DIR MODDIR LUOSHU_PUBLIC_DIR USER_FONTS_DIR LUOSHU_SYSTEM_FONTS_ROOT LUOSHU_PRODUCT_FONTS_ROOT LUOSHU_SYSTEM_EXT_FONTS_ROOT LUOSHU_MI_EXT_FONTS_ROOT LUOSHU_ODM_FONTS_ROOT LUOSHU_CUST_FONTS_ROOT

mkdir -p "$MODULE_DIR/system/fonts" "$MODULE_DIR/product/fonts" "$MODULE_DIR/system_ext/fonts" "$MODULE_DIR/mi_ext/fonts" \
    "$USER_FONTS_DIR" "$LUOSHU_SYSTEM_FONTS_ROOT" "$LUOSHU_PRODUCT_FONTS_ROOT" "$LUOSHU_SYSTEM_EXT_FONTS_ROOT" "$LUOSHU_MI_EXT_FONTS_ROOT" \
    "$LUOSHU_ODM_FONTS_ROOT" "$LUOSHU_CUST_FONTS_ROOT"
printf 'regular-source\n' > "$USER_FONTS_DIR/Demo-Regular.ttf"
printf 'medium-source\n' > "$USER_FONTS_DIR/Demo-Medium.ttf"
printf 'bold-source\n' > "$USER_FONTS_DIR/Demo-Bold.ttf"
printf 'stock-core\n' > "$LUOSHU_PRODUCT_FONTS_ROOT/MiSansVF.ttf"
printf 'stock-overlay\n' > "$LUOSHU_SYSTEM_EXT_FONTS_ROOT/MiSansVF_Overlay.ttf"
printf 'stock-400\n' > "$LUOSHU_SYSTEM_FONTS_ROOT/400.ttf"
printf 'stock-700\n' > "$LUOSHU_PRODUCT_FONTS_ROOT/700.ttf"
printf 'stock-metrics\n' > "$LUOSHU_SYSTEM_FONTS_ROOT/Roboto-Regular.ttf"
printf 'stock-italic\n' > "$LUOSHU_SYSTEM_FONTS_ROOT/Roboto-Italic.ttf"
printf 'stock-google-regular\n' > "$LUOSHU_PRODUCT_FONTS_ROOT/GoogleSansText-Regular.ttf"
printf 'stock-google-medium\n' > "$LUOSHU_PRODUCT_FONTS_ROOT/GoogleSansText-Medium.ttf"
printf 'stock-google-bold\n' > "$LUOSHU_PRODUCT_FONTS_ROOT/GoogleSansText-Bold.ttf"
printf 'stock-clock\n' > "$LUOSHU_MI_EXT_FONTS_ROOT/MiClock.otf"
printf 'stock-mitype\n' > "$LUOSHU_PRODUCT_FONTS_ROOT/MitypeClock.otf"
printf 'stock-noto\n' > "$LUOSHU_ODM_FONTS_ROOT/NotoSansUI-Regular.ttf"
printf 'stock-source\n' > "$LUOSHU_CUST_FONTS_ROOT/SourceSansPro-Bold.ttf"
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
    for _suffix in -Thin -ExtraLight -Light -Regular -Medium -SemiBold -Bold -ExtraBold -Black; do
        case "$_name" in *"$_suffix") _name=${_name%"$_suffix"}; break ;; esac
    done
    printf '%s\n' "$_name"
}
detect_font_weight() {
    case "$1" in *-Bold.*) printf 'bold\n' ;; *-Medium.*) printf 'medium\n' ;; *) printf 'regular\n' ;; esac
}
is_variable_font() { return 1; }
_log_step() { :; }

. "$REPO_ROOT/common/hyperos_global.sh"
NORMALIZE_COUNT_FILE="$ROOT/normalize-count"
printf '0\n' > "$NORMALIZE_COUNT_FILE"
_hyperos_compact_normalize() {
    _count=$(cat "$NORMALIZE_COUNT_FILE")
    _count=$((_count + 1))
    printf '%s\n' "$_count" > "$NORMALIZE_COUNT_FILE"
    cp -f "$1" "$2"
}
CASE='HyperOS 物理槽与字重映射'
copy_as_hyperos "$USER_FONTS_DIR/Demo-Bold.ttf" "$MODULE_DIR/system/fonts" quick Demo

ok test "$(cat "$MODULE_DIR/product/fonts/MiSansVF.ttf")" = 'regular-source'
ok test "$(cat "$MODULE_DIR/system_ext/fonts/MiSansVF_Overlay.ttf")" = 'regular-source'
ok test "$(cat "$MODULE_DIR/system/fonts/400.ttf")" = 'regular-source'
ok test "$(cat "$MODULE_DIR/product/fonts/700.ttf")" = 'bold-source'
no test -e "$MODULE_DIR/system/fonts/MiSansVF.ttf"
ok test "$(cat "$MODULE_DIR/system/fonts/Roboto-Regular.ttf")" = 'regular-source'
no test -e "$MODULE_DIR/product/fonts/Roboto-Regular.ttf"
no test -e "$MODULE_DIR/system_ext/fonts/Roboto-Regular.ttf"
no test -e "$MODULE_DIR/system/fonts/Roboto-Italic.ttf"
ok test "$(cat "$MODULE_DIR/product/fonts/GoogleSansText-Regular.ttf")" = 'regular-source'
ok test "$(cat "$MODULE_DIR/product/fonts/GoogleSansText-Medium.ttf")" = 'medium-source'
ok test "$(cat "$MODULE_DIR/product/fonts/GoogleSansText-Bold.ttf")" = 'bold-source'
ok test "$(cat "$MODULE_DIR/mi_ext/fonts/MiClock.otf")" = 'regular-source'
ok test "$(cat "$MODULE_DIR/product/fonts/MitypeClock.otf")" = 'regular-source'
ok test "$(cat "$MODULE_DIR/odm/fonts/NotoSansUI-Regular.ttf")" = 'regular-source'
ok test "$(cat "$MODULE_DIR/cust/fonts/SourceSansPro-Bold.ttf")" = 'bold-source'
ok test "$(cat "$NORMALIZE_COUNT_FILE")" -eq 11
_luoshu_hyperos_root_pairs > "$ROOT/hyperos-root-pairs"
ok grep -qF "$LUOSHU_MI_EXT_FONTS_ROOT|$MODULE_DIR/mi_ext/fonts" "$ROOT/hyperos-root-pairs"
ok grep -qF "$LUOSHU_ODM_FONTS_ROOT|$MODULE_DIR/odm/fonts" "$ROOT/hyperos-root-pairs"
ok grep -qF "$LUOSHU_CUST_FONTS_ROOT|$MODULE_DIR/cust/fonts" "$ROOT/hyperos-root-pairs"
printf 'HyperOS global mapping and compact-anchor reuse tests passed.\n'

# Safe v4 staging must not regress to hard-linking the raw regular/composite font into
# every HyperOS target. The dedicated helper normalizes general UI slots and routes
# MiClock/Mitype clock/mono slots through the existing stock-aligned slot engine first.
CASE='HyperOS 安全暂存度量对齐链'
METRIC_STAGE="$REPO_ROOT/common/legacy_v14_4/hyperos_metric_stage.sh"
METRIC_ALIGN="$REPO_ROOT/common/legacy_v14_4/hyperos_metric_align.py"
ok test -s "$METRIC_STAGE"
ok test -s "$METRIC_ALIGN"
ok grep -q 'hyperos_metric_stage.sh' "$REPO_ROOT/common/hyperos_stage_complete.sh"
ok grep -q 'luoshu_hyperos_stage_metric_anchor' "$REPO_ROOT/common/hyperos_stage_complete.sh"
ok grep -q 'font_metrics_normalize' "$METRIC_ALIGN"
ok grep -q 'device_font_slot_plan' "$METRIC_ALIGN"
ok grep -q 'device_font_slot_build' "$METRIC_ALIGN"
python3 -m py_compile "$METRIC_ALIGN"
. "$METRIC_STAGE"
ok test "$(_lhms_role_for_target MiClock.otf)" = clock
ok test "$(_lhms_role_for_target MitypeClockMono.ttf)" = mono
ok test "$(_lhms_role_for_target Roboto-Regular.ttf)" = ui
printf 'HyperOS safe-stage metric alignment regression gates passed.\n'

# Keep OEM partition regressions in the always-on source gate.
sh "$REPO_ROOT/scripts/coloros_partition_mapping_test.sh"
sh "$REPO_ROOT/scripts/originos_flyme_mapping_test.sh"
