#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/scripts/assert.sh"
CASE='设备对齐缓存'
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

ok grep -q 'source-contract-v5-content' "$ROOT/common/device_font_cache.sh"
ok grep -q 'alignment-cache-v5-content' "$ROOT/common/device_font_cache.sh"
! device_font_cache_lookup MissingFont >/dev/null 2>&1

CASE='设备缓存键只认字体内容'
FIRST_SOURCE_KEY=$(_dfcache_source_key)
cp "$MODULE/system/fonts/.luoshu-font-store/regular.font" "$TMP/recreated.font"
rm -f "$MODULE/system/fonts/.luoshu-font-store/regular.font"
mv "$TMP/recreated.font" "$MODULE/system/fonts/.luoshu-font-store/regular.font"
touch "$MODULE/system/fonts/.luoshu-font-store/regular.font"
SECOND_SOURCE_KEY=$(_dfcache_source_key)
eq "$SECOND_SOURCE_KEY" "$FIRST_SOURCE_KEY"
printf 'font-date\n' > "$MODULE/system/fonts/.luoshu-font-store/regular.font"
THIRD_SOURCE_KEY=$(_dfcache_source_key)
ne "$THIRD_SOURCE_KEY" "$FIRST_SOURCE_KEY"
printf 'font-data\n' > "$MODULE/system/fonts/.luoshu-font-store/regular.font"
eq "$(_dfcache_source_key)" "$FIRST_SOURCE_KEY"

CASE='v4 设备缓存无损升级为内容键'
V4_SOURCE_KEY=$(_dfcache_source_key_v4)
V4_CACHE_ID=$(_dfcache_id_v4 DemoFont trusted-key "$V4_SOURCE_KEY")
V4_CACHE="$MODULE/config/device-font-cache/$V4_CACHE_ID"
mkdir -p "$V4_CACHE/payload" "$V4_CACHE/overlay"
printf '{}\n' > "$V4_CACHE/payload/manifest.json"
printf '{}\n' > "$V4_CACHE/overlay/overlay-manifest.json"
cat > "$V4_CACHE/cache.conf" <<EOF_V4_CACHE
state=ready
font=DemoFont
cacheId=$V4_CACHE_ID
templateKey=trusted-key
sourceKey=$V4_SOURCE_KEY
EOF_V4_CACHE
V5_CACHE_ID=$(_dfcache_id DemoFont trusted-key "$FIRST_SOURCE_KEY")
V5_CACHE="$MODULE/config/device-font-cache/$V5_CACHE_ID"
eq "$(device_font_cache_lookup DemoFont)" "$V5_CACHE"
ok grep -q "^sourceKey=$FIRST_SOURCE_KEY$" "$V5_CACHE/cache.conf"

_dfcache_foreground_idle
touch "$MODULE/.font_switch.lock"
! _dfcache_foreground_idle
rm -f "$MODULE/.font_switch.lock"
mkdir "$MODULE/config/.payload-transaction.fixture"
! _dfcache_foreground_idle
rmdir "$MODULE/config/.payload-transaction.fixture"
_dfcache_foreground_idle

device_font_cache_schedule DemoFont
PENDING="$MODULE/config/device-font-cache-pending.conf"
ok grep -q '^state=pending$' "$PENDING"
ok grep -q '^font=DemoFont$' "$PENDING"
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

ok test "$(device_font_cache_lookup DemoFont)" = "$CACHE"
device_font_cache_activate DemoFont
ok grep -qx "$CACHE/overlay" "$INSTALLS"
ok grep -q '^state=installed$' "$MODULE/config/device-font-engine.conf"
ok grep -q '^templateKey=trusted-key$' "$MODULE/config/device-font-engine.conf"
ok grep -q '^planRevision=2$' "$MODULE/config/device-font-engine.conf"
no test -e "$PENDING"

sh -n "$ROOT/common/device_font_cache.sh"
echo 'Device font cache tests passed.'
