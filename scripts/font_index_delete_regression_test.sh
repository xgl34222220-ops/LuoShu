#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

FONT=$(find /usr/share/fonts -type f -iname 'DejaVuSans.ttf' -print -quit 2>/dev/null || true)
if [ ! -s "$FONT" ]; then
    echo 'Font index deletion regression skipped: DejaVu Sans is unavailable.'
    exit 0
fi

MODULE="$TMP/module"
PUBLIC="$TMP/public"
mkdir -p "$MODULE/common" "$MODULE/config" "$PUBLIC/fonts"
cp "$ROOT/common/font_manager.sh" "$MODULE/common/font_manager.sh"
cp "$ROOT/common/util_functions.sh" "$MODULE/common/util_functions.sh"
cp "$ROOT/common/font_check.sh" "$MODULE/common/font_check.sh"
cp "$ROOT/common/font_library_cache.sh" "$MODULE/common/font_library_cache.sh"
cp "$FONT" "$PUBLIC/fonts/Alpha-Regular.ttf"
cp "$FONT" "$PUBLIC/fonts/Beta-Regular.ttf"

BEFORE=$(MODDIR="$MODULE" LUOSHU_PUBLIC_DIR="$PUBLIC" sh "$MODULE/common/font_manager.sh" action list refresh)
printf '%s\n' "$BEFORE" | grep -q '"count":2'
printf '%s\n' "$BEFORE" | grep -q '"id":"Alpha"'
printf '%s\n' "$BEFORE" | grep -q '"id":"Beta"'

DELETED=$(MODDIR="$MODULE" LUOSHU_PUBLIC_DIR="$PUBLIC" sh "$MODULE/common/font_manager.sh" action delete Alpha)
printf '%s\n' "$DELETED" | grep -q '"status":"ok"'
printf '%s\n' "$DELETED" | grep -q '"deleted":1'
test ! -e "$PUBLIC/fonts/Alpha-Regular.ttf"
test -s "$PUBLIC/fonts/Beta-Regular.ttf"

AFTER=$(MODDIR="$MODULE" LUOSHU_PUBLIC_DIR="$PUBLIC" sh "$MODULE/common/font_manager.sh" action list refresh)
printf '%s\n' "$AFTER" | grep -q '"count":1'
! printf '%s\n' "$AFTER" | grep -q '"id":"Alpha"'
printf '%s\n' "$AFTER" | grep -q '"id":"Beta"'

! grep -Fq 'case "$_name|$_family"' "$ROOT/common/font_manager.sh"
grep -Fq 'case "$_name" in' "$ROOT/common/font_manager.sh"
grep -Fq 'case "$_family" in' "$ROOT/common/font_manager.sh"
echo 'Deleting one font preserves every remaining font in the native index.'
