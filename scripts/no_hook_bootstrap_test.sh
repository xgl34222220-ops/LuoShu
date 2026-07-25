#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
MOUNT_LOADER="$ROOT/common/mount_compat.sh"
MOUNT_CORE="$ROOT/common/mount_compat_base.sh"
BOOT_WRAPPER="$ROOT/post-fs-data.sh"
BOOT_CORE="$ROOT/.luoshu-runtime/post-fs-data-v227.sh"

# The native App's direct switch path loads font_library_cache after rom_adapters; that helper must
# load the unified dispatcher and the extended partition map.
grep -q 'common/font_library_cache.sh' "$ROOT/common/font_manager.sh"
grep -q 'common/hyperos_global.sh' "$ROOT/common/font_library_cache.sh"
grep -q 'common/font_config_partitions.sh' "$ROOT/common/font_library_cache.sh"

# v2.3.0 keeps a thin self-mount policy loader around the verified mount core. The loader must source
# the core, and the core must still load the unified dispatcher and full partition map.
grep -q 'common/mount_compat.sh' "$ROOT/common/font_mix.sh"
grep -q 'mount_compat_base.sh' "$MOUNT_LOADER"
grep -q 'private_mount_policy.sh' "$MOUNT_LOADER"
grep -q 'common/hyperos_global.sh' "$MOUNT_CORE"
grep -q 'common/font_config_partitions.sh' "$MOUNT_CORE"
grep -q 'system system_ext product vendor odm oem my_product' "$MOUNT_CORE"

# The dispatcher must load both the XML runtime and static-weight preparation layer, then invoke the
# same transactional enable function for HyperOS and for ColorOS/generic Android.
grep -q 'common/font_config_runtime.sh' "$ROOT/common/hyperos_global.sh"
grep -q 'common/font_config_weights.sh' "$ROOT/common/hyperos_global.sh"
grep -q 'font_config_enable_for_payload "$font_family"' "$ROOT/common/hyperos_global.sh"
_count=$(grep -c 'font_config_enable_for_payload' "$ROOT/common/hyperos_global.sh")
[ "$_count" -ge 2 ]

# Composite output commits its file-slot payload first and only then attempts the XML transaction;
# failure therefore retains a bootable compatibility mapping instead of leaving an empty font map.
grep -q 'payload_stage_activate' "$ROOT/common/font_mix.sh"
grep -q 'font_config_enable_for_payload mix' "$ROOT/common/font_mix.sh"

# v2.3.0 wraps the verified pre-Zygote initializer so it can expose the private payload only while
# initialization runs. Both wrapper and delegated core are required, and neither may mutate Android's
# /data/fonts database.
test -f "$BOOT_CORE"
grep -q 'private_payload.sh' "$BOOT_WRAPPER"
grep -q 'post-fs-data-v227.sh' "$BOOT_WRAPPER"
grep -q 'common/font_config_runtime.sh' "$BOOT_CORE"
grep -q 'common/font_config_partitions.sh' "$BOOT_CORE"
grep -q 'font_config_boot_guard' "$BOOT_CORE"
! grep -Eq '(^|[[:space:]])(cp|ln|rm)[[:space:]].*/data/fonts|_dest="/data/fonts/' "$BOOT_WRAPPER" "$BOOT_CORE"

# Extended specs must include ColorOS/Oplus and OEM fallback partitions while preserving the same
# transaction and rollback functions from font_config_runtime.sh.
grep -q 'my_product' "$ROOT/common/font_config_partitions.sh"
grep -q 'oplus_fonts_customization.xml' "$ROOT/common/font_config_partitions.sh"
grep -q 'vendor' "$ROOT/common/font_config_partitions.sh"
grep -q 'odm' "$ROOT/common/font_config_partitions.sh"

# Restoring the system default must remove generated XML and partition aliases.
grep -q 'font_config_disable' "$ROOT/common/font_manager.sh"
grep -q 'font_config_disable' "$ROOT/common/font_config_runtime.sh"

printf 'No-Hook bootstrap integration tests passed through v2.3 private self-mount wrappers.\n'
