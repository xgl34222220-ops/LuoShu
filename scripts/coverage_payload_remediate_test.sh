#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-remediate)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/module"
STAGE="$MOD/.luoshu-payload-stage.test"
mkdir -p "$MOD/common/python/bin" "$MOD/common/legacy_v14_4" "$MOD/config" "$MOD/logs"     "$STAGE/system/fonts/.luoshu-font-store"
printf '{}\n' > "$MOD/config/device_font_inventory.json"
printf '# fixture\n' > "$MOD/common/font_inventory.py"
printf '# fixture\n' > "$MOD/common/font_metrics_normalize.py"
head -c 4096 /dev/zero > "$STAGE/system/fonts/.luoshu-font-store/regular.font"

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
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --batch) batch="$2"; shift 2 ;;
        *) shift ;;
      esac
    done
    tab=$(printf '\t')
    while IFS="$tab" read -r source output mono slot; do
      [ -n "$source" ] && [ -n "$output" ] || continue
      mkdir -p "${output%/*}"
      cp -f "$source" "$output"
    done < "$batch"
    ;;
  *) exit 2 ;;
esac
EOF
chmod 0755 "$MOD/common/python/bin/luoshu-python"

cat > "$MOD/common/legacy_v14_4/util_functions.sh" <<'EOF'
#!/bin/sh
scan_family_weights() { printf 'regular\n'; }
EOF

LUOSHU_REAL_MODDIR="$MOD" LUOSHU_PUBLIC_DIR="$TMP/public"     sh "$ROOT/common/coverage_payload_remediate.sh" "$STAGE" direct Demo > "$TMP/out1"
grep -q '"status":"ok"' "$TMP/out1"
test -s "$STAGE/system/fonts/A.ttf"
test -s "$STAGE/product/vivo/fonts/Vivo.ttf"
test ! -e "$STAGE/system/fonts/Bold.ttf"
test ! -e "$STAGE/system/fonts/Italic.ttf"
test ! -e "$STAGE/system/fonts/C.ttc"
grep -Fqx '/system/fonts/Bold.ttf	missing-real-source-weight-700' "$STAGE/.luoshu-coverage-preserved.tsv"
grep -Fqx '/system/fonts/Italic.ttf	preserved-style-italic' "$STAGE/.luoshu-coverage-preserved.tsv"
grep -Fqx '/system/fonts/C.ttc	preserved-collection' "$STAGE/.luoshu-coverage-preserved.tsv"
grep -q '^added=2$' "$STAGE/.luoshu-coverage-remediation.conf"
grep -q '^preserved=3$' "$STAGE/.luoshu-coverage-remediation.conf"

# Once the selected family really contains Bold, remediation may consume the
# exact staged Bold anchor; it must never use Regular as a fake Bold.
head -c 4096 /dev/zero > "$STAGE/system/fonts/.luoshu-font-store/bold.font"
cat > "$MOD/common/legacy_v14_4/util_functions.sh" <<'EOF'
#!/bin/sh
scan_family_weights() { printf 'regular,bold\n'; }
EOF
LUOSHU_REAL_MODDIR="$MOD" LUOSHU_PUBLIC_DIR="$TMP/public"     sh "$ROOT/common/coverage_payload_remediate.sh" "$STAGE" direct Demo > "$TMP/out2"
test -s "$STAGE/system/fonts/Bold.ttf"
! grep -q '^/system/fonts/Bold.ttf' "$STAGE/.luoshu-coverage-preserved.tsv"
grep -q '^preserved=2# normal TTF/OTF UI weights; exact direct-family role files are irrelevant.
MIX="$MOD/.luoshu-mix-stage"
mkdir -p "$MIX/system/fonts/.luoshu-font-store"
head -c 4096 /dev/zero > "$MIX/system/fonts/.luoshu-font-store/mix-composite.font"
LUOSHU_REAL_MODDIR="$MOD" LUOSHU_PUBLIC_DIR="$TMP/public"     sh "$ROOT/common/coverage_payload_remediate.sh" "$MIX" mix mix > "$TMP/out3"
test -s "$MIX/system/fonts/A.ttf"
test -s "$MIX/product/vivo/fonts/Vivo.ttf"
test -s "$MIX/system/fonts/Bold.ttf"
test ! -e "$MIX/system/fonts/Italic.ttf"
test ! -e "$MIX/system/fonts/C.ttc"
grep -q '^added=3$' "$MIX/.luoshu-coverage-remediation.conf"
grep -q '^preserved=2$' "$MIX/.luoshu-coverage-remediation.conf"

