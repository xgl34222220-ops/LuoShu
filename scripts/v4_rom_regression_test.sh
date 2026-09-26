#!/bin/sh
set -eu
! grep -q 'mount-active-visible-layout-differs' common/device_font_load_verify.sh
grep -q 'physical_font_load_verify.py' common/device_font_load_verify.sh
! grep -A45 '^luoshu_payload_quarantine()' common/font_runtime_policy.sh | grep -q "printf 'default"
! grep -q '字体挂载连续三次不可见，已安全恢复系统默认字体' .luoshu-runtime/core/service.sh
! grep -A25 '^_font_anchor()' common/rom_adapters.sh | grep -q '_hyperos_compact_normalize'
! grep -A35 '^sync_secondary_hyperos_dirs()' common/font_mix.sh | grep -q 'LUOSHU_VENDOR_FONTS_ROOT'
grep -q '^_device_font_inventory_partition_allowed()' common/rom_adapters.sh
grep -A35 '^_device_font_inventory_target()' common/rom_adapters.sh | grep -q '_dfit_rest'
grep -A35 '^_device_font_inventory_target()' common/rom_adapters.sh | grep -q '\.ttf|\*\.otf|\*\.ttc|\*\.otc'
grep -q '^def _text_face_reason' common/font_inventory.py
grep -q 'monospaced.*fixed_pitch' common/font_inventory.py
grep -q 'directPhysicalSlots' common/device_font_payload_overlay.py
grep -q 'physical-{name}' common/device_font_payload_build.py
! grep -A20 '^_luoshu_coloros_root_pairs()' common/coloros_global.sh | grep -Eq '/vendor/fonts|/odm/fonts|/oem/fonts|/oplus_'
grep -q 'ColorOS 原厂模板不可用' common/device_font_payload_policy.sh
! grep -q '请先恢复系统默认字体并完整重启一次' common/device_font_payload_policy.sh
grep -q 'fun rebootDevice()' android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt
! grep -A12 'fun rebootDevice()' android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt | grep -q 'operationBusy || mixState.busy'
echo 'v4 device regression guards passed'
