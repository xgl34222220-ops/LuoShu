#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/scripts/assert.sh"
CASE='负载事务守卫'
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-device-transaction)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MODULE="$TMP/module"
mkdir -p "$MODULE/common" "$MODULE/config" "$MODULE/system/fonts" "$MODULE/system/etc"
cp "$ROOT/common/font_safety.sh" "$MODULE/common/font_safety.sh"
cp "$ROOT/common/device_font_payload_runtime.sh" "$MODULE/common/device_font_payload_runtime.sh"
cp "$ROOT/common/device_font_transaction_guard.sh" "$MODULE/common/device_font_transaction_guard.sh"

printf 'old-slot\n' > "$MODULE/system/fonts/LuoShuSlot-old-400.ttf"
printf '<familyset old="true"><font>LuoShuSlot-old-400.ttf</font></familyset>\n' > "$MODULE/system/etc/font_fallback.xml"
printf '<fontConfig sanitized="true"/>\n' > "$MODULE/system/etc/.luoshu-data-fonts-config.xml"
printf 'old-font\n' > "$MODULE/config/active_font.conf"
printf 'state=installed\nschema=device-font-payload-v1\nfont=old-font\n' > "$MODULE/config/device-font-engine.conf"
printf 'state=prepared\nsource=system/etc/.luoshu-data-fonts-config.xml\ntarget=/data/fonts/config/config.xml\n' > "$MODULE/config/device-font-dynamic-mount.conf"
printf 'state=pending\nfont=old-font\n' > "$MODULE/config/device-font-cache-pending.conf"
printf 'state=verified\nmode=aligned\nactiveFont=old-font\n' > "$MODULE/config/device-font-load-verification.conf"
printf '{"state":"verified"}\n' > "$MODULE/config/device-font-load-verification.json"
printf 'LuoShuSlot-old-400\n' > "$MODULE/config/device-font-manager-dump.txt"
printf 'system/fonts/LuoShuSlot-old-400.ttf|/system/fonts/LuoShuSlot-old-400.ttf|ok|a|a|9\n' > "$MODULE/config/device-font-mount-evidence.txt"
cat > "$MODULE/config/device-font-installed.conf" <<'EOF_MANIFEST'
file|system/fonts/LuoShuSlot-old-400.ttf|fixture|9
file|system/etc/font_fallback.xml|fixture|75
file|system/etc/.luoshu-data-fonts-config.xml|fixture|37
EOF_MANIFEST

MODDIR="$MODULE"
MODULE_DIR="$MODULE"
CONFIG_DIR="$MODULE/config"
export MODDIR MODULE_DIR CONFIG_DIR
. "$MODULE/common/font_safety.sh"
. "$MODULE/common/device_font_payload_runtime.sh"
. "$MODULE/common/device_font_transaction_guard.sh"

luoshu_payload_transaction_begin
ok test -n "$LUOSHU_PAYLOAD_TXN"
no test -e "$MODULE/system/fonts/LuoShuSlot-old-400.ttf"
no test -e "$MODULE/system/etc/font_fallback.xml"
no test -e "$MODULE/system/etc/.luoshu-data-fonts-config.xml"
no test -e "$MODULE/config/device-font-engine.conf"
no test -e "$MODULE/config/device-font-installed.conf"
no test -e "$MODULE/config/device-font-dynamic-mount.conf"
no test -e "$MODULE/config/device-font-cache-pending.conf"
no test -e "$MODULE/config/device-font-load-verification.conf"
no test -e "$MODULE/config/device-font-load-verification.json"

# Simulate a later direct/composite stage that partially writes a replacement and fails.
printf 'new-slot\n' > "$MODULE/system/fonts/LuoShuSlot-new-400.ttf"
printf '<familyset new="true"/>\n' > "$MODULE/system/etc/font_fallback.xml"
printf 'new-font\n' > "$MODULE/config/active_font.conf"
printf 'state=installed\nfont=new-font\n' > "$MODULE/config/device-font-engine.conf"
luoshu_payload_transaction_abort

ok test -z "$LUOSHU_PAYLOAD_TXN"
ok test -e "$MODULE/system/fonts/LuoShuSlot-old-400.ttf"
no test -e "$MODULE/system/fonts/LuoShuSlot-new-400.ttf"
ok grep -q 'old="true"' "$MODULE/system/etc/font_fallback.xml"
ok grep -q 'sanitized="true"' "$MODULE/system/etc/.luoshu-data-fonts-config.xml"
ok test "$(cat "$MODULE/config/active_font.conf")" = old-font
ok grep -q '^font=old-font$' "$MODULE/config/device-font-engine.conf"
ok test -s "$MODULE/config/device-font-installed.conf"
ok test -s "$MODULE/config/device-font-dynamic-mount.conf"
ok grep -q '^font=old-font$' "$MODULE/config/device-font-cache-pending.conf"
ok grep -q '^state=verified$' "$MODULE/config/device-font-load-verification.conf"
ok grep -q 'verified' "$MODULE/config/device-font-load-verification.json"
ok test -s "$MODULE/config/device-font-manager-dump.txt"
ok test -s "$MODULE/config/device-font-mount-evidence.txt"

# If the ownership manifest itself is lost, the unique LuoShuSlot namespace still
# provides a safe cleanup boundary. Unrelated ROM XML remains untouched.
rm -f "$MODULE/config/device-font-installed.conf"
mkdir -p "$MODULE/product/fonts" "$MODULE/product/etc"
printf 'orphan-slot\n' > "$MODULE/product/fonts/LuoShuSlot-orphan-500.ttf"
printf '<familyset><font>LuoShuSlot-orphan-500.ttf</font></familyset>\n' > "$MODULE/product/etc/fonts.xml"
printf '<familyset rom="true"/>\n' > "$MODULE/product/etc/rom-fallback.xml"
device_font_payload_clear
no test -e "$MODULE/system/fonts/LuoShuSlot-old-400.ttf"
no test -e "$MODULE/system/etc/font_fallback.xml"
no test -e "$MODULE/product/fonts/LuoShuSlot-orphan-500.ttf"
no test -e "$MODULE/product/etc/fonts.xml"
ok test -e "$MODULE/product/etc/rom-fallback.xml"
no test -e "$MODULE/config/device-font-engine.conf"
no test -e "$MODULE/config/device-font-dynamic-mount.conf"
no test -e "$MODULE/config/device-font-cache-pending.conf"
no test -e "$MODULE/config/device-font-load-verification.conf"

sh -n "$ROOT/common/device_font_transaction_guard.sh"
ok grep -q 'device_font_payload_clear' "$ROOT/common/device_font_transaction_guard.sh"
ok grep -q 'LuoShuSlot-' "$ROOT/common/device_font_transaction_guard.sh"
ok grep -q 'device-font-cache-pending.conf' "$ROOT/common/device_font_transaction_guard.sh"
ok grep -q 'device-font-load-verification.conf' "$ROOT/common/device_font_transaction_guard.sh"

echo 'Device font transaction guard snapshots, clears and restores v2 payload state.'