# Production wiring: only explicit coverage remediation invokes the helper.
grep -q 'LUOSHU_COVERAGE_REMEDIATE:-0' "$ROOT/common/legacy_v14_4/font_switch_safe.sh"
grep -q 'coverage_payload_remediate.sh' "$ROOT/common/legacy_v14_4/font_switch_safe.sh"
grep -q 'coverageRemediate=' "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -q 'coverage_payload_remediate.sh' "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -q 'LUOSHU_COVERAGE_REMEDIATE=1' "$ROOT/common/app_bridge.sh"
grep -q 'LUOSHU_COVERAGE_REMEDIATE' "$ROOT/common/font_switch_task.sh"
grep -q 'LUOSHU_COVERAGE_PLAN' "$ROOT/common/font_switch_task.sh"
grep -q 'LUOSHU_COVERAGE_PLAN' "$ROOT/common/app_bridge.sh"
grep -Fq '[ "${LUOSHU_COVERAGE_REMEDIATE:-0}" != 1 ] && safe_switch_cache_restore' "$ROOT/common/legacy_v14_4/font_switch_safe.sh"
grep -q 'font_metrics_normalize.py' "$ROOT/common/coverage_payload_remediate.sh"
grep -q -- '--target-slot\|--batch' "$ROOT/common/coverage_payload_remediate.sh"

echo 'coverage_payload_remediate_test: PASS'
 "$STAGE/.luoshu-coverage-remediation.conf"

# Exact App remediation must rewrite a requested target even when the ROM mapper
# already created a file at that path. This is the regression behind "补齐提交没效果".
PLAN="$MOD/config/font-coverage-remediation-paths.txt"
printf '/system/fonts/A.ttf\n' > "$PLAN"
printf 'stale-target\n' > "$STAGE/system/fonts/A.ttf"
LUOSHU_REAL_MODDIR="$MOD" LUOSHU_PUBLIC_DIR="$TMP/public" LUOSHU_COVERAGE_PLAN="$PLAN" \
    sh "$ROOT/common/coverage_payload_remediate.sh" "$STAGE" direct Demo > "$TMP/out-plan"
grep -q '"status":"ok"' "$TMP/out-plan"
cmp -s "$STAGE/system/fonts/A.ttf" "$STAGE/system/fonts/.luoshu-font-store/regular.font"
grep -q '^requested=1# normal TTF/OTF UI weights; exact direct-family role files are irrelevant.
MIX="$MOD/.luoshu-mix-stage"
mkdir -p "$MIX/system/fonts/.luoshu-font-store"
head -c 4096 /dev/zero > "$MIX/system/fonts/.luoshu-font-store/mix-composite.font"
LUOSHU_REAL_MODDIR="$MOD" LUOSHU_PUBLIC_DIR="$TMP/public"     sh "$ROOT/common/coverage_payload_remediate.sh" "$MIX" mix mix > "$TMP/out3"
test -s "$MIX/system/fonts/A.ttf"
test -s "$MIX/product/vivo/fonts/Vivo.ttf"
test -s "$MIX/system/fonts/Bold.ttf"
test ! -e "$MIX/system/fonts/Italic.ttf"
test ! -e "$MIX/system/fonts/C.ttc"
grep -q '^added=3$' "$MIX/.luoshu-coverage-remediation.conf"
grep -q '^preserved=2$' "$MIX/.luoshu-coverage-remediation.conf"

# Production wiring: only explicit coverage remediation invokes the helper.
grep -q 'LUOSHU_COVERAGE_REMEDIATE:-0' "$ROOT/common/legacy_v14_4/font_switch_safe.sh"
grep -q 'coverage_payload_remediate.sh' "$ROOT/common/legacy_v14_4/font_switch_safe.sh"
grep -q 'coverageRemediate=' "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -q 'coverage_payload_remediate.sh' "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -q 'LUOSHU_COVERAGE_REMEDIATE=1' "$ROOT/common/app_bridge.sh"
grep -q 'LUOSHU_COVERAGE_REMEDIATE' "$ROOT/common/font_switch_task.sh"
grep -q 'font_metrics_normalize.py' "$ROOT/common/coverage_payload_remediate.sh"
grep -q -- '--target-slot\|--batch' "$ROOT/common/coverage_payload_remediate.sh"

echo 'coverage_payload_remediate_test: PASS'
 "$STAGE/.luoshu-coverage-remediation.conf"
