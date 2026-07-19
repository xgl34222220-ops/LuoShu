#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-font-cache)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

USER_FONTS_DIR="$TMP/fonts"
CONFIG_DIR="$TMP/config"
ACTIVE_FONT_CONF="$CONFIG_DIR/active_font.conf"
mkdir -p "$USER_FONTS_DIR" "$CONFIG_DIR"

json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
}

. "$ROOT/common/font_library_cache.sh"

printf 'font-one' > "$USER_FONTS_DIR/One-Regular.ttf"
printf 'font-two' > "$USER_FONTS_DIR/Two.otf"
printf 'One\n' > "$ACTIVE_FONT_CONF"

FIRST=$(font_library_fingerprint_value)
SECOND=$(font_library_fingerprint_value)
test "$FIRST" = "$SECOND"
printf '%s' "$FIRST" | grep -q '^v2:'
printf '%s' "$FIRST" | grep -q ':2:'

JSON=$(font_library_fingerprint_json)
printf '%s' "$JSON" | grep -q '"status":"ok"'
printf '%s' "$JSON" | grep -q '"current":"One"'
printf '%s' "$JSON" | grep -q '"count":2'

sleep 1
printf 'font-one-modified' > "$USER_FONTS_DIR/One-Regular.ttf"
MODIFIED=$(font_library_fingerprint_value)
test "$MODIFIED" != "$FIRST"
printf '%s' "$MODIFIED" | grep -q ':2:'

printf 'font-three' > "$USER_FONTS_DIR/Three.ttc"
ADDED=$(font_library_fingerprint_value)
test "$ADDED" != "$MODIFIED"
printf '%s' "$ADDED" | grep -q ':3:'

rm -f "$USER_FONTS_DIR/Two.otf"
REMOVED=$(font_library_fingerprint_value)
test "$REMOVED" != "$ADDED"
printf '%s' "$REMOVED" | grep -q ':2:'

# ROM 内部映射字体不属于用户字体库索引。
printf 'internal' > "$USER_FONTS_DIR/SysFont-Regular.ttf"
INTERNAL=$(font_library_fingerprint_value)
test "$INTERNAL" = "$REMOVED"

printf 'Font library fingerprint tests passed.\n'
