#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-device-runtime)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MODULE="$TMP/module"
OVERLAY="$TMP/overlay"
TARGET="$TMP/data-fonts-config.xml"
ORIGINAL="$TMP/data-fonts-config.original.xml"
MOUNTINFO="$TMP/mountinfo"
BIN="$TMP/bin"
FONT=$(find /usr/share/fonts -type f \( -iname 'DejaVuSans.ttf' -o -iname 'LiberationSans-Regular.ttf' \) -print -quit)
test -s "$FONT"

mkdir -p "$MODULE/common" "$MODULE/config" "$MODULE/system/etc" "$BIN" \
    "$OVERLAY/system/fonts" "$OVERLAY/system/etc" "$OVERLAY/dynamic"
cp "$ROOT/common/device_font_payload_runtime.sh" "$MODULE/common/device_font_payload_runtime.sh"
cp "$ROOT/common/device_font_dynamic_guard.sh" "$MODULE/common/device_font_dynamic_guard.sh"
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
cp "$TARGET" "$ORIGINAL"
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
LUOSHU_PAYLOAD_SCHEMA_CURRENT=device-template-v1-baseline-v7-mono-v6
LUOSHU_MOUNTINFO="$MOUNTINFO"
export MODDIR MODULE_DIR LUOSHU_DATA_FONTS_CONFIG_TARGET LUOSHU_PAYLOAD_SCHEMA_CURRENT LUOSHU_MOUNTINFO
. "$MODULE/common/device_font_payload_runtime.sh"
. "$MODULE/common/device_font_dynamic_guard.sh"
set -eu

_dfpr_install_overlay "$OVERLAY"
test -s "$MODULE/system/fonts/LuoShuSlot-fixture-400.ttf"
test -s "$MODULE/system/etc/font_fallback.xml"
test -s "$MODULE/system/etc/.luoshu-data-fonts-config.xml"
grep -q '^targetSha256=' "$MODULE/config/device-font-dynamic-mount.conf"
grep -q '^file|system/etc/.luoshu-data-fonts-config.xml|' "$MODULE/config/device-font-installed.conf"
printf 'state=installed\nschema=device-font-payload-v1\nfont=fixture\n' > "$MODULE/config/device-font-engine.conf"
printf 'fixture\n' > "$MODULE/config/active_font.conf"
printf 'schema=device-template-v1-baseline-v7-mono-v6\nfont=fixture\n' > "$MODULE/config/font-payload-schema.conf"
device_font_payload_validate_installed

# Simulate the early-boot read-only bind. Boot-complete release must verify that the
# visible target is LuoShu's sanitized source, unmount it and reveal the original XML.
cp "$MODULE/system/etc/.luoshu-data-fonts-config.xml" "$TARGET"
printf '101 1 0:42 / %s ro,relatime - tmpfs tmpfs ro\n' "$TARGET" > "$MOUNTINFO"
cat > "$BIN/umount" <<'EOF_UMOUNT'
#!/bin/sh
[ "$1" = "$LUOSHU_RELEASE_TARGET" ] || exit 1
cp "$LUOSHU_RELEASE_ORIGINAL" "$LUOSHU_RELEASE_TARGET" || exit 1
: > "$LUOSHU_MOUNTINFO"
printf '%s\n' "$1" > "$LUOSHU_RELEASE_LOG"
EOF_UMOUNT
chmod 0755 "$BIN/umount"
PATH="$BIN:$PATH"
LUOSHU_RELEASE_TARGET="$TARGET"
LUOSHU_RELEASE_ORIGINAL="$ORIGINAL"
LUOSHU_RELEASE_LOG="$TMP/release.log"
export PATH LUOSHU_RELEASE_TARGET LUOSHU_RELEASE_ORIGINAL LUOSHU_RELEASE_LOG

device_font_dynamic_mount_release
test "$(cat "$TMP/release.log")" = "$TARGET"
cmp -s "$TARGET" "$ORIGINAL"
test ! -s "$MOUNTINFO"

# A changed FontManagerService config must be detected before any bind mount is attempted,
# and the complete active payload is scheduled for one background rebuild.
printf '<fontConfig version="changed"/>\n' > "$TARGET"
set +e
device_font_dynamic_mount_apply
RC=$?
set -e
test "$RC" -eq 2
grep -q '^state=pending$' "$MODULE/config/font-payload-rebuild-pending.conf"
grep -q '^font=fixture$' "$MODULE/config/font-payload-rebuild-pending.conf"
grep -q '^reason=dynamic-config-changed$' "$MODULE/config/font-payload-rebuild-pending.conf"

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

# A missing real dynamic config removes stale state instead of carrying it into the next boot.
printf 'stale\n' > "$MODULE/system/etc/.luoshu-data-fonts-config.xml"
printf 'state=prepared\n' > "$MODULE/config/device-font-dynamic-mount.conf"
rm -f "$TARGET"
: > "$MODULE/config/dynamic-manifest.tmp"
set +e
_dfpr_prepare_dynamic_state "$OVERLAY" "$MODULE/config/dynamic-manifest.tmp"
RC=$?
set -e
test "$RC" -eq 2
test ! -e "$MODULE/system/etc/.luoshu-data-fonts-config.xml"
test ! -e "$MODULE/config/device-font-dynamic-mount.conf"

# Syntax and architecture boundaries.
sh -n "$ROOT/common/device_font_payload_runtime.sh"
sh -n "$ROOT/common/device_font_dynamic_guard.sh"
sh -n "$ROOT/common/device_font_payload_bridge.sh"
grep -q 'mount -o bind' "$ROOT/common/device_font_dynamic_guard.sh"
grep -q 'remount,bind,ro' "$ROOT/common/device_font_dynamic_guard.sh"
grep -q '_dfpr_dynamic_mount_is_readonly' "$ROOT/common/device_font_dynamic_guard.sh"
grep -q 'device_font_dynamic_mount_release' "$ROOT/common/device_font_dynamic_guard.sh"
grep -q 'targetSha256' "$ROOT/common/device_font_dynamic_guard.sh"
! grep -qE 'cp -f .*LUOSHU_PROVIDER_DIR|cp -f .*_lpcs_f' "$ROOT/common/font_provider_cache.sh"
grep -q 'never overwrites provider font files' "$ROOT/common/font_provider_cache.sh"

echo 'Device font payload runtime tests passed.'
