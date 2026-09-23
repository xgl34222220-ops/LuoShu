#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-remediate)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/module"
STAGE="$MOD/.luoshu-payload-stage.test"
mkdir -p "$MOD/common/python/bin" "$MOD/common/legacy_v14_4" "$MOD/config" "$MOD/logs" \
    "$STAGE/system/fonts/.luoshu-font-store"
printf '{}\n' > "$MOD/config/device_font_inventory.json"
printf '# fixture\n' > "$MOD/common/font_inventory.py"
printf '# fixture\n' > "$MOD/common/font_metrics_normalize.py"
head -c 4096 /dev/zero > "$STAGE/system/fonts/.luoshu-font-store/regular.font"
head -c 4096 /dev/zero > "$STAGE/system/fonts/.luoshu-font-store/bold.font"

cat > "$MOD/common/python/bin/luoshu-python" <<'EOF'
#!/bin/sh
case "${1##*/}" in
  font_inventory.py)
    cat <<'ROWS'
/system/fonts/A.ttf	A.ttf	system	TTF	400	normal	verified-scan
/product/vivo/fonts/Vivo.ttf	Vivo.ttf	product	TTF	400	normal	verified-scan
/system/fonts/Bold.ttf	Bold.ttf	system	TTF	700	normal	verified-scan
/system/fonts/Italic.ttf	Italic.ttf	system	TTF	400	italic	xml
/system/fonts/C.ttc	C.ttc	system	TTC	400	normal	xml
ROWS
    ;;
  font_metrics_normalize.py)
    shift
    batch=''
    input=''
    output=''
    slot=''
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --batch) batch="$2"; shift 2 ;;
        --input) input="$2"; shift 2 ;;
        --output) output="$2"; shift 2 ;;
        --target-slot) slot="$2"; shift 2 ;;
        --inventory) shift 2 ;;
        --strict-contract) shift ;;
        *) shift ;;
      esac
    done
    if [ -n "$batch" ]; then
      tab=$(printf '\t')
      rc=0
      while IFS="$tab" read -r source target mono row_slot; do
        [ -n "$source" ] && [ -n "$target" ] || continue
        if [ -n "${LUOSHU_TEST_BATCH_FAIL_SLOT:-}" ] && [ "$row_slot" = "$LUOSHU_TEST_BATCH_FAIL_SLOT" ]; then
          rc=2
          continue
        fi
        mkdir -p "${target%/*}"
        cp -f "$source" "$target"
      done < "$batch"
      exit "$rc"
    fi
    [ -n "$input" ] && [ -n "$output" ] || exit 2
    if [ -n "${LUOSHU_TEST_BATCH_FAIL_SLOT:-}" ] && [ "$slot" = "$LUOSHU_TEST_BATCH_FAIL_SLOT" ]; then
      exit 2
    fi
    mkdir -p "${output%/*}"
    cp -f "$input" "$output"
    exit 0
    ;;
  *) exit 2 ;;
esac
EOF
chmod 0755 "$MOD/common/python/bin/luoshu-python"

cat > "$MOD/common/legacy_v14_4/util_functions.sh" <<'EOF'
#!/bin/sh
scan_family_weights() { printf 'regular,bold\n'; }
EOF

# 1) No-plan behavior fills every safe missing UI slot.
LUOSHU_REAL_MODDIR="$MOD" LUOSHU_PUBLIC_DIR="$TMP/public" \
    sh "$ROOT/common/coverage_payload_remediate.sh" "$STAGE" direct Demo > "$TMP/out1"
grep -q '"status":"ok"' "$TMP/out1"
test -s "$STAGE/system/fonts/A.ttf"
test -s "$STAGE/product/vivo/fonts/Vivo.ttf"
test -s "$STAGE/system/fonts/Bold.ttf"
test ! -e "$STAGE/system/fonts/Italic.ttf"
test ! -e "$STAGE/system/fonts/C.ttc"
grep -q '^added=3$' "$STAGE/.luoshu-coverage-remediation.conf"
grep -q '^preserved=2$' "$STAGE/.luoshu-coverage-remediation.conf"

