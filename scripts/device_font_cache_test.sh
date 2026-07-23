#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-cache)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MODULE="$TMP/module"
mkdir -p "$MODULE/common" "$MODULE/config" "$MODULE/logs" "$MODULE/system/fonts/.luoshu-font-store"
printf 'font-data\n' > "$MODULE/system/fonts/.luoshu-font-store/regular.font"
printf 'trusted-key\n' > "$MODULE/config/device-font-template.key"
cat > "$MODULE/common/device_font_template.sh" <<'EOF'
#!/bin/sh
[ "${1:-}" = trusted ]
EOF
chmod 0755 "$MODULE/common/device_font_template.sh"

MODDIR="$MODULE"
MODULE_DIR="$MODULE"
LUOSHU_CACHE_AUTOSTART=0
export MODDIR MODULE_DIR LUOSHU_CACHE_AUTOSTART
INSTALLS="$TMP/installs"
: > "$INSTALLS"
_dfpr_install_overlay() { printf '%s\n' "$1" >> "$INSTALLS"; printf 'file|system/fonts/X.ttf|hash|1024\n' > "$MODULE/config/device-font-installed.conf"; }
device_font_payload_validate_installed() { return 0; }

. "$ROOT/common/device_font_cache.sh"

device_font_cache_schedule DemoFont
PENDING="$MODULE/config/device-font-cache-pending.conf"
grep -q '^state=pending$' "$PENDING"
grep -q '^font=DemoFont$' "$PENDING"
CACHE_ID=$(sed -n 's/^cacheId=//p' "$PENDING")
SOURCE_KEY=$(sed -n 's/^sourceKey=//p' "$PENDING")
CACHE="$MODULE/config/device-font-cache/$CACHE_ID"
mkdir -p "$CACHE/payload" "$CACHE/overlay"
printf '{}\n' > "$CACHE/payload/manifest.json"
printf '{}\n' > "$CACHE/overlay/overlay-manifest.json"
cat > "$CACHE/cache.conf" <<EOF
state=ready
font=DemoFont
cacheId=$CACHE_ID
templateKey=trusted-key
sourceKey=$SOURCE_KEY
EOF

test "$(device_font_cache_lookup DemoFont)" = "$CACHE"
device_font_cache_activate DemoFont
grep -qx "$CACHE/overlay" "$INSTALLS"
grep -q '^state=installed$' "$MODULE/config/device-font-engine.conf"
grep -q '^templateKey=trusted-key$' "$MODULE/config/device-font-engine.conf"
grep -q '^planRevision=2$' "$MODULE/config/device-font-engine.conf"
test ! -e "$PENDING"

sh -n "$ROOT/common/device_font_cache.sh"
echo 'Device font cache tests passed.'