#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one match, found {count}: {old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# 1. Import FAB: keep the full label visible and anchor the overlay inside the screen width.
replace_once(
    "android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportOverlay.kt",
    """    Row(\n        modifier = modifier,\n        horizontalArrangement = Arrangement.spacedBy(10.dp),\n        verticalAlignment = Alignment.CenterVertically,\n    ) {\n        FontMetadataInspector(\n            viewModel = viewModel,\n            style = style,\n        )\n        ImportActionButton(\n""",
    """    Row(\n        modifier = modifier.fillMaxWidth(),\n        horizontalArrangement = Arrangement.End,\n        verticalAlignment = Alignment.CenterVertically,\n    ) {\n        FontMetadataInspector(\n            viewModel = viewModel,\n            style = style,\n        )\n        Spacer(Modifier.width(10.dp))\n        ImportActionButton(\n""",
)
replace_once(
    "android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportOverlay.kt",
    """        taskVisible -> 166.dp\n        else -> 132.dp\n""",
    """        taskVisible -> 180.dp\n        else -> 148.dp\n""",
)
replace_once(
    "android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportOverlay.kt",
    """                modifier = Modifier.padding(horizontal = 17.dp, vertical = if (taskVisible) 10.dp else 12.dp),\n""",
    """                modifier = Modifier.padding(horizontal = 14.dp, vertical = if (taskVisible) 10.dp else 12.dp),\n""",
)
replace_once(
    "android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportOverlay.kt",
    """                        color = textColor,\n                        fontWeight = FontWeight.Black,\n                    )\n""",
    """                        color = textColor,\n                        fontWeight = FontWeight.Black,\n                        fontSize = 15.sp,\n                        maxLines = 1,\n                        softWrap = false,\n                    )\n""",
)

# 2. Composite builder reserves the last 20% for payload generation, validation and mount sync.
progress_replacements = {
    '_progress(args.progress, "load-cjk", "正在读取中文基底", 5)': '_progress(args.progress, "load-cjk", "正在读取中文基底", 4)',
    '_progress(args.progress, "latin", "正在导入英文字形", 20)': '_progress(args.progress, "latin", "正在导入英文字形", 18)',
    '_progress(args.progress, "digit", "正在导入数字字形", 52)': '_progress(args.progress, "digit", "正在导入数字字形", 42)',
    '_progress(args.progress, "save", "正在写入完整复合字体", 68)': '_progress(args.progress, "save", "正在写入完整复合字体", 60)',
    '_progress(args.progress, "validate", "正在验证复合字体", 90)': '_progress(args.progress, "validate", "正在验证复合字体", 74)',
    '_progress(args.progress, "done", "完整复合字体已生成", 100)': '_progress(args.progress, "done", "完整复合字体已生成", 80)',
}
for old, new in progress_replacements.items():
    replace_once("common/composite_font.py", old, new)

