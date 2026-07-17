#!/bin/sh
set -eu
STAGE=${1:?stage directory required}
PATCH_FILE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/test3_runtime.patch
[ -f "$PATCH_FILE" ]
for file in common/font_manager.sh webroot/app.js webroot/v14.js webroot/v14.css; do test -f "$STAGE/$file"; done
# --forward makes a second accidental invocation harmless only when all hunks are already present.
if ! patch --batch --forward -p1 -d "$STAGE" < "$PATCH_FILE"; then
    grep -q 'PREVIEW_CACHE_SCRIPT' "$STAGE/common/font_manager.sh" \
      && grep -q 'prepareFontPreview' "$STAGE/webroot/app.js" \
      && grep -q '字体角色检测' "$STAGE/webroot/v14.js" \
      && grep -q 'v14-storage-summary' "$STAGE/webroot/v14.css" \
      || { echo '无法应用 v14.1 Test3 运行时补丁' >&2; exit 1; }
fi
sh -n "$STAGE/common/font_manager.sh"
if command -v node >/dev/null 2>&1; then
    TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-test3-js)
    trap 'rm -rf "$TMP"' EXIT HUP INT TERM
    cp "$STAGE/webroot/app.js" "$TMP/app.mjs"
    cp "$STAGE/webroot/v14.js" "$TMP/v14.mjs"
    node --check "$TMP/app.mjs"
    node --check "$TMP/v14.mjs"
    rm -rf "$TMP"; trap - EXIT HUP INT TERM
fi
