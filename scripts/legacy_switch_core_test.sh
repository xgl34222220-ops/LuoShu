#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ROUTER="$ROOT/common/font_manager.sh"
BACKEND="$ROOT/common/legacy_v14_4_switch.sh"
ROM="$ROOT/common/legacy_v14_4/rom_adapters.sh"
HYPEROS_COMPAT="$ROOT/common/legacy_v14_4/hyperos_clock_compat.sh"
MIX_ROUTER="$ROOT/common/font_mix_controller.sh"
LEGACY_MIX_ROUTER="$ROOT/common/legacy_v14_4/mix_router.sh"
LEGACY_MIX_BRIDGE="$ROOT/common/legacy_v14_4/v14_mix.sh"
LEGACY_WEIGHTED="$ROOT/common/legacy_v14_4/v142_weighted_mix.sh"
LEGACY_AUTO="$ROOT/common/legacy_v14_4/v143_auto_multiweight_mix.sh"
LEGACY_MIX_ENGINE="$ROOT/common/legacy_v14_4/font_mix_engine.sh"
SERVICE="$ROOT/service.sh"
POSTFS="$ROOT/post-fs-data.sh"
POSTMOUNT="$ROOT/post-mount.sh"

# Current App-facing manager stays in place for every action except final apply.
grep -q 'font_manager_v4.sh' "$ROUTER"
grep -q 'legacy_v14_4_switch.sh' "$ROUTER"
grep -q '\[ "${1:-}" = action \].*\[ "${2:-}" = switch \]' "$ROUTER"
grep -q 'exec sh "$CURRENT_MANAGER" "$@"' "$ROUTER"

# The compatibility backend must be the pre-reset physical filename mapping path.
grep -q 'apply_font_by_rom' "$BACKEND"
grep -q '\.luoshu-payload' "$BACKEND"
grep -q 'legacyCore.*v14.4.0' "$BACKEND"
grep -q 'physical-file-map' "$BACKEND"
grep -q 'MiSansLatinVF.ttf' "$ROM"
grep -q 'GoogleSans' "$ROM"
grep -q 'Roboto' "$ROM"

# Restoring the old switch core must not throw away the later proven HyperOS 3
# status-bar / lock-screen coverage from v2.1.2. The bridge is boot-time only,
# writes physical aliases into the private payload and never enters the v4 pipeline.
test -f "$HYPEROS_COMPAT"
grep -q 'MitypeClock.ttf' "$HYPEROS_COMPAT"
grep -q 'MiClock.ttf' "$HYPEROS_COMPAT"
grep -q 'AndroidClock.ttf' "$HYPEROS_COMPAT"
grep -q 'Clockopia.ttf' "$HYPEROS_COMPAT"
grep -q 'mi_ext' "$HYPEROS_COMPAT"
grep -q 'hyperos_clock_compat.sh' "$POSTFS"
grep -q 'luoshu_hyperos_clock_payload_ensure' "$POSTFS"
grep -q 'hyperos_clock_compat.sh' "$POSTMOUNT"
grep -q 'luoshu_hyperos_clock_payload_ensure' "$POSTMOUNT"
! grep -qE 'font_validate_fast_v4|device_font_template|device_font_slot|font_config_overlay|font_config_batch|device_font_payload_build' "$HYPEROS_COMPAT"

# Functional fixture: a HyperOS 3 clock file living only in mi_ext and another
# clock file in product must both be mirrored from the selected/composite anchor.
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-legacy-clock)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
mkdir -p "$TMP/module/.luoshu-payload/system/fonts" "$TMP/stock/mi_ext" "$TMP/stock/product"
printf 'selected-font-anchor\n' > "$TMP/module/.luoshu-payload/system/fonts/MiSansVF.ttf"
: > "$TMP/stock/mi_ext/MitypeClock.ttf"
: > "$TMP/stock/product/MiClock.ttf"
MODDIR="$TMP/module" \
LUOSHU_HYPEROS_CLOCK_PAYLOAD_ROOT="$TMP/module/.luoshu-payload" \
LUOSHU_SYSTEM_FONTS_ROOT="$TMP/stock/system" \
LUOSHU_SYSTEM_EXT_FONTS_ROOT="$TMP/stock/system_ext" \
LUOSHU_PRODUCT_FONTS_ROOT="$TMP/stock/product" \
LUOSHU_MI_EXT_FONTS_ROOT="$TMP/stock/mi_ext" \
LUOSHU_VENDOR_FONTS_ROOT="$TMP/stock/vendor" \
LUOSHU_ODM_FONTS_ROOT="$TMP/stock/odm" \
LUOSHU_OEM_FONTS_ROOT="$TMP/stock/oem" \
LUOSHU_MY_PRODUCT_FONTS_ROOT="$TMP/stock/my_product" \
LUOSHU_HW_PRODUCT_FONTS_ROOT="$TMP/stock/hw_product" \
LUOSHU_CUST_FONTS_ROOT="$TMP/stock/cust" \
    sh -c '. "$1"; luoshu_hyperos_clock_payload_ensure' sh "$HYPEROS_COMPAT"
