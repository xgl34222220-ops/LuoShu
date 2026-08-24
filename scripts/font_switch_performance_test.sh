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
grep -q 'LUOSHU_FOREGROUND_QUICK_SWITCH=1' "$ROOT/common/font_manager.sh"
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
# All routed header actions share a compact visual container and keep a 48 dp touch target.
grep -q 'LuoShuHeaderAction(' \
    "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/logs/DiagnosticExportUi.kt"
grep -q 'HeaderTouchTarget = 48.dp' \
    "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/theme/LuoShuIconSystem.kt"
grep -q 'HeaderContainer = 36.dp' \
    "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/theme/LuoShuIconSystem.kt"
grep -q 'HeaderGlyph = 18.dp' \
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

# A direct switch cache miss must only schedule the background enhancement. It must never enter
# XML discovery, nine-weight preparation or another Python-backed foreground generator.
_fsp_tmp="$(mktemp -d)"
(
    export MODULE_DIR="$_fsp_tmp/module" MODDIR="$_fsp_tmp/module"
    mkdir -p "$MODULE_DIR/config" "$MODULE_DIR/logs"
    . "$ROOT/common/device_font_payload_policy.sh"
    set -eu
    device_font_payload_build_install() { return 2; }
    font_config_prepare_payload_weights() { : > "$_fsp_tmp/heavy-weights"; return 0; }
    font_config_generate() { : > "$_fsp_tmp/heavy-xml"; return 0; }
    font_config_disable() { : > "$_fsp_tmp/heavy-disable"; return 0; }
    device_font_cache_schedule() { printf '%s\n' "$1" > "$_fsp_tmp/scheduled"; return 0; }
    IS_COLOROS=false
    LUOSHU_FOREGROUND_QUICK_SWITCH=1
    export IS_COLOROS LUOSHU_FOREGROUND_QUICK_SWITCH
    font_config_enable_for_payload FastFixture || exit 1
    test "$LUOSHU_DEVICE_PAYLOAD_RESULT" = slot-only
    grep -qx FastFixture "$_fsp_tmp/scheduled"
    test ! -e "$_fsp_tmp/heavy-weights"
    test ! -e "$_fsp_tmp/heavy-xml"
    test ! -e "$_fsp_tmp/heavy-disable"
)
rm -rf "$_fsp_tmp"
echo 'font_switch_performance_test: PASS'
