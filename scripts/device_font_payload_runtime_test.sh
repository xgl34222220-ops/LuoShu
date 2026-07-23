#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-device-runtime)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MODULE="$TMP/module"
OVERLAY="$TMP/overlay"
TARGET="$TMP/data-fonts-config.xml"
FONT=$(find /usr/share/fonts -type f \( -iname 'DejaVuSans.ttf' -o -iname 'LiberationSans-Regular.ttf' \) -print -quit)
test -s "$FONT"

mkdir -p "$MODULE/common" "$MODULE/config" "$MODULE/system/etc" \
    "$OVERLAY/system/fonts" "$OVERLAY/system/etc" "$OVERLAY/dynamic"
cp "$ROOT/common/device_font_payload_runtime.sh" "$MODULE/common/device_font_payload_runtime.sh"
cp "$FONT" "$OVERLAY/system/fonts/LuoShuSlot-fixture-400.ttf"
cat > "$OVERLAY/system/etc/font_fallback.xml" <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<familyset>
  <family name="sans-serif">
    <font weight="400" style="normal">LuoShuSlot-fixture-400.ttf</font>
  </family>
</familyset>
XML
cat > "$TARGET" <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<fontConfig>
  <family name="google-sans"><font name="GoogleSans-Regular"/></family>
  <family name="emoji"><font name="NotoColorEmoji"/></family>
</fontConfig>
XML
cat > "$OVERLAY/dynamic/data-fonts-config.xml" <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<fontConfig>
  <family name="emoji"><font name="NotoColorEmoji"/></family>
</fontConfig>
XML
printf '{"schema":"device-font-overlay-v1"}\n' > "$OVERLAY/overlay-manifest.json"

MODDIR="$MODULE"
MODULE_DIR="$MODULE"
LUOSHU_DATA_FONTS_CONFIG_TARGET="$TARGET"
export MODDIR MODULE_DIR LUOSHU_DATA_FONTS_CONFIG_TARGET
. "$MODULE/common/device_font_payload_runtime.sh"
set -eu

_dfpr_install_overlay "$OVERLAY"
test -s "$MODULE/system/fonts/LuoShuSlot-fixture-400.ttf"
test -s "$MODULE/system/etc/font_fallback.xml"
test -s "$MODULE/system/etc/.luoshu-data-fonts-config.xml"
grep -q '^targetSha256=' "$MODULE/config/device-font-dynamic-mount.conf"
grep -q '^file|system/etc/.luoshu-data-fonts-config.xml|' "$MODULE/config/device-font-installed.conf"
printf 'state=installed\nschema=device-font-payload-v1\nfont=fixture\n' > "$MODULE/config/device-font-engine.conf"
device_font_payload_validate_installed

# A changed FontManagerService config must be detected before any bind mount is attempted.
printf '<fontConfig version="changed"/>\n' > "$TARGET"
set +e
device_font_dynamic_mount_apply
RC=$?
set -e
test "$RC" -eq 2

# Content tampering invalidates the installed payload manifest.
printf 'damage\n' >> "$MODULE/system/etc/font_fallback.xml"
set +e
device_font_payload_validate_installed
RC=$?
set -e
test "$RC" -eq 1

# Restore default removes only paths owned by the v2 installed manifest.
device_font_payload_clear
test ! -e "$MODULE/system/fonts/LuoShuSlot-fixture-400.ttf"
test ! -e "$MODULE/system/etc/font_fallback.xml"
test ! -e "$MODULE/system/etc/.luoshu-data-fonts-config.xml"
test ! -e "$MODULE/config/device-font-dynamic-mount.conf"
test ! -e "$MODULE/config/device-font-engine.conf"

# Syntax and architecture boundaries.
sh -n "$ROOT/common/device_font_payload_runtime.sh"
sh -n "$ROOT/common/device_font_payload_bridge.sh"
grep -q 'mount -o bind' "$ROOT/common/device_font_payload_runtime.sh"
grep -q 'targetSha256' "$ROOT/common/device_font_payload_runtime.sh"
! grep -qE 'cp -f .*LUOSHU_PROVIDER_DIR|cp -f .*_lpcs_f' "$ROOT/common/font_provider_cache.sh"
grep -q 'never overwrites provider font files' "$ROOT/common/font_provider_cache.sh"

echo 'Device font payload runtime tests passed.'
