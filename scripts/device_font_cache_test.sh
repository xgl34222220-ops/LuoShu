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
printf '{"schema":"device-font-inventory-v1","state":"ready","buildKey":"fixture","slotCount":0,"slots":{},"mainSlot":{"slotName":"Fixture.ttf","path":"/system/fonts/Fixture.ttf","partition":"system","format":"TTF","weight":400,"style":"normal","source":"fixture","metrics":{"upem":1000,"hhea":{"ascent":800,"descent":-200}}}}\n' > "$MODULE/config/device_font_inventory.json"
printf 'system\n' > "$MODULE/config/device_font_partitions.conf"
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
_dfpr_install_overlay() {
    printf '%s\n' "$1" >> "$INSTALLS"
    printf 'file|system/fonts/X.ttf|hash|1024\n' > "$MODULE/config/device-font-installed.conf"
}
device_font_payload_validate_installed() { return 0; }

. "$ROOT/common/device_font_cache.sh"

ok grep -q 'source-contract-v5-content' "$ROOT/common/device_font_cache.sh"
ok grep -q 'alignment-cache-v6-inventory' "$ROOT/common/device_font_cache.sh"
! device_font_cache_lookup MissingFont >/dev/null 2>&1

CASE='设备缓存键认字体内容与本机清单'
FIRST_SOURCE_KEY=$(_dfcache_source_key)
FIRST_INVENTORY_KEY=$(_dfcache_inventory_key)
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

printf 'system\nproduct\n' > "$MODULE/config/device_font_partitions.conf"
SECOND_INVENTORY_KEY=$(_dfcache_inventory_key)
ne "$SECOND_INVENTORY_KEY" "$FIRST_INVENTORY_KEY"
printf 'system\n' > "$MODULE/config/device_font_partitions.conf"
eq "$(_dfcache_inventory_key)" "$FIRST_INVENTORY_KEY"

CASE='旧设备缓存没有 inventory proof 不得晋升'
OLD_CACHE="$MODULE/config/device-font-cache/legacy-cache"
mkdir -p "$OLD_CACHE/payload" "$OLD_CACHE/overlay"
printf '{}\n' > "$OLD_CACHE/payload/manifest.json"
printf '{}\n' > "$OLD_CACHE/overlay/overlay-manifest.json"
cat > "$OLD_CACHE/cache.conf" <<EOF_OLD
state=ready
font=DemoFont
cacheId=legacy-cache
templateKey=trusted-key
sourceKey=$FIRST_SOURCE_KEY
EOF_OLD
! device_font_cache_lookup DemoFont >/dev/null 2>&1

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
ok grep -q "^inventoryKey=$FIRST_INVENTORY_KEY$" "$PENDING"
CACHE_ID=$(sed -n 's/^cacheId=//p' "$PENDING")
SOURCE_KEY=$(sed -n 's/^sourceKey=//p' "$PENDING")
INVENTORY_KEY=$(sed -n 's/^inventoryKey=//p' "$PENDING")
CACHE="$MODULE/config/device-font-cache/$CACHE_ID"
mkdir -p "$CACHE/payload" "$CACHE/overlay"
printf '{}\n' > "$CACHE/payload/manifest.json"
printf '{}\n' > "$CACHE/overlay/overlay-manifest.json"
cat > "$CACHE/cache.conf" <<EOF_CACHE
state=ready
font=DemoFont
cacheId=$CACHE_ID
templateKey=trusted-key
sourceKey=$SOURCE_KEY
inventoryKey=$INVENTORY_KEY
EOF_CACHE

ok test "$(device_font_cache_lookup DemoFont)" = "$CACHE"

CASE='扫描清单变化必须拒绝旧设备缓存'
printf 'system\nproduct\n' > "$MODULE/config/device_font_partitions.conf"
! device_font_cache_lookup DemoFont >/dev/null 2>&1
printf 'system\n' > "$MODULE/config/device_font_partitions.conf"
ok test "$(device_font_cache_lookup DemoFont)" = "$CACHE"

device_font_cache_activate DemoFont
ok grep -qx "$CACHE/overlay" "$INSTALLS"
ok grep -q '^state=installed$' "$MODULE/config/device-font-engine.conf"
ok grep -q '^templateKey=trusted-key$' "$MODULE/config/device-font-engine.conf"
ok grep -q "^inventoryKey=$FIRST_INVENTORY_KEY$" "$MODULE/config/device-font-engine.conf"
ok grep -q '^planRevision=3$' "$MODULE/config/device-font-engine.conf"
ok grep -q '^slotTraceRevision=1$' "$MODULE/config/device-font-engine.conf"
no test -e "$PENDING"

sh -n "$ROOT/common/device_font_cache.sh"
echo 'Device font cache tests passed.'
