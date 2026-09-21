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
    printf 'switch-start|%s\n' "\${2:-}" >> "$CALLS"
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
    printf 'mix-start|%s|%s|%s|%s|%s|%s\n' "\${2:-}" "\${3:-}" "\${4:-}" "\${5:-}" "\${6:-}" "\${7:-}" >> "$CALLS"
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
grep -qx 'switch-start|Demo' "$CALLS"
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
grep -qx 'mix-start|CJK Demo|Latin Demo|Digit Demo|wght=500,wdth=95|wght=600|wght=700' "$CALLS"
grep -qx 'font=mix' "$MOD/config/font-payload-rebuild-pending.conf"
grep -qx 'reason=coverage-remediate' "$MOD/config/font-payload-rebuild-pending.conf"

sh -n "$ROOT/common/app_bridge.sh"
grep -q 'coverage_reapply)' "$ROOT/common/app_bridge.sh"
grep -q 'coverage_verify)' "$ROOT/common/app_bridge.sh"
grep -q 'coverage_export)' "$ROOT/common/app_bridge.sh"
grep -q 'device_font_candidates.json' "$ROOT/common/app_bridge.sh"

echo 'Font coverage center backend tests passed.'
