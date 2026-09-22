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
    printf 'switch-start|%s|force=%s|remediate=%s|plan=%s\n' "\${2:-}" "\${LUOSHU_FORCE_REBUILD:-0}" "\${LUOSHU_COVERAGE_REMEDIATE:-0}" "\${LUOSHU_COVERAGE_PLAN:-}" >> "$CALLS"
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
    printf 'mix-start|%s|%s|%s|%s|%s|%s|force=%s|remediate=%s|plan=%s\n' "\${2:-}" "\${3:-}" "\${4:-}" "\${5:-}" "\${6:-}" "\${7:-}" "\${LUOSHU_FORCE_REBUILD:-0}" "\${LUOSHU_COVERAGE_REMEDIATE:-0}" "\${LUOSHU_COVERAGE_PLAN:-}" >> "$CALLS"
    printf '{"status":"ok","data":{"task":"coverage-mix"}}\n'
    exit 0
    ;;
  config) printf '{"status":"ok","data":{}}\n' ;;
  *) exit 0 ;;
esac
EOF
chmod 0755 "$MOD/common/font_switch_task.sh" "$MOD/common/font_mix_controller.sh"

# coverage_reapply must always build an exact plan from the same inventory-backed
# trace shown in the App before it starts any worker.
mkdir -p "$MOD/common/python/bin" "$MOD/.luoshu-payload/system/fonts"
printf 'active-font\n' > "$MOD/.luoshu-payload/system/fonts/A.ttf"
cat > "$MOD/config/device_font_inventory.json" <<'EOF'
{"schema":"device-font-inventory-v1","buildKey":"fixture","romKind":"generic","slots":{"/system/fonts/A.ttf":{"slotName":"A.ttf","partition":"system","source":"verified-scan","format":"TTF","weight":400,"style":"normal","families":[]}}}
EOF
cat > "$MOD/common/device_font_slot_trace.py" <<'EOF'
# test stub: fake luoshu-python below emits the trace and exact plan
EOF
cat > "$MOD/common/python/bin/luoshu-python" <<'EOF'
#!/bin/sh
plan=''
while [ "$#" -gt 0 ]; do
    case "$1" in
        --remediation-plan) plan="$2"; shift 2 ;;
        *) shift ;;
    esac
done
[ -z "$plan" ] || printf '/system/fonts/A.ttf\n' > "$plan"
printf '{"schema":"device-font-slot-trace-v1","inventoryRomKind":"generic","activeFont":"Demo","summary":{"inventorySlots":1,"censusSlots":1,"censusOnlySlots":0,"replaceableSlots":1,"replaced":0,"pending":0,"protected":0,"issues":1,"remediable":1},"slots":[{"path":"/system/fonts/A.ttf","slotName":"A.ttf","partition":"system","format":"TTF","weight":400,"style":"normal","source":"verified-scan","families":[],"state":"mapping-missing","category":"issue","safeToRetry":true,"reason":"active-physical-payload-missing-slot","routes":[]}],"censusOnly":[]}\n'
EOF
chmod 0755 "$MOD/common/python/bin/luoshu-python"

run_bridge() {
    MODDIR="$MOD" sh "$ROOT/common/app_bridge.sh" "$@"
}

printf 'Demo\n' > "$MOD/config/active_font.conf"
OUT=$(run_bridge coverage_reapply)
printf '%s\n' "$OUT" | grep -q '"status":"ok"'
PLAN="$MOD/config/font-coverage-remediation-paths.txt"
grep -qx "switch-start|Demo|force=1|remediate=1|plan=$PLAN" "$CALLS"
grep -Fqx '/system/fonts/A.ttf' "$PLAN"
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
grep -qx "mix-start|CJK Demo|Latin Demo|Digit Demo|wght=500,wdth=95|wght=600|wght=700|force=1|remediate=1|plan=$PLAN" "$CALLS"
grep -Fqx '/system/fonts/A.ttf' "$PLAN"
grep -qx 'font=mix' "$MOD/config/font-payload-rebuild-pending.conf"
grep -qx 'reason=coverage-remediate' "$MOD/config/font-payload-rebuild-pending.conf"

