#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ROUTER="$ROOT/common/font_manager.sh"
SAFE_BACKEND="$ROOT/common/legacy_v14_4/font_switch_safe.sh"
LEGACY_BACKEND="$ROOT/common/legacy_v14_4_switch.sh"
ROM="$ROOT/common/legacy_v14_4/rom_adapters.sh"
HYPEROS_COMPAT="$ROOT/common/legacy_v14_4/hyperos_full_coverage.sh"
MIX_ROUTER="$ROOT/common/font_mix_controller.sh"
LEGACY_MIX_ROUTER="$ROOT/common/legacy_v14_4/mix_router.sh"
LEGACY_MIX_BRIDGE="$ROOT/common/legacy_v14_4/v14_mix.sh"
LEGACY_WEIGHTED="$ROOT/common/legacy_v14_4/v142_weighted_mix.sh"
LEGACY_AUTO="$ROOT/common/legacy_v14_4/v143_auto_multiweight_mix.sh"
LEGACY_MIX_ENGINE="$ROOT/common/legacy_v14_4/font_mix_engine.sh"
SERVICE="$ROOT/service.sh"
POSTFS="$ROOT/post-fs-data.sh"
POSTMOUNT="$ROOT/post-mount.sh"

grep -q 'font_manager_v4.sh' "$ROUTER"
grep -q 'font_switch_safe.sh' "$ROUTER"
grep -q 'legacy_v14_4_switch.sh' "$ROUTER"
grep -q 'exec sh "$SAFE_SWITCH" "$@"' "$ROUTER"
grep -q 'exec sh "$CURRENT_MANAGER" "$@"' "$ROUTER"

grep -q 'STAGE_PAYLOAD=.*\.luoshu-payload-stage' "$SAFE_BACKEND"
grep -q 'RETIRED_ROOT=.*\.luoshu-retired' "$SAFE_BACKEND"
grep -q 'cp -al "$LIVE_PAYLOAD/\." "$STAGE_PAYLOAD/"' "$SAFE_BACKEND"
grep -q 'mv "$LIVE_PAYLOAD" "$_retired"' "$SAFE_BACKEND"
grep -q 'mv "$STAGE_PAYLOAD" "$LIVE_PAYLOAD"' "$SAFE_BACKEND"
! grep -q 'rm -rf "$LIVE_PAYLOAD"' "$SAFE_BACKEND"
grep -q 'apply_font_by_rom' "$SAFE_BACKEND"
grep -q 'atomic-next-boot' "$SAFE_BACKEND"
grep -q 'LUOSHU_SWITCH_PROGRESS_FILE' "$SAFE_BACKEND"

grep -q 'apply_font_by_rom' "$LEGACY_BACKEND"
grep -q '\.luoshu-payload' "$LEGACY_BACKEND"
grep -q 'physical-file-map' "$LEGACY_BACKEND"
grep -q 'MiSansLatinVF.ttf' "$ROM"
grep -q 'GoogleSans' "$ROM"
grep -q 'Roboto' "$ROM"

# HyperOS 3 coverage is dynamic across real partitions, but only for safe upright
# TTF/OTF slots. TTC containers remain stock until their face-index layout is proven.
test -f "$HYPEROS_COMPAT"
grep -q 'XiaomiSans\*\.ttf' "$HYPEROS_COMPAT"
grep -q 'MiLanPro\*\.ttf' "$HYPEROS_COMPAT"
grep -q 'Mitype\*\.ttf' "$HYPEROS_COMPAT"
! grep -q 'MiSans\*\.ttc' "$HYPEROS_COMPAT"
grep -q 'hyperos_full_coverage.sh' "$POSTFS"
grep -q 'luoshu_hyperos_full_payload_ensure' "$POSTFS"
grep -q 'hyperos_full_coverage.sh' "$POSTMOUNT"
grep -q 'luoshu_hyperos_full_payload_ensure' "$POSTMOUNT"
! grep -qE 'font_validate_fast_v4|device_font_template|device_font_slot|font_config_overlay|font_config_batch|device_font_payload_build' "$HYPEROS_COMPAT"

TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-safe-switch)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
mkdir -p \
    "$TMP/module/.luoshu-payload/system/fonts" \
    "$TMP/stock/system" "$TMP/stock/system_ext" "$TMP/stock/product" \
    "$TMP/stock/mi_ext" "$TMP/stock/vendor"
printf 'selected-font-anchor\n' > "$TMP/module/.luoshu-payload/system/fonts/MiSansVF.ttf"
: > "$TMP/stock/mi_ext/MitypeClock.ttf"
: > "$TMP/stock/product/MiClock.ttf"
: > "$TMP/stock/system_ext/GoogleSansText-Regular.ttf"
: > "$TMP/stock/product/NotoSansUI-Medium.ttf"
: > "$TMP/stock/vendor/MiLanProVF.ttf"
: > "$TMP/stock/system_ext/MiSansGlobalVF.ttf"
: > "$TMP/stock/product/XiaomiSansUI-Regular.ttf"
: > "$TMP/stock/product/XiaomiSansCollection.ttc"
IS_HYPEROS=true \
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
    sh -c '. "$1"; luoshu_hyperos_full_payload_ensure' sh "$HYPEROS_COMPAT"
for generated in \
    "$TMP/module/.luoshu-payload/mi_ext/fonts/MitypeClock.ttf" \
    "$TMP/module/.luoshu-payload/product/fonts/MiClock.ttf" \
    "$TMP/module/.luoshu-payload/system_ext/fonts/GoogleSansText-Regular.ttf" \
    "$TMP/module/.luoshu-payload/product/fonts/NotoSansUI-Medium.ttf" \
    "$TMP/module/.luoshu-payload/vendor/fonts/MiLanProVF.ttf" \
    "$TMP/module/.luoshu-payload/system_ext/fonts/MiSansGlobalVF.ttf" \
    "$TMP/module/.luoshu-payload/product/fonts/XiaomiSansUI-Regular.ttf"; do
    cmp -s "$TMP/module/.luoshu-payload/system/fonts/MiSansVF.ttf" "$generated"
done
test ! -e "$TMP/module/.luoshu-payload/product/fonts/XiaomiSansCollection.ttc"

! grep -qE 'font_validate_fast_v4|device_font_template|device_font_slot|font_config_overlay|font_config_batch|device_font_payload_build' \
    "$SAFE_BACKEND" "$LEGACY_BACKEND"

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
sh -n "$SAFE_BACKEND"
sh -n "$LEGACY_BACKEND"
sh -n "$HYPEROS_COMPAT"
sh -n "$MIX_ROUTER"
sh -n "$LEGACY_MIX_ROUTER"
sh -n "$LEGACY_MIX_BRIDGE"
sh -n "$LEGACY_WEIGHTED"
sh -n "$LEGACY_AUTO"
sh -n "$LEGACY_MIX_ENGINE"
sh -n "$ROOT/common/font_switch_task.sh"
sh -n "$ROOT/customize.sh"
sh -n "$ROOT/service_v4.sh"
sh -n "$ROOT/post-fs-data-v4.sh"
sh -n "$ROOT/post-mount-v4.sh"

echo 'safe single/composite switching keeps full HyperOS physical UI coverage and current-boot payload integrity.'