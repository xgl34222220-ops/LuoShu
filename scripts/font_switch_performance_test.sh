#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

verify_body="$(awk '/^_verify_font_copy\(\)/,/^}/' "$ROOT/common/rom_adapters.sh")"
printf '%s\n' "$verify_body" | grep -q '_font_file_size_fast'
! printf '%s\n' "$verify_body" | grep -q 'wc -c'

payload_body="$(awk '/^luoshu_payload_validate_current\(\)/,/^}/' "$ROOT/common/font_safety.sh")"
! printf '%s\n' "$payload_body" | grep -q 'wc -c'
dynamic_body="$(awk '/^luoshu_dynamic_targets_apply\(\)/,/^}/' "$ROOT/common/font_safety.sh")"
! printf '%s\n' "$dynamic_body" | grep -q 'wc -c'

grep -q 'LUOSHU_SWITCH_TIMEOUT_SECONDS:-110' "$ROOT/common/font_switch_task.sh"
grep -q 'luoshu_start_detached' "$ROOT/common/font_switch_task.sh"
grep -q 'mark_load_verification_pending' "$ROOT/common/font_switch_task.sh"
grep -q 'luoshu_switch_perf_mark complete' "$ROOT/common/font_manager.sh"
grep -q 'top = if (style == UiStyle.MIUIX) 25.dp else 14.dp' \
    "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/logs/LogsRoute.kt"
grep -q 'mode in setOf("aligned", "mount-verified")' \
    "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/home/DeviceTrustUi.kt"

sh "$ROOT/scripts/font_switch_task_test.sh"
sh "$ROOT/scripts/device_font_trust_test.sh"
echo 'font_switch_performance_test: PASS'
