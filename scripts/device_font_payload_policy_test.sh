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
_dfcache_inventory_key() { printf 'fixture-inventory-key\n'; }
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
inventoryKey=fixture-inventory-key
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
inventoryKey=fixture-inventory-key
EOF

a=0
device_font_payload_build_install SameFont || a=$?
ok test "$a" -eq 0
ok grep -qx SameFont "$TMP/schedules"
ok grep -qx SameFont "$TMP/builds"
ok grep -qx SameFont "$TMP/activations"

# Same template/font but a different scanner inventory must rebuild the aligned payload.
# The previous fixture created a ready marker for the old identity; the real cache
# key includes inventoryKey, so do not let this simplified font-name-only stub
# pretend that stale marker is a hit for the new inventory.
rm -f "$TMP/cache-ready-SameFont"
: > "$TMP/schedules"
: > "$TMP/builds"
: > "$TMP/activations"
cat > "$MODULE/config/device-font-engine.conf" <<'EOF'
state=installed
font=SameFont
templateKey=fixture-template-key
inventoryKey=old-inventory-key
EOF
a=0
device_font_payload_build_install SameFont || a=$?
ok test "$a" -eq 0
ok grep -qx SameFont "$TMP/schedules"
ok grep -qx SameFont "$TMP/builds"
ok grep -qx SameFont "$TMP/activations"

CASE='OriginOS final policy keeps legacy dialer slots'
mkdir -p "$MODULE/system/fonts/.luoshu-font-store"
printf 'origin-anchor\n' > "$MODULE/system/fonts/.luoshu-font-store/regular.font"
_luoshu_detect_originos() { return 0; }
_lfrp_payload_font_dir() { printf '%s/system/fonts\n' "$MODULE"; }
_lfrp_alias_originos_critical() {
    printf '%s\n' "$2" >> "$TMP/origin-critical"
    printf '1\n'
}
_device_font_stage_originos_critical
ok grep -qx VivoFont.ttf "$TMP/origin-critical"
ok grep -qx DroidSansFallbackBBK.ttf "$TMP/origin-critical"

# Without a trusted stock template, generic ROMs refuse an uncertain per-slot payload.
# Never instruct the user to restore the system/default font as a prerequisite.
unset LUOSHU_TRUSTED_TEMPLATE_KEY
rm -f "$MODULE/common/device_font_template.sh"
unset IS_COLOROS LUOSHU_SAFE_PHYSICAL_FALLBACK 2>/dev/null || true
a=0
device_font_payload_build_install MissingTemplate || a=$?
ok test "$a" -eq 2
ok test "$LUOSHU_DEVICE_PAYLOAD_ERROR" = '缺少可信原厂字体模板，未提交不确定的逐槽负载'
case "$LUOSHU_DEVICE_PAYLOAD_ERROR" in
    *'恢复系统默认字体'*) fail '错误提示不应要求恢复系统默认字体' ;;
esac

# ColorOS is different: if the foreground mapper already staged the verified
# system/system_ext/product physical slots, a missing template must not block the switch.
IS_COLOROS=true
LUOSHU_SAFE_PHYSICAL_FALLBACK=1
export IS_COLOROS LUOSHU_SAFE_PHYSICAL_FALLBACK
a=0
device_font_payload_build_install ColorOsPhysicalFallback || a=$?
ok test "$a" -eq 3
ok grep -q 'ColorOS 原厂模板不可用；保留已验证的 system/system_ext/product 物理槽映射' "$MODULE/logs/device-font-payload.log"

sh -n "$ROOT/common/device_font_payload_policy.sh"
echo 'Device font foreground policy tests passed.'