grep -q '^matched=1# normal TTF/OTF UI weights; exact direct-family role files are irrelevant.
MIX="$MOD/.luoshu-mix-stage"
mkdir -p "$MIX/system/fonts/.luoshu-font-store"
head -c 4096 /dev/zero > "$MIX/system/fonts/.luoshu-font-store/mix-composite.font"
LUOSHU_REAL_MODDIR="$MOD" LUOSHU_PUBLIC_DIR="$TMP/public"     sh "$ROOT/common/coverage_payload_remediate.sh" "$MIX" mix mix > "$TMP/out3"
test -s "$MIX/system/fonts/A.ttf"
test -s "$MIX/product/vivo/fonts/Vivo.ttf"
test -s "$MIX/system/fonts/Bold.ttf"
test ! -e "$MIX/system/fonts/Italic.ttf"
test ! -e "$MIX/system/fonts/C.ttc"
grep -q '^added=3$' "$MIX/.luoshu-coverage-remediation.conf"
grep -q '^preserved=2$' "$MIX/.luoshu-coverage-remediation.conf"

# Production wiring: only explicit coverage remediation invokes the helper.
grep -q 'LUOSHU_COVERAGE_REMEDIATE:-0' "$ROOT/common/legacy_v14_4/font_switch_safe.sh"
grep -q 'coverage_payload_remediate.sh' "$ROOT/common/legacy_v14_4/font_switch_safe.sh"
grep -q 'coverageRemediate=' "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -q 'coverage_payload_remediate.sh' "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -q 'LUOSHU_COVERAGE_REMEDIATE=1' "$ROOT/common/app_bridge.sh"
grep -q 'LUOSHU_COVERAGE_REMEDIATE' "$ROOT/common/font_switch_task.sh"
grep -q 'font_metrics_normalize.py' "$ROOT/common/coverage_payload_remediate.sh"
grep -q -- '--target-slot\|--batch' "$ROOT/common/coverage_payload_remediate.sh"

echo 'coverage_payload_remediate_test: PASS'
 "$STAGE/.luoshu-coverage-remediation.conf"
grep -q '^planned=1# normal TTF/OTF UI weights; exact direct-family role files are irrelevant.
MIX="$MOD/.luoshu-mix-stage"
mkdir -p "$MIX/system/fonts/.luoshu-font-store"
head -c 4096 /dev/zero > "$MIX/system/fonts/.luoshu-font-store/mix-composite.font"
LUOSHU_REAL_MODDIR="$MOD" LUOSHU_PUBLIC_DIR="$TMP/public"     sh "$ROOT/common/coverage_payload_remediate.sh" "$MIX" mix mix > "$TMP/out3"
test -s "$MIX/system/fonts/A.ttf"
test -s "$MIX/product/vivo/fonts/Vivo.ttf"
test -s "$MIX/system/fonts/Bold.ttf"
test ! -e "$MIX/system/fonts/Italic.ttf"
test ! -e "$MIX/system/fonts/C.ttc"
grep -q '^added=3$' "$MIX/.luoshu-coverage-remediation.conf"
grep -q '^preserved=2$' "$MIX/.luoshu-coverage-remediation.conf"

# Production wiring: only explicit coverage remediation invokes the helper.
grep -q 'LUOSHU_COVERAGE_REMEDIATE:-0' "$ROOT/common/legacy_v14_4/font_switch_safe.sh"
grep -q 'coverage_payload_remediate.sh' "$ROOT/common/legacy_v14_4/font_switch_safe.sh"
grep -q 'coverageRemediate=' "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -q 'coverage_payload_remediate.sh' "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -q 'LUOSHU_COVERAGE_REMEDIATE=1' "$ROOT/common/app_bridge.sh"
grep -q 'LUOSHU_COVERAGE_REMEDIATE' "$ROOT/common/font_switch_task.sh"
grep -q 'font_metrics_normalize.py' "$ROOT/common/coverage_payload_remediate.sh"
grep -q -- '--target-slot\|--batch' "$ROOT/common/coverage_payload_remediate.sh"

echo 'coverage_payload_remediate_test: PASS'
 "$STAGE/.luoshu-coverage-remediation.conf"
