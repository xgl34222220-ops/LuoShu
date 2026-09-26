#!/bin/sh
# This bridge contract runs real generated fonts through the real stock scanner
# and engine. Invalid metrics must fail instead of silently copying Regular.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python3 "$ROOT/scripts/coverage_inventory_integration_test.py"
sh -n "$ROOT/common/coverage_payload_remediate.sh"
sh -n "$ROOT/common/inventory_font_stage.sh"
sh -n "$ROOT/common/legacy_v14_4/font_switch_safe.sh"
sh -n "$ROOT/common/legacy_v14_4/mix_router.sh"
printf '%s\n' 'coverage_payload_remediate_test: PASS'
