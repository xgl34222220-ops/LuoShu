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
grep -q 'START_LOCK=' "$ROOT/common/font_switch_task.sh"
grep -q 'start_lock_acquire' "$ROOT/common/font_switch_task.sh"
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
# All routed header actions keep an accessible touch target while their visible surface stays quiet.
grep -q 'LuoShuHeaderAction(' \
    "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/logs/DiagnosticExportUi.kt"
grep -q 'HeaderTouchTarget = 48.dp' \
    "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/theme/LuoShuIconSystem.kt"
grep -q 'HeaderContainer = 40.dp' \
    "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/theme/LuoShuIconSystem.kt"
grep -q 'HeaderGlyph = 21.dp' \
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

# A direct switch calls the final stock-aligned builder exactly once. Cache lookup/build/activation
# may happen inside that single foreground call, but the policy wrapper must never run a second
# provisional path or schedule a post-commit mutation.
_fsp_tmp="$(mktemp -d)"
(
    export MODULE_DIR="$_fsp_tmp/module" MODDIR="$_fsp_tmp/module"
    mkdir -p "$MODULE_DIR/config" "$MODULE_DIR/logs"
    . "$ROOT/common/device_font_payload_policy.sh"
    set -eu
    device_font_payload_build_install() {
        printf 'x\n' >> "$_fsp_tmp/final-builder-calls"
        return 0
    }
    font_config_prepare_payload_weights() { : > "$_fsp_tmp/heavy-weights"; return 0; }
    font_config_generate() { : > "$_fsp_tmp/heavy-xml"; return 0; }
    font_config_disable() { : > "$_fsp_tmp/heavy-disable"; return 0; }
    IS_COLOROS=false
    LUOSHU_FOREGROUND_QUICK_SWITCH=1
    export IS_COLOROS LUOSHU_FOREGROUND_QUICK_SWITCH
    font_config_enable_for_payload FastFixture || exit 1
    test "$LUOSHU_DEVICE_PAYLOAD_RESULT" = device
    test "$(wc -l < "$_fsp_tmp/final-builder-calls" | tr -d '[:space:]')" -eq 1
    test ! -e "$_fsp_tmp/heavy-weights"
    test ! -e "$_fsp_tmp/heavy-xml"
    test ! -e "$_fsp_tmp/heavy-disable"
)
rm -rf "$_fsp_tmp"

# The ROM adapter stages anchors only; font_manager owns the one final builder invocation.
quick_body="$(awk '/^apply_font_by_rom\(\)/,/^}/' "$ROOT/common/device_font_payload_policy.sh")"
! printf '%s\n' "$quick_body" | grep -q 'font_config_enable_for_payload'
manager_switch_body="$(awk '/^switch_font\(\)/,/^}/' "$ROOT/common/font_manager.sh")"
test "$(printf '%s\n' "$manager_switch_body" | grep -c 'font_config_enable_for_payload')" -eq 2

# The final source-order manifest builder must checksum one inode once even when HyperOS exposes
# it through dozens of hard-link aliases. This is the difference between seconds and minutes.
_fsp_tmp="$(mktemp -d)"
(
    export MODULE_DIR="$_fsp_tmp/module" MODDIR="$_fsp_tmp/module"
    mkdir -p "$MODULE_DIR/config" "$MODULE_DIR/.luoshu-payload/system/fonts"
    . "$ROOT/common/font_safety.sh"
    . "$ROOT/common/font_runtime_policy.sh"
    _lfrp_partitions() { printf '%s\n' system; }
    dd if=/dev/zero of="$MODULE_DIR/.luoshu-payload/system/fonts/regular.font" bs=2048 count=1 2>/dev/null
    for _fsp_name in MiSansVF.ttf MiSansLatinVF.ttf Roboto-Regular.ttf GoogleSans-Regular.ttf \
        100.ttf 200.ttf 300.ttf 400.ttf 500.ttf 600.ttf 700.ttf 800.ttf 900.ttf MitypeMonoVF.ttf; do
        ln "$MODULE_DIR/.luoshu-payload/system/fonts/regular.font" \
           "$MODULE_DIR/.luoshu-payload/system/fonts/$_fsp_name"
    done
    _luoshu_checksum_original="$(command -v cksum)"
    _luoshu_checksum() {
        printf 'x\n' >> "$_fsp_tmp/checksum-calls"
        "$_luoshu_checksum_original" "$1" | awk '{print $1 "|" $2}'
    }
    luoshu_payload_build_manifest
    test "$(wc -l < "$_fsp_tmp/checksum-calls" | tr -d '[:space:]')" -eq 1
    test "$(wc -l < "$MODULE_DIR/config/font-payload-manifest.conf" | tr -d '[:space:]')" -eq 15
)
rm -rf "$_fsp_tmp"
echo 'font_switch_performance_test: PASS'
