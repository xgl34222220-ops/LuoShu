#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MOD="$TMP/module"
PY="$MOD/common/python/bin/luoshu-python"
PLANNER="$MOD/common/device_font_slot_plan.py"
SOURCE="$TMP/font.ttf"
COUNT="$TMP/run-count"
mkdir -p "$MOD/common/python/bin" "$MOD/config" "$MOD/logs"
cp "$ROOT/common/device_font_slot_plan.sh" "$MOD/common/device_font_slot_plan.sh"
printf '{"slots":[]}\n' > "$MOD/config/device-font-template.json"
printf '# fake planner\n' > "$PLANNER"
printf 'font-v1\n' > "$SOURCE"

cat > "$PY" <<EOF_PY
#!/bin/sh
shift
output=''
while [ "\$#" -gt 0 ]; do
    case "\$1" in
        --output) output="\$2"; shift 2 ;;
        *) shift ;;
    esac
done
count=\$(cat "$COUNT" 2>/dev/null || echo 0)
count=\$((count + 1))
printf '%s\n' "\$count" > "$COUNT"
if [ -f "$TMP/slow" ]; then
    sleep 5
fi
printf '{"ok":true}\n' > "\$output"
printf 'planned\n'
EOF_PY
chmod +x "$PY" "$MOD/common/device_font_slot_plan.sh"

MODDIR="$MOD" LUOSHU_SLOT_PLAN_TIMEOUT_SECONDS=30 sh "$MOD/common/device_font_slot_plan.sh" build "$SOURCE" Demo
test "$(cat "$COUNT")" = 1
test -s "$MOD/config/active-font-slot-plan.json"
grep -q '^slot-plan-v2|' "$MOD/config/active-font-slot-plan.key"

MODDIR="$MOD" sh "$MOD/common/device_font_slot_plan.sh" build "$SOURCE" Demo
test "$(cat "$COUNT")" = 1

sleep 1
printf 'font-v2\n' > "$SOURCE"
MODDIR="$MOD" sh "$MOD/common/device_font_slot_plan.sh" build "$SOURCE" Demo
test "$(cat "$COUNT")" = 2

mkdir -p "$MOD/.device-font-slot-plan.lock"
printf 'different-boot\n' > "$MOD/.device-font-slot-plan.lock/boot_id"
printf '1\n' > "$MOD/.device-font-slot-plan.lock/pid"
rm -f "$MOD/config/active-font-slot-plan.json"
MODDIR="$MOD" sh "$MOD/common/device_font_slot_plan.sh" build "$SOURCE" Demo
test "$(cat "$COUNT")" = 3
test ! -d "$MOD/.device-font-slot-plan.lock"

echo 'device_font_slot_plan_test: PASS'
