#!/bin/sh
# 生成洛书预发行就绪报告。默认只报告；传入 --enforce 时阻断未满足的发布条件。
set -eu

ROOT="${ROOT:-${GITHUB_WORKSPACE:-$(pwd)}}"
TARGET_VERSION="v2.2.2"
ENFORCE=0
OUTPUT_DIR="${LUOSHU_READINESS_DIR:-$ROOT/dist/pre-release-readiness}"

while [ "$#" -gt 0 ]; do
    case "$1" in
        --target)
            [ "$#" -ge 2 ] || { echo '--target requires a value' >&2; exit 2; }
            TARGET_VERSION="$2"
            shift 2
            ;;
        --enforce)
            ENFORCE=1
            shift
            ;;
        --output)
            [ "$#" -ge 2 ] || { echo '--output requires a value' >&2; exit 2; }
            OUTPUT_DIR="$2"
            shift 2
            ;;
        *)
            echo "unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

mkdir -p "$OUTPUT_DIR"
REPORT_MD="$OUTPUT_DIR/readiness.md"
REPORT_JSON="$OUTPUT_DIR/readiness.json"
CHECKS_TSV="$OUTPUT_DIR/checks.tsv"
: > "$CHECKS_TSV"

blockers=0
warnings=0
ready=0

json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r\t' '   '
}

add_check() {
    severity="$1"
    id="$2"
    title="$3"
    detail="$4"
    case "$severity" in
        blocker) blockers=$((blockers + 1)) ;;
        warning) warnings=$((warnings + 1)) ;;
        ready) ready=$((ready + 1)) ;;
        *) echo "invalid severity: $severity" >&2; exit 2 ;;
    esac
    printf '%s\t%s\t%s\t%s\n' "$severity" "$id" "$title" "$detail" >> "$CHECKS_TSV"
}

prop_get() {
    sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

base_version() {
    printf '%s' "$1" | sed 's/^[vV]//; s/[-+].*$//'
}

expected_code() {
    value="$(base_version "$1")"
    old_ifs="$IFS"
    IFS=.
    set -- $value
    IFS="$old_ifs"
    major="${1:-}"
    minor="${2:-}"
    patch="${3:-}"
    case "$major.$minor.$patch" in
        *[!0-9.]*|.*|*..*|*.) return 1 ;;
    esac
    printf '%s\n' $((major * 10000 + minor * 100 + patch))
}

MODULE_PROP="$ROOT/module.prop"
VERSION_NOTES="$ROOT/config/version_notes.conf"
current_version=''
current_code=''
notes_version=''

if [ -f "$MODULE_PROP" ]; then
    current_version="$(prop_get "$MODULE_PROP" version)"
    current_code="$(prop_get "$MODULE_PROP" versionCode)"
    if [ -n "$current_version" ] && [ -n "$current_code" ]; then
        add_check ready module-prop '模块版本源' "module.prop 可读取：$current_version ($current_code)"
    else
        add_check blocker module-prop '模块版本源' 'module.prop 缺少 version 或 versionCode'
    fi
else
    add_check blocker module-prop '模块版本源' 'module.prop 不存在'
fi

if [ -n "$current_version" ] && [ "$(base_version "$current_version")" = "$(base_version "$TARGET_VERSION")" ]; then
    add_check ready target-version '候选版本号' "当前版本 $current_version 已进入 $TARGET_VERSION 候选线"
else
    add_check blocker target-version '候选版本号' "当前版本 ${current_version:-unknown}，发布前需要切换到 $TARGET_VERSION"
fi

expected="$(expected_code "$current_version" 2>/dev/null || true)"
if [ -n "$expected" ] && [ "$current_code" = "$expected" ]; then
    add_check ready version-code '版本代码' "versionCode $current_code 与语义版本一致"
elif [ -n "$current_code" ]; then
    add_check blocker version-code '版本代码' "versionCode $current_code 与当前语义版本预期 ${expected:-unknown} 不一致"
else
    add_check blocker version-code '版本代码' 'versionCode 不可用'
fi

if [ -f "$VERSION_NOTES" ]; then
    notes_version="$(prop_get "$VERSION_NOTES" version)"
    summary="$(prop_get "$VERSION_NOTES" summary)"
    notes="$(prop_get "$VERSION_NOTES" notes)"
    if [ "$notes_version" = "$current_version" ] && [ -n "$summary" ] && [ -n "$notes" ]; then
        add_check ready version-notes '版本说明' "version_notes.conf 已覆盖 $current_version"
    else
        add_check blocker version-notes '版本说明' "版本说明未与 ${current_version:-unknown} 对齐，或 summary/notes 为空"
    fi
else
    add_check blocker version-notes '版本说明' 'config/version_notes.conf 不存在'
fi

update_json="$(prop_get "$MODULE_PROP" updateJson 2>/dev/null || true)"
if [ -n "$update_json" ]; then
    add_check ready update-json '更新元数据' 'module.prop 已配置 updateJson'
else
    add_check warning update-json '更新元数据' 'updateJson 为空；预发行可继续，但正式发布前需要确认更新渠道'
fi

required_files='
common/app_bridge.sh
common/font_archive_export.sh
common/font_details.sh
common/font_manager.sh
common/font_mix_controller.sh
scripts/build.sh
scripts/check.sh
scripts/version.sh
android-app/app/build.gradle.kts
'
missing=0
printf '%s' "$required_files" | while IFS= read -r path; do
    [ -n "$path" ] || continue
    [ -f "$ROOT/$path" ] || printf '%s\n' "$path"
