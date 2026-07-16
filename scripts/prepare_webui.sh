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

test -f "$INDEX"
test -f "$WEBROOT/app.js"
test -f "$WEBROOT/stability.js"
test -f "$WEBROOT/stability.css"
test -f "$WEBROOT/environment.js"
test -f "$WEBROOT/ui_refine.css"
test -f "$WEBROOT/v14.js"
test -f "$WEBROOT/v14.css"

# 统一缓存号，升级后不继续使用旧 WebView 资源。
sed -i -E "s#style\.css\?v=[0-9]+#style.css?v=${CACHE}#g" "$INDEX"
sed -i -E "s#app\.js\?v=[0-9]+#app.js?v=${CACHE}#g" "$INDEX"
sed -i -E "s#stability\.js\?v=[0-9]+#stability.js?v=${CACHE}#g" "$INDEX"
sed -i -E "s#environment\.js\?v=[0-9]+#environment.js?v=${CACHE}#g" "$INDEX"
sed -i -E "s#v14\.js\?v=[0-9]+#v14.js?v=${CACHE}#g" "$INDEX"
sed -i -E "s#v14\.css\?v=[0-9]+#v14.css?v=${CACHE}#g" "$INDEX"
sed -i -E "s#const STYLE_VERSION = '[0-9]+';#const STYLE_VERSION = '${CACHE}';#" "$WEBROOT/stability.js"
sed -i -E "s#const UI_VERSION = '[0-9]+';#const UI_VERSION = '${CACHE}';#" "$WEBROOT/environment.js"

# 构建产物中的可见版本以 module.prop 为准。
sed -i -E "s#v13\.4 Beta2 Hotfix[0-9]+#${VERSION}#g" "$INDEX"
sed -i -E "s#v13\.5 Stable( Hotfix[0-9]+)?#${VERSION}#g" "$INDEX" "$WEBROOT/stability.js"
sed -i -E "s#>v14(\.0)?<#>${VERSION}<#g" "$INDEX" 2>/dev/null || true

# 自救先加载；环境识别在主应用前；v14 稳定层在主应用后接管切换流程。
if ! grep -q 'stability.js?v=' "$INDEX"; then
    sed -i "s#    <script type=\"module\" src=\"app.js?v=${CACHE}\"></script>#    <script type=\"module\" src=\"stability.js?v=${CACHE}\"></script>\n    <script type=\"module\" src=\"app.js?v=${CACHE}\"></script>#" "$INDEX"
fi
if ! grep -q 'environment.js?v=' "$INDEX"; then
    sed -i "s#    <script type=\"module\" src=\"app.js?v=${CACHE}\"></script>#    <script type=\"module\" src=\"environment.js?v=${CACHE}\"></script>\n    <script type=\"module\" src=\"app.js?v=${CACHE}\"></script>#" "$INDEX"
fi
if ! grep -q 'v14.js?v=' "$INDEX"; then
    sed -i "s#    <script type=\"module\" src=\"app.js?v=${CACHE}\"></script>#    <script type=\"module\" src=\"app.js?v=${CACHE}\"></script>\n    <script type=\"module\" src=\"v14.js?v=${CACHE}\"></script>#" "$INDEX"
fi
if ! grep -q 'v14.css?v=' "$INDEX"; then
    sed -i "/<\/head>/i\\    <link rel=\"stylesheet\" href=\"v14.css?v=${CACHE}\">" "$INDEX"
fi

# 仅公开 Mountify 适配，不显示其他元模块或命令行高级工具。
sed -i '/<strong>Hybrid Mount<\/strong>/d' "$INDEX"
_tmp="${INDEX}.advanced.$$"
awk '
BEGIN { skip=0 }
/<details class="more-advanced">/ { skip=1; next }
skip && /<\/details>/ { skip=0; next }
!skip { print }
' "$INDEX" > "$_tmp"
mv "$_tmp" "$INDEX"

# 自救按钮关键尺寸内联，样式尚未加载时也不会被全局规则拉伸。
if ! grep -q 'stability-critical-style' "$INDEX"; then
    sed -i '/<\/head>/i\    <style id="stability-critical-style">body>#stabilityRescueButton{position:fixed!important;left:auto!important;right:18px!important;bottom:104px!important;width:52px!important;min-width:52px!important;max-width:52px!important;height:52px!important;min-height:52px!important;max-height:52px!important;margin:0!important;padding:0!important;z-index:9800!important}</style>' "$INDEX"
fi

grep -q "stability.js?v=${CACHE}" "$INDEX"
grep -q "environment.js?v=${CACHE}" "$INDEX"
grep -q "app.js?v=${CACHE}" "$INDEX"
grep -q "v14.js?v=${CACHE}" "$INDEX"
grep -q "v14.css?v=${CACHE}" "$INDEX"
grep -q "style.css?v=${CACHE}" "$INDEX"
grep -q "STYLE_VERSION = '${CACHE}'" "$WEBROOT/stability.js"
grep -q "UI_VERSION = '${CACHE}'" "$WEBROOT/environment.js"
grep -q 'stability-critical-style' "$INDEX"
grep -q "$VERSION" "$INDEX"
! grep -q 'Hybrid Mount' "$INDEX"
! grep -q 'more-advanced' "$INDEX"