# 3. Build new font payloads from an empty stage instead of copying and deleting the old payload first.
replace_once(
    "common/font_mix.sh",
    """    mkdir -p \"$PAYLOAD_STAGE\" 2>/dev/null || return 1\n    if [ -d \"$SYSTEM_FONTS_DIR\" ]; then\n        cp -af \"$SYSTEM_FONTS_DIR/.\" \"$PAYLOAD_STAGE/\" 2>/dev/null || \\\n            cp -rfp \"$SYSTEM_FONTS_DIR/.\" \"$PAYLOAD_STAGE/\" 2>/dev/null || return 1\n    fi\n    clear_text_targets_in_dir \"$PAYLOAD_STAGE\"\n    return 0\n""",
    """    # The active payload is already protected by the transaction snapshot and by PAYLOAD_BACKUP.\n    # Starting from an empty directory avoids copying dozens of large hard-linked aliases only to\n    # delete them immediately before generating the replacement payload.\n    mkdir -p \"$PAYLOAD_STAGE\" 2>/dev/null || return 1\n    return 0\n""",
)
replace_once(
    "common/font_mix.sh",
    """write_progress() {\n    _stage=\"$1\"; _message=\"$2\"; _percent=\"$3\"; _progress=\"$CONFIG_DIR/composite_progress.json\"\n    _tmp=\"$_progress.$$\"\n    printf '{\"stage\":\"%s\",\"message\":\"%s\",\"percent\":%s,\"time\":%s}\\n' \\\n        \"$(json_escape \"$_stage\")\" \"$(json_escape \"$_message\")\" \"$_percent\" \"$(date +%s)\" > \"$_tmp\" 2>/dev/null && mv -f \"$_tmp\" \"$_progress\" 2>/dev/null\n}\n""",
    """write_progress() {\n    _stage=\"$1\"; _message=\"$2\"; _percent=\"$3\"; _progress=\"$CONFIG_DIR/composite_progress.json\"\n    _tmp=\"$_progress.$$\"\n    printf '{\"stage\":\"%s\",\"message\":\"%s\",\"percent\":%s,\"time\":%s}\\n' \\\n        \"$(json_escape \"$_stage\")\" \"$(json_escape \"$_message\")\" \"$_percent\" \"$(date +%s)\" > \"$_tmp\" 2>/dev/null && mv -f \"$_tmp\" \"$_progress\" 2>/dev/null\n}\n\nmix_stage() {\n    write_progress \"$1\" \"$2\" \"$3\"\n    printf '[%s] mix stage=%s percent=%s message=%s\\n' \\\n        \"$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)\" \"$1\" \"$3\" \"$2\" >> \"$LOG_FILE\" 2>/dev/null || true\n}\n""",
)
replace_once(
    "common/font_mix.sh",
    """        write_progress cache '已验证并使用现有复合字体缓存' 100\n""",
    """        write_progress cache '已验证并使用现有复合字体缓存' 80\n""",
)
replace_once(
    "common/font_mix.sh",
    """        write_progress done '复合字体已生成并通过验证' 100\n""",
    """        write_progress done '复合字体已生成并通过验证' 80\n""",
)
replace_once(
    "common/font_mix.sh",
    """    [ -n \"$_cjk\" ] && [ -n \"$_latin\" ] && [ -n \"$_digit\" ] || { set_mix_error '组合配置不完整'; return 1; }\n    recover_interrupted_payload\n""",
    """    [ -n \"$_cjk\" ] && [ -n \"$_latin\" ] && [ -n \"$_digit\" ] || { set_mix_error '组合配置不完整'; return 1; }\n    mix_stage initialize '正在初始化字体组合任务' 1\n    recover_interrupted_payload\n""",
)
replace_once(
    "common/font_mix.sh",
    """    if ! type luoshu_payload_transaction_begin >/dev/null 2>&1 || ! luoshu_payload_transaction_begin; then\n        set_mix_error '无法创建字体负载安全快照'\n        return 4\n    fi\n\n    _cjk_src=$(find_family_file \"$_cjk\")\n""",
    """    mix_stage snapshot '正在创建字体负载回滚点' 3\n    if ! type luoshu_payload_transaction_begin >/dev/null 2>&1 || ! luoshu_payload_transaction_begin; then\n        set_mix_error '无法创建字体负载安全快照'\n        return 4\n    fi\n\n    _cjk_src=$(find_family_file \"$_cjk\")\n""",
)
replace_once(
    "common/font_mix.sh",
    """    build_composite_file \"$_cjk_src\" \"$_latin_src\" \"$_digit_src\" || return 5\n    payload_stage_begin || { set_mix_error '无法创建字体负载暂存区'; return 5; }\n""",
    """    build_composite_file \"$_cjk_src\" \"$_latin_src\" \"$_digit_src\" || return 5\n    mix_stage payload '复合字形已完成，正在生成 ROM 字体负载' 82\n    payload_stage_begin || { set_mix_error '无法创建字体负载暂存区'; return 5; }\n""",
)
replace_once(
    "common/font_mix.sh",
    """    prepare_mix_config \"$_cjk\" \"$_latin\" \"$_digit\" || { set_mix_error '无法准备字体组合状态'; return 6; }\n    payload_stage_activate || { set_mix_error '无法原子替换字体负载'; return 6; }\n""",
    """    mix_stage activate '正在准备原子替换字体负载' 87\n    prepare_mix_config \"$_cjk\" \"$_latin\" \"$_digit\" || { set_mix_error '无法准备字体组合状态'; return 6; }\n    payload_stage_activate || { set_mix_error '无法原子替换字体负载'; return 6; }\n""",
)
replace_once(
    "common/font_mix.sh",
    """    if type font_config_enable_for_payload >/dev/null 2>&1; then\n        if font_config_enable_for_payload mix; then\n""",
    """    mix_stage mapping '正在生成系统字体映射' 91\n    if type font_config_enable_for_payload >/dev/null 2>&1; then\n        if font_config_enable_for_payload mix; then\n""",
)
replace_once(
    "common/font_mix.sh",
    """    if ! type luoshu_payload_validate_current >/dev/null 2>&1 || ! luoshu_payload_validate_current mix; then\n        set_mix_error '复合字体负载覆盖校验失败，已恢复旧字体'\n        return 7\n    fi\n    if type luoshu_sync_mount_payload >/dev/null 2>&1 && ! luoshu_sync_mount_payload; then\n""",
    """    mix_stage validate '正在校验完整字体负载' 94\n    if ! type luoshu_payload_validate_current >/dev/null 2>&1 || ! luoshu_payload_validate_current mix; then\n        set_mix_error '复合字体负载覆盖校验失败，已恢复旧字体'\n        return 7\n    fi\n    mix_stage mount-sync '正在同步元模块字体负载' 96\n    if type luoshu_sync_mount_payload >/dev/null 2>&1 && ! luoshu_sync_mount_payload; then\n""",
)
replace_once(
    "common/font_mix.sh",
    """    if ! luoshu_payload_transaction_commit mix; then\n        set_mix_error '无法提交复合字体负载事务，已恢复旧字体'\n        return 7\n    fi\n    rm -f \"$LOCK_FILE\" 2>/dev/null || true\n""",
    """    mix_stage manifest '正在生成安全启动清单' 98\n    if ! luoshu_payload_transaction_commit mix; then\n        set_mix_error '无法提交复合字体负载事务，已恢复旧字体'\n        return 7\n    fi\n    mix_stage complete '完整复合字体负载已准备完成' 100\n    rm -f \"$LOCK_FILE\" 2>/dev/null || true\n""",
)

