#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

# The native App's direct switch path loads font_library_cache after rom_adapters; that helper must
# then load hyperos_global, which owns the unified HyperOS/ColorOS/AOSP dispatcher.
grep -q 'common/font_library_cache.sh' "$ROOT/common/font_manager.sh"
grep -q 'common/hyperos_global.sh' "$ROOT/common/font_library_cache.sh"

# The composite path loads mount_compat after rom_adapters; mount_compat must load the same unified
# dispatcher so composite and single-font payloads cannot diverge.
grep -q 'common/mount_compat.sh' "$ROOT/common/font_mix.sh"
grep -q 'common/hyperos_global.sh' "$ROOT/common/mount_compat.sh"

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

# Restoring the system default must remove generated XML and partition aliases.
grep -q 'font_config_disable' "$ROOT/common/font_manager.sh"
grep -q 'font_config_disable' "$ROOT/common/font_config_runtime.sh"

printf 'No-Hook bootstrap integration tests passed.\n'
