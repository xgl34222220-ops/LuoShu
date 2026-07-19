#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
mkdir -p "$TMP/public/fonts"

# 同一字体族存在多档时，预览必须稳定选择 Regular，不能依赖目录遍历顺序。
printf regular > "$TMP/public/fonts/Demo-Regular.ttf"
printf bold > "$TMP/public/fonts/Demo-Bold.ttf"
OUTPUT=$(LUOSHU_PUBLIC_DIR="$TMP/public" MODDIR="$ROOT" sh "$ROOT/common/app_bridge.sh" preview_source Demo)
printf '%s\n' "$OUTPUT" | grep -q '"status":"ok"'
printf '%s\n' "$OUTPUT" | grep -q '"file":"Demo-Regular.ttf"'

# 没有 Regular 时才允许使用可用的其他档位。
printf only-bold > "$TMP/public/fonts/Only-Bold.ttf"
OUTPUT=$(LUOSHU_PUBLIC_DIR="$TMP/public" MODDIR="$ROOT" sh "$ROOT/common/app_bridge.sh" preview_source Only)
printf '%s\n' "$OUTPUT" | grep -q '"file":"Only-Bold.ttf"'

echo 'Native preview source regression test passed.'