grep -q '^rewritten=1# normal TTF/OTF UI weights; exact direct-family role files are irrelevant.
MIX="$MOD/.luoshu-mix-stage"
mkdir -p "$MIX/system/fonts/.luoshu-font-store"
head -c 4096 /dev/zero > "$MIX/system/fonts/.luoshu-font-store/mix-composite.font"
LUOSHU_REAL_MODDIR="$MOD" LUOSHU_PUBLIC_DIR="$TMP/public"     sh "$ROOT/common/coverage_payload_remediate.sh" "$MIX" mix mix > "$TMP/out3"
test -s "$MIX/system/fonts/A.ttf"
test -s "$MIX/product/vivo/fonts/Vivo.ttf"
test -s "$MIX/system/fonts/Bold.ttf"
test ! -e "$MIX/system/fonts/Italic.ttf"
test ! -e "$MIX/system/fonts/C.ttc"
grep -q '^added=3$' "$MIX/.luoshu-coverage-remediation.conf"
grep -q '^preserved=2$' "$MIX/.luoshu-coverage-remediation.conf"

# Production wiring: only explicit coverage remediation invokes the helper.
grep -q 'LUOSHU_COVERAGE_REMEDIATE:-0' "$ROOT/common/legacy_v14_4/font_switch_safe.sh"
grep -q 'coverage_payload_remediate.sh' "$ROOT/common/legacy_v14_4/font_switch_safe.sh"
grep -q 'coverageRemediate=' "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -q 'coverage_payload_remediate.sh' "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -q 'LUOSHU_COVERAGE_REMEDIATE=1' "$ROOT/common/app_bridge.sh"
grep -q 'LUOSHU_COVERAGE_REMEDIATE' "$ROOT/common/font_switch_task.sh"
grep -q 'font_metrics_normalize.py' "$ROOT/common/coverage_payload_remediate.sh"
grep -q -- '--target-slot\|--batch' "$ROOT/common/coverage_payload_remediate.sh"

echo 'coverage_payload_remediate_test: PASS'
 "$STAGE/.luoshu-coverage-remediation.conf"

# A variable family is a genuine multi-weight source. A requested Bold slot must
# not stay permanently "protected" merely because there is no separate Bold file.
rm -f "$STAGE/system/fonts/Bold.ttf" "$STAGE/system/fonts/.luoshu-font-store/bold.font"
printf '/system/fonts/Bold.ttf\n' > "$PLAN"
cat > "$MOD/common/legacy_v14_4/util_functions.sh" <<'EOF'
#!/bin/sh
scan_family_weights() { printf 'variable\n'; }
EOF
LUOSHU_REAL_MODDIR="$MOD" LUOSHU_PUBLIC_DIR="$TMP/public" LUOSHU_COVERAGE_PLAN="$PLAN" \
    sh "$ROOT/common/coverage_payload_remediate.sh" "$STAGE" direct Demo > "$TMP/out-variable"
test -s "$STAGE/system/fonts/Bold.ttf"
! grep -q '^/system/fonts/Bold.ttf' "$STAGE/.luoshu-coverage-preserved.tsv"
grep -q '^requested=1# normal TTF/OTF UI weights; exact direct-family role files are irrelevant.
MIX="$MOD/.luoshu-mix-stage"
mkdir -p "$MIX/system/fonts/.luoshu-font-store"
head -c 4096 /dev/zero > "$MIX/system/fonts/.luoshu-font-store/mix-composite.font"
LUOSHU_REAL_MODDIR="$MOD" LUOSHU_PUBLIC_DIR="$TMP/public"     sh "$ROOT/common/coverage_payload_remediate.sh" "$MIX" mix mix > "$TMP/out3"
test -s "$MIX/system/fonts/A.ttf"
test -s "$MIX/product/vivo/fonts/Vivo.ttf"
test -s "$MIX/system/fonts/Bold.ttf"
test ! -e "$MIX/system/fonts/Italic.ttf"
test ! -e "$MIX/system/fonts/C.ttc"
grep -q '^added=3$' "$MIX/.luoshu-coverage-remediation.conf"
grep -q '^preserved=2$' "$MIX/.luoshu-coverage-remediation.conf"

# Production wiring: only explicit coverage remediation invokes the helper.
grep -q 'LUOSHU_COVERAGE_REMEDIATE:-0' "$ROOT/common/legacy_v14_4/font_switch_safe.sh"
grep -q 'coverage_payload_remediate.sh' "$ROOT/common/legacy_v14_4/font_switch_safe.sh"
grep -q 'coverageRemediate=' "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -q 'coverage_payload_remediate.sh' "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -q 'LUOSHU_COVERAGE_REMEDIATE=1' "$ROOT/common/app_bridge.sh"
grep -q 'LUOSHU_COVERAGE_REMEDIATE' "$ROOT/common/font_switch_task.sh"
grep -q 'font_metrics_normalize.py' "$ROOT/common/coverage_payload_remediate.sh"
grep -q -- '--target-slot\|--batch' "$ROOT/common/coverage_payload_remediate.sh"