# 4. Surface the real finalization stage and fail quickly when the inner worker has died.
replace_once(
    "common/v142_weighted_mix.sh",
    """            if [ -s \"$PROGRESS_FILE\" ]; then\n                _base_percent=$(sed -n 's/^.*\"percent\":\\([0-9][0-9]*\\).*$/\\1/p' \"$PROGRESS_FILE\" 2>/dev/null | head -n1)\n            fi\n""",
    """            _progress_message=''\n            if [ -s \"$PROGRESS_FILE\" ]; then\n                _base_percent=$(sed -n 's/^.*\"percent\":\\([0-9][0-9]*\\).*$/\\1/p' \"$PROGRESS_FILE\" 2>/dev/null | head -n1)\n                _progress_message=$(sed -n 's/^.*\"message\":\"\\([^\"]*\\)\".*$/\\1/p' \"$PROGRESS_FILE\" 2>/dev/null | head -n1)\n            fi\n""",
)
replace_once(
    "common/v142_weighted_mix.sh",
    """            [ -n \"$_base_message\" ] || _base_message='完整复合字体正在后台生成'\n            case \"$_base_state\" in\n""",
    """            [ -z \"$_progress_message\" ] || _base_message=\"$_progress_message\"\n            [ -n \"$_base_message\" ] || _base_message='完整复合字体正在后台生成'\n            if [ \"$_base_state\" = running ] && [ \"$_loops\" -ge 3 ]; then\n                _inner_pid=$(cat \"$CONFIG_DIR/mix_worker.pid\" 2>/dev/null)\n                if [ -z \"$_inner_pid\" ] || ! kill -0 \"$_inner_pid\" 2>/dev/null; then\n                    _dead_message=$(tail -n1 \"$CONFIG_DIR/mix_last_error.txt\" 2>/dev/null | tr -d '\\r')\n                    [ -n \"$_dead_message\" ] || _dead_message='完整复合字体后台进程已退出，请查看日志'\n                    update_task \"$_wanted\" failed \"$_dead_message\" 100 \"$_child\" \"$(date +%s)\"\n                    rm -rf \"$_root\"; luoshu_clear_task_pid \"$WORKER_PID\" \"$_wanted\"; exit 1\n                fi\n            fi\n            case \"$_base_state\" in\n""",
)

