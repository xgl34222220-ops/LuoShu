#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/module"
mkdir -p "$MOD/common" "$MOD/config" "$MOD/logs" "$MOD/.luoshu-retired"
printf '{}\n' > "$MOD/config/device_font_topology.json"
printf 'OldFont\n' > "$MOD/config/active_font.conf"

cat > "$MOD/common/luoshu_engine.sh" <<'SH'
#!/bin/sh
case "$1" in
  prepare)
    printf '%s %s\n' "${LUOSHU_ENGINE_DEADLINE:-}" "$(date +%s)" > "$MODDIR/config/prepare-deadline"
    [ "${FAKE_PREPARE:-ok}" = ok ] || { echo '{"status":"error","message":"fake prepare failed"}'; exit 1; }
    mkdir -p "$MODDIR/config/build/payload"
    printf '%s\n' "$2" > "$MODDIR/config/build/family"
    printf '{"keptStock":[{"path":"/system/fonts/Odd.ttf","reason":"x"}]}\n' > "$MODDIR/config/build/report.json"
    printf '{"status":"ok"}\n'
    ;;
  report) printf '%s\n' "$MODDIR/config/build/report.json" ;;
  stage)
    [ "$(cat "$MODDIR/config/build/family")" = "$2" ] || exit 1
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
    printf '{"status":"ok","state":"staged-next-boot","pipeline":"luoshu-engine-v3","deploymentId":"fake-new"}\n'
    ;;
  *) exit 2 ;;
esac
SH
cat > "$MOD/common/luoshu_payload.py" <<'PY'
# fake deployer marker
PY
cat > "$TMP/fake-python" <<'SH'
#!/bin/sh
case "$1" in
  */luoshu_payload.py)
    exit 0
    ;;
  -)
    if [ -n "${2:-}" ] && grep -q keptStock "$2" 2>/dev/null; then
      printf '1|Odd.ttf\n'
      exit 0
    fi
    printf 'previous-universal-id\nprevious-universal-digest\n'
    exit 0
    ;;
  *) exit 1 ;;
esac
SH
chmod +x "$MOD/common/"*.sh "$TMP/fake-python"

OUT="$(
  MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PYTHON="$TMP/fake-python" \
    sh "$ROOT/common/universal_font_cutover.sh" switch DemoFont
)"
printf '%s' "$OUT" | grep -q '"pipeline":"luoshu-engine-v3"'
grep -q '^state=staged$' "$MOD/config/universal-font-cutover.conf"
grep -q '^font=DemoFont$' "$MOD/config/universal-font-next.conf"
# Slots the engine left stock are recorded for the task message.
grep -q '^font=DemoFont$' "$MOD/config/universal-kept-stock.conf"
grep -q '^files=Odd.ttf$' "$MOD/config/universal-kept-stock.conf"

# The engine stops starting work 30 s before the switch timeout so it can report
# a clear failure.
read -r deadline now < "$MOD/config/prepare-deadline"
[ $((deadline - now)) -ge 325 ] && [ $((deadline - now)) -le 330 ]
grep -q 'engine prepare start font=DemoFont budget=330s' "$MOD/logs/fontswitch.log"
cp -a "$MOD/config" "$TMP/config-after-first-switch"
MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PYTHON="$TMP/fake-python" \
  LUOSHU_SWITCH_TIMEOUT_SECONDS=100 sh "$ROOT/common/universal_font_cutover.sh" switch DemoFont >/dev/null
read -r deadline now < "$MOD/config/prepare-deadline"
[ $((deadline - now)) -ge 65 ] && [ $((deadline - now)) -le 70 ]
MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PYTHON="$TMP/fake-python" \
  LUOSHU_UNIVERSAL_BUDGET_SECONDS=bogus sh "$ROOT/common/universal_font_cutover.sh" switch DemoFont >/dev/null
read -r deadline now < "$MOD/config/prepare-deadline"
[ $((deadline - now)) -ge 325 ] && [ $((deadline - now)) -le 330 ]
rm -rf "$MOD/config"
mv "$TMP/config-after-first-switch" "$MOD/config"

# A failed switch reports the engine message and changes nothing: the queued
# DemoFont request and the active selection stay.
cp "$MOD/config/universal-font-next.conf" "$TMP/next-before.conf"
OUT="$(MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PYTHON="$TMP/fake-python" FAKE_PREPARE=fail \
  sh "$ROOT/common/universal_font_cutover.sh" switch PrepareFail || true)"
printf '%s' "$OUT" | grep -q '"reason":"universal-prepare-failed"'
printf '%s' "$OUT" | grep -q 'fake prepare failed'
grep -q '^state=failed$' "$MOD/config/universal-font-cutover.conf"
cmp -s "$TMP/next-before.conf" "$MOD/config/universal-font-next.conf"
grep -q '^DemoFont$' "$MOD/config/active_font.conf"
[ -d "$MOD/.luoshu-payload-next" ]
[ ! -f "$MOD/config/universal-kept-stock.conf" ]

# Composite temporary families and the old composite runtime are refused.
MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PYTHON="$TMP/fake-python" \
  sh "$ROOT/common/universal_font_cutover.sh" switch LuoShuAutoMix | grep -q '组合字体请在组合页面应用'
LUOSHU_REAL_MODDIR="$MOD" MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PYTHON="$TMP/fake-python" \
  sh "$ROOT/common/universal_font_cutover.sh" switch DemoFont | grep -q '旧组合运行时已停用'

# Restoring the system font stages an empty next payload in default mode and
# records the font running in this boot (OldFont), not the queued DemoFont.
MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PYTHON="$TMP/fake-python" \
  sh "$ROOT/common/universal_font_cutover.sh" switch default | grep -q '"pipeline":"universal-default"'
[ -d "$MOD/.luoshu-payload-next" ] && [ -z "$(ls -A "$MOD/.luoshu-payload-next")" ]
grep -q '^font=default$' "$MOD/config/font-payload-next.conf"
grep -q '^targetMode=default$' "$MOD/config/font-payload-next.conf"
grep -q '^previousFont=OldFont$' "$MOD/config/font-payload-next.conf"
[ ! -f "$MOD/config/universal-font-next.conf" ]
grep -q '^default$' "$MOD/config/active_font.conf"
grep -q '^font=default$' "$MOD/config/text_reboot_required.conf"

rm -rf "$MOD/.luoshu-payload-next"
rm -f "$MOD/config/font-payload-next.conf" "$MOD/config/universal-font-next.conf"
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
