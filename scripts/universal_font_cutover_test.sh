#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/module"
mkdir -p "$MOD/common/legacy_v14_4" "$MOD/config" "$MOD/logs" "$MOD/.luoshu-retired"
printf '{}\n' > "$MOD/config/device_font_topology.json"
printf '{}\n' > "$MOD/config/device_font_roles.json"
printf 'OldFont\n' > "$MOD/config/active_font.conf"

cat > "$MOD/common/universal_font_plan.sh" <<'SH'
#!/bin/sh
[ "$1" = path ] || exit 1
printf '%s\n' "$MODDIR/config/plan.json"
SH
cat > "$MOD/common/minimal_xml_router.sh" <<'SH'
#!/bin/sh
[ "$1" = path ] || exit 1
printf '%s\n' "$MODDIR/config/route.json"
SH
cat > "$MOD/common/universal_font_compiler.sh" <<'SH'
#!/bin/sh
case "$1" in manifest|path) printf '%s\n' "$MODDIR/config/artifacts.json" ;; *) exit 1 ;; esac
SH
cat > "$MOD/common/universal_font_deployment.sh" <<'SH'
#!/bin/sh
case "$1" in
  prepare)
    printf '%s %s\n' "${LUOSHU_UNIVERSAL_DEADLINE:-}" "$(date +%s)" > "$MODDIR/config/prepare-deadline"
    [ "${FAKE_PREPARE:-ok}" = ok ] || { echo '{"status":"error","message":"fake prepare failed"}'; exit 1; }
    mkdir -p "$MODDIR/config/prepared-payload"
    printf '{}\n' > "$MODDIR/config/plan.json"
    printf '{}\n' > "$MODDIR/config/route.json"
    printf '{}\n' > "$MODDIR/config/artifacts.json"
    printf '{}\n' > "$MODDIR/config/deployment.json"
    printf '{"status":"ok"}\n'
    ;;
  manifest|path) printf '%s\n' "$MODDIR/config/deployment.json" ;;
  payload) printf '%s\n' "$MODDIR/config/prepared-payload" ;;
  stage-prepared)
    previous=$(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null || printf 'default')
    [ -n "$previous" ] || previous=default
    mkdir -p "$MODDIR/.luoshu-payload-next"
    {
      printf 'state=prepared\n'
      printf 'font=%s\n' "$2"
      printf 'deploymentId=fake-new\n'
      printf 'payloadDigest=fake-digest\n'
      printf 'previousFont=%s\n' "$previous"
      printf 'previousMode=classic\n'
      printf 'previousLegacy=false\n'
    } > "$MODDIR/config/universal-font-next.conf"
    printf '%s\n' "$2" > "$MODDIR/config/active_font.conf"
    printf '{"status":"ok","state":"staged-next-boot","pipeline":"universal","fallback":false,"deploymentId":"fake-new"}\n'
    ;;
  *) exit 2 ;;
esac
SH
cat > "$MOD/common/legacy_v14_4/font_switch_safe.sh" <<'SH'
#!/bin/sh
previous=$(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null || printf 'default')
[ -n "$previous" ] || previous=default
printf '%s\n' "${3:-unknown}" >> "$MODDIR/config/legacy-called"
mkdir -p "$MODDIR/.luoshu-payload-next"
{
  printf 'state=prepared\n'
  printf 'font=%s\n' "${3:-default}"
  printf 'previousFont=%s\n' "$previous"
  printf 'previousLegacy=false\n'
} > "$MODDIR/config/font-payload-next.conf"
printf '%s\n' "${3:-default}" > "$MODDIR/config/active_font.conf"
printf '{"status":"ok","state":"prepared","fallback":true}\n'
SH
cat > "$MOD/common/universal_font_cutover_gate.py" <<'PY'
# fake gate marker
PY
cat > "$MOD/common/universal_font_deployment.py" <<'PY'
# fake deployer marker
PY
cat > "$TMP/fake-python" <<'SH'
#!/bin/sh
case "$1" in
  */universal_font_cutover_gate.py)
    if [ "${FAKE_GATE:-pass}" = pass ]; then
      printf '{"schema":"universal-font-cutover-gate-v1","eligible":true,"decision":"universal"}\n'
      exit 0
    fi
    printf '{"schema":"universal-font-cutover-gate-v1","eligible":false,"decision":"legacy-fallback","reasons":["fake-reject"]}\n'
    exit 2
    ;;
  */universal_font_deployment.py)
    exit 0
    ;;
  -)
    printf 'previous-universal-id\nprevious-universal-digest\n'
    exit 0
    ;;
  *) exit 1 ;;
esac
SH
chmod +x "$MOD/common/"*.sh "$MOD/common/legacy_v14_4/font_switch_safe.sh" "$TMP/fake-python"
printf '{}\n' > "$MOD/config/plan.json"
printf '{}\n' > "$MOD/config/route.json"
printf '{}\n' > "$MOD/config/artifacts.json"
printf '{}\n' > "$MOD/config/deployment.json"
mkdir -p "$MOD/config/prepared-payload"

