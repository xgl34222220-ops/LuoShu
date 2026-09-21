#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-coverage)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/module"
mkdir -p "$MOD/common" "$MOD/config" "$MOD/logs"
CALLS="$TMP/calls"
: > "$CALLS"

cat > "$MOD/common/font_switch_task.sh" <<EOF
#!/system/bin/sh
case "\${1:-}" in
  reconcile) exit 0 ;;
  start)
    printf 'switch-start|%s|force=%s\n' "\${2:-}" "\${LUOSHU_FORCE_REBUILD:-0}" >> "$CALLS"
    printf '{"status":"ok","data":{"task":"coverage-direct","font":"%s"}}\n' "\${2:-}"
    exit 0
    ;;
  *) exit 0 ;;
esac
EOF

cat > "$MOD/common/font_mix_controller.sh" <<EOF
#!/system/bin/sh
case "\${1:-}" in
  reconcile) exit 0 ;;
  start)
    printf 'mix-start|%s|%s|%s|%s|%s|%s|force=%s\n' "\${2:-}" "\${3:-}" "\${4:-}" "\${5:-}" "\${6:-}" "\${7:-}" "\${LUOSHU_FORCE_REBUILD:-0}" >> "$CALLS"
    printf '{"status":"ok","data":{"task":"coverage-mix"}}\n'
    exit 0
    ;;
  config) printf '{"status":"ok","data":{}}\n' ;;
  *) exit 0 ;;
esac
EOF
chmod 0755 "$MOD/common/font_switch_task.sh" "$MOD/common/font_mix_controller.sh"

run_bridge() {
    MODDIR="$MOD" sh "$ROOT/common/app_bridge.sh" "$@"
}

printf 'Demo\n' > "$MOD/config/active_font.conf"
OUT=$(run_bridge coverage_reapply)
printf '%s\n' "$OUT" | grep -q '"status":"ok"'
grep -qx 'switch-start|Demo|force=1' "$CALLS"
grep -qx 'state=pending' "$MOD/config/font-payload-rebuild-pending.conf"
grep -qx 'font=Demo' "$MOD/config/font-payload-rebuild-pending.conf"
grep -qx 'reason=coverage-remediate' "$MOD/config/font-payload-rebuild-pending.conf"

# Default font has no LuoShu payload to rebuild.
printf 'default\n' > "$MOD/config/active_font.conf"
rm -f "$MOD/config/font-payload-rebuild-pending.conf"
OUT=$(run_bridge coverage_reapply 2>&1)
printf '%s\n' "$OUT" | grep -q '"status":"error"'
printf '%s\n' "$OUT" | grep -q '系统默认字体'
[ ! -e "$MOD/config/font-payload-rebuild-pending.conf" ]

# A running task must block a second remediation transaction.
printf 'Demo\n' > "$MOD/config/active_font.conf"
cat > "$MOD/config/switch_task.conf" <<'EOF'
task=busy
state=running
font=Demo
EOF
OUT=$(run_bridge coverage_reapply 2>&1)
printf '%s\n' "$OUT" | grep -q '"status":"error"'
printf '%s\n' "$OUT" | grep -q '已有字体任务正在运行'
rm -f "$MOD/config/switch_task.conf"

# Composite remediation must replay the current persisted mix configuration,
# not invent a new selection or flatten the axes.
cat > "$MOD/config/active_font.conf" <<'EOF'
mix
EOF
cat > "$MOD/config/axes_mix.conf" <<'EOF'
cjk=CJK Demo
latin=Latin Demo
digit=Digit Demo
cjkWeight=500
latinWeight=600
digitWeight=700
cjkAxes=wght=500,wdth=95
latinAxes=wght=600
digitAxes=wght=700
EOF
rm -f "$MOD/config/font-payload-rebuild-pending.conf"
OUT=$(run_bridge coverage_reapply)
printf '%s\n' "$OUT" | grep -q '"status":"ok"'
grep -qx 'mix-start|CJK Demo|Latin Demo|Digit Demo|wght=500,wdth=95|wght=600|wght=700|force=1' "$CALLS"
grep -qx 'font=mix' "$MOD/config/font-payload-rebuild-pending.conf"
grep -qx 'reason=coverage-remediate' "$MOD/config/font-payload-rebuild-pending.conf"

sh -n "$ROOT/common/app_bridge.sh"
grep -q 'coverage_reapply)' "$ROOT/common/app_bridge.sh"
grep -q 'coverage_verify)' "$ROOT/common/app_bridge.sh"
grep -q 'coverage_export)' "$ROOT/common/app_bridge.sh"
grep -q 'device_font_candidates.json' "$ROOT/common/app_bridge.sh"
grep -Fq '_tmp="${_pending}.tmp.$$"' "$ROOT/common/app_bridge.sh"
grep -Fq '_tmp="${_out}.tmp.$$"' "$ROOT/common/app_bridge.sh"
grep -q 'DEVICE_FONT_CACHE=' "$ROOT/common/app_bridge.sh"
grep -Fq 'sh "$DEVICE_FONT_CACHE" lookup "$_active"' "$ROOT/common/app_bridge.sh"
grep -Fq '[ "${LUOSHU_FORCE_REBUILD:-0}" != 1 ] && router_verified_noop' "$ROOT/common/font_manager.sh"
grep -Fq '[ "${LUOSHU_FORCE_REBUILD:-0}" != 1 ] && \' "$ROOT/common/weighted_mix_task.sh"
grep -Fq '[ "${LUOSHU_FORCE_REBUILD:-0}" != 1 ] && \' "$ROOT/common/multiweight_mix_task.sh"

