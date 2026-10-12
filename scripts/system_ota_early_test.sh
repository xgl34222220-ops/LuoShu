#!/bin/sh
# Early (pre-mount) system OTA detection: on a ro.build.fingerprint mismatch the
# first boot skips the generated XML overlay and the /data/fonts dynamic view,
# keeps the physical slots, requests the existing rescan, and the next boot
# puts the held XML back before anything validates the payload.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d "${TMPDIR:-/tmp}/luoshu-ota-early.XXXXXX")
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

fail() {
  printf 'system OTA early regression: %s\n' "$*" >&2
  exit 1
}

BIN="$TMP/bin"
mkdir -p "$BIN"
cat > "$BIN/getprop" <<'EOF'
#!/bin/sh
case "$1" in
  ro.build.fingerprint) printf '%s\n' "${FIXTURE_FINGERPRINT:-}" ;;
  ro.build.version.incremental) printf '%s\n' "${FIXTURE_INCREMENTAL:-}" ;;
esac
EOF
chmod 0755 "$BIN/getprop"
PATH="$BIN:$PATH"

MODDIR="$TMP/module"
MODULE_DIR="$MODDIR"
export MODDIR MODULE_DIR PATH
PAYLOAD="$MODDIR/.luoshu-payload"
mkdir -p "$MODDIR/common" "$MODDIR/config" "$PAYLOAD/system/etc" "$PAYLOAD/system/fonts" "$PAYLOAD/product/etc"
printf 'id=LuoShu\n' > "$MODDIR/module.prop"
for file in system_ota_guard.sh font_safety.sh device_font_dynamic_guard.sh device_font_payload_runtime.sh; do
  cp "$ROOT/common/$file" "$MODDIR/common/$file"
done
. "$MODDIR/common/system_ota_guard.sh"

reset_payload() {
  printf '<familyset><font>LuoShu-400.ttf</font></familyset>\n' > "$PAYLOAD/system/etc/fonts.xml"
  printf '<familyset><font>LuoShuSlot-1.ttf</font></familyset>\n' > "$PAYLOAD/product/etc/fonts_customization.xml"
  printf '<unrelated/>\n' > "$PAYLOAD/system/etc/other.xml"
  dd if=/dev/zero of="$PAYLOAD/system/fonts/LuoShu-400.ttf" bs=2048 count=1 2>/dev/null
}
reset_payload
printf 'Demo\n' > "$MODDIR/config/active_font.conf"

early() { # early BOOT_ID FINGERPRINT
  FIXTURE_FINGERPRINT="$2" luoshu_system_ota_early_boot "$MODDIR" "$1"
}

# 1. No baseline recorded yet: nothing to compare.
if early boot-a fp-new; then fail 'held without a recorded baseline'; fi
[ -f "$PAYLOAD/system/etc/fonts.xml" ] || fail 'XML moved without a baseline'

# 2. Same build: no hold.
printf 'fingerprint=fp-old\nincremental=1\n' > "$MODDIR/config/system-build.conf"
if early boot-a fp-old; then fail 'held on an unchanged build'; fi

# 3. Default font: nothing of LuoShu is mounted.
printf 'default\n' > "$MODDIR/config/active_font.conf"
if early boot-a fp-new; then fail 'held while the default font is selected'; fi
printf 'Demo\n' > "$MODDIR/config/active_font.conf"

# 4. OTA: hold this boot.
early boot-b fp-new || fail 'OTA mismatch not detected'
[ ! -e "$PAYLOAD/system/etc/fonts.xml" ] || fail 'generated system XML still in the payload'
[ ! -e "$PAYLOAD/product/etc/fonts_customization.xml" ] || fail 'generated product XML still in the payload'
[ -f "$PAYLOAD/system/etc/other.xml" ] || fail 'unrelated XML was moved'
[ -f "$PAYLOAD/system/fonts/LuoShu-400.ttf" ] || fail 'physical slot removed'
[ -f "$MODDIR/config/stock_inventory_scan_pending" ] || fail 'existing rescan marker not requested'
grep -qx 'bootId=boot-b' "$MODDIR/config/system-ota-boot-hold.conf" || fail 'hold record missing'
grep -qx 'fingerprint=fp-old' "$MODDIR/config/system-build.conf" || fail 'early check must not rewrite the build record'
grep -q '\[SYSTEM-OTA\].*开机早期检测到系统更新' "$MODDIR/logs/fontswitch.log" || fail 'early detection not logged'
# Repeated post-fs-data in the same boot is idempotent.
early boot-b fp-new || fail 'repeated post-fs-data lost the hold'
[ -f "$MODDIR/.luoshu-ota-held-xml/system/etc/fonts.xml" ] || fail 'held XML lost on repeat'