# 5. Reuse checksums for hard-linked aliases and avoid validating the same payload twice.
replace_once(
    "common/font_safety.sh",
    """_luoshu_filesize() {\n    _lfs_file=\"$1\"\n    if command -v stat >/dev/null 2>&1; then\n        stat -c '%s' \"$_lfs_file\" 2>/dev/null && return 0\n    fi\n    if command -v toybox >/dev/null 2>&1; then\n        toybox stat -c '%s' \"$_lfs_file\" 2>/dev/null && return 0\n    fi\n    wc -c < \"$_lfs_file\" 2>/dev/null | tr -d '[:space:]'\n}\n""",
    """_luoshu_filesize() {\n    _lfs_file=\"$1\"\n    if command -v stat >/dev/null 2>&1; then\n        stat -c '%s' \"$_lfs_file\" 2>/dev/null && return 0\n    fi\n    if command -v toybox >/dev/null 2>&1; then\n        toybox stat -c '%s' \"$_lfs_file\" 2>/dev/null && return 0\n    fi\n    wc -c < \"$_lfs_file\" 2>/dev/null | tr -d '[:space:]'\n}\n\n_luoshu_file_identity() {\n    _lfi_file=\"$1\"\n    if command -v stat >/dev/null 2>&1; then\n        stat -c '%d:%i:%s:%Y:%Z' \"$_lfi_file\" 2>/dev/null && return 0\n    fi\n    if command -v toybox >/dev/null 2>&1; then\n        toybox stat -c '%d:%i:%s:%Y:%Z' \"$_lfi_file\" 2>/dev/null && return 0\n    fi\n    printf 'path:%s:%s\\n' \"$_lfi_file\" \"$(_luoshu_filesize \"$_lfi_file\")\"\n}\n\n_luoshu_cached_checksum() {\n    _lcc_file=\"$1\"\n    _lcc_cache=\"$2\"\n    _lcc_identity=$(_luoshu_file_identity \"$_lcc_file\")\n    _lcc_value=$(awk -F'|' -v key=\"$_lcc_identity\" '$1 == key { print $2 \"|\" $3; exit }' \"$_lcc_cache\" 2>/dev/null)\n    if [ -z \"$_lcc_value\" ]; then\n        _lcc_value=$(_luoshu_checksum \"$_lcc_file\")\n        [ -n \"$_lcc_value\" ] || return 1\n        printf '%s|%s\\n' \"$_lcc_identity\" \"$_lcc_value\" >> \"$_lcc_cache\" 2>/dev/null || true\n    fi\n    printf '%s\\n' \"$_lcc_value\"\n}\n""",
)
replace_once(
    "common/font_safety.sh",
    """    _lpm_tmp=\"$_lpm_config/font-payload-manifest.conf.tmp.$$\"\n    : > \"$_lpm_tmp\" 2>/dev/null || return 1\n""",
    """    _lpm_tmp=\"$_lpm_config/font-payload-manifest.conf.tmp.$$\"\n    _lpm_checksum_cache=\"$_lpm_config/.font-payload-checksums.$$\"\n    : > \"$_lpm_tmp\" 2>/dev/null || return 1\n    : > \"$_lpm_checksum_cache\" 2>/dev/null || { rm -f \"$_lpm_tmp\"; return 1; }\n""",
)
replace_once(
    "common/font_safety.sh",
    """                _lpm_sum=$(_luoshu_checksum \"$_lpm_file\")\n""",
    """                _lpm_sum=$(_luoshu_cached_checksum \"$_lpm_file\" \"$_lpm_checksum_cache\")\n""",
)
# The XML checksum line is the second identical occurrence after the first replacement.
replace_once(
    "common/font_safety.sh",
    """                _lpm_sum=$(_luoshu_checksum \"$_lpm_file\")\n""",
    """                _lpm_sum=$(_luoshu_cached_checksum \"$_lpm_file\" \"$_lpm_checksum_cache\")\n""",
)
replace_once(
    "common/font_safety.sh",
    """    [ -s \"$_lpm_tmp\" ] || { rm -f \"$_lpm_tmp\" 2>/dev/null; return 1; }\n    mv -f \"$_lpm_tmp\" \"$_lpm_config/font-payload-manifest.conf\" 2>/dev/null || return 1\n""",
    """    rm -f \"$_lpm_checksum_cache\" 2>/dev/null || true\n    [ -s \"$_lpm_tmp\" ] || { rm -f \"$_lpm_tmp\" 2>/dev/null; return 1; }\n    mv -f \"$_lpm_tmp\" \"$_lpm_config/font-payload-manifest.conf\" 2>/dev/null || return 1\n""",
)
replace_once(
    "common/font_safety.sh",
    """LUOSHU_PAYLOAD_TXN=''\nluoshu_payload_transaction_begin() {\n    [ -z \"$LUOSHU_PAYLOAD_TXN\" ] || return 1\n""",
    """LUOSHU_PAYLOAD_TXN=''\nLUOSHU_PAYLOAD_VALIDATED_ACTIVE=''\nluoshu_payload_transaction_begin() {\n    [ -z \"$LUOSHU_PAYLOAD_TXN\" ] || return 1\n    LUOSHU_PAYLOAD_VALIDATED_ACTIVE=''\n""",
)
replace_once(
    "common/font_safety.sh",
    """    done <<EOF_LUOSHU_VALIDATE\n$(_luoshu_font_config_specs)\nEOF_LUOSHU_VALIDATE\n    return 0\n}\n""",
    """    done <<EOF_LUOSHU_VALIDATE\n$(_luoshu_font_config_specs)\nEOF_LUOSHU_VALIDATE\n    LUOSHU_PAYLOAD_VALIDATED_ACTIVE=\"$_lpv_active\"\n    return 0\n}\n""",
)
replace_once(
    "common/font_safety.sh",
    """    if [ \"$_lptc_active\" != default ]; then\n        luoshu_payload_validate_current \"$_lptc_active\" || return 1\n    fi\n""",
    """    if [ \"$_lptc_active\" != default ] && [ \"${LUOSHU_PAYLOAD_VALIDATED_ACTIVE:-}\" != \"$_lptc_active\" ]; then\n        luoshu_payload_validate_current \"$_lptc_active\" || return 1\n    fi\n""",
)

