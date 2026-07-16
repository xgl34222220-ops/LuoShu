#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-db-test)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MOD="$TMP/modules_update/LuoShu"
mkdir -p "$MOD/common" "$MOD/config" "$TMP/system/fonts"
cp "$ROOT/common/db_engine" "$MOD/common/db_engine"
printf 'direct\n' > "$MOD/config/mount_mode.conf"
printf 'DemoFont\n' > "$MOD/config/active_font.conf"
printf 'font-data-for-test-abcdefghijklmnopqrstuvwxyz\n' > "$TMP/source.ttf"
# Ensure test source passes minimum-size validation.
i=0
while [ "$(wc -c < "$TMP/source.ttf")" -lt 2048 ]; do
    printf '0123456789abcdef0123456789abcdef\n' >> "$TMP/source.ttf"
    i=$((i + 1))
done
printf 'rom-target\n' > "$TMP/system/fonts/Roboto-Regular.ttf"

test "$(MODDIR="$MOD" sh "$MOD/common/db_engine" mode)" = direct
test "$(MODDIR="$MOD" LUOSHU_DB_MODE=module sh "$MOD/common/db_engine" mode)" = module

MODDIR="$MOD" LUOSHU_DB_MODE=direct sh -c '
    . "$MODDIR/common/db_engine"
    luoshu_db_begin
    luoshu_db_add "$1" "$2"
    luoshu_db_add "$1" "$2"
    luoshu_db_finish
' sh "$TMP/source.ttf" "$TMP/system/fonts/Roboto-Regular.ttf"

MAP="$MOD/direct_map/current.map"
test -s "$MAP"
test "$(wc -l < "$MAP" | tr -d ' ')" = 1
! grep -q "$MOD" "$MAP"
REL=$(cut -d'|' -f1 "$MAP")
test -s "$MOD/direct_map/gens/$REL"
grep -q '^mode=direct$' "$MOD/config/direct_map_status.conf"
grep -q '^targets=1$' "$MOD/config/direct_map_status.conf"

# The manifest must remain valid when the installed module path changes.
INST="$TMP/modules/LuoShu"
mkdir -p "$TMP/modules"
mv "$MOD" "$INST"
REL2=$(cut -d'|' -f1 "$INST/direct_map/current.map")
test -s "$INST/direct_map/gens/$REL2"

printf 'default\n' > "$INST/config/active_font.conf"
MODDIR="$INST" LUOSHU_DB_MODE=direct sh "$INST/common/db_engine" apply

echo "Direct map tests passed."
