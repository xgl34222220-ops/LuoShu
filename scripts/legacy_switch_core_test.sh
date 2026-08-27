#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ROUTER="$ROOT/common/font_manager.sh"
BACKEND="$ROOT/common/legacy_v14_4_switch.sh"
ROM="$ROOT/common/legacy_v14_4/rom_adapters.sh"
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

# 94% v4 pipeline components are forbidden from the actual legacy apply backend.
! grep -qE 'font_validate_fast_v4|device_font_template|device_font_slot|font_config_overlay|font_config_batch|device_font_payload_build' "$BACKEND"

# Once selected, all three boot stages keep the legacy payload immutable.
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
sh -n "$ROOT/service_v4.sh"
sh -n "$ROOT/post-fs-data-v4.sh"
sh -n "$ROOT/post-mount-v4.sh"

echo 'v14.4 compatibility switch core is isolated from the v4 94% pipeline.'
