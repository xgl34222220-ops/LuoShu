#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

find "$ROOT" -type f -name '*.sh' -print | while IFS= read -r file; do
    sh -n "$file"
done

if command -v node >/dev/null 2>&1; then
    node --check "$ROOT/webroot/app.js"
    node --check "$ROOT/webroot/kernelsu.js"
fi

test -f "$ROOT/module.prop"
test -f "$ROOT/customize.sh"
test -f "$ROOT/service.sh"
test -f "$ROOT/webroot/index.html"

echo "LuoShu source checks passed."

