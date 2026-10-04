#!/bin/sh
# App composite protocol on the Universal engine: start -> worker -> status,
# failure without legacy fallback, config, recover, controller dispatch.
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/module"
mkdir -p "$MOD/common/legacy_v14_4" "$MOD/config" "$MOD/logs"
cp "$ROOT/common/universal_composite.sh" "$ROOT/common/font_mix_controller.sh" "$MOD/common/"
printf 'OldFont\n' > "$MOD/config/active_font.conf"

# Role check: the "NoLatin" family lacks Latin glyphs.
cat > "$MOD/common/font_role_check.sh" <<'SH'
#!/bin/sh
[ "$1" = NoLatin ] && [ "$2" = latin ] && exit 1
exit 0
SH
# Fake cutover: records the assignment it was given and stages like Universal.
cat > "$MOD/common/universal_font_cutover.sh" <<'SH'
#!/bin/sh
[ "$1" = switch-composite ] || exit 2
cp "$MODDIR/config/universal-composite.conf" "$MODDIR/config/seen-composite.conf"
printf 'budget=%s\n' "${LUOSHU_UNIVERSAL_BUDGET_SECONDS:-}" >> "$MODDIR/config/seen-composite.conf"
if [ "${FAKE_UNIVERSAL:-ok}" != ok ]; then
  printf '{"status":"error","reason":"universal-readiness-gate-rejected","message":"通用引擎无法应用该组合，当前字体未改变（unclassified-text-slot:/system/fonts/X.ttf）"}\n'
  exit 1
fi
printf 'mix\n' > "$MODDIR/config/active_font.conf"
printf 'font=mix\n' > "$MODDIR/config/text_reboot_required.conf"
printf '{"status":"ok","state":"staged-next-boot","pipeline":"universal"}\n'
SH
# A legacy router that must never be reached.
cat > "$MOD/common/legacy_v14_4/mix_router.sh" <<'SH'
#!/bin/sh
printf 'legacy\n' >> "$MODDIR/config/legacy-called"
printf '{"status":"ok","data":{"task":"legacy"}}\n'
SH

wait_done() {
  _i=0
  while [ "$_i" -lt 100 ]; do
    case "$(sed -n 's/^state=//p' "$MOD/config/axes_task.conf")" in success|failed) return 0 ;; esac
    _i=$((_i + 1)); sleep 0.1
  done
  echo "worker did not finish" >&2; cat "$MOD/config/axes_task.conf" >&2; return 1
}

run() { MODDIR="$MOD" sh "$MOD/common/font_mix_controller.sh" "$@"; }

# 1) Success: protocol output, task file, staged identity, saved config.
OUT="$(run start CJKFont LatinFont DigitFont 'wght=400' 'wght=500' 'wght=400' auto fixed auto)"
printf '%s' "$OUT" | grep -q '"status":"ok"'
TASK=$(printf '%s' "$OUT" | sed -n 's/.*"task":"\([^"]*\)".*/\1/p')
case "$TASK" in universal-mix-*) ;; *) echo "bad task $TASK" >&2; exit 1 ;; esac
printf '%s' "$OUT" | grep -q '"latinMode":"fixed"'
wait_done
STATUS="$(run status "$TASK")"
printf '%s' "$STATUS" | grep -q '"state":"success"'
printf '%s' "$STATUS" | grep -q '"latinWeight":500'
printf '%s' "$STATUS" | grep -q '"percent":100'
grep -q '^cjk=CJKFont$' "$MOD/config/seen-composite.conf"
grep -q '^latinMode=fixed$' "$MOD/config/seen-composite.conf"
grep -q '^budget=600$' "$MOD/config/seen-composite.conf"
grep -q '^engine=universal$' "$MOD/config/font_mix.conf"
grep -q '^mix$' "$MOD/config/active_font.conf"
run config | grep -q '"enabled":true'
run config | grep -q '"latin":"LatinFont"'
[ ! -f "$MOD/config/legacy-called" ]
[ ! -e "$MOD/.font_switch.lock" ]

# 2) Failure: reported with the Universal reason, no legacy fallback, no change.
rm -f "$MOD/config/text_reboot_required.conf"
printf 'OldFont\n' > "$MOD/config/active_font.conf"
cp "$MOD/config/font_mix.conf" "$TMP/mix-before.conf"
OUT="$(FAKE_UNIVERSAL=fail run start CJKFont LatinFont DigitFont 'wght=400' 'wght=400' 'wght=400' auto auto auto)"
TASK=$(printf '%s' "$OUT" | sed -n 's/.*"task":"\([^"]*\)".*/\1/p')
FAKE_UNIVERSAL=fail wait_done
STATUS="$(run status "$TASK")"
printf '%s' "$STATUS" | grep -q '"state":"failed"'
printf '%s' "$STATUS" | grep -q 'unclassified-text-slot'
grep -q '^OldFont$' "$MOD/config/active_font.conf"
cmp -s "$TMP/mix-before.conf" "$MOD/config/font_mix.conf"
[ ! -f "$MOD/config/legacy-called" ]

# 3) Precheck and stale/other task handling.
run start CJKFont NoLatin DigitFont | grep -q '英文字体缺少必要字形'
run status other-task | grep -q '任务不存在或已被新任务替换'
printf 'task=stuck\nstate=running\n' > "$MOD/config/axes_task.conf"
run recover | grep -q '"status":"ok"'
grep -q '^state=failed$' "$MOD/config/axes_task.conf"
run reconcile | grep -q '"status":"ok"'

echo "universal_composite_bridge_test: PASS"
