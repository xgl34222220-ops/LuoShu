#!/bin/sh
set -eu
grep -q 'degraded:booting.*degraded:confirmed' common/device_font_load_verify.sh
! grep -A45 '^luoshu_payload_quarantine()' common/font_runtime_policy.sh | grep -q "printf 'default"
! grep -q '字体挂载连续三次不可见，已安全恢复系统默认字体' service_v4.sh
grep -q 'mount-verification-inconclusive' service_v4.sh
grep -q 'if \[ "${IS_HYPEROS:-false}" = true \].*_hyperos_compact_normalize' common/rom_adapters.sh
grep -q 'my_product|${LUOSHU_MY_PRODUCT_FONTS_ROOT' common/font_mix.sh
grep -q 'fun rebootDevice()' android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt
! grep -A12 'fun rebootDevice()' android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt | grep -q 'operationBusy || mixState.busy'
echo 'v4 ROM regression guards passed'