cmp -s "$TMP/module/.luoshu-payload/system/fonts/MiSansVF.ttf" \
    "$TMP/module/.luoshu-payload/mi_ext/fonts/MitypeClock.ttf"
cmp -s "$TMP/module/.luoshu-payload/system/fonts/MiSansVF.ttf" \
    "$TMP/module/.luoshu-payload/product/fonts/MiClock.ttf"

# 94% v4 pipeline components are forbidden from the actual legacy apply backend.
! grep -qE 'font_validate_fast_v4|device_font_template|device_font_slot|font_config_overlay|font_config_batch|device_font_payload_build' "$BACKEND"

# Composite App actions must also leave the v4 runtime immediately and enter the exact
# pre-reset bridge / weighted / auto-multiweight / full composite chain.
grep -q 'legacy_v1.*4_4/mix_router.sh' "$MIX_ROUTER"
grep -q 'exec sh "$LEGACY_V14_MIX" "$@"' "$MIX_ROUTER"
grep -q 'v142_weighted_mix.sh' "$LEGACY_MIX_BRIDGE"
grep -q 'v143_auto_multiweight_mix.sh' "$LEGACY_MIX_BRIDGE"
grep -q 'font_mix.sh' "$LEGACY_MIX_BRIDGE"
grep -q 'for _weight in 100 200 300 400 500 600 700 800 900' "$LEGACY_AUTO"
grep -q 'build_composite_cached' "$LEGACY_AUTO"
grep -q 'LuoShuAutoMix' "$LEGACY_AUTO"
grep -q 'action switch' "$LEGACY_AUTO"
grep -q 'BASE_ENGINE=.*font_mix.sh' "$LEGACY_WEIGHTED"
grep -q '中文字体保留为完整基底' "$LEGACY_MIX_ENGINE"
grep -q '不裁剪 ROM 字体槽' "$LEGACY_MIX_ENGINE"
grep -q '\.legacy-v14-runtime' "$LEGACY_MIX_ROUTER"
grep -q '\.luoshu-payload' "$LEGACY_MIX_ROUTER"
grep -q 'font_mix_engine.sh' "$LEGACY_MIX_ROUTER"
! grep -qE 'font_validate_fast_v4|device_font_template|device_font_slot|font_config_overlay|font_config_batch|device_font_payload_build' \
    "$LEGACY_MIX_ROUTER" "$LEGACY_MIX_BRIDGE" "$LEGACY_WEIGHTED" "$LEGACY_AUTO" "$LEGACY_MIX_ENGINE"

# Once selected, all three boot stages keep the legacy payload immutable except for
# the deterministic HyperOS clock/status aliases above.
for file in "$SERVICE" "$POSTFS" "$POSTMOUNT"; do
    grep -q 'font_runtime_legacy_v14_4.conf' "$file"
    sh -n "$file"
done
grep -q 'service_v4.sh' "$SERVICE"
grep -q 'post-fs-data-v4.sh' "$POSTFS"
grep -q 'post-mount-v4.sh' "$POSTMOUNT"
! grep -q 'device_font_template.sh' "$SERVICE"
! grep -q 'font_config_runtime.sh' "$POSTFS"
! grep -q 'font_config_runtime.sh' "$POSTMOUNT"

sh -n "$ROUTER"
sh -n "$BACKEND"
sh -n "$HYPEROS_COMPAT"
sh -n "$MIX_ROUTER"
sh -n "$LEGACY_MIX_ROUTER"
sh -n "$LEGACY_MIX_BRIDGE"
sh -n "$LEGACY_WEIGHTED"
sh -n "$LEGACY_AUTO"
sh -n "$LEGACY_MIX_ENGINE"
sh -n "$ROOT/service_v4.sh"
sh -n "$ROOT/post-fs-data-v4.sh"
sh -n "$ROOT/post-mount-v4.sh"

echo 'single/composite legacy switching keeps HyperOS status-bar and lock-screen physical slots.'
