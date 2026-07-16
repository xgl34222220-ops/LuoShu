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
    for file in app.js font_analyzer.js kernelsu.js; do
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
test -s "$ROOT/system/bin/luoshud"

grep -q '^version=v13.4 Beta2 Hotfix6$' "$ROOT/module.prop"
grep -q '^versionCode=13426$' "$ROOT/module.prop"
grep -q 'app.js?v=13426' "$ROOT/webroot/index.html"
grep -q 'style.css?v=13426' "$ROOT/webroot/index.html"
! grep -q 'app.js?v=13426"' "$ROOT/webroot/index.html"

echo "LuoShu source checks passed."