# 5. The hold is per boot.
LUOSHU_BOOTLOOP_BOOT_ID=boot-b luoshu_system_ota_boot_hold_active "$MODDIR" || fail 'hold inactive in its own boot'
if LUOSHU_BOOTLOOP_BOOT_ID=boot-x luoshu_system_ota_boot_hold_active "$MODDIR"; then fail 'hold leaked into another boot'; fi

# 6. font_safety: neither the manifest (XML missing now) nor the transaction is judged.
(
  . "$MODDIR/common/font_safety.sh"
  printf 'schema=%s\n' "$LUOSHU_PAYLOAD_SCHEMA_CURRENT" > "$MODDIR/config/font-payload-schema.conf"
  printf 'state=confirmed\nfont=Demo\n' > "$MODDIR/config/font-payload-boot.conf"
  : > "$MODDIR/config/font-payload-manifest.conf"
  LUOSHU_BOOTLOOP_BOOT_ID=boot-b font_config_boot_guard Demo || exit 11
  grep -qx 'state=confirmed' "$MODDIR/config/font-payload-boot.conf" || exit 12
  [ ! -e "$MODDIR/config/font-payload-quarantine.conf" ] || exit 13
  grep -qx Demo "$MODDIR/config/active_font.conf" || exit 14
) || fail "font_safety judged the payload during the OTA hold (rc=$?)"

# 7. Both dynamic view implementations refuse during the hold. The record is
#    deliberately invalid: outside the hold each implementation rejects it
#    with 1, so a 2 here can only come from the OTA hold.
printf 'source=invalid\ntarget=/data/fonts/config/config.xml\n' \
  > "$MODDIR/config/device-font-dynamic-mount.conf"
for impl in device_font_dynamic_guard.sh device_font_payload_runtime.sh; do
  rc=0
  ( . "$MODDIR/common/device_font_payload_runtime.sh"; . "$MODDIR/common/$impl"; LUOSHU_BOOTLOOP_BOOT_ID=boot-b device_font_dynamic_mount_apply ) >/dev/null 2>&1 || rc=$?
  [ "$rc" = 2 ] || fail "$impl applied the dynamic view during the OTA hold (rc=$rc)"
  rc=0
  ( . "$MODDIR/common/device_font_payload_runtime.sh"; . "$MODDIR/common/$impl"; LUOSHU_BOOTLOOP_BOOT_ID=boot-x device_font_dynamic_mount_apply ) >/dev/null 2>&1 || rc=$?
  [ "$rc" = 1 ] || fail "$impl control (no hold) rc=$rc"
done
rm -f "$MODDIR/config/device-font-dynamic-mount.conf"

# 8. Next boot: the post-boot check recorded the new build; held XML returns.
printf 'fingerprint=fp-new\nincremental=2\npreviousFingerprint=fp-old\n' > "$MODDIR/config/system-build.conf"
if early boot-c fp-new; then fail 'held again on the new, recorded build'; fi
[ -f "$PAYLOAD/system/etc/fonts.xml" ] || fail 'system XML not restored on the next boot'
[ -f "$PAYLOAD/product/etc/fonts_customization.xml" ] || fail 'product XML not restored on the next boot'
[ ! -e "$MODDIR/.luoshu-ota-held-xml" ] || fail 'held directory left behind'

# 9. A newer apply during the held boot wins over the held copy.
printf 'fingerprint=fp-new\n' > "$MODDIR/config/system-build.conf"
early boot-d fp-newer || fail 'second OTA not detected'
printf '<familyset><font>LuoShu-700.ttf</font></familyset>\n' > "$PAYLOAD/system/etc/fonts.xml"
printf 'fingerprint=fp-newer\n' > "$MODDIR/config/system-build.conf"
early boot-e fp-newer || true
grep -q 'LuoShu-700' "$PAYLOAD/system/etc/fonts.xml" || fail 'held XML overwrote a newer apply'

printf 'System OTA early detection checks passed.\n'