# 6. Keep immutable composite caches across test-module updates.
replace_once(
    "common/module_update_state.sh",
    """    cp -af \"$_source/.\" \"$_destination/\" 2>/dev/null || \\\n        cp -rfp \"$_source/.\" \"$_destination/\" 2>/dev/null\n}\n""",
    """    cp -al \"$_source/.\" \"$_destination/\" 2>/dev/null || \\\n        cp -af \"$_source/.\" \"$_destination/\" 2>/dev/null || \\\n        cp -rfp \"$_source/.\" \"$_destination/\" 2>/dev/null\n}\n""",
)
replace_once(
    "common/module_update_state.sh",
    """luoshu_migrate_active_install() {\n""",
    """luoshu_migrate_update_cache() {\n    _old=\"$1\"\n    _new=\"$2\"\n    for _relative in \\\n        cache/full-composite-v5 \\\n        cache/auto-multiweight-mix/composites-v2 \\\n        cache/auto-multiweight-mix/prepared-v2 \\\n        cache/auto-multiweight-mix/source-meta-v1; do\n        [ -d \"$_old/$_relative\" ] || continue\n        rm -rf \"$_new/$_relative\" 2>/dev/null || true\n        mkdir -p \"${_new}/${_relative%/*}\" 2>/dev/null || continue\n        luoshu_copy_update_tree \"$_old/$_relative\" \"$_new/$_relative\" || true\n    done\n    mkdir -p \"$_new/cache\" 2>/dev/null || true\n    for _probe in \"$_old/cache\"/runtime_probe.*.ok; do\n        [ -f \"$_probe\" ] || continue\n        cp -al \"$_probe\" \"$_new/cache/${_probe##*/}\" 2>/dev/null || \\\n            cp -af \"$_probe\" \"$_new/cache/${_probe##*/}\" 2>/dev/null || true\n    done\n}\n\nluoshu_migrate_active_install() {\n""",
)
replace_once(
    "common/module_update_state.sh",
    """    [ -s \"$_new/config/active_font.conf\" ] || printf '%s\\n' \"$_active\" >\"$_new/config/active_font.conf\"\n    luoshu_clear_update_volatile \"$_new\"\n""",
    """    luoshu_migrate_update_cache \"$_old\" \"$_new\"\n    [ -s \"$_new/config/active_font.conf\" ] || printf '%s\\n' \"$_active\" >\"$_new/config/active_font.conf\"\n    luoshu_clear_update_volatile \"$_new\"\n""",
)

