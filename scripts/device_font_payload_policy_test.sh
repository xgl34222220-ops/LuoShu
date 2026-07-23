#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-policy)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MODULE="$TMP/module"
mkdir -p "$MODULE/config" "$MODULE/logs"
MODDIR="$MODULE"
MODULE_DIR="$MODULE"
LUOSHU_TRUSTED_TEMPLATE_KEY=fixture-template-key
export MODDIR MODULE_DIR LUOSHU_TRUSTED_TEMPLATE_KEY

CLEARS="$TMP/clears"
: > "$CLEARS"
device_font_payload_validate_installed() { return 0; }
device_font_payload_clear() { printf 'clear\n' >> "$CLEARS"; rm -f "$MODULE/config/device-font-engine.conf"; }

. "$ROOT/common/device_font_payload_policy.sh"

cat > "$MODULE/config/device-font-engine.conf" <<'EOF'
state=installed
font=SameFont
templateKey=fixture-template-key
EOF

device_font_payload_build_install SameFont
test ! -s "$CLEARS"

a=0
device_font_payload_build_install OtherFont || a=$?
test "$a" -eq 2
grep -qx clear "$CLEARS"
grep -q '设备缓存未命中' "$MODULE/logs/device-font-payload.log"

: > "$CLEARS"
cat > "$MODULE/config/device-font-engine.conf" <<'EOF'
state=installed
font=SameFont
templateKey=old-template-key
EOF

a=0
device_font_payload_build_install SameFont || a=$?
test "$a" -eq 2
grep -qx clear "$CLEARS"
grep -q '模板指纹变化' "$MODULE/logs/device-font-payload.log"

sh -n "$ROOT/common/device_font_payload_policy.sh"
echo 'Device font foreground policy tests passed.'