sh -n "$ROOT/common/app_bridge.sh"
grep -q 'coverage_reapply)' "$ROOT/common/app_bridge.sh"
grep -q 'coverage_verify)' "$ROOT/common/app_bridge.sh"
grep -q 'coverage_export)' "$ROOT/common/app_bridge.sh"
grep -q 'device_font_candidates.json' "$ROOT/common/app_bridge.sh"
grep -q -- '--remediation-plan' "$ROOT/common/app_bridge.sh"
grep -q 'font-coverage-remediation-paths.txt' "$ROOT/common/app_bridge.sh"
grep -q 'LUOSHU_COVERAGE_PLAN' "$ROOT/common/font_switch_task.sh"
grep -Fq '_tmp="${_pending}.tmp.$$"' "$ROOT/common/app_bridge.sh"
grep -Fq '_tmp="${_out}.tmp.$$"' "$ROOT/common/app_bridge.sh"
grep -q 'DEVICE_FONT_CACHE=' "$ROOT/common/app_bridge.sh"
grep -Fq 'sh "$DEVICE_FONT_CACHE" lookup "$_active"' "$ROOT/common/app_bridge.sh"
grep -Fq '[ "${LUOSHU_FORCE_REBUILD:-0}" != 1 ] && router_verified_noop' "$ROOT/common/font_manager.sh"
grep -Fq '[ "${LUOSHU_FORCE_REBUILD:-0}" != 1 ] && \' "$ROOT/common/weighted_mix_task.sh"
grep -Fq '[ "${LUOSHU_FORCE_REBUILD:-0}" != 1 ] && \' "$ROOT/common/multiweight_mix_task.sh"


# A stale/recycled Android PID must not block a new coverage-triggered mix task.
grep -Fq 'luoshu_task_pid_alive "$WORKER_PID" "$_old_task"' "$ROOT/common/weighted_mix_task.sh"
grep -Fq 'luoshu_clear_task_pid "$WORKER_PID" "$_old_task"' "$ROOT/common/weighted_mix_task.sh"
grep -Fq 'luoshu_task_pid_alive "$WORKER_PID" "$_old_task"' "$ROOT/common/multiweight_mix_task.sh"
grep -Fq 'luoshu_clear_task_pid "$WORKER_PID" "$_old_task"' "$ROOT/common/multiweight_mix_task.sh"
sh -n "$ROOT/common/weighted_mix_task.sh"
sh -n "$ROOT/common/multiweight_mix_task.sh"


# Composite coverage must carry the exact App remediation plan across the detached
# worker/finalize boundary and must consume the rebuild intent before reboot.
grep -Fq "printf 'coveragePlan=%s\\n' \"\$_coverage_plan\"" "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -Fq 'LUOSHU_COVERAGE_PLAN="$_coverage_plan"' "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -Fq '"$REALMOD/config/font-payload-rebuild-pending.conf"' "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -Fq 'font-coverage-remediation-paths.txt' "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -Fq 'coverage_intent_abort_if_owned' "$ROOT/common/legacy_v14_4/mix_router.sh"
sh -n "$ROOT/common/legacy_v14_4/mix_router.sh"

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

# A missing obsolete aligned cache is not itself an error anymore. Current
# releases are traced from the active physical-safe payload below.
rm -rf "$MOD/config/device-font-cache/recovered"
cat > "$MOD/common/device_font_cache.sh" <<'EOF'
#!/system/bin/sh
exit 2
EOF
chmod 0755 "$MOD/common/device_font_cache.sh"
rm -f "$MOD/config/font-payload-rebuild-pending.conf"

