#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

find "$ROOT" -type f -name '*.sh' -print | while IFS= read -r file; do
    sh -n "$file"
done
sh -n "$ROOT/common/play_font_bridge"
sh -n "$ROOT/common/wechat_xweb_bridge"
sh -n "$ROOT/common/font_report"
sh -n "$ROOT/common/meta_overlay_compat"

if command -v node >/dev/null 2>&1; then
    TMP_JS=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-js-check)
    trap 'rm -rf "$TMP_JS"' EXIT HUP INT TERM
    for file in app.js font_analyzer.js kernelsu.js stability.js; do
        cp "$ROOT/webroot/$file" "$TMP_JS/${file%.js}.mjs"
        node --check "$TMP_JS/${file%.js}.mjs"
    done
    rm -rf "$TMP_JS"
    trap - EXIT HUP INT TERM
fi

test -f "$ROOT/module.prop"
test -f "$ROOT/customize.sh"
test -f "$ROOT/service.sh"
test -f "$ROOT/webroot/index.html"
test -f "$ROOT/webroot/stability.js"
test -f "$ROOT/webroot/stability.css"
test -f "$ROOT/common/stability.sh"
test -f "$ROOT/common/meta_overlay_compat"
test -f "$ROOT/common/font_report"
test -f "$ROOT/scripts/prepare_mount_compat.sh"
test -s "$ROOT/system/bin/luoshud"

grep -q '^version=v13.5 Stable Hotfix3$' "$ROOT/module.prop"
grep -q '^versionCode=13503$' "$ROOT/module.prop"
grep -q 'body > #stabilityRescueButton' "$ROOT/webroot/stability.css"
grep -q 'width: 56px !important' "$ROOT/webroot/stability.css"
grep -q 'data-stability-action="snapshot"' "$ROOT/webroot/stability.js"
grep -q 'save_snapshot|manual_snapshot' "$ROOT/common/stability.sh"
grep -q 'snapshotMatchesCurrent' "$ROOT/common/stability.sh"

TMP_STAGE=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-stage-check)
trap 'rm -rf "$TMP_STAGE"' EXIT HUP INT TERM
mkdir -p "$TMP_STAGE/common" "$TMP_STAGE/webroot"
cp "$ROOT/module.prop" "$TMP_STAGE/module.prop"
cp "$ROOT/post-fs-data.sh" "$TMP_STAGE/post-fs-data.sh"
cp "$ROOT/service.sh" "$TMP_STAGE/service.sh"
cp "$ROOT/customize.sh" "$TMP_STAGE/customize.sh"
cp "$ROOT/common/stability.sh" "$TMP_STAGE/common/stability.sh"
cp "$ROOT/common/font_manager.sh" "$TMP_STAGE/common/font_manager.sh"
cp "$ROOT/common/meta_overlay_compat" "$TMP_STAGE/common/meta_overlay_compat"
cp -R "$ROOT/webroot/." "$TMP_STAGE/webroot/"
sh "$ROOT/scripts/prepare_webui.sh" "$TMP_STAGE/webroot"
sh "$ROOT/scripts/prepare_mount_compat.sh" "$TMP_STAGE"
grep -q 'stability.js?v=13503' "$TMP_STAGE/webroot/index.html"
grep -q 'app.js?v=13503' "$TMP_STAGE/webroot/index.html"
grep -q 'style.css?v=13503' "$TMP_STAGE/webroot/index.html"
grep -q "STYLE_VERSION = '13503'" "$TMP_STAGE/webroot/stability.js"
grep -q 'stability-critical-style' "$TMP_STAGE/webroot/index.html"
grep -q 'common/meta_overlay_compat' "$TMP_STAGE/common/font_manager.sh"
test "$(grep -c 'luoshu_sync_meta_payload' "$TMP_STAGE/common/font_manager.sh")" -ge 2
grep -q 'luoshu_sync_meta_payload' "$TMP_STAGE/post-fs-data.sh"
grep -q 'luoshu_sync_meta_payload' "$TMP_STAGE/service.sh"
rm -rf "$TMP_STAGE"
trap - EXIT HUP INT TERM

sh "$ROOT/scripts/stability_test.sh"
sh "$ROOT/scripts/mount_compat_test.sh"

echo "LuoShu source checks passed."