# 7. Regression coverage for cache reuse, truthful final stages and the complete import label.
perf_test = ROOT / "scripts/mix_finalize_performance_test.sh"
perf_test.write_text(
    r'''#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-mix-finalize)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

# Hard-linked aliases must be checksummed once, not once per path.
MODULE="$TMP/module"
mkdir -p "$MODULE/common" "$MODULE/config" "$MODULE/system/fonts" "$TMP/bin"
cp "$ROOT/common/font_safety.sh" "$MODULE/common/font_safety.sh"
printf 'font payload\n' > "$MODULE/system/fonts/LuoShu-400.ttf"
# Make the test file large enough for payload validation and add aliases to the same inode.
dd if=/dev/zero bs=1024 count=4 >> "$MODULE/system/fonts/LuoShu-400.ttf" 2>/dev/null
ln "$MODULE/system/fonts/LuoShu-400.ttf" "$MODULE/system/fonts/Roboto-Regular.ttf"
ln "$MODULE/system/fonts/LuoShu-400.ttf" "$MODULE/system/fonts/GoogleSans-Regular.ttf"
REAL_CKSUM=$(command -v cksum)
printf '0\n' > "$TMP/cksum-count"
cat > "$TMP/bin/cksum" <<'EOS'
#!/bin/sh
count=$(cat "$LUOSHU_CKSUM_COUNT" 2>/dev/null || printf '0')
printf '%s\n' "$((count + 1))" > "$LUOSHU_CKSUM_COUNT"
exec "$LUOSHU_REAL_CKSUM" "$@"
EOS
chmod 0755 "$TMP/bin/cksum"
PATH="$TMP/bin:$PATH" LUOSHU_REAL_CKSUM="$REAL_CKSUM" LUOSHU_CKSUM_COUNT="$TMP/cksum-count" \
MODULE_DIR="$MODULE" MODDIR="$MODULE" sh -c '
    . "$1/common/font_safety.sh"
    luoshu_payload_build_manifest
' sh "$MODULE"
test "$(cat "$TMP/cksum-count")" -eq 1
test "$(wc -l < "$MODULE/config/font-payload-manifest.conf" | tr -d '[:space:]')" -eq 3

# Finalization progress must reserve space after glyph generation and expose real stages.
grep -q '完整复合字体已生成", 80' "$ROOT/common/composite_font.py"
grep -q "mix_stage mount-sync '正在同步元模块字体负载' 96" "$ROOT/common/font_mix.sh"
grep -q "mix_stage manifest '正在生成安全启动清单' 98" "$ROOT/common/font_mix.sh"
! grep -q 'cp -af "$SYSTEM_FONTS_DIR/." "$PAYLOAD_STAGE/"' "$ROOT/common/font_mix.sh"
grep -q '_progress_message=' "$ROOT/common/v142_weighted_mix.sh"
grep -q '完整复合字体后台进程已退出' "$ROOT/common/v142_weighted_mix.sh"

# The import action must fit the full Chinese label on one line.
grep -q 'else -> 148.dp' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportOverlay.kt"
grep -q 'softWrap = false' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportOverlay.kt"
grep -q 'modifier = modifier.fillMaxWidth()' "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeImportOverlay.kt"

echo 'Mix finalization reuses hard-link checksums, reports real stages, and keeps the full import label.'
''',
    encoding="utf-8",
)
perf_test.chmod(0o755)

