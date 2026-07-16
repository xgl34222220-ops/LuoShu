#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
WEBROOT=${1:-"$ROOT/webroot"}
INDEX="$WEBROOT/index.html"
VERSION='v13.5 Stable'
CACHE='13500'

test -f "$INDEX"
test -f "$WEBROOT/app.js"
test -f "$WEBROOT/stability.js"
test -f "$WEBROOT/stability.css"

# 统一静态资源缓存号，避免升级后 WebView 继续使用旧脚本。
sed -i -E "s#style\.css\?v=[0-9]+#style.css?v=${CACHE}#g" "$INDEX"
sed -i -E "s#app\.js\?v=[0-9]+#app.js?v=${CACHE}#g" "$INDEX"

# 构建产物中的可见版本全部以 module.prop 对应版本为准。
sed -i -E "s#v13\.4 Beta2 Hotfix[0-9]+#${VERSION}#g" "$INDEX"

# 独立自救模块必须先于主 app.js 加载。即使 app.js 解析失败，
# stability.js 仍能提供清缓存、修权限、回滚和报告功能。
if ! grep -q 'stability.js?v=' "$INDEX"; then
    sed -i "s#    <script type=\"module\" src=\"app.js?v=${CACHE}\"></script>#    <script type=\"module\" src=\"stability.js?v=${CACHE}\"></script>\n    <script type=\"module\" src=\"app.js?v=${CACHE}\"></script>#" "$INDEX"
else
    sed -i -E "s#stability\.js\?v=[0-9]+#stability.js?v=${CACHE}#g" "$INDEX"
fi

grep -q "stability.js?v=${CACHE}" "$INDEX"
grep -q "app.js?v=${CACHE}" "$INDEX"
grep -q "style.css?v=${CACHE}" "$INDEX"
grep -q "$VERSION" "$INDEX"
