#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/scripts/assert.sh"
CASE='负载策略'
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-policy)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MODULE="$TMP/module"
mkdir -p "$MODULE/config" "$MODULE/logs"
MODDIR="$MODULE"
MODULE_DIR="$MODULE"
LUOSHU_TRUSTED_TEMPLATE_KEY=fixture-template-key
export MODDIR MODULE_DIR LUOSHU_TRUSTED_TEMPLATE_KEY

device_font_payload_validate_installed() { return 0; }
device_font_cache_activate() {
    [ -f "$TMP/cache-ready-$1" ] || return 2
    printf '%s\n' "$1" >> "$TMP/activations"
    return 0
}
device_font_cache_schedule() {
    printf '%s\n' "$1" >> "$TMP/schedules"
    return 0
}
device_font_cache_build_pending() {
    _test_font=$(tail -n1 "$TMP/schedules")
    : > "$TMP/cache-ready-$_test_font"
    printf '%s\n' "$_test_font" >> "$TMP/builds"
    return 0
}

. "$ROOT/common/device_font_payload_policy.sh"

cat > "$MODULE/config/device-font-engine.conf" <<'EOF'
state=installed
font=SameFont
templateKey=fixture-template-key
EOF

device_font_payload_build_install SameFont
no test -s "$TMP/schedules"

a=0
device_font_payload_build_install OtherFont || a=$?
ok test "$a" -eq 0
ok grep -qx OtherFont "$TMP/schedules"
ok grep -qx OtherFont "$TMP/builds"
ok grep -qx OtherFont "$TMP/activations"
ok grep -q '同一任务生成最终对齐负载' "$MODULE/logs/device-font-payload.log"

: > "$TMP/schedules"
: > "$TMP/builds"
: > "$TMP/activations"
cat > "$MODULE/config/device-font-engine.conf" <<'EOF'
state=installed
font=SameFont
templateKey=old-template-key
EOF

a=0
device_font_payload_build_install SameFont || a=$?
ok test "$a" -eq 0
ok grep -qx SameFont "$TMP/schedules"
ok grep -qx SameFont "$TMP/builds"
ok grep -qx SameFont "$TMP/activations"

# Without a trusted stock template v4 refuses to commit a universal-metrics fallback.
unset LUOSHU_TRUSTED_TEMPLATE_KEY
rm -f "$MODULE/common/device_font_template.sh"
a=0
device_font_payload_build_install MissingTemplate || a=$?
ok test "$a" -eq 2
ok test "$LUOSHU_DEVICE_PAYLOAD_ERROR" = '缺少原厂字体模板；请先恢复系统默认字体并完整重启一次'

sh -n "$ROOT/common/device_font_payload_policy.sh"
echo 'Device font foreground policy tests passed.'