# Add the regression to the source inventory and execution list.
replace_once(
    "scripts/check.sh",
    """  scripts/auto_multiweight_mode_test.sh scripts/auto_multiweight_engine_test.sh scripts/rc3_audit.sh \\\n""",
    """  scripts/auto_multiweight_mode_test.sh scripts/auto_multiweight_engine_test.sh scripts/mix_finalize_performance_test.sh scripts/rc3_audit.sh \\\n""",
)
replace_once(
    "scripts/check.sh",
    """sh \"$ROOT/scripts/background_mix_worker_test.sh\"\nsh \"$ROOT/scripts/stability_test.sh\"\n""",
    """sh \"$ROOT/scripts/background_mix_worker_test.sh\"\nsh \"$ROOT/scripts/mix_finalize_performance_test.sh\"\nsh \"$ROOT/scripts/stability_test.sh\"\n""",
)

# Update the existing module-update regression to prove composite caches survive updates.
replace_once(
    "scripts/module_update_state_test.sh",
    """    \"$OLD/config\" \"$OLD/system/fonts/.luoshu-font-store\" \"$OLD/system/etc\" \"$OLD/product/fonts\" \\\n    \"$NEW/config\" \"$NEW/system/bin\"\n""",
    """    \"$OLD/config\" \"$OLD/system/fonts/.luoshu-font-store\" \"$OLD/system/etc\" \"$OLD/product/fonts\" \\\n    \"$OLD/cache/full-composite-v5\" \"$OLD/cache/auto-multiweight-mix/composites-v2\" \\\n    \"$NEW/config\" \"$NEW/system/bin\"\n""",
)
replace_once(
    "scripts/module_update_state_test.sh",
    """printf 'OEM payload\\n' >\"$OLD/product/fonts/OEM-Regular.ttf\"\n\nprintf 'new notes\\n' >\"$NEW/config/version_notes.conf\"\n""",
    """printf 'OEM payload\\n' >\"$OLD/product/fonts/OEM-Regular.ttf\"\nprintf 'cached composite\\n' >\"$OLD/cache/full-composite-v5/test.otf\"\nprintf 'cached auto composite\\n' >\"$OLD/cache/auto-multiweight-mix/composites-v2/test.font\"\n\nprintf 'new notes\\n' >\"$NEW/config/version_notes.conf\"\n""",
)
replace_once(
    "scripts/module_update_state_test.sh",
    """test -f \"$NEW/product/fonts/OEM-Regular.ttf\"\ntest -f \"$NEW/system/bin/洛书\"\n""",
    """test -f \"$NEW/product/fonts/OEM-Regular.ttf\"\ntest -f \"$NEW/cache/full-composite-v5/test.otf\"\ntest -f \"$NEW/cache/auto-multiweight-mix/composites-v2/test.font\"\ntest -f \"$NEW/system/bin/洛书\"\n""",
)

# Keep the permanent stability contract explicit.
replace_once(
    "scripts/stability_test.sh",
    """# 字体卡片必须使用紧凑单行样张，完整两行样张只出现在详情页。\ngrep -q '\"洛书 Aa 0123456789\"' \"$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/font/FontUiSupport.kt\"\n""",
    """# 字体卡片必须使用紧凑单行样张，完整两行样张只出现在详情页。\ngrep -q '\"洛书 Aa 0123456789\"' \"$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/font/FontUiSupport.kt\"\n# 导入按钮不得裁掉“体”，复合收尾不得对硬链接别名重复读取大字体。\nsh \"$ROOT/scripts/mix_finalize_performance_test.sh\"\n""",
)

# Remove this one-shot patcher before committing the actual source change.
Path(__file__).unlink()
print("Applied import FAB and mix finalization performance hotfix.")
