#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ -d "$ROOT/common/python/lib/python3.14/site-packages" ]; then
    PYTHONPATH="$ROOT/common/python/lib/python3.14/site-packages${PYTHONPATH:+:$PYTHONPATH}"
    export PYTHONPATH
fi
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

export MODULE_DIR="$TMP/module"
export MODDIR="$MODULE_DIR"
mkdir -p "$MODULE_DIR/common" "$MODULE_DIR/config" "$MODULE_DIR/system/fonts"
cp "$ROOT/common/font_inventory.py" "$MODULE_DIR/common/font_inventory.py"
cp "$1" "$TMP/source.ttf"

cat > "$MODULE_DIR/config/device_font_inventory.json" <<'JSON'
{
  "schema": "device-font-inventory-v1",
  "inventoryRevision": 1,
  "state": "ready",
  "buildKey": "test-rom",
  "slotCount": 3,
  "slots": {
    "/system/fonts/MiSansVF.ttf": {
      "slotName": "MiSansVF.ttf",
      "path": "/system/fonts/MiSansVF.ttf",
      "partition": "system",
      "format": "TTF",
      "weight": 400,
      "style": "normal",
      "source": "heuristic",
      "metrics": {"upem": 2048, "hhea": {"ascent": 1900, "descent": -500}}
    },
    "/system_ext/fonts/GoogleSansText-Regular.ttf": {
      "slotName": "GoogleSansText-Regular.ttf",
      "path": "/system_ext/fonts/GoogleSansText-Regular.ttf",
      "partition": "system_ext",
      "format": "TTF",
      "weight": 400,
      "style": "normal",
      "source": "heuristic",
      "metrics": {"upem": 2048, "hhea": {"ascent": 1900, "descent": -500}}
    },
    "/product/fonts/400.ttf": {
      "slotName": "400.ttf",
      "path": "/product/fonts/400.ttf",
      "partition": "product",
      "format": "TTF",
      "weight": 400,
      "style": "normal",
      "source": "heuristic",
      "metrics": {"upem": 2048, "hhea": {"ascent": 1900, "descent": -500}}
    }
  },
  "mainSlot": {
    "slotName": "MiSansVF.ttf",
    "path": "/system/fonts/MiSansVF.ttf",
    "partition": "system",
    "format": "TTF",
    "weight": 400,
    "style": "normal",
    "source": "heuristic",
    "metrics": {"upem": 2048, "hhea": {"ascent": 1900, "descent": -500}}
  }
}
JSON

# shellcheck disable=SC1090
. "$ROOT/common/rom_adapters.sh"
IS_HYPEROS=true
IS_COLOROS=false
export IS_HYPEROS IS_COLOROS

apply_font_by_rom "$TMP/source.ttf" "$MODULE_DIR/system/fonts" quick TestFamily

test -s "$MODULE_DIR/system/fonts/MiSansVF.ttf"
test -s "$MODULE_DIR/system_ext/fonts/GoogleSansText-Regular.ttf"
test -s "$MODULE_DIR/product/fonts/400.ttf"
anchor="$MODULE_DIR/system/fonts/.luoshu-font-store/regular.font"
test -s "$anchor"
inode=$(stat -c '%d:%i' "$anchor")
for file in \
  "$MODULE_DIR/system/fonts/MiSansVF.ttf" \
  "$MODULE_DIR/system_ext/fonts/GoogleSansText-Regular.ttf" \
  "$MODULE_DIR/product/fonts/400.ttf"; do
  test "$(stat -c '%d:%i' "$file")" = "$inode"
done

test "${LUOSHU_INVENTORY_TARGETS_MAPPED:-0}" = 1
cp "$MODULE_DIR/config/device_font_inventory.json" "$TMP/valid-inventory.json"

# The foreground policy overrides the dispatcher later in the bootstrap chain; it must keep the
# same inventory-first behavior for quick and full modes.
# shellcheck disable=SC1090
. "$ROOT/common/device_font_payload_policy.sh"
font_config_enable_for_payload() { return 0; }
cp "$TMP/valid-inventory.json" "$MODULE_DIR/config/device_font_inventory.json"
rm -rf "$MODULE_DIR/system_ext" "$MODULE_DIR/product"
apply_font_by_rom "$TMP/source.ttf" "$MODULE_DIR/system/fonts" quick TestFamily
test -s "$MODULE_DIR/system_ext/fonts/GoogleSansText-Regular.ttf"
test -s "$MODULE_DIR/product/fonts/400.ttf"

rm -rf "$MODULE_DIR/system_ext" "$MODULE_DIR/product"
apply_font_by_rom "$TMP/source.ttf" "$MODULE_DIR/system/fonts" full TestFamily
test -s "$MODULE_DIR/system_ext/fonts/GoogleSansText-Regular.ttf"
test -s "$MODULE_DIR/product/fonts/400.ttf"

# Malformed inventory must not block untested devices: the existing static mapper is the fallback.
printf '%s\n' '{"schema":"broken"}' > "$MODULE_DIR/config/device_font_inventory.json"
_device_font_fast_map() { touch "$TMP/quick-static-fallback"; return 0; }
copy_as_hyperos() { touch "$TMP/full-static-fallback"; return 0; }
apply_font_by_rom "$TMP/source.ttf" "$MODULE_DIR/system/fonts" quick TestFamily
test -e "$TMP/quick-static-fallback"
apply_font_by_rom "$TMP/source.ttf" "$MODULE_DIR/system/fonts" full TestFamily
test -e "$TMP/full-static-fallback"

echo 'rom_adapter_inventory_test: PASS'
