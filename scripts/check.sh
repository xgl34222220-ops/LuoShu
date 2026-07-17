#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
find "$ROOT" -type f -name '*.sh' -print | while IFS= read -r file; do sh -n "$file"; done
sh -n "$ROOT/common/play_font_bridge"; sh -n "$ROOT/common/wechat_xweb_bridge"
if command -v node >/dev/null 2>&1; then
    TMP_JS=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-js-check); trap 'rm -rf "$TMP_JS"' EXIT HUP INT TERM
    for file in app.js font_analyzer.js kernelsu.js environment.js v14.js; do cp "$ROOT/webroot/$file" "$TMP_JS/${file%.js}.mjs"; node --check "$TMP_JS/${file%.js}.mjs"; done
    rm -rf "$TMP_JS"; trap - EXIT HUP INT TERM
fi
for file in module.prop update.json customize.sh post-fs-data.sh post-mount.sh service.sh uninstall.sh \
    common/font_transaction.sh common/font_switch_v141.sh common/font_mix.sh common/v14_switch.sh common/v14_mix.sh common/device_capabilities.sh common/preview_cache.sh common/luoshu_cli.sh \
    webroot/index.html webroot/environment.js webroot/app.js webroot/v14.js webroot/v14.css \
    scripts/build.sh scripts/patch_test3_runtime.sh scripts/test3_runtime.patch scripts/prepare_v14_package.sh scripts/prepare_webui.sh scripts/prepare_mount_compat.sh scripts/v141_test.sh scripts/mount_compat_test.sh; do test -f "$ROOT/$file"; done

grep -q '^version=v14.1 Test3$' "$ROOT/module.prop"; grep -q '^versionCode=14103$' "$ROOT/module.prop"; grep -q '^webroot=webroot_v14103$' "$ROOT/module.prop"
grep -q '^updateJson=https://raw.githubusercontent.com/' "$ROOT/module.prop"
grep -q 'APatch.*source' "$ROOT/customize.sh"; ! grep -q '^exit 0$' "$ROOT/customize.sh"; ! grep -q 'touch .*magic' "$ROOT/customize.sh"
grep -q 'font_transaction.sh' "$ROOT/common/font_switch_v141.sh"; grep -q 'resolve_slot_file' "$ROOT/common/font_mix.sh"; grep -q 'cjk_sha256' "$ROOT/common/font_mix.sh"
grep -q 'PREVIEW_CACHE_SCRIPT' "$ROOT/scripts/test3_runtime.patch"; grep -q 'preview_prepare' "$ROOT/scripts/test3_runtime.patch"; grep -q 'webroot=//p' "$ROOT/common/preview_cache.sh"
grep -q '字体角色检测' "$ROOT/scripts/test3_runtime.patch"; grep -q '模块实际占用' "$ROOT/scripts/test3_runtime.patch"; grep -q 'prepareFontPreview' "$ROOT/scripts/test3_runtime.patch"
grep -q '清除旧目标' "$ROOT/post-mount.sh"; grep -q 'preview_cache.sh' "$ROOT/service.sh"

TMP_STAGE=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-stage-check); trap 'rm -rf "$TMP_STAGE"' EXIT HUP INT TERM
mkdir -p "$TMP_STAGE/common" "$TMP_STAGE/webroot" "$TMP_STAGE/system/bin" "$TMP_STAGE/config"
for file in module.prop customize.sh post-fs-data.sh post-mount.sh service.sh uninstall.sh; do cp "$ROOT/$file" "$TMP_STAGE/$file"; done
cp -R "$ROOT/common/." "$TMP_STAGE/common/"; cp -R "$ROOT/webroot/." "$TMP_STAGE/webroot/"; cp "$ROOT/system/bin/luoshud" "$TMP_STAGE/system/bin/"
sh "$ROOT/scripts/patch_test3_runtime.sh" "$TMP_STAGE"
sh "$ROOT/scripts/prepare_v14_package.sh" "$TMP_STAGE"; sh "$ROOT/scripts/prepare_webui.sh" "$TMP_STAGE/webroot"; sh "$ROOT/scripts/prepare_mount_compat.sh" "$TMP_STAGE"
grep -q 'environment.js?v=14103' "$TMP_STAGE/webroot/index.html"; grep -q 'app.js?v=14103' "$TMP_STAGE/webroot/index.html"; grep -q 'v14.js?v=14103' "$TMP_STAGE/webroot/index.html"; grep -q 'v14.css?v=14103' "$TMP_STAGE/webroot/index.html"
grep -q 'id="emojiSection"' "$TMP_STAGE/webroot/index.html"; grep -q '#emojiSection' "$TMP_STAGE/webroot/v14.css"; ! grep -q '^exit 0$' "$TMP_STAGE/customize.sh"
for flag in magic skip_mount skip_mountify remove disable; do test ! -e "$TMP_STAGE/$flag"; done
rm -rf "$TMP_STAGE"; trap - EXIT HUP INT TERM
sh "$ROOT/scripts/v141_test.sh"
sh "$ROOT/scripts/mount_compat_test.sh"
echo 'LuoShu v14.1 Test3 source checks passed.'
