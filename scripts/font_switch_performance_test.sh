#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

verify_body="$(awk '/^_verify_font_copy\(\)/,/^}/' "$ROOT/common/rom_adapters.sh")"
printf '%s\n' "$verify_body" | grep -q '_font_file_size_fast'
! printf '%s\n' "$verify_body" | grep -q 'wc -c'

legacy_verify_body="$(awk '/^_verify_font_copy\(\)/,/^}/' "$ROOT/common/legacy_v14_4/rom_adapters.sh")"
printf '%s\n' "$legacy_verify_body" | grep -q 'stat -c %s'
! printf '%s\n' "$legacy_verify_body" | grep -q 'wc -c'

legacy_hyperos_body="$(awk '/^copy_as_hyperos\(\)/,/^}/' "$ROOT/common/legacy_v14_4/rom_adapters.sh")"
printf '%s\n' "$legacy_hyperos_body" | grep -q 'if \[ "$mode" = quick \]'
printf '%s\n' "$legacy_hyperos_body" | grep -q '仅暂存 donor'

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

# Startup/refresh and task submission must remain non-blocking.
_start_body="$(awk '/^start_task\(\)/,/^}/' "$ROOT/common/font_switch_task.sh")"
! printf '%s\n' "$_start_body" | grep -q 'write_task .* running '
grep -q 'switch_reconcile' "$ROOT/common/app_bridge.sh"
grep -q 'Home status/refresh is a pure persisted-state read' "$ROOT/common/app_bridge.sh"
_status_select="$(awk '/^select_task_file\(\)/,/^}/' "$ROOT/common/app_bridge.sh")"
! printf '%s\n' "$_status_select" | grep -q ' sh .*reconcile'
_status_body="$(awk '/^status_json\(\)/,/^}/' "$ROOT/common/app_bridge.sh")"
! printf '%s\n' "$_status_body" | grep -q 'luoshu_text_reboot_reconcile'
grep -q 'runningSwitchTask' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt"
grep -q 'ensureMixConfig' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt"
grep -q 'ensureSystemWeight' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/Alpha15FeatureViewModel.kt"
grep -q 'loading = fontLoading,' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryContract.kt"
grep -q 'loading = (fontLoading && fonts.isEmpty()) || current.loading' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/FontStudioContract.kt"
grep -q 'adoptRunningSwitch' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt"
grep -q 'timeoutMs = 8_000L' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt"
grep -q 'kill -0 "$_lfla_pid"' "$ROOT/common/font_switch_lock.sh"
! grep -q 'if (parsed.installed) requestFontPrewarm()' \
    "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt"
! grep -q 'if (snapshot.installed) requestFontPrewarm()' \
    "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt"
! grep -q 'validate .*fontId' \
    "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt"
_unit_effect="$(awk '/LaunchedEffect\(Unit\)/,/^    }/' \
    "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuAppShell.kt")"
! printf '%s\n' "$_unit_effect" | grep -q 'refreshSystemWeight'

# The full v4 manager is preserved behind the router for inventory and regression coverage.
# Its performance markers remain pinned here, but final App apply no longer enters this body.
grep -q 'luoshu_switch_perf_mark complete' "$ROOT/common/font_manager_v4.sh"
grep -q 'LUOSHU_FOREGROUND_QUICK_SWITCH=1' "$ROOT/common/font_manager_v4.sh"
grep -q 'luoshu_font_lock_acquire' "$ROOT/common/font_manager_v4.sh"
grep -q 'luoshu_switch_signal_exit 143' "$ROOT/common/font_manager_v4.sh"

