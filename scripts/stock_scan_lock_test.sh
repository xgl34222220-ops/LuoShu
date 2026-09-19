#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-stock-lock)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/module"
mkdir -p "$MOD/common/python/bin" "$MOD/config" "$MOD/logs"
cp "$ROOT/common/font_manager.sh" "$MOD/common/font_manager.sh"
: > "$MOD/common/stock_inventory_scan.py"
: > "$MOD/common/font_inventory.py"
: > "$MOD/common/font_check.sh"
: > "$MOD/common/font_target_manifest.py"
chmod 0755 "$MOD/common/font_check.sh"

cat > "$MOD/common/python/bin/luoshu-python" <<'EOF_PY'
#!/bin/sh
script="$1"
shift
case "${script##*/}" in
  font_target_manifest.py)
    output=''
    list_output=''
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --output) shift; output="$1" ;;
        --list-output) shift; list_output="$1" ;;
      esac
      shift
    done
    [ -n "$output" ] && printf '%s\n' '{"schema":"device-font-target-manifest-v1","buildKey":"fixture","replaceableCount":2,"physicalCount":1,"targets":[]}' > "$output"
    [ -n "$list_output" ] && printf '%s\n' '# schema=device-font-target-manifest-v1' '# buildKey=fixture' > "$list_output"
    printf '%s\n' '{"status":"ok","replaceableCount":2,"physicalCount":1}'
    exit 0
    ;;
esac
mode=scan
output=''
while [ "$#" -gt 0 ]; do
    case "$1" in
        --validate) mode=validate ;;
        --output) shift; output="$1" ;;
    esac
    shift
done
if [ "$mode" = validate ]; then
    printf '{"status":"ok","slotCount":2,"mainSlot":"Roboto-Regular.ttf"}\n'
    exit 0
fi
printf 'scan\n' >> "${LUOSHU_SCAN_COUNT:?}"
sleep 2
printf '{"schema":"device-font-inventory-v1","state":"ready","buildKey":"fixture"}\n' > "$output"
printf '{"status":"ok","slotCount":2,"mainSlot":"Roboto-Regular.ttf"}\n'

EOF_PY
chmod 0755 "$MOD/common/python/bin/luoshu-python"

LUOSHU_SCAN_COUNT="$TMP/count" MODDIR="$MOD" sh "$MOD/common/font_manager.sh" action stock_scan >"$TMP/one" &
first=$!
tries=0
while [ ! -d "$MOD/.stock-inventory-scan.lock" ] && [ "$tries" -lt 30 ]; do
    sleep 1
    tries=$((tries + 1))
done
LUOSHU_SCAN_COUNT="$TMP/count" MODDIR="$MOD" sh "$MOD/common/font_manager.sh" action stock_scan >"$TMP/two" &
second=$!
wait "$first"
wait "$second"

grep -q '"status":"ok"' "$TMP/one"
grep -q '"status":"ok"' "$TMP/two"
test "$(wc -l < "$TMP/count" | tr -d '[:space:]')" -eq 1
test ! -e "$MOD/.stock-inventory-scan.lock"
echo 'Stock inventory scan is serialized and a waiting App reuses the completed boot scan.'