# Current production runtime is physical-safe: coverage must work from the
# already-activated .luoshu-payload even when no device-font v2 manifest exists.
PHYS="$TMP/physical"
mkdir -p "$PHYS/system/fonts" "$PHYS/product/fonts" "$PHYS/product/vivo/fonts" "$PHYS/vendor/fonts"
printf 'font-a\n' > "$PHYS/system/fonts/A.ttf"
printf 'font-vivo\n' > "$PHYS/product/vivo/fonts/Vivo.ttf"
printf 'font-d\n' > "$PHYS/vendor/fonts/D.ttf"
printf '/system/fonts/E.ttf\tmissing-real-source-weight-700\n' > "$PHYS/.luoshu-coverage-preserved.tsv"
cat > "$TMP/self-mount.conf" <<'EOF'
state=degraded
backend=self-overlay-bind
mounted=system/fonts:overlay,product/fonts:overlay,product/vivo/fonts:overlay
failed=vendor/fonts-bind-incomplete
EOF
cat > "$TMP/physical-inventory.json" <<'EOF'
{"schema":"device-font-inventory-v1","buildKey":"physical-fixture","romKind":"hyperos","discoveredFontRoots":[{"partition":"product","relative":"vivo/fonts","logical":"/product/vivo/fonts","mountKey":"product-nested-fixture"}],"slots":{"/system/fonts/A.ttf":{"slotName":"A.ttf","partition":"system","source":"verified-scan","format":"TTF","weight":400,"style":"normal","families":["sans-serif"]},"/system/fonts/B.ttf":{"slotName":"B.ttf","partition":"system","source":"verified-scan","format":"TTF","weight":400,"style":"normal","families":[]},"/product/fonts/C.ttc":{"slotName":"C.ttc","partition":"product","source":"verified-scan","format":"TTC","weight":400,"style":"normal","families":[]},"/vendor/fonts/D.ttf":{"slotName":"D.ttf","partition":"vendor","source":"verified-scan","format":"TTF","weight":400,"style":"normal","families":[]},"/product/vivo/fonts/Vivo.ttf":{"slotName":"Vivo.ttf","partition":"product","source":"verified-scan","format":"TTF","weight":400,"style":"normal","families":[]},"/system/fonts/E.ttf":{"slotName":"E.ttf","partition":"system","source":"verified-scan","format":"TTF","weight":700,"style":"normal","families":[]}}}
EOF
cat > "$TMP/physical-candidates.json" <<'EOF'
{"schema":"device-font-candidates-v1","paths":[{"path":"/system/fonts/A.ttf","partition":"system","slotName":"A.ttf","candidate":true,"reason":"visible-font-path"},{"path":"/system/fonts/B.ttf","partition":"system","slotName":"B.ttf","candidate":true,"reason":"visible-font-path"},{"path":"/product/fonts/C.ttc","partition":"product","slotName":"C.ttc","candidate":true,"reason":"visible-font-path"},{"path":"/vendor/fonts/D.ttf","partition":"vendor","slotName":"D.ttf","candidate":true,"reason":"visible-font-path"},{"path":"/product/vivo/fonts/Vivo.ttf","partition":"product","slotName":"Vivo.ttf","candidate":true,"reason":"visible-font-path"},{"path":"/system/fonts/E.ttf","partition":"system","slotName":"E.ttf","candidate":true,"reason":"visible-font-path"}]}
EOF
python3 "$ROOT/common/device_font_slot_trace.py" \
    --inventory "$TMP/physical-inventory.json" \
    --physical-root "$PHYS" \
    --physical-confirmed \
    --active-font Demo \
    --mount-state "$TMP/self-mount.conf" \
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
assert states["/vendor/fonts/D.ttf"] == ("missing-mount","issue",False), states
assert states["/product/vivo/fonts/Vivo.ttf"] == ("loaded","replaced",False), states
assert states["/system/fonts/E.ttf"] == ("preserved","protected",False), states
assert data["summary"]["replaced"] == 2, data["summary"]
assert data["summary"]["issues"] == 2, data["summary"]
assert data["summary"]["protected"] == 2, data["summary"]
assert data["summary"]["remediable"] == 1, data["summary"]
assert data["summary"]["missingMount"] == 1, data["summary"]
PY
grep -q -- '--physical-root "$MODDIR/.luoshu-payload"' "$ROOT/common/app_bridge.sh"
grep -q 'traceSource.*physical-safe' "$ROOT/common/device_font_slot_trace.py"
grep -q 'luoshu_nested_font_roots' "$ROOT/common/mount_compat_base.sh"
grep -q 'device_font_roots.conf' "$ROOT/common/mount_compat_base.sh"
grep -q '_lsme_nested_key' "$ROOT/common/mount_self_atomic.sh"
grep -q '_lsme_nested_key' "$ROOT/common/mount_self_fallback.sh"
sh -n "$ROOT/common/mount_compat_base.sh"
sh -n "$ROOT/common/mount_self_atomic.sh"
sh -n "$ROOT/common/mount_self_fallback.sh"

# Coverage remediation must become a first-class tracked task in the App:
# taskId is mandatory, live progress is shown, a running task cannot be submitted
# twice, and success turns the primary action into a single full reboot.
python3 - "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/coverage/FontCoverageRoute.kt" "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuAppShell.kt" "$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt" <<'PY'
from pathlib import Path
import sys
coverage=Path(sys.argv[1]).read_text(encoding="utf-8")
shell=Path(sys.argv[2]).read_text(encoding="utf-8")
vm=Path(sys.argv[3]).read_text(encoding="utf-8")
start=coverage.index("val canReapply =")
end=coverage.index("val needsCoverageBootstrap", start)
block=coverage[start:end]
assert "!taskRunning" in block, block
assert "!rebootRequired" in block, block
assert "coverageActiveFont" in block, block
assert '(data?.summary?.remediable ?: 0) > 0' in block, block
assert 'activeFont = root.optString("activeFont", "")' in coverage
assert "正在实时检查任务状态并启动补齐" in coverage
assert "补齐任务没有返回任务 ID" in coverage
assert 'onTaskStarted(taskId, coverageActiveFont == "mix")' in coverage
assert 'taskRunning -> "补齐中 " + taskProgress.coerceIn(0, 100) + "%"' in coverage
assert 'rebootRequired -> "完整重启"' in coverage
assert "补齐负载已生成并提交。现在完整重启一次" in coverage
assert "followCoverageTask(taskId, mix)" in shell
assert "onReboot = viewModel::rebootDevice" in shell
assert "fun followCoverageTask(taskId: String, mix: Boolean)" in vm
assert "watchMixTask(taskId)" in vm
assert "watchSwitchTask(taskId, snapshot.activeFont)" in vm
PY

echo 'Font coverage center backend tests passed.'
