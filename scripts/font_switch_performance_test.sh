#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

verify_body="$(awk '/^_verify_font_copy\(\)/,/^}/' "$ROOT/common/rom_adapters.sh")"
printf '%s
' "$verify_body" | grep -q '_font_file_size_fast'
! printf '%s
' "$verify_body" | grep -q 'wc -c'

payload_body="$(awk '/^luoshu_payload_validate_current\(\)/,/^}/' "$ROOT/common/font_safety.sh")"
! printf '%s
' "$payload_body" | grep -q 'wc -c'
dynamic_body="$(awk '/^luoshu_dynamic_targets_apply\(\)/,/^}/' "$ROOT/common/font_safety.sh")"
! printf '%s
' "$dynamic_body" | grep -q 'wc -c'

grep -q 'LUOSHU_SWITCH_TIMEOUT_SECONDS:-45' "$ROOT/common/font_switch_task.sh"
grep -q 'luoshu_switch_perf_mark complete' "$ROOT/common/font_manager.sh"
echo 'font_switch_performance_test: PASS'
