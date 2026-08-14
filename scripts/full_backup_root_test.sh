#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BASE=/tmp/luoshu-full-backup-test/$$
MOD="$BASE/module"; PUB="$BASE/public"; STAGE="$BASE/stage"
trap 'rm -rf "$BASE"' EXIT
mkdir -p "$MOD/config" "$PUB/fonts" "$STAGE"
printf 'font-bytes' > "$PUB/fonts/Demo.ttf"
printf 'name=Demo\n' > "$PUB/fonts/Demo.conf"
printf 'cjk=A\nlatin=B\ndigit=C\n' > "$MOD/config/font_mix.conf"
OUT=$(MODDIR="$MOD" LUOSHU_PUBLIC_DIR="$PUB" sh "$ROOT/system/bin/luoshu-backup" export-root "$STAGE")
printf '%s' "$OUT" | grep -q '"status":"ok"'
[ -f "$STAGE/root/fonts/Demo.ttf" ]
rm -rf "$PUB/fonts"; mkdir -p "$PUB/fonts"
OUT=$(MODDIR="$MOD" LUOSHU_PUBLIC_DIR="$PUB" sh "$ROOT/system/bin/luoshu-backup" restore-root "$STAGE")
printf '%s' "$OUT" | grep -q '"status":"ok"'
[ "$(cat "$PUB/fonts/Demo.ttf")" = 'font-bytes' ]
[ -f "$MOD/config/font_mix.conf" ]
echo 'full backup root tests passed'
