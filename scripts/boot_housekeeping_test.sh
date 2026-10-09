#!/bin/sh
# Post-boot cost control: native-index key, module.prop idempotence, log caps.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/scripts/assert.sh"
CASE='启动后维护降耗'

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MODULE="$TMP/module"
FONTS="$TMP/public/fonts"
mkdir -p "$MODULE/common" "$MODULE/config" "$MODULE/logs" "$FONTS"
cp "$ROOT/common/boot_housekeeping.sh" "$MODULE/common/"
cp "$ROOT/common/module_status.sh" "$MODULE/common/"
printf 'id=LuoShu\nversionCode=1\ndescription=old\n' > "$MODULE/module.prop"
printf 'font-a' > "$FONTS/A-Regular.ttf"

. "$MODULE/common/boot_housekeeping.sh"
LUOSHU_PUBLIC_DIR="$TMP/public"
export LUOSHU_PUBLIC_DIR

# Native index key: stable for identical inputs, changes with fonts/active/version.
K1=$(luoshu_native_index_boot_key "$MODULE" Alpha)
K2=$(luoshu_native_index_boot_key "$MODULE" Alpha)
ok test -n "$K1"
eq "$K2" "$K1"
ne "$(luoshu_native_index_boot_key "$MODULE" Beta)" "$K1"

# Missing index or missing key is never "fresh".
no luoshu_native_index_boot_fresh "$MODULE" "$K1"
printf '{"status":"ok","data":{}}\n' > "$MODULE/config/native_font_index.json"
no luoshu_native_index_boot_fresh "$MODULE" "$K1"
luoshu_native_index_boot_record "$MODULE" "$K1"
ok luoshu_native_index_boot_fresh "$MODULE" "$K1"
no luoshu_native_index_boot_fresh "$MODULE" ''

sleep 1
printf 'font-b-longer' > "$FONTS/B-Regular.ttf"
K3=$(luoshu_native_index_boot_key "$MODULE" Alpha)
ne "$K3" "$K1"
no luoshu_native_index_boot_fresh "$MODULE" "$K3"
sed -i 's/^versionCode=1$/versionCode=2/' "$MODULE/module.prop"
ne "$(luoshu_native_index_boot_key "$MODULE" Alpha)" "$K3"

# Unreadable public storage yields no key, so the caller falls back to prewarm.
LUOSHU_PUBLIC_DIR="$TMP/locked" no luoshu_native_index_boot_key "$MODULE" Alpha

# A bad index must not be treated as fresh even with the right key.
printf '{"status":"error"}\n' > "$MODULE/config/native_font_index.json"
luoshu_native_index_boot_record "$MODULE" "$K3"
no luoshu_native_index_boot_fresh "$MODULE" "$K3"

# module_status does not rewrite module.prop when the description is unchanged.
MODDIR="$MODULE" sh "$MODULE/common/module_status.sh" default >/dev/null
contains "$MODULE/module.prop" '当前字体：系统默认字体'
touch -d '2001-01-01 00:00:00' "$MODULE/module.prop"
BEFORE=$(stat -c %Y "$MODULE/module.prop")
MODDIR="$MODULE" sh "$MODULE/common/module_status.sh" default >/dev/null
eq "$(stat -c %Y "$MODULE/module.prop")" "$BEFORE"
MODDIR="$MODULE" sh "$MODULE/common/module_status.sh" Gamma >/dev/null
contains "$MODULE/module.prop" '当前字体：Gamma'

# Log caps: oversized log is trimmed to its newest lines, count is bounded,
# stale pid-suffixed scratch files are removed, fresh ones and real state kept.
i=0
while [ "$i" -lt 30000 ]; do printf 'line-%s padding padding padding\n' "$i"; i=$((i + 1)); done > "$MODULE/logs/big.log"
j=0
while [ "$j" -lt 50 ]; do printf 'x\n' > "$MODULE/logs/extra-$j.log"; touch -d "2001-01-01 00:00:$((j % 60))" "$MODULE/logs/extra-$j.log"; j=$((j + 1)); done
printf 'tmp' > "$MODULE/config/active_font.conf.tmp.123"
touch -d '2001-01-01 00:00:00' "$MODULE/config/active_font.conf.tmp.123"
printf 'tmp' > "$MODULE/config/fresh.conf.tmp.456"
printf 'Alpha\n' > "$MODULE/config/active_font.conf"
touch -d '2001-01-01 00:00:00' "$MODULE/config/active_font.conf"
luoshu_boot_housekeep "$MODULE"
SIZE=$(wc -c < "$MODULE/logs/big.log" | tr -d ' ')
ok test "$SIZE" -le 524288
contains "$MODULE/logs/big.log" 'line-29999'
COUNT=$(find "$MODULE/logs" -maxdepth 1 -type f | wc -l | tr -d ' ')
ok test "$COUNT" -le 40
ok test -f "$MODULE/logs/big.log"
no test -e "$MODULE/config/active_font.conf.tmp.123"
ok test -f "$MODULE/config/fresh.conf.tmp.456"
ok test -f "$MODULE/config/active_font.conf"

# Runtime-paths layout: config/logs are links into .luoshu-state; caps still apply.
M2="$TMP/m2"
mkdir -p "$M2/.luoshu-state/logs" "$M2/.luoshu-state/config"
ln -s .luoshu-state/logs "$M2/logs"
ln -s .luoshu-state/config "$M2/config"
k=0
while [ "$k" -lt 45 ]; do printf 'y\n' > "$M2/.luoshu-state/logs/l-$k.log"; k=$((k + 1)); done
luoshu_boot_housekeep "$M2"
COUNT=$(find "$M2/.luoshu-state/logs" -maxdepth 1 -type f | wc -l | tr -d ' ')
ok test "$COUNT" -le 40
ok test -L "$M2/logs"

# Settle delay is bounded and can be disabled.
LUOSHU_BOOT_SETTLE_SECONDS=0 luoshu_boot_settle
LUOSHU_BOOT_SETTLE_SECONDS=abc sh -c ". '$MODULE/common/boot_housekeeping.sh'; sleep() { echo \"\$1\"; }; luoshu_boot_settle" > "$TMP/settle"
eq "$(cat "$TMP/settle")" 25
LUOSHU_BOOT_SETTLE_SECONDS=999 sh -c ". '$MODULE/common/boot_housekeeping.sh'; sleep() { echo \"\$1\"; }; luoshu_boot_settle" > "$TMP/settle"
eq "$(cat "$TMP/settle")" 120

# Service contract: mount confirmation is written before any deferred work.
SERVICE="$ROOT/service.sh"
CONFIRM=$(grep -n 'font load confirmed' "$SERVICE" | head -n1 | cut -d: -f1)
SETTLE=$(grep -n 'luoshu_boot_settle' "$SERVICE" | head -n1 | cut -d: -f1)
LISTING=$(grep -n 'action list --native-index' "$SERVICE" | head -n1 | cut -d: -f1)
ok test "$CONFIRM" -lt "$SETTLE"
ok test "$SETTLE" -lt "$LISTING"
contains "$SERVICE" 'luoshu_native_index_boot_fresh'
contains "$SERVICE" 'luoshu_boot_housekeep'

echo 'boot housekeeping tests passed'
