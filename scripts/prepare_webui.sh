#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
WEBROOT=${1:-"$ROOT/webroot"}; INDEX="$WEBROOT/index.html"; PROP="${WEBROOT%/*}/module.prop"
[ -f "$PROP" ] || PROP="$ROOT/module.prop"
VERSION=$(sed -n 's/^version=//p' "$PROP" | head -n1); CACHE=$(sed -n 's/^versionCode=//p' "$PROP" | head -n1)
[ -n "$VERSION" ]; [ -n "$CACHE" ]
for file in "$INDEX" "$WEBROOT/app.js" "$WEBROOT/environment.js" "$WEBROOT/ui_refine.css" "$WEBROOT/v14.js" "$WEBROOT/v14.css" "$WEBROOT/v14_1.js" "$WEBROOT/v14_1.css"; do test -f "$file"; done

sed -i -E "s#style\.css\?v=[0-9]+#style.css?v=${CACHE}#g; s#app\.js\?v=[0-9]+#app.js?v=${CACHE}#g; s#environment\.js\?v=[0-9]+#environment.js?v=${CACHE}#g; s#v14\.js\?v=[0-9]+#v14.js?v=${CACHE}#g; s#v14\.css\?v=[0-9]+#v14.css?v=${CACHE}#g; s#v14_1\.js\?v=[0-9]+#v14_1.js?v=${CACHE}#g; s#v14_1\.css\?v=[0-9]+#v14_1.css?v=${CACHE}#g" "$INDEX"
sed -i -E "s#const UI_VERSION = '[0-9]+';#const UI_VERSION = '${CACHE}';#" "$WEBROOT/environment.js"
sed -i -E "s#v13\.4 Beta2 Hotfix[0-9]+#${VERSION}#g; s#v13\.5 Stable( Hotfix[0-9]+)?#${VERSION}#g; s#>v14(\.0|\.1)?<#>${VERSION}<#g" "$INDEX" 2>/dev/null || true

# 从正式包 HTML 中直接删除旧 Emoji 和重复设置，不再依赖启动后隐藏。
remove_block() {
    _pattern="$1"; _tmp="${INDEX}.strip.$$"
    awk -v pattern="$_pattern" 'BEGIN{skip=0} !skip && $0 ~ pattern {skip=1; next} skip && /<\/section>|<\/button>/ {skip=0; next} !skip {print}' "$INDEX" > "$_tmp"
    mv "$_tmp" "$INDEX"
}
remove_block '<section class="emoji-section"'
for _id in moreImportZipBtn moreOpenFolderBtn moreOpenEmojiFolderBtn generateReportBtn copyFontPathBtn; do remove_block "id=\"${_id}\""; done

sed -i '/stability\.js?v=/d; /stability-critical-style/d; /<strong>Hybrid Mount<\/strong>/d' "$INDEX"
_tmp="${INDEX}.advanced.$$"
awk 'BEGIN{skip=0}/<details class="more-advanced">/{skip=1;next}skip&&/<\/details>/{skip=0;next}!skip{print}' "$INDEX" > "$_tmp"; mv "$_tmp" "$INDEX"
sed -i -E 's/文字和 Emoji 可分别选择/可整套切换，也可组合中文、英文和数字/; s/自动识别可变字体、常规字重与 Emoji/自动识别可变字体与静态多字重/; s#字体与 Emoji 配置#字体配置#g' "$INDEX"

if ! grep -q 'environment.js?v=' "$INDEX"; then
    sed -i "s#    <script type=\"module\" src=\"app.js?v=${CACHE}\"></script>#    <script type=\"module\" src=\"environment.js?v=${CACHE}\"></script>\n    <script type=\"module\" src=\"app.js?v=${CACHE}\"></script>#" "$INDEX"
fi
if ! grep -q 'v14.js?v=' "$INDEX"; then sed -i "s#    <script type=\"module\" src=\"app.js?v=${CACHE}\"></script>#    <script type=\"module\" src=\"app.js?v=${CACHE}\"></script>\n    <script type=\"module\" src=\"v14.js?v=${CACHE}\"></script>#" "$INDEX"; fi
if ! grep -q 'v14_1.js?v=' "$INDEX"; then sed -i "s#    <script type=\"module\" src=\"v14.js?v=${CACHE}\"></script>#    <script type=\"module\" src=\"v14.js?v=${CACHE}\"></script>\n    <script type=\"module\" src=\"v14_1.js?v=${CACHE}\"></script>#" "$INDEX"; fi
if ! grep -q 'v14.css?v=' "$INDEX"; then sed -i "/<\/head>/i\    <link rel=\"stylesheet\" href=\"v14.css?v=${CACHE}\">" "$INDEX"; fi
if ! grep -q 'v14_1.css?v=' "$INDEX"; then sed -i "/<\/head>/i\    <link rel=\"stylesheet\" href=\"v14_1.css?v=${CACHE}\">" "$INDEX"; fi

grep -q "environment.js?v=${CACHE}" "$INDEX"; grep -q "app.js?v=${CACHE}" "$INDEX"; grep -q "v14.js?v=${CACHE}" "$INDEX"; grep -q "v14_1.js?v=${CACHE}" "$INDEX"
grep -q "v14.css?v=${CACHE}" "$INDEX"; grep -q "v14_1.css?v=${CACHE}" "$INDEX"; grep -q "style.css?v=${CACHE}" "$INDEX"
! grep -q 'id="emojiSection"' "$INDEX"; ! grep -q 'moreOpenEmojiFolderBtn' "$INDEX"; ! grep -q 'Hybrid Mount' "$INDEX"; ! grep -q 'more-advanced' "$INDEX"
