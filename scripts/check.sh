#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

find "$ROOT" -type f -name '*.sh' -print | while IFS= read -r file; do
    sh -n "$file"
done
sh -n "$ROOT/common/play_font_bridge"
sh -n "$ROOT/common/wechat_xweb_bridge"

if command -v node >/dev/null 2>&1; then
    TMP_JS=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-js-check)
    trap 'rm -rf "$TMP_JS"' EXIT HUP INT TERM
    for file in app.js font_analyzer.js kernelsu.js stability.js environment.js v14.js; do
        cp "$ROOT/webroot/$file" "$TMP_JS/${file%.js}.mjs"
        node --check "$TMP_JS/${file%.js}.mjs"
    done
    rm -rf "$TMP_JS"
    trap - EXIT HUP INT TERM
fi

for file in \
    module.prop customize.sh post-fs-data.sh service.sh \
    webroot/index.html webroot/stability.js webroot/stability.css \
    webroot/environment.js webroot/ui_refine.css webroot/v14.js webroot/v14.css \
    common/stability.sh common/mount_compat.sh common/module_status.sh common/v14_switch.sh \
    scripts/prepare_mount_compat.sh scripts/prepare_v14_package.sh; do
    test -f "$ROOT/$file"
done
test -s "$ROOT/system/bin/luoshud"

grep -q '^version=v14$' "$ROOT/module.prop"
grep -q '^versionCode=14000$' "$ROOT/module.prop"
grep -q '^description=Android 全局字体管理，当前字体：系统默认字体$' "$ROOT/module.prop"
grep -q 'body > #stabilityRescueButton' "$ROOT/webroot/stability.css"
grep -q '/data/adb/modules/mountify' "$ROOT/webroot/environment.js"
grep -q 'APatch' "$ROOT/webroot/environment.js"
grep -q 'SukiSU Ultra' "$ROOT/webroot/environment.js"
grep -q 'luoshu_v14_pending_switch' "$ROOT/webroot/v14.js"
grep -q 'common/v14_switch.sh' "$ROOT/webroot/v14.js"
grep -q 'data-stability-action=.permissions' "$ROOT/webroot/v14.css"
grep -q 'content-visibility:auto' "$ROOT/webroot/v14.css"
grep -q 'module_status.sh' "$ROOT/service.sh"
grep -q 'module_status.sh' "$ROOT/post-fs-data.sh"
! grep -q 'boot_snapshot' "$ROOT/service.sh"
grep -q '元模块推荐：Mountify' "$ROOT/customize.sh"
! grep -q 'Hybrid Mount：推荐' "$ROOT/customize.sh"
! grep -q '^hybrid_mount=' "$ROOT/config/version_notes.conf"
! grep -q '^Hybrid Mount$' "$ROOT/兼容与目录说明.txt"

# 在临时副本中验证正式构建阶段的补丁，不修改工作区。
TMP_STAGE=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-stage-check)
trap 'rm -rf "$TMP_STAGE"' EXIT HUP INT TERM
mkdir -p "$TMP_STAGE/common" "$TMP_STAGE/webroot"
cp "$ROOT/module.prop" "$TMP_STAGE/module.prop"
cp "$ROOT/customize.sh" "$TMP_STAGE/customize.sh"
cp "$ROOT/post-fs-data.sh" "$TMP_STAGE/post-fs-data.sh"
cp "$ROOT/service.sh" "$TMP_STAGE/service.sh"
cp "$ROOT/common/font_manager.sh" "$TMP_STAGE/common/font_manager.sh"
cp "$ROOT/common/mount_compat.sh" "$TMP_STAGE/common/mount_compat.sh"
cp "$ROOT/common/module_status.sh" "$TMP_STAGE/common/module_status.sh"
cp "$ROOT/common/v14_switch.sh" "$TMP_STAGE/common/v14_switch.sh"
cp -R "$ROOT/webroot/." "$TMP_STAGE/webroot/"

sh "$ROOT/scripts/prepare_v14_package.sh" "$TMP_STAGE"
sh "$ROOT/scripts/prepare_webui.sh" "$TMP_STAGE/webroot"
sh "$ROOT/scripts/prepare_mount_compat.sh" "$TMP_STAGE"

grep -q 'stability.js?v=14000' "$TMP_STAGE/webroot/index.html"
grep -q 'environment.js?v=14000' "$TMP_STAGE/webroot/index.html"
grep -q 'app.js?v=14000' "$TMP_STAGE/webroot/index.html"
grep -q 'v14.js?v=14000' "$TMP_STAGE/webroot/index.html"
grep -q 'v14.css?v=14000' "$TMP_STAGE/webroot/index.html"
grep -q 'style.css?v=14000' "$TMP_STAGE/webroot/index.html"
grep -q "STYLE_VERSION = '14000'" "$TMP_STAGE/webroot/stability.js"
grep -q "UI_VERSION = '14000'" "$TMP_STAGE/webroot/environment.js"
grep -q 'stability-critical-style' "$TMP_STAGE/webroot/index.html"
grep -q 'v14-lightweight-preview-sync' "$TMP_STAGE/common/font_manager.sh"
grep -q 'case "$action" in' "$TMP_STAGE/common/font_manager.sh"
grep -q 'module_status.sh.*SELECTED_FONT' "$TMP_STAGE/customize.sh"
grep -q 'common/v14_switch.sh' "$TMP_STAGE/customize.sh"
grep -q '^description=Android 全局字体管理，当前字体：系统默认字体$' "$TMP_STAGE/module.prop"
! grep -q 'Hybrid Mount' "$TMP_STAGE/webroot/index.html"
! grep -q 'more-advanced' "$TMP_STAGE/webroot/index.html"
grep -q 'common/mount_compat.sh' "$TMP_STAGE/common/font_manager.sh"
test "$(grep -c 'luoshu_sync_mount_payload' "$TMP_STAGE/common/font_manager.sh")" -ge 2
grep -q 'luoshu_sync_mount_payload' "$TMP_STAGE/post-fs-data.sh"
grep -q 'luoshu_sync_mount_payload' "$TMP_STAGE/service.sh"
rm -rf "$TMP_STAGE"
trap - EXIT HUP INT TERM

sh "$ROOT/scripts/stability_test.sh"
sh "$ROOT/scripts/mount_compat_test.sh"

echo 'LuoShu v14 source checks passed.'