# 2) Plan mode forces requested existing slots to be rewritten.
PLAN="$MOD/config/font-coverage-remediation-paths.txt"
printf '/system/fonts/A.ttf\n' > "$PLAN"
LUOSHU_REAL_MODDIR="$MOD" LUOSHU_PUBLIC_DIR="$TMP/public" LUOSHU_COVERAGE_PLAN="$PLAN" \
    sh "$ROOT/common/coverage_payload_remediate.sh" "$STAGE" direct Demo > "$TMP/out2"
grep -q '"status":"ok"' "$TMP/out2"
grep -q '^requested=1$' "$STAGE/.luoshu-coverage-remediation.conf"
grep -q '^matched=1$' "$STAGE/.luoshu-coverage-remediation.conf"
grep -q '^planned=1$' "$STAGE/.luoshu-coverage-remediation.conf"
grep -q '^rewritten=1$' "$STAGE/.luoshu-coverage-remediation.conf"
grep -q '^added=1$' "$STAGE/.luoshu-coverage-remediation.conf"

# 2b) If ROM stage completion already normalized the requested slot, remediation
# must not run the same large font through fontTools a second time.
printf '/system/fonts/A.ttf\n' > "$PLAN"
printf '/system/fonts/A.ttf\n' > "$STAGE/.luoshu-metrics-covered.lst"
LUOSHU_REAL_MODDIR="$MOD" LUOSHU_PUBLIC_DIR="$TMP/public" LUOSHU_COVERAGE_PLAN="$PLAN" \
    sh "$ROOT/common/coverage_payload_remediate.sh" "$STAGE" direct Demo > "$TMP/out2b"
grep -q '"status":"ok"' "$TMP/out2b"
grep -q '^requested=1$' "$STAGE/.luoshu-coverage-remediation.conf"
grep -q '^matched=1$' "$STAGE/.luoshu-coverage-remediation.conf"
grep -q '^planned=0$' "$STAGE/.luoshu-coverage-remediation.conf"
grep -q '^rewritten=0$' "$STAGE/.luoshu-coverage-remediation.conf"
rm -f "$STAGE/.luoshu-metrics-covered.lst"

# 3) Stale plans fail closed.
printf '/system/fonts/DoesNotExist.ttf\n' > "$PLAN"
set +e
LUOSHU_REAL_MODDIR="$MOD" LUOSHU_PUBLIC_DIR="$TMP/public" LUOSHU_COVERAGE_PLAN="$PLAN" \
    sh "$ROOT/common/coverage_payload_remediate.sh" "$STAGE" direct Demo > "$TMP/out3" 2>&1
rc=$?
set -e
test "$rc" -ne 0
grep -q '"status":"error"' "$TMP/out3"

# 4) Composite remediation rewrites requested slots and backfills all other safe
# inventory slots removed by the clean stage, including nested OEM roots.
MIX="$MOD/.luoshu-mix-stage"
mkdir -p "$MIX/system/fonts/.luoshu-font-store"
head -c 4096 /dev/zero > "$MIX/system/fonts/.luoshu-font-store/mix-composite.font"
printf '/system/fonts/A.ttf\n/product/vivo/fonts/Vivo.ttf\n' > "$PLAN"
LUOSHU_REAL_MODDIR="$MOD" LUOSHU_PUBLIC_DIR="$TMP/public" LUOSHU_COVERAGE_PLAN="$PLAN" \
    sh "$ROOT/common/coverage_payload_remediate.sh" "$MIX" mix mix > "$TMP/out4"