done > "$OUTPUT_DIR/missing-files.txt"
if [ -s "$OUTPUT_DIR/missing-files.txt" ]; then
    missing="$(wc -l < "$OUTPUT_DIR/missing-files.txt" | tr -d '[:space:]')"
    add_check blocker required-files '候选文件清单' "缺少 $missing 个必需文件，详见 missing-files.txt"
else
    rm -f "$OUTPUT_DIR/missing-files.txt"
    add_check ready required-files '候选文件清单' '模块桥、字体归档、构建脚本和原生 App 文件齐全'
fi

shell_failed=0
for script in \
    "$ROOT/common/app_bridge.sh" \
    "$ROOT/common/font_archive_export.sh" \
    "$ROOT/scripts/build.sh" \
    "$ROOT/scripts/check.sh" \
    "$ROOT/scripts/version.sh"; do
    [ -f "$script" ] || continue
    if ! sh -n "$script"; then shell_failed=$((shell_failed + 1)); fi
done
if [ "$shell_failed" -eq 0 ]; then
    add_check ready shell-syntax 'Shell 语法' '关键模块与发布脚本通过 sh -n'
else
    add_check blocker shell-syntax 'Shell 语法' "$shell_failed 个关键脚本未通过 sh -n"
fi

if grep -q 'module.prop is the only version source' "$ROOT/android-app/app/build.gradle.kts" 2>/dev/null && \
   grep -q 'versionCode = moduleVersionCode \* 100 + 1' "$ROOT/android-app/app/build.gradle.kts" 2>/dev/null; then
    add_check ready app-version-source 'App 版本来源' '原生 App 继续以 module.prop 为唯一版本源'
else
    add_check blocker app-version-source 'App 版本来源' '原生 App 版本配置未证明与 module.prop 同源'
fi

if [ -d "$ROOT/dist" ] && find "$ROOT/dist" -maxdepth 1 -type f -name 'LuoShu-*.zip' -size +0c | grep -q .; then
    add_check ready candidate-artifact '候选模块成品' 'dist 中存在模块候选 ZIP；仍需由候选工作流校验 SHA-256 与内容清单'
else
    add_check warning candidate-artifact '候选模块成品' '当前工作区没有模块候选 ZIP；请以 Build Test Candidate 工作流成品为准'
fi

if [ -d "$ROOT/dist" ] && find "$ROOT/dist" -maxdepth 1 -type f -name 'LuoShu-App-*.apk' -size +0c | grep -q .; then
    add_check ready candidate-app '候选 App 成品' 'dist 中存在候选 APK'
else
    add_check warning candidate-app '候选 App 成品' '当前工作区没有候选 APK；发布前需要下载并真机验收工作流成品'
fi

if [ -n "${GITHUB_SHA:-}" ]; then
    add_check ready source-revision '源码修订' "报告绑定提交 ${GITHUB_SHA}"
else
    add_check warning source-revision '源码修订' '本地报告未绑定 GITHUB_SHA，归档时应同时记录提交哈希'
fi

status='ready'
[ "$blockers" -gt 0 ] && status='blocked'

{
    echo '# 洛书预发行就绪报告'
    echo
    echo "- 目标版本：\`$TARGET_VERSION\`"
    echo "- 当前版本：\`${current_version:-unknown}\`"
    echo "- 状态：**$status**"
    echo "- 阻断：**$blockers**"
    echo "- 提示：**$warnings**"
    echo "- 通过：**$ready**"
    [ -n "${GITHUB_SHA:-}" ] && echo "- 提交：\`$GITHUB_SHA\`"
    echo
    echo '| 状态 | 检查 | 说明 |'
    echo '|---|---|---|'
    while IFS='\t' read -r severity id title detail; do
        case "$severity" in ready) label='通过' ;; warning) label='提示' ;; blocker) label='阻断' ;; esac
        safe_detail="$(printf '%s' "$detail" | sed 's/|/\\|/g')"
        echo "| $label | $title | $safe_detail |"
    done < "$CHECKS_TSV"
    echo
    echo '> 该报告不替代真机测试矩阵、GitHub Actions 候选成品校验或人工发布确认。'
} > "$REPORT_MD"

{
    printf '{\n'
    printf '  "schema": 1,\n'
    printf '  "type": "luoshu-pre-release-readiness",\n'
    printf '  "targetVersion": "%s",\n' "$(json_escape "$TARGET_VERSION")"
    printf '  "currentVersion": "%s",\n' "$(json_escape "${current_version:-unknown}")"
    printf '  "status": "%s",\n' "$status"
    printf '  "blockers": %s,\n' "$blockers"
    printf '  "warnings": %s,\n' "$warnings"
    printf '  "readyChecks": %s,\n' "$ready"
    printf '  "commit": "%s",\n' "$(json_escape "${GITHUB_SHA:-}")"
    printf '  "checks": [\n'
    index=0
    total="$(wc -l < "$CHECKS_TSV" | tr -d '[:space:]')"
    while IFS='\t' read -r severity id title detail; do
        index=$((index + 1))
        printf '    {"severity":"%s","id":"%s","title":"%s","detail":"%s"}' \
            "$(json_escape "$severity")" "$(json_escape "$id")" "$(json_escape "$title")" "$(json_escape "$detail")"
        [ "$index" -lt "$total" ] && printf ','
        printf '\n'
    done < "$CHECKS_TSV"
    printf '  ]\n'
    printf '}\n'
} > "$REPORT_JSON"

cat "$REPORT_MD"
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then cat "$REPORT_MD" >> "$GITHUB_STEP_SUMMARY"; fi

if [ "$ENFORCE" -eq 1 ] && [ "$blockers" -gt 0 ]; then
    echo "pre-release readiness blocked by $blockers check(s)" >&2
    exit 1
fi
exit 0
