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

grep -q 'LUOSHU_SWITCH_TIMEOUT_SECONDS:-360' "$ROOT/common/font_switch_task.sh"
grep -q 'luoshu_start_detached' "$ROOT/common/font_switch_task.sh"
grep -q 'mark_load_verification_pending' "$ROOT/common/font_switch_task.sh"
grep -q 'heartbeat=%s' "$ROOT/common/font_switch_task.sh"
grep -q 'timeout=%s' "$ROOT/common/font_switch_task.sh"
grep -q 'luoshu_switch_perf_mark complete' "$ROOT/common/font_manager.sh"
grep -q 'luoshu_font_lock_acquire' "$ROOT/common/font_manager.sh"
grep -q 'luoshu_switch_signal_exit 143' "$ROOT/common/font_manager.sh"
grep -q 'MiuixTaskCenterHeader(' \
    "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/logs/LogsScreenMiuix.kt"
grep -q 'DiagnosticExportButton(' \
    "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/logs/LogsScreenMiuix.kt"
grep -q 'horizontalArrangement = Arrangement.spacedBy(10.dp)' \
    "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/logs/LogsScreenMiuix.kt"
! grep -q 'top = if (style == UiStyle.MIUIX)' \
    "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/logs/LogsRoute.kt"
# Compact task-center header actions use the shared 48 dp / 22 dp icon system.
grep -q 'LuoShuHeaderAction(' \
    "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/logs/DiagnosticExportUi.kt"
grep -q 'HeaderContainer = 48.dp' \
    "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/theme/LuoShuIconSystem.kt"
grep -q 'HeaderGlyph = 22.dp' \
    "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/theme/LuoShuIconSystem.kt"
grep -q 'timeoutSeconds = 390' \
    "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt"
grep -q 'advertisedTimeout' \
    "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt"
grep -q 'DeviceTrustLevel.SYSTEM' \
    "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/home/DeviceTrustUi.kt"
grep -q 'DeviceTrustLevel.COMPATIBILITY' \
    "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/home/DeviceTrustUi.kt"
grep -q 'attempt < 9' \
    "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/home/HomeRoute.kt"
grep -q 'LUOSHU_BOOT_VERIFY_RETRY_LIMIT:-3' "$ROOT/common/device_font_boot_verify.sh"

sh "$ROOT/scripts/font_switch_task_test.sh"
sh "$ROOT/scripts/font_switch_lock_test.sh"
sh "$ROOT/scripts/device_font_trust_test.sh"
echo 'font_switch_performance_test: PASS'
