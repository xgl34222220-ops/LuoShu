#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
find "$ROOT" -type f -name '*.sh' -print | while IFS= read -r file; do sh -n "$file"; done
sh -n "$ROOT/common/play_font_bridge"; sh -n "$ROOT/common/wechat_xweb_bridge"
if command -v node >/dev/null 2>&1; then
    TMP_JS=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-js-check); trap 'rm -rf "$TMP_JS"' EXIT HUP INT TERM
    for file in app.js font_analyzer.js kernelsu.js environment.js v14.js v14_1.js; do cp "$ROOT/webroot/$file" "$TMP_JS/${file%.js}.mjs"; node --check "$TMP_JS/${file%.js}.mjs"; done
    rm -rf "$TMP_JS"; trap - EXIT HUP INT TERM
fi
for file in module.prop update.json customize.sh post-fs-data.sh post-mount.sh service.sh uninstall.sh \
    common/font_transaction.sh common/font_switch_v141.sh common/font_mix.sh common/v14_switch.sh common/v14_mix.sh common/device_capabilities.sh common/luoshu_cli.sh \
    webroot/index.html webroot/environment.js webroot/v14.js webroot/v14.css webroot/v14_1.js webroot/v14_1.css \
    scripts/build.sh scripts/prepare_v14_package.sh scripts/prepare_webui.sh scripts/v141_test.sh; do test -f "$ROOT/$file"; done

grep -q '^version=v14.1$' "$ROOT/module.prop"; grep -q '^versionCode=14100$' "$ROOT/module.prop"
grep -q '^updateJson=https://raw.githubusercontent.com/' "$ROOT/module.prop"
grep -q 'APatch.*source' "$ROOT/customize.sh"; ! grep -q '^exit 0$' "$ROOT/customize.sh"; ! grep -q 'touch .*magic' "$ROOT/customize.sh"
grep -q '默认卸载模块' "$ROOT/customize.sh"; grep -q '默认卸载模块' "$ROOT/webroot/v14_1.js"
grep -q 'font_transaction.sh' "$ROOT/common/font_switch_v141.sh"; grep -q 'font_transaction.sh' "$ROOT/common/font_mix.sh"
grep -q '原配置已保留\|原字体配置未被破坏' "$ROOT/common/font_switch_v141.sh"
grep -q 'digitIndependent' "$ROOT/common/device_capabilities.sh"
grep -q 'v14_1.js' "$ROOT/scripts/prepare_webui.sh"; grep -q 'v14_1.css' "$ROOT/scripts/prepare_webui.sh"
! grep -q 'webroot/emoji' "$ROOT/scripts/build.sh"; ! grep -q ' magic ' "$ROOT/scripts/build.sh"

TMP_STAGE=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-stage-check); trap 'rm -rf "$TMP_STAGE"' EXIT HUP INT TERM
mkdir -p "$TMP_STAGE/common" "$TMP_STAGE/webroot" "$TMP_STAGE/system/bin" "$TMP_STAGE/config"
for file in module.prop customize.sh post-fs-data.sh post-mount.sh service.sh uninstall.sh; do cp "$ROOT/$file" "$TMP_STAGE/$file"; done
cp -R "$ROOT/common/." "$TMP_STAGE/common/"; cp -R "$ROOT/webroot/." "$TMP_STAGE/webroot/"; cp "$ROOT/system/bin/luoshud" "$TMP_STAGE/system/bin/"
sh "$ROOT/scripts/prepare_v14_package.sh" "$TMP_STAGE"; sh "$ROOT/scripts/prepare_webui.sh" "$TMP_STAGE/webroot"
grep -q 'environment.js?v=14100' "$TMP_STAGE/webroot/index.html"; grep -q 'app.js?v=14100' "$TMP_STAGE/webroot/index.html"
grep -q 'v14.js?v=14100' "$TMP_STAGE/webroot/index.html"; grep -q 'v14_1.js?v=14100' "$TMP_STAGE/webroot/index.html"
grep -q 'v14_1.css?v=14100' "$TMP_STAGE/webroot/index.html"; ! grep -q 'id="emojiSection"' "$TMP_STAGE/webroot/index.html"
! grep -q 'Hybrid Mount' "$TMP_STAGE/webroot/index.html"; ! grep -q '^exit 0$' "$TMP_STAGE/customize.sh"
for flag in magic skip_mount skip_mountify remove disable; do test ! -e "$TMP_STAGE/$flag"; done
rm -rf "$TMP_STAGE"; trap - EXIT HUP INT TERM
sh "$ROOT/scripts/v141_test.sh"
sh "$ROOT/scripts/mount_compat_test.sh"
echo 'LuoShu v14.1 source checks passed.'
