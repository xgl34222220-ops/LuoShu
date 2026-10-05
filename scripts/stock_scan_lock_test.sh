#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-stock-lock)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/module"
mkdir -p "$MOD/common/python/bin" "$MOD/config" "$MOD/logs"
cp "$ROOT/common/font_manager.sh" "$MOD/common/font_manager.sh"
for helper in task_scope.sh task_scope.py runtime_paths.sh runtime_paths_lock.py; do
    cp "$ROOT/common/$helper" "$MOD/common/$helper"
done
LUOSHU_TASK_SCOPE_PYTHON=$(command -v python3)
LUOSHU_RUNTIME_PATHS_PYTHON="$LUOSHU_TASK_SCOPE_PYTHON"
export LUOSHU_TASK_SCOPE_PYTHON LUOSHU_RUNTIME_PATHS_PYTHON
: > "$MOD/common/stock_inventory_scan.py"
: > "$MOD/common/font_inventory.py"
: > "$MOD/common/font_check.sh"
chmod 0755 "$MOD/common/font_check.sh"

cat > "$MOD/common/python/bin/luoshu-python" <<'EOF_PY'
#!/bin/sh
shift
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
printf '{"schema":"device-font-inventory-v1","state":"ready"}\n' > "$output"
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
test -z "$(find "$MOD/.luoshu-state/tasks" -name '*.owner.json' -print)"
python3 - "$MOD/.luoshu-state/tasks" <<'PY'
import json, pathlib, sys
proofs = list(pathlib.Path(sys.argv[1]).glob('*.cleanup.json'))
assert len(proofs) == 2, proofs
assert all((p := json.loads(path.read_text()))['cleaned'] and not p['leftoverPids'] for path in proofs)
PY
echo 'Stock inventory scan is serialized and a waiting App reuses the completed boot scan.'
