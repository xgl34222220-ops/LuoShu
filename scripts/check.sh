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
test -x "$ROOT/common/stability.sh"
test -s "$ROOT/system/bin/luoshud"

grep -q '^version=v13.5 Stable$' "$ROOT/module.prop"
grep -q '^versionCode=13500$' "$ROOT/module.prop"
grep -q "STYLE_VERSION = '13500'" "$ROOT/webroot/stability.js"

# 在临时副本中验证构建时的资源注入，不修改工作区。
TMP_WEB=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-web-check)
trap 'rm -rf "$TMP_WEB"' EXIT HUP INT TERM
cp -R "$ROOT/webroot/." "$TMP_WEB/"
sh "$ROOT/scripts/prepare_webui.sh" "$TMP_WEB"
grep -q 'stability.js?v=13500' "$TMP_WEB/index.html"
grep -q 'app.js?v=13500' "$TMP_WEB/index.html"
grep -q 'style.css?v=13500' "$TMP_WEB/index.html"
rm -rf "$TMP_WEB"
trap - EXIT HUP INT TERM

sh "$ROOT/scripts/stability_test.sh"

echo "LuoShu source checks passed."
