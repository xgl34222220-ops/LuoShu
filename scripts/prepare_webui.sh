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

# 统一静态资源缓存号，避免升级后 WebView 继续使用旧脚本和样式。
sed -i -E "s#style\.css\?v=[0-9]+#style.css?v=${CACHE}#g" "$INDEX"
sed -i -E "s#app\.js\?v=[0-9]+#app.js?v=${CACHE}#g" "$INDEX"
sed -i -E "s#stability\.js\?v=[0-9]+#stability.js?v=${CACHE}#g" "$INDEX"
sed -i -E "s#environment\.js\?v=[0-9]+#environment.js?v=${CACHE}#g" "$INDEX"
sed -i -E "s#const STYLE_VERSION = '[0-9]+';#const STYLE_VERSION = '${CACHE}';#" "$WEBROOT/stability.js"
sed -i -E "s#const UI_VERSION = '[0-9]+';#const UI_VERSION = '${CACHE}';#" "$WEBROOT/environment.js"

# 构建产物中的可见版本全部以 module.prop 为准。
sed -i -E "s#v13\.4 Beta2 Hotfix[0-9]+#${VERSION}#g" "$INDEX"
sed -i -E "s#v13\.5 Stable( Hotfix[0-9]+)?#${VERSION}#g" "$INDEX" "$WEBROOT/stability.js"

# 独立自救模块必须先于主 app.js 加载。即使 app.js 解析失败，
# stability.js 仍能提供清缓存、修权限、重建索引和回滚功能。
if ! grep -q 'stability.js?v=' "$INDEX"; then
    sed -i "s#    <script type=\"module\" src=\"app.js?v=${CACHE}\"></script>#    <script type=\"module\" src=\"stability.js?v=${CACHE}\"></script>\n    <script type=\"module\" src=\"app.js?v=${CACHE}\"></script>#" "$INDEX"
fi

# 环境识别与 UI 精修层放在稳定性组件之后、主应用之前。
if ! grep -q 'environment.js?v=' "$INDEX"; then
    sed -i "s#    <script type=\"module\" src=\"app.js?v=${CACHE}\"></script>#    <script type=\"module\" src=\"environment.js?v=${CACHE}\"></script>\n    <script type=\"module\" src=\"app.js?v=${CACHE}\"></script>#" "$INDEX"
fi

# 当前稳定版只公开 Mountify 适配，不再显示其他元模块提示。
sed -i '/<strong>Hybrid Mount<\/strong>/d' "$INDEX"
_tmp="${INDEX}.advanced.$$"
awk '
BEGIN { skip=0 }
/<details class="more-advanced">/ { skip=1; next }
skip && /<\/details>/ { skip=0; next }
!skip { print }
' "$INDEX" > "$_tmp"
mv "$_tmp" "$INDEX"

# 关键尺寸放入 index，防止独立 CSS 尚未加载时，被主样式 body > * 规则拉成整行。
if ! grep -q 'stability-critical-style' "$INDEX"; then
    sed -i '/<\/head>/i\    <style id="stability-critical-style">body>#stabilityRescueButton{position:fixed!important;left:auto!important;right:18px!important;bottom:104px!important;width:56px!important;min-width:56px!important;max-width:56px!important;height:56px!important;min-height:56px!important;max-height:56px!important;margin:0!important;padding:0!important;z-index:9800!important}</style>' "$INDEX"
fi

grep -q "stability.js?v=${CACHE}" "$INDEX"
grep -q "environment.js?v=${CACHE}" "$INDEX"
grep -q "app.js?v=${CACHE}" "$INDEX"
grep -q "style.css?v=${CACHE}" "$INDEX"
grep -q "STYLE_VERSION = '${CACHE}'" "$WEBROOT/stability.js"
grep -q "UI_VERSION = '${CACHE}'" "$WEBROOT/environment.js"
grep -q 'stability-critical-style' "$INDEX"
grep -q "$VERSION" "$INDEX"
! grep -q 'Hybrid Mount' "$INDEX"
! grep -q 'more-advanced' "$INDEX"