OUT="$(
  MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PYTHON="$TMP/fake-python" FAKE_GATE=pass \
    sh "$ROOT/common/universal_font_cutover.sh" switch DemoFont
)"
printf '%s' "$OUT" | grep -q '"pipeline":"universal"'
[ ! -f "$MOD/config/legacy-called" ]
grep -q '^state=staged$' "$MOD/config/universal-font-cutover.conf"
grep -q '^font=DemoFont$' "$MOD/config/universal-font-next.conf"

# Universal stops starting work 30 s before the switch timeout so it can report
# a clear failure; there is no legacy fallback to leave time for.
read -r deadline now < "$MOD/config/prepare-deadline"
[ $((deadline - now)) -ge 325 ] && [ $((deadline - now)) -le 330 ]
grep -q 'universal prepare start font=DemoFont budget=330s' "$MOD/logs/fontswitch.log"
cp -a "$MOD/config" "$TMP/config-after-first-switch"
MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PYTHON="$TMP/fake-python" FAKE_GATE=pass \
  LUOSHU_SWITCH_TIMEOUT_SECONDS=100 sh "$ROOT/common/universal_font_cutover.sh" switch DemoFont >/dev/null
read -r deadline now < "$MOD/config/prepare-deadline"
[ $((deadline - now)) -ge 65 ] && [ $((deadline - now)) -le 70 ]
MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PYTHON="$TMP/fake-python" FAKE_GATE=pass \
  LUOSHU_UNIVERSAL_BUDGET_SECONDS=bogus sh "$ROOT/common/universal_font_cutover.sh" switch DemoFont >/dev/null
read -r deadline now < "$MOD/config/prepare-deadline"
[ $((deadline - now)) -ge 325 ] && [ $((deadline - now)) -le 330 ]
rm -rf "$MOD/config"
mv "$TMP/config-after-first-switch" "$MOD/config"

# A rejected Universal switch reports the gate reason and changes nothing: no
# legacy engine, the queued DemoFont request and the active selection stay.
cp "$MOD/config/universal-font-next.conf" "$TMP/next-before.conf"
OUT="$(MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PYTHON="$TMP/fake-python" FAKE_GATE=reject \
  sh "$ROOT/common/universal_font_cutover.sh" switch RejectedFont || true)"
printf '%s' "$OUT" | grep -q '"status":"error"'
printf '%s' "$OUT" | grep -q '"reason":"universal-readiness-gate-rejected"'
printf '%s' "$OUT" | grep -q 'fake-reject'
[ ! -f "$MOD/config/legacy-called" ]
grep -q '^state=failed$' "$MOD/config/universal-font-cutover.conf"
cmp -s "$TMP/next-before.conf" "$MOD/config/universal-font-next.conf"
grep -q '^DemoFont$' "$MOD/config/active_font.conf"
[ -d "$MOD/.luoshu-payload-next" ]

OUT="$(MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PYTHON="$TMP/fake-python" FAKE_PREPARE=fail \
  sh "$ROOT/common/universal_font_cutover.sh" switch PrepareFail || true)"
printf '%s' "$OUT" | grep -q '"reason":"universal-prepare-failed"'
printf '%s' "$OUT" | grep -q 'fake prepare failed'
[ ! -f "$MOD/config/legacy-called" ]

# Composite temporary families and the old composite runtime are refused.
MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PYTHON="$TMP/fake-python" \
  sh "$ROOT/common/universal_font_cutover.sh" switch LuoShuAutoMix | grep -q '组合字体请在组合页面应用'
LUOSHU_REAL_MODDIR="$MOD" MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PYTHON="$TMP/fake-python" \
  sh "$ROOT/common/universal_font_cutover.sh" switch DemoFont | grep -q '旧组合运行时已停用'

# Restoring the system font stages an empty next payload in default mode and
# records the font running in this boot (OldFont), not the queued DemoFont.
MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PYTHON="$TMP/fake-python" \
  sh "$ROOT/common/universal_font_cutover.sh" switch default | grep -q '"pipeline":"universal-default"'
[ ! -f "$MOD/config/legacy-called" ]
[ -d "$MOD/.luoshu-payload-next" ] && [ -z "$(ls -A "$MOD/.luoshu-payload-next")" ]
grep -q '^font=default$' "$MOD/config/font-payload-next.conf"
grep -q '^targetMode=default$' "$MOD/config/font-payload-next.conf"
grep -q '^previousFont=OldFont$' "$MOD/config/font-payload-next.conf"
[ ! -f "$MOD/config/universal-font-next.conf" ]
grep -q '^default$' "$MOD/config/active_font.conf"
grep -q '^font=default$' "$MOD/config/text_reboot_required.conf"

