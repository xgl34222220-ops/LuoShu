#!/bin/sh
# Early (pre-mount) system OTA detection: on a ro.build.fingerprint mismatch the
# first boot skips the generated XML overlay and the /data/fonts dynamic view,
# keeps the physical slots, requests the existing rescan; later boots keep the
# hold until the rescanned stock inventory is trusted, then put the XML back.
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

# Step 6 left a payload manifest behind; it did not exist when the hold began,
# so drop it again (a changed manifest identity means "the user re-applied").
rm -f "$MODDIR/config/font-payload-manifest.conf"

# 8. Next boot: the post-boot check recorded the new build, but the stock
#    inventory is not trusted yet (rescan still pending, no inventory for this
#    build): the hold continues and the XML stays out of the payload.
printf 'fingerprint=fp-new\nincremental=2\npreviousFingerprint=fp-old\n' > "$MODDIR/config/system-build.conf"
grep -qx 'state=pending' "$MODDIR/config/system-ota-resume.conf" || fail 'resume record not pending after the hold'
early boot-c fp-new || fail 'XML released before the stock inventory was trusted'
[ ! -e "$PAYLOAD/system/etc/fonts.xml" ] || fail 'system XML back while the inventory is untrusted'
[ -f "$MODDIR/.luoshu-ota-held-xml/system/etc/fonts.xml" ] || fail 'held XML lost while untrusted'
grep -qx 'bootId=boot-c' "$MODDIR/config/system-ota-boot-hold.conf" || fail 'hold not re-recorded for the untrusted boot'
grep -qx 'state=pending' "$MODDIR/config/system-ota-resume.conf" || fail 'untrusted inventory advanced the resume state'
grep -q '\[SYSTEM-OTA-RESUME\].*继续暂停' "$MODDIR/logs/fontswitch.log" || fail 'continued hold not logged'

# 9. A trusted inventory for this build (rescan marker consumed, inventory
#    fingerprint == ro.build.fingerprint) and every referenced font present:
#    the next boot puts the held XML back.
rm -f "$MODDIR/config/stock_inventory_scan_pending"
printf '{"buildFingerprint": "fp-new", "fonts": []}\n' > "$MODDIR/config/device_font_inventory.json"
mkdir -p "$PAYLOAD/product/fonts"
dd if=/dev/zero of="$PAYLOAD/product/fonts/LuoShuSlot-1.ttf" bs=2048 count=1 2>/dev/null
if early boot-d fp-new; then fail 'held again with a trusted inventory'; fi
[ -f "$PAYLOAD/system/etc/fonts.xml" ] || fail 'system XML not restored with a trusted inventory'
[ -f "$PAYLOAD/product/etc/fonts_customization.xml" ] || fail 'product XML not restored with a trusted inventory'
[ ! -e "$MODDIR/.luoshu-ota-held-xml" ] || fail 'held directory left behind'
grep -qx 'state=apply-ready' "$MODDIR/config/system-ota-resume.conf" || fail 'resume record not apply-ready'
grep -qx 'applyBootId=boot-d' "$MODDIR/config/system-ota-resume.conf" || fail 'resume boot not recorded'
if LUOSHU_BOOTLOOP_BOOT_ID=boot-d luoshu_system_ota_boot_hold_active "$MODDIR"; then fail 'hold active in the resume boot'; fi

printf 'System OTA early detection checks passed.\n'
