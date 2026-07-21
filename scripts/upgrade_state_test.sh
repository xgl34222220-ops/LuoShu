#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
OLD="$TMP/old"
NEW="$TMP/new"
mkdir -p "$OLD/config" "$OLD/system/fonts/.luoshu-font-store" "$OLD/product/fonts" "$NEW/config"
printf 'id=LuoShu\n' > "$OLD/module.prop"
printf 'DemoFamily\n' > "$OLD/config/active_font.conf"
printf 'adjustment=25\n' > "$OLD/config/font_weight.conf"
printf 'recent\n' > "$OLD/config/recent_fonts.conf"
printf 'regular\n' > "$OLD/system/fonts/Roboto-Regular.ttf"
printf 'anchor\n' > "$OLD/system/fonts/.luoshu-font-store/wght-400.font"
printf 'product\n' > "$OLD/product/fonts/GoogleSans-Regular.ttf"
printf 'emoji\n' > "$OLD/system/fonts/NotoColorEmoji.ttf"
printf 'clock\n' > "$OLD/system/fonts/AndroidClock.ttf"

. "$ROOT/common/upgrade_state.sh"
luoshu_migrate_upgrade_state "$OLD" "$NEW"

test "$LUOSHU_UPGRADE_ACTIVE_FONT" = DemoFamily
test "$LUOSHU_UPGRADE_PAYLOAD_COUNT" -eq 3
test "$(cat "$NEW/config/active_font.conf")" = DemoFamily
test "$(cat "$NEW/config/font_weight.conf")" = 'adjustment=25'
test -f "$NEW/system/fonts/Roboto-Regular.ttf"
test -f "$NEW/system/fonts/.luoshu-font-store/wght-400.font"
test -f "$NEW/product/fonts/GoogleSans-Regular.ttf"
test ! -e "$NEW/system/fonts/NotoColorEmoji.ttf"
test ! -e "$NEW/system/fonts/AndroidClock.ttf"

EMPTY_OLD="$TMP/empty-old"
EMPTY_NEW="$TMP/empty-new"
mkdir -p "$EMPTY_OLD/config" "$EMPTY_NEW/config"
printf 'id=LuoShu\n' > "$EMPTY_OLD/module.prop"
printf 'MissingFamily\n' > "$EMPTY_OLD/config/active_font.conf"
luoshu_migrate_upgrade_state "$EMPTY_OLD" "$EMPTY_NEW"
test "$LUOSHU_UPGRADE_ACTIVE_FONT" = default
test "$LUOSHU_UPGRADE_PAYLOAD_COUNT" -eq 0
test "$(cat "$EMPTY_NEW/config/active_font.conf")" = default

# Geometry algorithm upgrades must invalidate the old source-hash-only composite cache. Otherwise
# selecting the same three fonts after an update silently reuses the pre-fix output.
grep -q 'cache/auto-multiweight-mix/composites-v1' "$ROOT/customize.sh"
grep -q "printf 'geometry-v2" "$ROOT/customize.sh"

printf 'Upgrade state migration tests passed.\n'
