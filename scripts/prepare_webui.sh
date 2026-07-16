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

# 统一静态资源缓存号，避免升级后 WebView 继续使用旧脚本和旧自救样式。
sed -i -E "s#style\.css\?v=[0-9]+#style.css?v=${CACHE}#g" "$INDEX"
sed -i -E "s#app\.js\?v=[0-9]+#app.js?v=${CACHE}#g" "$INDEX"
sed -i -E "s#stability\.js\?v=[0-9]+#stability.js?v=${CACHE}#g" "$INDEX"
sed -i -E "s#const STYLE_VERSION = '[0-9]+';#const STYLE_VERSION = '${CACHE}';#" "$WEBROOT/stability.js"

# 构建产物中的可见版本全部以 module.prop 为准。
sed -i -E "s#v13\.4 Beta2 Hotfix[0-9]+#${VERSION}#g" "$INDEX"
sed -i -E "s#v13\.5 Stable( Hotfix[0-9]+)?#${VERSION}#g" "$INDEX" "$WEBROOT/stability.js"
sed -i -E "s#v13\.6 Beta[0-9]+#${VERSION}#g" "$INDEX" "$WEBROOT/stability.js"

# 独立自救模块必须先于主 app.js 加载。即使 app.js 解析失败，
# stability.js 仍能提供清缓存、修权限、回滚和报告功能。
if ! grep -q 'stability.js?v=' "$INDEX"; then
    sed -i "s#    <script type=\"module\" src=\"app.js?v=${CACHE}\"></script>#    <script type=\"module\" src=\"stability.js?v=${CACHE}\"></script>\n    <script type=\"module\" src=\"app.js?v=${CACHE}\"></script>#" "$INDEX"
fi

# 关键尺寸放入 index，防止独立 CSS 尚未加载时，被主样式 body > * 规则拉成整行。
if ! grep -q 'stability-critical-style' "$INDEX"; then
    sed -i '/<\/head>/i\    <style id="stability-critical-style">body>#stabilityRescueButton{position:fixed!important;left:auto!important;right:18px!important;bottom:104px!important;width:56px!important;min-width:56px!important;max-width:56px!important;height:56px!important;min-height:56px!important;max-height:56px!important;margin:0!important;padding:0!important;z-index:9800!important}</style>' "$INDEX"
fi

grep -q "stability.js?v=${CACHE}" "$INDEX"
grep -q "app.js?v=${CACHE}" "$INDEX"
grep -q "style.css?v=${CACHE}" "$INDEX"
grep -q "STYLE_VERSION = '${CACHE}'" "$WEBROOT/stability.js"
grep -q 'stability-critical-style' "$INDEX"
grep -q "$VERSION" "$INDEX"
