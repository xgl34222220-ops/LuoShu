#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

MOD="$TMP/module"
BIN="$TMP/bin"
COUNT="$TMP/count"
NSLOG="$TMP/nsenter.log"
mkdir -p "$MOD/common/python/bin" "$MOD/config" "$MOD/logs" "$BIN"
cp "$ROOT/common/font_manager.sh" "$MOD/common/font_manager.sh"
: > "$MOD/common/stock_inventory_scan.py"
: > "$MOD/common/font_inventory.py"
: > "$MOD/common/font_check.sh"

cat > "$MOD/common/python/bin/luoshu-python" <<'EOF_PY'
#!/bin/sh
count_file="$LUOSHU_SCAN_COUNT"
count=$(cat "$count_file" 2>/dev/null || echo 0)
count=$((count + 1))
printf '%s\n' "$count" > "$count_file"
out=''
prev=''
for arg in "$@"; do
    if [ "$prev" = --output ]; then out="$arg"; fi
    prev="$arg"
done
[ -n "$out" ] || exit 2
mkdir -p "${out%/*}"
cat > "$out" <<'EOF_JSON'
{"schema":"device-font-inventory-v1","state":"ready","buildKey":"fixture","romKind":"hyperos","slots":{"/system/fonts/Roboto-Regular.ttf":{"format":"TTF"}}}
EOF_JSON
printf '%s\n' '{"status":"ok","slotCount":1,"mainSlot":"Roboto-Regular.ttf","romKind":"hyperos"}'
EOF_PY
chmod 0755 "$MOD/common/python/bin/luoshu-python"

cat > "$BIN/nsenter" <<'EOF_NS'
#!/bin/sh
printf 'nsenter\n' >> "$LUOSHU_NS_LOG"
while [ "$#" -gt 0 ] && [ "$1" != -- ]; do shift; done
[ "$#" -gt 0 ] && shift
exec "$@"
EOF_NS
chmod 0755 "$BIN/nsenter"

printf '0\n' > "$COUNT"
LUOSHU_SCAN_COUNT="$COUNT" \
LUOSHU_NS_LOG="$NSLOG" \
LUOSHU_STOCK_SCAN_NSENTER="$BIN/nsenter" \
LUOSHU_STOCK_SCAN_ANDROID_SHELL="$(command -v sh)" \
LUOSHU_STOCK_SCAN_FORCE_NAMESPACE=1 \
MODDIR="$MOD" \
sh "$MOD/common/font_manager.sh" action stock_scan > "$TMP/global.out"

grep -q '"status":"ok"' "$TMP/global.out"
[ "$(cat "$COUNT")" = 1 ]
[ "$(wc -l < "$NSLOG" | tr -d ' ')" = 1 ]
[ -s "$MOD/config/device_font_inventory.json" ]

cat > "$BIN/nsenter-fail" <<'EOF_FAIL'
#!/bin/sh
exit 126
EOF_FAIL
chmod 0755 "$BIN/nsenter-fail"
rm -f "$MOD/config/device_font_inventory.json"
printf '0\n' > "$COUNT"

LUOSHU_SCAN_COUNT="$COUNT" \
LUOSHU_NS_LOG="$NSLOG" \
LUOSHU_STOCK_SCAN_NSENTER="$BIN/nsenter-fail" \
LUOSHU_STOCK_SCAN_ANDROID_SHELL="$(command -v sh)" \
LUOSHU_STOCK_SCAN_FORCE_NAMESPACE=1 \
MODDIR="$MOD" \
sh "$MOD/common/font_manager.sh" action stock_scan > "$TMP/fallback.out"

grep -q '"status":"ok"' "$TMP/fallback.out"
[ "$(cat "$COUNT")" = 1 ]
[ -s "$MOD/config/device_font_inventory.json" ]

echo 'Stock scan namespace broker tests passed.'
