#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
mkdir -p "$TMP/public/fonts" "$TMP/export"

printf regular > "$TMP/public/fonts/Demo-Regular.ttf"
printf bold > "$TMP/public/fonts/Demo-Bold.ttf"
printf extra > "$TMP/public/fonts/Demo-ExtraBold.ttf"

OUTPUT=$(LUOSHU_PUBLIC_DIR="$TMP/public" MODDIR="$ROOT" sh "$ROOT/common/app_bridge.sh" preview_source Demo 400)
printf '%s\n' "$OUTPUT" | grep -q '"status":"ok"'
printf '%s\n' "$OUTPUT" | grep -q '"file":"Demo-Regular.ttf"'

OUTPUT=$(LUOSHU_PUBLIC_DIR="$TMP/public" MODDIR="$ROOT" sh "$ROOT/common/app_bridge.sh" preview_source Demo 700)
printf '%s\n' "$OUTPUT" | grep -q '"file":"Demo-Bold.ttf"'

OUTPUT=$(LUOSHU_PUBLIC_DIR="$TMP/public" MODDIR="$ROOT" sh "$ROOT/common/app_bridge.sh" preview_source Demo 800)
printf '%s\n' "$OUTPUT" | grep -q '"file":"Demo-ExtraBold.ttf"'


printf only-bold > "$TMP/public/fonts/Only-Bold.ttf"
OUTPUT=$(LUOSHU_PUBLIC_DIR="$TMP/public" MODDIR="$ROOT" sh "$ROOT/common/app_bridge.sh" preview_source Only 400)
printf '%s\n' "$OUTPUT" | grep -q '"file":"Only-Bold.ttf"'

echo 'Native weighted preview source regression test passed.'
