#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-device-bridge)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MODULE="$TMP/module"
mkdir -p "$MODULE/config" "$MODULE/system/fonts"
printf 'font\n' > "$TMP/source.ttf"

MODDIR="$MODULE"
MODULE_DIR="$MODULE"
export MODDIR MODULE_DIR

ROM=generic
DEVICE_RC=0
LEGACY_RC=0
CALLS="$TMP/calls"
: > "$CALLS"

record() { printf '%s\n' "$1" >> "$CALLS"; }
detect_font_family() { printf 'Fixture\n'; }
copy_as_hyperos() { record hyperos; }
copy_as_coloros() { record coloros; }
copy_as_originos() { record originos; }
copy_as_flyme() { record flyme; }
copy_as_generic() { record generic; }
_luoshu_detect_originos() { [ "$ROM" = originos ]; }
_luoshu_detect_flyme() { [ "$ROM" = flyme ]; }
font_config_prepare_payload_weights() { record prepare; return 0; }
device_font_payload_build_install() { record device; return "$DEVICE_RC"; }
font_config_generate() { record legacy; return "$LEGACY_RC"; }
device_font_payload_clear() { record device-clear; }
luoshu_dynamic_targets_clear() { record dynamic-clear; }
_luoshu_font_config_disable_base() { record base-clear; }
luoshu_oem_clear_managed_fonts() { record oem-clear; }
_luoshu_flyme_prepare_data_restore() { record flyme-restore; }
luoshu_flyme_pending_apply() { record flyme-apply; }
_luoshu_safety_module() { printf '%s\n' "$MODULE"; }
_luoshu_safety_config() { printf '%s/config\n' "$MODULE"; }
_luoshu_payload_parts() { printf '\n'; }
_luoshu_safety_log() { record safety-log; }
_log_step() { :; }

. "$ROOT/common/device_font_payload_bridge.sh"

# OriginOS and Flyme must never fall through to the generic adapter after the bridge loads.
ROM=originos
DEVICE_RC=0
: > "$CALLS"
apply_font_by_rom "$TMP/source.ttf" "$MODULE/system/fonts" quick Fixture
grep -qx originos "$CALLS"
! grep -qx generic "$CALLS"
grep -qx device "$CALLS"
test "$LUOSHU_DEVICE_PAYLOAD_RESULT" = device
test "$LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE" = 0

ROM=flyme
DEVICE_RC=0
: > "$CALLS"
apply_font_by_rom "$TMP/source.ttf" "$MODULE/system/fonts" quick Fixture
grep -qx flyme "$CALLS"
! grep -qx generic "$CALLS"
grep -qx device "$CALLS"

# Unsupported outline sources may keep a complete physical-slot mapping when legacy XML is absent.
ROM=originos
DEVICE_RC=2
LEGACY_RC=1
: > "$CALLS"
apply_font_by_rom "$TMP/source.ttf" "$MODULE/system/fonts" quick Fixture
grep -qx originos "$CALLS"
grep -qx legacy "$CALLS"
test "$LUOSHU_DEVICE_PAYLOAD_RESULT" = slot-only

# A hard v2 install failure is not downgraded to apparent success, while the fresh OEM slots
# remain untouched until the outer payload transaction restores the previous tree.
DEVICE_RC=1
LEGACY_RC=0
: > "$CALLS"
set +e
apply_font_by_rom "$TMP/source.ttf" "$MODULE/system/fonts" quick Fixture
RC=$?
set -e
test "$RC" -eq 1
grep -qx device-clear "$CALLS"
! grep -qx oem-clear "$CALLS"

# Explicit default/reset restores Flyme's persistent theme slot and clears OEM mappings.
ROM=flyme
LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE=0
: > "$CALLS"
font_config_disable
grep -qx device-clear "$CALLS"
grep -qx oem-clear "$CALLS"
grep -qx flyme-restore "$CALLS"
grep -qx dynamic-clear "$CALLS"
grep -qx base-clear "$CALLS"

# Boot quarantine must apply the pending Flyme restoration before returning to default.
printf 'active\n' > "$MODULE/config/active_font.conf"
printf '0\n' > "$MODULE/config/font-boot-failures"
: > "$CALLS"
luoshu_payload_quarantine
grep -qx oem-clear "$CALLS"
grep -qx flyme-restore "$CALLS"
grep -qx flyme-apply "$CALLS"
grep -qx device-clear "$CALLS"
test "$(cat "$MODULE/config/active_font.conf")" = default

# The foreground policy is loaded after the bridge in production. On a cache miss it must
# finish with the physical ROM mapping and must never enter the 18-file weight preparation
# or legacy XML generator that made a simple switch take minutes.
. "$ROOT/common/device_font_payload_policy.sh"
ROM=originos
rm -f "$MODULE/config/device-font-engine.conf"
: > "$CALLS"
apply_font_by_rom "$TMP/source.ttf" "$MODULE/system/fonts" quick Fixture
grep -qx originos "$CALLS"
! grep -qx generic "$CALLS"
! grep -qx prepare "$CALLS"
! grep -qx legacy "$CALLS"
grep -qx device-clear "$CALLS"
grep -qx dynamic-clear "$CALLS"
grep -qx base-clear "$CALLS"
! grep -qx oem-clear "$CALLS"
test "$LUOSHU_DEVICE_PAYLOAD_RESULT" = slot-only

# ColorOS discovery is cached by ROM fingerprint and the old post-adapter alias pass is
# suppressed only after the partition-aware adapter has completed.
_coloros_core_files() { printf '%s\n' 'Core-Regular.ttf Core-Medium.ttf'; }
_coloros_google_text_files() { printf '%s\n' 'GoogleSansText-Regular.ttf'; }
_coloros_vendor_files() { printf '%s\n' 'Vendor-Regular.ttf'; }
_coloros_oem_ui_files() { printf '%s\n' 'OplusSans-Regular.ttf'; }
_coloros_discovered_ui_files() { printf '%s\n' 'Discovered-Regular.ttf Core-Regular.ttf'; }
LUOSHU_COLOROS_CACHE_KEY=fixture-rom
export LUOSHU_COLOROS_CACHE_KEY
rm -f "$MODULE/config/coloros-font-targets.cache"
get_all_coloros_files > "$TMP/coloros-first"
grep -qx Core-Regular.ttf "$TMP/coloros-first"
grep -qx GoogleSansText-Regular.ttf "$TMP/coloros-first"
test "$(grep -c '^Core-Regular.ttf$' "$TMP/coloros-first")" -eq 1
_coloros_discovered_ui_files() { printf '%s\n' 'Should-Not-Appear.ttf'; }
get_all_coloros_files > "$TMP/coloros-second"
cmp "$TMP/coloros-first" "$TMP/coloros-second"
LUOSHU_COLOROS_TARGETS_MAPPED=1
export LUOSHU_COLOROS_TARGETS_MAPPED
test -z "$(get_all_coloros_names)"
LUOSHU_COLOROS_TARGETS_MAPPED=0
export LUOSHU_COLOROS_TARGETS_MAPPED
grep -qx Core-Regular "$(get_all_coloros_names > "$TMP/coloros-names"; printf '%s' "$TMP/coloros-names")"

sh -n "$ROOT/common/device_font_payload_bridge.sh"
sh -n "$ROOT/common/device_font_payload_policy.sh"
echo 'Device font payload OEM bridge tests passed.'
