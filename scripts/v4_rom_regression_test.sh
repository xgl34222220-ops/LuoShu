#!/bin/sh
set -eu
grep -q 'degraded:booting.*degraded:confirmed' common/device_font_load_verify.sh
! grep -A45 '^luoshu_payload_quarantine()' common/font_runtime_policy.sh | grep -q "printf 'default"
! grep -q '字体挂载连续三次不可见，已安全恢复系统默认字体' service_v4.sh
! grep -A25 '^_font_anchor()' common/rom_adapters.sh | grep -q '_hyperos_compact_normalize'
! grep -A35 '^sync_secondary_hyperos_dirs()' common/font_mix.sh | grep -q 'LUOSHU_VENDOR_FONTS_ROOT'
grep -A40 '^_device_font_inventory_target()' common/rom_adapters.sh | grep -q '/mi_ext/fonts/'
grep -A40 '^_device_font_inventory_target()' common/rom_adapters.sh | grep -q '/hw_product/fonts/'
grep -q 'Mitype' common/font_inventory.py
grep -q 'MiClock' common/font_inventory.py
grep -q 'directPhysicalSlots' common/device_font_payload_overlay.py
grep -q 'physical-{name}' common/device_font_payload_build.py
! grep -A20 '^_luoshu_coloros_root_pairs()' common/coloros_global.sh | grep -Eq '/vendor/fonts|/odm/fonts|/oem/fonts|/oplus_'
grep -q 'ColorOS 原厂模板不可用' common/device_font_payload_policy.sh
! grep -q '请先恢复系统默认字体并完整重启一次' common/device_font_payload_policy.sh
grep -q 'fun rebootDevice()' android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt
! grep -A12 'fun rebootDevice()' android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt | grep -q 'operationBusy || mixState.busy'
echo 'v4 device regression guards passed'
