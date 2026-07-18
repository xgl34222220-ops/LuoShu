#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
WEBROOT=${1:-"$ROOT/webroot"}
INDEX="$WEBROOT/index.html"
PROP="${WEBROOT%/*}/module.prop"
[ -f "$PROP" ] || PROP="$ROOT/module.prop"
VERSION=$(sed -n 's/^version=//p' "$PROP" | head -n1)
CACHE=$(sed -n 's/^versionCode=//p' "$PROP" | head -n1)
[ -n "$VERSION" ]
[ -n "$CACHE" ]

for file in "$INDEX" "$WEBROOT/app.js" "$WEBROOT/environment.js" "$WEBROOT/ui_refine.css" "$WEBROOT/v14.js" "$WEBROOT/v14.css"; do
    test -f "$file"
done

sed -i -E "s#style\.css\?v=[0-9]+#style.css?v=${CACHE}#g; s#app\.js\?v=[0-9]+#app.js?v=${CACHE}#g; s#environment\.js\?v=[0-9]+#environment.js?v=${CACHE}#g; s#v14\.js\?v=[0-9]+#v14.js?v=${CACHE}#g; s#v14\.css\?v=[0-9]+#v14.css?v=${CACHE}#g" "$INDEX"
sed -i -E "s#const UI_VERSION = '[0-9]+';#const UI_VERSION = '${CACHE}';#" "$WEBROOT/environment.js"
[ ! -f "$WEBROOT/workbench.js" ] || sed -i -E "s#workbench\.css\?v=[0-9]+#workbench.css?v=${CACHE}#g" "$WEBROOT/workbench.js"
[ ! -f "$WEBROOT/workbench_weight_extension.js" ] || sed -i -E "s#workbench_weight_extension\.css\?v=[0-9]+#workbench_weight_extension.css?v=${CACHE}#g" "$WEBROOT/workbench_weight_extension.js"
[ ! -f "$WEBROOT/environment.js" ] || sed -i -E "s#(mix_state_guard|workbench_bridge|workbench)\.js\?v=[0-9]+#\1.js?v=${CACHE}#g" "$WEBROOT/environment.js"
for versioned in "$INDEX" "$WEBROOT/app.js" "$WEBROOT/environment.js" "$WEBROOT/workbench.js" \
                 "$WEBROOT/workbench_bridge.js" "$WEBROOT/workbench_weight_extension.js"; do
    [ ! -f "$versioned" ] || sed -i -E "s#v[0-9]+\.[0-9]+(\.[0-9]+)? ([Aa]lpha|[Bb]eta|RC)[0-9]+#${VERSION}#g" "$versioned"
done
[ ! -f "$WEBROOT/stability.js" ] || sed -i -E "s#const STYLE_VERSION = '[0-9]+';#const STYLE_VERSION = '${CACHE}';#" "$WEBROOT/stability.js"
sed -i -E "s#v13\.4 Beta2 Hotfix[0-9]+#${VERSION}#g; s#v13\.5 Stable( Hotfix[0-9]+)?#${VERSION}#g; s#>v14(\.0)?<#>${VERSION}<#g" "$INDEX" 2>/dev/null || true

# v14 不再加载独立自救弹层，避免设置页与自救页双层叠加、只显示半屏。
sed -i '/stability\.js?v=/d; /stability-critical-style/d' "$INDEX"

if ! grep -q 'environment.js?v=' "$INDEX"; then
    sed -i "s#    <script type=\"module\" src=\"app.js?v=${CACHE}\"></script>#    <script type=\"module\" src=\"environment.js?v=${CACHE}\"></script>\n    <script type=\"module\" src=\"app.js?v=${CACHE}\"></script>#" "$INDEX"
fi
if ! grep -q 'v14.js?v=' "$INDEX"; then
    sed -i "s#    <script type=\"module\" src=\"app.js?v=${CACHE}\"></script>#    <script type=\"module\" src=\"app.js?v=${CACHE}\"></script>\n    <script type=\"module\" src=\"v14.js?v=${CACHE}\"></script>#" "$INDEX"
fi
if ! grep -q 'v14.css?v=' "$INDEX"; then
    sed -i "/<\/head>/i\    <link rel=\"stylesheet\" href=\"v14.css?v=${CACHE}\">" "$INDEX"
fi

sed -i '/<strong>Hybrid Mount<\/strong>/d' "$INDEX"
_tmp="${INDEX}.advanced.$$"
awk 'BEGIN{skip=0}/<details class="more-advanced">/{skip=1;next}skip&&/<\/details>/{skip=0;next}!skip{print}' "$INDEX" > "$_tmp"
mv "$_tmp" "$INDEX"

grep -q "environment.js?v=${CACHE}" "$INDEX"
grep -q "app.js?v=${CACHE}" "$INDEX"
grep -q "v14.js?v=${CACHE}" "$INDEX"
grep -q "v14.css?v=${CACHE}" "$INDEX"
grep -q "style.css?v=${CACHE}" "$INDEX"
grep -q "UI_VERSION = '${CACHE}'" "$WEBROOT/environment.js"
[ ! -f "$WEBROOT/environment.js" ] || grep -q "workbench.js?v=${CACHE}" "$WEBROOT/environment.js"
[ ! -f "$WEBROOT/workbench.js" ] || grep -q "workbench.css?v=${CACHE}" "$WEBROOT/workbench.js"
[ ! -f "$WEBROOT/workbench_weight_extension.js" ] || grep -q "workbench_weight_extension.css?v=${CACHE}" "$WEBROOT/workbench_weight_extension.js"
! grep -q 'stability.js?v=' "$INDEX"
! grep -q 'stability-critical-style' "$INDEX"
! grep -q 'Hybrid Mount' "$INDEX"
! grep -q 'more-advanced' "$INDEX"
