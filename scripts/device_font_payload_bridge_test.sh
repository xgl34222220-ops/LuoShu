#!/bin/sh
set -u

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
LEGACY_REAL_XML=0
VARIABLE_SOURCE=0
CALLS="$TMP/calls"
: > "$CALLS"

CASE='setup'
fail() { printf 'FAIL [%s]: %s\n' "$CASE" "$*" >&2; exit 1; }
has() { grep -qx "$1" "$CALLS" || fail "expected call '$1'"; }
hasnt() { if grep -qx "$1" "$CALLS"; then fail "unexpected call '$1'"; fi; }
eq() { [ "$1" = "$2" ] || fail "expected '$2', got '$1'"; }
ok() { "$@" || fail "command failed: $*"; }

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
device_font_cache_schedule() { record schedule; return 0; }
_luoshu_config_weight_source() { printf '%s\n' "$TMP/source.ttf"; }
is_variable_font() { [ "$VARIABLE_SOURCE" = 1 ]; }
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

CASE='bridge/originos device hit'
ROM=originos
DEVICE_RC=0
: > "$CALLS"
ok apply_font_by_rom "$TMP/source.ttf" "$MODULE/system/fonts" quick Fixture
has originos
hasnt generic
has device
eq "$LUOSHU_DEVICE_PAYLOAD_RESULT" device
eq "$LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE" 0

CASE='bridge/flyme device hit'
ROM=flyme
DEVICE_RC=0
: > "$CALLS"
ok apply_font_by_rom "$TMP/source.ttf" "$MODULE/system/fonts" quick Fixture
has flyme
hasnt generic
has device

CASE='bridge/legacy xml unavailable'
ROM=originos
DEVICE_RC=2
LEGACY_RC=1
: > "$CALLS"
ok apply_font_by_rom "$TMP/source.ttf" "$MODULE/system/fonts" quick Fixture
has originos
has legacy
eq "$LUOSHU_DEVICE_PAYLOAD_RESULT" slot-only

CASE='bridge/hard install failure'
DEVICE_RC=1
LEGACY_RC=0
: > "$CALLS"
RC=0
apply_font_by_rom "$TMP/source.ttf" "$MODULE/system/fonts" quick Fixture || RC=$?
eq "$RC" 1
has device-clear
hasnt oem-clear

CASE='bridge/explicit disable'
ROM=flyme
LUOSHU_OEM_PRESERVE_ON_CONFIG_DISABLE=0
: > "$CALLS"
ok font_config_disable
has device-clear
has oem-clear
has flyme-restore
has dynamic-clear
has base-clear

CASE='bridge/quarantine'
printf 'active\n' > "$MODULE/config/active_font.conf"
printf '0\n' > "$MODULE/config/font-boot-failures"
: > "$CALLS"
ok luoshu_payload_quarantine
has oem-clear
has flyme-restore
has flyme-apply
has device-clear
eq "$(cat "$MODULE/config/active_font.conf")" default

# Production loads the policy last. Its real device-cache probe should return unsupported/cache-miss
# in this fixture, then the stubs below exercise foreground XML result handling.
. "$ROOT/common/device_font_payload_policy.sh"
_dfpp_xml_overlay_active() { [ "$LEGACY_REAL_XML" = 1 ]; }
ROM=originos
rm -f "$MODULE/config/device-font-engine.conf"
VARIABLE_SOURCE=0

CASE='policy/cache miss enables real xml'
LEGACY_RC=0
LEGACY_REAL_XML=1
: > "$CALLS"
ok font_config_enable_for_payload Fixture
has prepare
has legacy
hasnt schedule
hasnt base-clear
eq "$LUOSHU_DEVICE_PAYLOAD_RESULT" legacy

CASE='policy/false xml success still schedules cache'
LEGACY_RC=0
LEGACY_REAL_XML=0
: > "$CALLS"
ok font_config_enable_for_payload Fixture
has prepare
has legacy
has schedule
has base-clear
hasnt oem-clear
eq "$LUOSHU_DEVICE_PAYLOAD_RESULT" slot-only

CASE='policy/xml generation failure falls back'
LEGACY_RC=1
LEGACY_REAL_XML=0
: > "$CALLS"
ok font_config_enable_for_payload Fixture
has prepare
has legacy
has schedule
has base-clear
hasnt oem-clear
eq "$LUOSHU_DEVICE_PAYLOAD_RESULT" slot-only

CASE='policy/variable source defers background'
VARIABLE_SOURCE=1
LEGACY_RC=0
: > "$CALLS"
ok font_config_enable_for_payload Fixture
hasnt prepare
hasnt legacy
has schedule
eq "$LUOSHU_DEVICE_PAYLOAD_RESULT" slot-only
VARIABLE_SOURCE=0
LEGACY_RC=0

CASE='policy/coloros discovery cache'
_coloros_core_files() { printf '%s\n' 'Core-Regular.ttf Core-Medium.ttf'; }
_coloros_google_text_files() { printf '%s\n' 'GoogleSansText-Regular.ttf'; }
_coloros_vendor_files() { printf '%s\n' 'Vendor-Regular.ttf'; }
_coloros_oem_ui_files() { printf '%s\n' 'OplusSans-Regular.ttf'; }
_coloros_discovered_ui_files() { printf '%s\n' 'Discovered-Regular.ttf Core-Regular.ttf'; }
LUOSHU_COLOROS_CACHE_KEY=fixture-rom
export LUOSHU_COLOROS_CACHE_KEY
rm -f "$MODULE/config/coloros-font-targets.cache"
get_all_coloros_files > "$TMP/coloros-first"
ok grep -qx Core-Regular.ttf "$TMP/coloros-first"
ok grep -qx GoogleSansText-Regular.ttf "$TMP/coloros-first"
eq "$(grep -c '^Core-Regular.ttf$' "$TMP/coloros-first")" 1
_coloros_discovered_ui_files() { printf '%s\n' 'Should-Not-Appear.ttf'; }
get_all_coloros_files > "$TMP/coloros-second"
ok cmp "$TMP/coloros-first" "$TMP/coloros-second"
LUOSHU_COLOROS_TARGETS_MAPPED=1
export LUOSHU_COLOROS_TARGETS_MAPPED
eq "$(get_all_coloros_names)" ''
LUOSHU_COLOROS_TARGETS_MAPPED=0
export LUOSHU_COLOROS_TARGETS_MAPPED
get_all_coloros_names > "$TMP/coloros-names"
ok grep -qx Core-Regular "$TMP/coloros-names"

CASE='syntax'
ok sh -n "$ROOT/common/device_font_payload_bridge.sh"
ok sh -n "$ROOT/common/device_font_payload_policy.sh"
echo 'Device font payload OEM bridge tests passed.'