# Upgrade regression: migration may intentionally clear device-font-engine.conf while
# a compatible content-addressed cache still exists. Coverage must recover that cache
# instead of failing solely because cacheId disappeared.
mkdir -p "$MOD/common/python/bin" "$MOD/config/device-font-cache/recovered/payload" "$MOD/config/device-font-cache/recovered/overlay"
printf '{}\n' > "$MOD/config/device_font_inventory.json"
printf '{}\n' > "$MOD/config/device-font-cache/recovered/payload/manifest.json"
printf '{}\n' > "$MOD/config/device-font-cache/recovered/overlay/overlay-manifest.json"
printf 'Demo\n' > "$MOD/config/active_font.conf"
rm -f "$MOD/config/device-font-engine.conf" "$MOD/config/font-payload-rebuild-pending.conf"
cat > "$MOD/common/device_font_slot_trace.py" <<'EOF'
# test stub: the fake Python launcher below owns the output
EOF
cat > "$MOD/common/device_font_cache.sh" <<EOF
#!/system/bin/sh
if [ "\${1:-}" = lookup ] && [ "\${2:-}" = Demo ]; then
    printf 'lookup|%s\\n' "\${2:-}" >> "$CALLS"
    printf '%s\\n' "$MOD/config/device-font-cache/recovered"
    exit 0
fi
exit 2
EOF
cat > "$MOD/common/python/bin/luoshu-python" <<'EOF'
#!/bin/sh
printf '{"schema":"device-font-slot-trace-v1","summary":{"inventorySlots":1,"censusSlots":1,"replaceableSlots":1,"replaced":1,"pending":0,"protected":0,"issues":0,"remediable":0},"slots":[]}\n'
EOF
chmod 0755 "$MOD/common/device_font_cache.sh" "$MOD/common/python/bin/luoshu-python"
OUT=$(run_bridge coverage 2>&1)
printf '%s\n' "$OUT" | grep -q '"schema":"device-font-slot-trace-v1"'
grep -qx 'lookup|Demo' "$CALLS"

# If the old aligned cache cannot be trusted after a builder/inventory upgrade,
# the error must tell the App to rebuild the preserved active font rather than
# suggesting that repeated reads can fix missing manifests.
rm -rf "$MOD/config/device-font-cache/recovered"
cat > "$MOD/common/device_font_cache.sh" <<'EOF'
#!/system/bin/sh
exit 2
EOF
chmod 0755 "$MOD/common/device_font_cache.sh"
cat > "$MOD/config/font-payload-rebuild-pending.conf" <<'EOF'
state=awaiting-explicit-apply
mode=preserve-current
font=Demo
reason=font-builder-changed
EOF
OUT=$(run_bridge coverage 2>&1)
printf '%s\n' "$OUT" | grep -q '升级保留负载'
printf '%s\n' "$OUT" | grep -q '重新应用一次'

# Current production runtime is physical-safe: coverage must work from the
# already-activated .luoshu-payload even when no device-font v2 manifest exists.
PHYS="$TMP/physical"
mkdir -p "$PHYS/system/fonts" "$PHYS/product/fonts"
printf 'font-a\n' > "$PHYS/system/fonts/A.ttf"
cat > "$TMP/physical-inventory.json" <<'EOF'
{"schema":"device-font-inventory-v1","buildKey":"physical-fixture","romKind":"hyperos","slots":{"/system/fonts/A.ttf":{"slotName":"A.ttf","partition":"system","source":"verified-scan","format":"TTF","weight":400,"style":"normal","families":["sans-serif"]},"/system/fonts/B.ttf":{"slotName":"B.ttf","partition":"system","source":"verified-scan","format":"TTF","weight":400,"style":"normal","families":[]},"/product/fonts/C.ttc":{"slotName":"C.ttc","partition":"product","source":"verified-scan","format":"TTC","weight":400,"style":"normal","families":[]}}}
EOF
cat > "$TMP/physical-candidates.json" <<'EOF'
{"schema":"device-font-candidates-v1","paths":[{"path":"/system/fonts/A.ttf","partition":"system","slotName":"A.ttf","candidate":true,"reason":"visible-font-path"},{"path":"/system/fonts/B.ttf","partition":"system","slotName":"B.ttf","candidate":true,"reason":"visible-font-path"},{"path":"/product/fonts/C.ttc","partition":"product","slotName":"C.ttc","candidate":true,"reason":"visible-font-path"}]}
EOF
python3 "$ROOT/common/device_font_slot_trace.py" \
    --inventory "$TMP/physical-inventory.json" \
    --physical-root "$PHYS" \
    --physical-confirmed \
    --active-font Demo \
    --candidates "$TMP/physical-candidates.json" \
    --output "$TMP/physical-trace.json" >/dev/null
python3 - "$TMP/physical-trace.json" <<'PY'
import json, sys
data=json.load(open(sys.argv[1], encoding="utf-8"))
assert data["schema"] == "device-font-slot-trace-v1", data
assert data["traceSource"] == "physical-safe", data
states={item["path"]:(item["state"], item["category"], item["safeToRetry"]) for item in data["slots"]}
assert states["/system/fonts/A.ttf"] == ("loaded","replaced",False), states
assert states["/system/fonts/B.ttf"] == ("mapping-missing","issue",True), states
assert states["/product/fonts/C.ttc"] == ("preserved","protected",False), states
assert data["summary"]["replaced"] == 1, data["summary"]
assert data["summary"]["issues"] == 1, data["summary"]
assert data["summary"]["protected"] == 1, data["summary"]
PY
grep -q -- '--physical-root "$MODDIR/.luoshu-payload"' "$ROOT/common/app_bridge.sh"
grep -q 'traceSource.*physical-safe' "$ROOT/common/device_font_slot_trace.py"

echo 'Font coverage center backend tests passed.'