echo 'coverage_payload_remediate_test: PASS'
 "$STAGE/.luoshu-coverage-remediation.conf"
grep -q '^matched=1# normal TTF/OTF UI weights; exact direct-family role files are irrelevant.
MIX="$MOD/.luoshu-mix-stage"
mkdir -p "$MIX/system/fonts/.luoshu-font-store"
head -c 4096 /dev/zero > "$MIX/system/fonts/.luoshu-font-store/mix-composite.font"
LUOSHU_REAL_MODDIR="$MOD" LUOSHU_PUBLIC_DIR="$TMP/public"     sh "$ROOT/common/coverage_payload_remediate.sh" "$MIX" mix mix > "$TMP/out3"
test -s "$MIX/system/fonts/A.ttf"
test -s "$MIX/product/vivo/fonts/Vivo.ttf"
test -s "$MIX/system/fonts/Bold.ttf"
test ! -e "$MIX/system/fonts/Italic.ttf"
test ! -e "$MIX/system/fonts/C.ttc"
grep -q '^added=3$' "$MIX/.luoshu-coverage-remediation.conf"
grep -q '^preserved=2$' "$MIX/.luoshu-coverage-remediation.conf"

# Production wiring: only explicit coverage remediation invokes the helper.
grep -q 'LUOSHU_COVERAGE_REMEDIATE:-0' "$ROOT/common/legacy_v14_4/font_switch_safe.sh"
grep -q 'coverage_payload_remediate.sh' "$ROOT/common/legacy_v14_4/font_switch_safe.sh"
grep -q 'coverageRemediate=' "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -q 'coverage_payload_remediate.sh' "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -q 'LUOSHU_COVERAGE_REMEDIATE=1' "$ROOT/common/app_bridge.sh"
grep -q 'LUOSHU_COVERAGE_REMEDIATE' "$ROOT/common/font_switch_task.sh"
grep -q 'font_metrics_normalize.py' "$ROOT/common/coverage_payload_remediate.sh"
grep -q -- '--target-slot\|--batch' "$ROOT/common/coverage_payload_remediate.sh"

echo 'coverage_payload_remediate_test: PASS'
 "$STAGE/.luoshu-coverage-remediation.conf"

# Composite mode intentionally uses the generated complete composite for all
# normal TTF/OTF UI weights; exact direct-family role files are irrelevant.
MIX="$MOD/.luoshu-mix-stage"
mkdir -p "$MIX/system/fonts/.luoshu-font-store"
head -c 4096 /dev/zero > "$MIX/system/fonts/.luoshu-font-store/mix-composite.font"
LUOSHU_REAL_MODDIR="$MOD" LUOSHU_PUBLIC_DIR="$TMP/public"     sh "$ROOT/common/coverage_payload_remediate.sh" "$MIX" mix mix > "$TMP/out3"
test -s "$MIX/system/fonts/A.ttf"
test -s "$MIX/product/vivo/fonts/Vivo.ttf"
test -s "$MIX/system/fonts/Bold.ttf"
test ! -e "$MIX/system/fonts/Italic.ttf"
test ! -e "$MIX/system/fonts/C.ttc"
grep -q '^added=3$' "$MIX/.luoshu-coverage-remediation.conf"
grep -q '^preserved=2$' "$MIX/.luoshu-coverage-remediation.conf"

# Production wiring: only explicit coverage remediation invokes the helper.
grep -q 'LUOSHU_COVERAGE_REMEDIATE:-0' "$ROOT/common/legacy_v14_4/font_switch_safe.sh"
grep -q 'coverage_payload_remediate.sh' "$ROOT/common/legacy_v14_4/font_switch_safe.sh"
grep -q 'coverageRemediate=' "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -q 'coverage_payload_remediate.sh' "$ROOT/common/legacy_v14_4/mix_router.sh"
grep -q 'LUOSHU_COVERAGE_REMEDIATE=1' "$ROOT/common/app_bridge.sh"
grep -q 'LUOSHU_COVERAGE_REMEDIATE' "$ROOT/common/font_switch_task.sh"
grep -q 'font_metrics_normalize.py' "$ROOT/common/coverage_payload_remediate.sh"
grep -q -- '--target-slot\|--batch' "$ROOT/common/coverage_payload_remediate.sh"

echo 'coverage_payload_remediate_test: PASS'