grep -q '"status":"ok"' "$TMP/out4"
test -s "$MIX/system/fonts/A.ttf"
test -s "$MIX/product/vivo/fonts/Vivo.ttf"
test -s "$MIX/system/fonts/Bold.ttf"
test ! -e "$MIX/system/fonts/Italic.ttf"
test ! -e "$MIX/system/fonts/C.ttc"
grep -q '^requested=2$' "$MIX/.luoshu-coverage-remediation.conf"
grep -q '^matched=2$' "$MIX/.luoshu-coverage-remediation.conf"
grep -q '^added=3$' "$MIX/.luoshu-coverage-remediation.conf"
grep -q '^preserved=2$' "$MIX/.luoshu-coverage-remediation.conf"

# 5) One bad row from the batch normalizer must not erase every successful row.
# The shell retries only that row and, if metric normalization still cannot emit
# it, falls back to the real font source so the coverage transaction still lands.
PARTIAL="$MOD/.luoshu-payload-stage.partial"
mkdir -p "$PARTIAL/system/fonts/.luoshu-font-store"
head -c 4096 /dev/zero > "$PARTIAL/system/fonts/.luoshu-font-store/regular.font"
head -c 4096 /dev/zero > "$PARTIAL/system/fonts/.luoshu-font-store/bold.font"
LUOSHU_TEST_BATCH_FAIL_SLOT='/product/vivo/fonts/Vivo.ttf' \
LUOSHU_REAL_MODDIR="$MOD" LUOSHU_PUBLIC_DIR="$TMP/public" \
    sh "$ROOT/common/coverage_payload_remediate.sh" "$PARTIAL" direct Demo > "$TMP/out5"
grep -q '"status":"ok"' "$TMP/out5"
test -s "$PARTIAL/system/fonts/A.ttf"
test -s "$PARTIAL/product/vivo/fonts/Vivo.ttf"
test -s "$PARTIAL/system/fonts/Bold.ttf"
grep -q '^added=3$' "$PARTIAL/.luoshu-coverage-remediation.conf"
grep -q '^fallback=1$' "$PARTIAL/.luoshu-coverage-remediation.conf"
grep -q '^failed=0$' "$PARTIAL/.luoshu-coverage-remediation.conf"

# Production wiring and one-reboot convergence contract.
grep -q 'LUOSHU_COVERAGE_REMEDIATE:-0' "$ROOT/common/legacy_v14_4/font_switch_safe.sh"
grep -q 'coverage_payload_remediate.sh' "$ROOT/common/legacy_v14_4/font_switch_safe.sh"
grep -q 'coverageRemediate=' "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -q 'coveragePlan=' "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -Fq 'LUOSHU_COVERAGE_PLAN="$_coverage_plan"' "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -q 'font-payload-rebuild-pending.conf' "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -q 'coverage_intent_abort_if_owned' "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -q 'font-coverage-remediation-paths.txt' "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -q 'LUOSHU_COVERAGE_REMEDIATE=1' "$ROOT/common/app_bridge.sh"
grep -q 'LUOSHU_COVERAGE_PLAN=' "$ROOT/common/app_bridge.sh"
grep -q 'font_metrics_normalize.py' "$ROOT/common/coverage_payload_remediate.sh"
grep -q 'PLAN_ENABLED' "$ROOT/common/coverage_payload_remediate.sh"
grep -q -- '--batch' "$ROOT/common/coverage_payload_remediate.sh"
grep -q 'METRICS_COVERED=' "$ROOT/common/coverage_payload_remediate.sh"
grep -q '正在校验并自动补齐本机安全字体槽位' "$ROOT/common/legacy_v14_4/font_switch_safe.sh"
grep -q '正在校验并自动补齐本机安全字体槽位' "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -q '单槽度量归一化失败，已回退真实字体源' "$ROOT/common/coverage_payload_remediate.sh"

sh -n "$ROOT/common/coverage_payload_remediate.sh"
sh -n "$ROOT/common/legacy_v14_4/font_switch_safe.sh"
sh -n "$ROOT/common/legacy_v14_4/mix_router.sh"
sh -n "$ROOT/common/app_bridge.sh"
sh -n "$ROOT/common/font_switch_task.sh"

echo 'coverage_payload_remediate_test: PASS'
