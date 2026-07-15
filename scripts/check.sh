#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

find "$ROOT" -type f -name '*.sh' -print | while IFS= read -r file; do
    sh -n "$file"
done
sh -n "$ROOT/common/play_font_bridge"
sh -n "$ROOT/common/wechat_xweb_bridge"

if command -v node >/dev/null 2>&1; then
    node --check "$ROOT/webroot/app.js"
    node --check "$ROOT/webroot/font_analyzer.js"
    node --check "$ROOT/webroot/kernelsu.js"
fi

test -f "$ROOT/module.prop"
test -f "$ROOT/customize.sh"
test -f "$ROOT/service.sh"
test -f "$ROOT/webroot/index.html"
test -s "$ROOT/system/bin/luoshud"

grep -q '^version=v13.3 Beta2$' "$ROOT/module.prop"
grep -q '^versionCode=13302$' "$ROOT/module.prop"

echo "LuoShu source checks passed."
