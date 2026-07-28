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
printf '%s' "$FIRST" | grep -q '^v3:'
printf '%s' "$FIRST" | grep -q ':2:'

JSON=$(font_library_fingerprint_json)
printf '%s' "$JSON" | grep -q '"status":"ok"'
printf '%s' "$JSON" | grep -q '"current":"One"'
printf '%s' "$JSON" | grep -q '"count":2'

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

printf 'internal' > "$USER_FONTS_DIR/SysFont-Regular.ttf"
INTERNAL=$(font_library_fingerprint_value)
test "$INTERNAL" = "$REMOVED"

DIRECT_MOD="$TMP/direct-module"
DIRECT_PUBLIC="$TMP/direct-public"
PLAN_MARKER="$TMP/plan-called"
mkdir -p "$DIRECT_MOD/common" "$DIRECT_MOD/config" "$DIRECT_PUBLIC/fonts"
cp "$ROOT/common/font_library_cache.sh" "$DIRECT_MOD/common/font_library_cache.sh"
printf 'One\n' > "$DIRECT_MOD/config/active_font.conf"
printf 'font-one' > "$DIRECT_PUBLIC/fonts/One-Regular.ttf"
cat > "$DIRECT_MOD/common/device_font_template.sh" <<'EOF_TEMPLATE'
#!/bin/sh
exit 0
EOF_TEMPLATE
cat > "$DIRECT_MOD/common/device_font_slot_plan.sh" <<EOF_PLANNER
#!/bin/sh
printf 'called\n' > "$PLAN_MARKER"
exit 0
EOF_PLANNER
chmod +x "$DIRECT_MOD/common/device_font_template.sh" "$DIRECT_MOD/common/device_font_slot_plan.sh"

MODDIR="$DIRECT_MOD" LUOSHU_PUBLIC_DIR="$DIRECT_PUBLIC" sh "$DIRECT_MOD/common/font_library_cache.sh" value >/dev/null
sleep 0.2
test ! -e "$PLAN_MARKER"
MODDIR="$DIRECT_MOD" LUOSHU_PUBLIC_DIR="$DIRECT_PUBLIC" sh "$DIRECT_MOD/common/font_library_cache.sh" fingerprint >/dev/null
sleep 0.2
test ! -e "$PLAN_MARKER"
MODDIR="$DIRECT_MOD" LUOSHU_PUBLIC_DIR="$DIRECT_PUBLIC" sh "$DIRECT_MOD/common/font_library_cache.sh" prepare-plan >/dev/null
test -e "$PLAN_MARKER"

printf 'Font library fingerprint tests passed.\n'