# HyperOS glyph-baseline correction must be donor-scoped, not alias-scoped.
# One large CJK font rewrite per physical slot regresses real-device switching into minutes.
grep -q 'canonical_baseline_target = _canonical_baseline_target' "$ROOT/common/hyperos_metrics_batch.py"
grep -q 'source_baselines\[profile_key\]' "$ROOT/common/hyperos_metrics_batch.py"
grep -q 'Baseline normalization is the only operation that rewrites' "$ROOT/common/hyperos_metrics_batch.py"
grep -q 'test_baseline_outline_rewrite_runs_once_per_shared_donor' "$ROOT/scripts/hyperos_metrics_batch_test.py"
grep -q 'persistent_baseline_source' "$ROOT/common/hyperos_metrics_batch.py"
grep -q 'cache/hyperos-baseline' "$ROOT/common/hyperos_metrics_batch.py"
grep -q 'test_baseline_donor_cache_survives_repeated_switches' "$ROOT/scripts/hyperos_metrics_batch_test.py"
grep -q 'cache/hyperos-slots' "$ROOT/common/hyperos_metrics_batch.py"
grep -q 'test_final_slot_cache_skips_fonttools_rewrite_on_reapply' "$ROOT/scripts/hyperos_metrics_batch_test.py"
grep -q 'luoshu_font_validation_cache_restore' "$ROOT/common/legacy_v14_4/font_switch_safe.sh"

# HyperOS 4 must follow the scanned ROM UI graph instead of processing every
# filename that happens to live under */fonts. This is both the OS4 coverage
# contract and the primary switch-speed guard for devices exposing 100+ files.
grep -q -- '--inventory-ui' "$ROOT/common/hyperos_stage_complete.sh"
grep -q '_inventory_targets' "$ROOT/common/hyperos_metrics_batch.py"
grep -q '.luoshu-hyperos-targets.list' "$ROOT/common/hyperos_metrics_batch.py"
grep -q '.luoshu-hyperos-targets.list' "$ROOT/common/legacy_v14_4/hyperos_clock_compat.sh"
grep -q 'HYPEROS_COVERAGE_REVISION = 5' "$ROOT/common/font_inventory_scan_v3.py"
grep -q 'LANGUAGE_FALLBACK_TOKENS' "$ROOT/common/hyperos_metrics_batch.py"

# Safe next-boot staging must never recursively delete large payload trees while
# the foreground switch holds its lock. Rename first; reclaim after the transaction.
_safe_switch="$ROOT/common/legacy_v14_4/font_switch_safe.sh"
grep -q 'retire_for_gc' "$_safe_switch"
grep -q 'finalize_next_payload_commit' "$_safe_switch"
_prepare_body="$(awk '/^prepare_next_payload\(\)/,/^}/' "$_safe_switch")"
! printf '%s\n' "$_prepare_body" | grep -q 'rm -rf.*NEXT_PAYLOAD'
grep -q 'action:list|list:\*|action:current|current:\*' "$ROOT/common/font_manager_v4.sh"

# Final apply is intentionally the v14.4 physical-file path. Keep the modern identity lock,
# but never reconnect the device-template/slot/XML payload pipeline that caused the 94% stall.
grep -q 'legacy_v14_4_switch.sh' "$ROOT/common/font_manager.sh"
grep -q 'legacy_lock_acquire' "$ROOT/common/legacy_v14_4_switch.sh"
! grep -qE 'font_validate_fast_v4|device_font_template|device_font_slot|font_config_overlay|device_font_payload_build' \
    "$ROOT/common/legacy_v14_4_switch.sh"

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
grep -q 'HeaderContainer = 44.dp' \
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

# A direct v4 switch calls the final stock-aligned builder exactly once. Cache lookup/build/activation
# may happen inside that single preserved foreground call, but the policy wrapper must never run a
# second provisional path or schedule a post-commit mutation.
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

# The ROM adapter stages anchors only; the preserved v4 manager owns one final builder invocation.
quick_body="$(awk '/^apply_font_by_rom\(\)/,/^}/' "$ROOT/common/device_font_payload_policy.sh")"
! printf '%s\n' "$quick_body" | grep -q 'font_config_enable_for_payload'
manager_switch_body="$(awk '/^switch_font\(\)/,/^}/' "$ROOT/common/font_manager_v4.sh")"
test "$(printf '%s\n' "$manager_switch_body" | grep -c 'font_config_enable_for_payload')" -eq 2

# The final source-order manifest builder must checksum one inode once even when HyperOS exposes
# it through dozens of hard-link aliases. This remains a regression guard for the preserved v4
# engine and update/migration paths even though explicit final apply uses v14.4 aliases.
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