rm -rf "$MOD/.luoshu-payload-next"
rm -f "$MOD/config/font-payload-next.conf" "$MOD/config/universal-font-next.conf" "$MOD/config/legacy-called"
mkdir -p "$MOD/.luoshu-retired/universal-boot-legacy/system/fonts"
printf 'old payload\n' > "$MOD/.luoshu-retired/universal-boot-legacy/system/fonts/Old.ttf"
cat > "$MOD/config/universal-font-runtime-verification.conf" <<'EOF'
grade=FAIL
bootId=boot-legacy
EOF
cat > "$MOD/config/universal-font-activated.conf" <<EOF
font=BadFont
previousFont=OldFont
previousMode=legacy
previousLegacy=true
recovery=false
retired=$MOD/.luoshu-retired/universal-boot-legacy
bootId=boot-legacy
EOF
MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PYTHON="$TMP/fake-python" \
  sh "$ROOT/common/universal_font_cutover.sh" rollback-from-fail boot-legacy >/dev/null
[ -f "$MOD/.luoshu-payload-next/system/fonts/Old.ttf" ]
grep -q '^font=OldFont$' "$MOD/config/font-payload-next.conf"
grep -q '^targetMode=legacy$' "$MOD/config/font-payload-next.conf"
grep -q '^state=staged$' "$MOD/config/universal-font-rollback.conf"
grep -q '^reason=universal-runtime-verification-failed-rollback$' "$MOD/config/text_reboot_required.conf"

# Previous system-default mode has no retired LuoShu payload; recovery must
# still stage a clean default next boot instead of failing on a missing directory.
rm -rf "$MOD/.luoshu-payload-next"
rm -f "$MOD/config/font-payload-next.conf" "$MOD/config/universal-font-next.conf" "$MOD/config/universal-font-rollback.conf"
cat > "$MOD/config/universal-font-runtime-verification.conf" <<'EOF'
grade=FAIL
bootId=boot-default
EOF
cat > "$MOD/config/universal-font-activated.conf" <<EOF
font=BadFromDefault
previousFont=default
previousMode=default
previousLegacy=false
recovery=false
retired=$MOD/.luoshu-retired/universal-boot-default
bootId=boot-default
EOF
MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PYTHON="$TMP/fake-python" \
  sh "$ROOT/common/universal_font_cutover.sh" rollback-from-fail boot-default >/dev/null
[ -d "$MOD/.luoshu-payload-next" ]
grep -q '^font=default$' "$MOD/config/font-payload-next.conf"
grep -q '^targetMode=default$' "$MOD/config/font-payload-next.conf"
grep -q '^recovery=true$' "$MOD/config/font-payload-next.conf"
grep -q '^targetFont=default$' "$MOD/config/universal-font-rollback.conf"
[ ! -f "$MOD/config/universal-font-next.conf" ]


rm -rf "$MOD/.luoshu-payload-next"
rm -f "$MOD/config/font-payload-next.conf" "$MOD/config/universal-font-next.conf"
mkdir -p "$MOD/.luoshu-retired/universal-boot-universal/.luoshu-runtime/deployment"
printf '{}\n' > "$MOD/.luoshu-retired/universal-boot-universal/.luoshu-runtime/deployment/deployment.json"
cat > "$MOD/config/universal-font-runtime-verification.conf" <<'EOF'
grade=FAIL
bootId=boot-universal
EOF
cat > "$MOD/config/universal-font-activated.conf" <<EOF
font=BadFont2
previousFont=GoodUniversal
previousMode=universal
previousLegacy=false
recovery=false
retired=$MOD/.luoshu-retired/universal-boot-universal
bootId=boot-universal
EOF
MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PYTHON="$TMP/fake-python" \
  sh "$ROOT/common/universal_font_cutover.sh" rollback-from-fail boot-universal >/dev/null
grep -q '^font=GoodUniversal$' "$MOD/config/universal-font-next.conf"
grep -q '^recovery=true$' "$MOD/config/universal-font-next.conf"
[ ! -f "$MOD/config/font-payload-next.conf" ]

rm -rf "$MOD/.luoshu-payload-next"
rm -f "$MOD/config/universal-font-next.conf" "$MOD/config/font-payload-next.conf"
sed 's/^recovery=false$/recovery=true/' "$MOD/config/universal-font-activated.conf" > "$MOD/config/universal-font-activated.conf.tmp"
mv "$MOD/config/universal-font-activated.conf.tmp" "$MOD/config/universal-font-activated.conf"
MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PYTHON="$TMP/fake-python" \
  sh "$ROOT/common/universal_font_cutover.sh" rollback-from-fail boot-universal >/dev/null || true
grep -q '^state=suppressed$' "$MOD/config/universal-font-rollback.conf"
grep -q '^reason=recovery-already-attempted$' "$MOD/config/universal-font-rollback.conf"
[ ! -d "$MOD/.luoshu-payload-next" ]

echo "universal_font_cutover_test: PASS"
