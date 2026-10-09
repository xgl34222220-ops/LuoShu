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
printf 'weight=500\nadjustment=100\n' > "$MOD/config/font_weight.conf"
printf 'adjustment=-25\n' > "$MOD/config/font_weight_original.conf"
OUT=$(MODDIR="$MOD" LUOSHU_PUBLIC_DIR="$PUB" sh "$ROOT/system/bin/luoshu-backup" export-root "$STAGE")
printf '%s' "$OUT" | grep -q '"status":"ok"'
[ -f "$STAGE/root/fonts/Demo.ttf" ]
[ ! -e "$STAGE/root/config/font_weight.conf" ]
[ ! -e "$STAGE/root/config/font_weight_original.conf" ]
# Old archives may contain these retired settings; restoration must ignore them.
printf 'weight=700\nadjustment=300\n' > "$STAGE/root/config/font_weight.conf"
printf 'adjustment=10\n' > "$STAGE/root/config/font_weight_original.conf"
rm -rf "$PUB/fonts"; mkdir -p "$PUB/fonts"
OUT=$(MODDIR="$MOD" LUOSHU_PUBLIC_DIR="$PUB" sh "$ROOT/system/bin/luoshu-backup" restore-root "$STAGE")
printf '%s' "$OUT" | grep -q '"status":"ok"'
[ "$(cat "$PUB/fonts/Demo.ttf")" = 'font-bytes' ]
[ -f "$MOD/config/font_mix.conf" ]
grep -qx 'adjustment=100' "$MOD/config/font_weight.conf"
grep -qx 'adjustment=-25' "$MOD/config/font_weight_original.conf"
rm -f "$MOD/config/font_weight.conf" "$MOD/config/font_weight_original.conf"
OUT=$(MODDIR="$MOD" LUOSHU_PUBLIC_DIR="$PUB" sh "$ROOT/system/bin/luoshu-backup" restore-root "$STAGE")
printf '%s' "$OUT" | grep -q '"status":"ok"'
[ ! -e "$MOD/config/font_weight.conf" ]
[ ! -e "$MOD/config/font_weight_original.conf" ]
echo 'full backup root tests passed'
