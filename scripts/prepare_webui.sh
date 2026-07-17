#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
WEBROOT=${1:-"$ROOT/webroot"}; INDEX="$WEBROOT/index.html"; PROP="${WEBROOT%/*}/module.prop"
[ -f "$PROP" ] || PROP="$ROOT/module.prop"
VERSION=$(sed -n 's/^version=//p' "$PROP" | head -n1); CACHE=$(sed -n 's/^versionCode=//p' "$PROP" | head -n1)
[ -n "$VERSION" ]; [ -n "$CACHE" ]
for file in "$INDEX" "$WEBROOT/app.js" "$WEBROOT/environment.js" "$WEBROOT/ui_refine.css" "$WEBROOT/v14.js" "$WEBROOT/v14.css"; do test -f "$file"; done

sed -i -E "s#style\.css\?v=[0-9]+#style.css?v=${CACHE}#g; s#app\.js\?v=[0-9]+#app.js?v=${CACHE}#g; s#environment\.js\?v=[0-9]+#environment.js?v=${CACHE}#g; s#v14\.js\?v=[0-9]+#v14.js?v=${CACHE}#g; s#v14\.css\?v=[0-9]+#v14.css?v=${CACHE}#g" "$INDEX"
sed -i -E "s#const UI_VERSION = '[0-9]+';#const UI_VERSION = '${CACHE}';#" "$WEBROOT/environment.js"
sed -i -E "s#v14\.1( Test[0-9]+)?#${VERSION}#g; s#>v14(\.0|\.1)?<#>${VERSION}<#g" "$INDEX" 2>/dev/null || true
sed -i '/v14_1\.js?v=/d; /v14_1\.css?v=/d; /stability\.js?v=/d; /stability-critical-style/d' "$INDEX"

if ! grep -q 'environment.js?v=' "$INDEX"; then
    sed -i "s#    <script type=\"module\" src=\"app.js?v=${CACHE}\"></script>#    <script type=\"module\" src=\"environment.js?v=${CACHE}\"></script>\n    <script type=\"module\" src=\"app.js?v=${CACHE}\"></script>#" "$INDEX"
fi
if ! grep -q 'v14.js?v=' "$INDEX"; then sed -i "s#    <script type=\"module\" src=\"app.js?v=${CACHE}\"></script>#    <script type=\"module\" src=\"app.js?v=${CACHE}\"></script>\n    <script type=\"module\" src=\"v14.js?v=${CACHE}\"></script>#" "$INDEX"; fi
if ! grep -q 'v14.css?v=' "$INDEX"; then sed -i "/<\/head>/i\    <link rel=\"stylesheet\" href=\"v14.css?v=${CACHE}\">" "$INDEX"; fi

grep -q "environment.js?v=${CACHE}" "$INDEX"
grep -q "app.js?v=${CACHE}" "$INDEX"
grep -q "v14.js?v=${CACHE}" "$INDEX"
grep -q "v14.css?v=${CACHE}" "$INDEX"
grep -q "style.css?v=${CACHE}" "$INDEX"
grep -q 'id="emojiSection"' "$INDEX"
grep -q '#emojiSection' "$WEBROOT/v14.css"
! grep -q 'v14_1.js?v=' "$INDEX"
! grep -q 'v14_1.css?v=' "$INDEX"
