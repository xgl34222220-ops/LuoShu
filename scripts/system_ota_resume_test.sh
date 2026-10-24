#!/bin/sh
# System OTA trusted rescan -> automatic resume (config/system-ota-resume.conf):
#   pending -> rescan-trusted -> apply-ready -> applied.
# Covers the full flow, a held XML naming a font the new ROM lacks, a failed
# resume boot (re-held, never retried), a user re-apply, the owned-disable rule
# and identical behaviour under Magisk, KernelSU (incl. late-load) and APatch.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d "${TMPDIR:-/tmp}/luoshu-ota-resume.XXXXXX")
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

fail() {
  printf 'system OTA resume regression [%s]: %s\n' "${CASE:-?}" "$*" >&2
  exit 1
}

BIN="$TMP/bin"
mkdir -p "$BIN"
cat > "$BIN/getprop" <<'EOF'
#!/bin/sh
case "$1" in
  ro.build.fingerprint) printf '%s\n' "${FIXTURE_FINGERPRINT:-}" ;;
  ro.build.version.incremental) printf '%s\n' "${FIXTURE_INCREMENTAL:-1}" ;;
esac
EOF
chmod 0755 "$BIN/getprop"
PATH="$BIN:$PATH"
export PATH

# The guard never branches on the root manager.
if grep -n -E '\b(KSU|KSU_VER|KSU_VER_CODE|APATCH|APATCH_VER|MAGISK_VER|MAGISK_VER_CODE|BOOTMODE)\b' \
     "$ROOT/common/system_ota_guard.sh"; then
  CASE=static fail 'system_ota_guard.sh depends on a root-manager variable'
fi

STATE_OF() { sed -n 's/^state=//p' "$MODDIR/config/system-ota-resume.conf" 2>/dev/null | head -n1; }
VALUE_OF() { sed -n "s/^$1=//p" "$MODDIR/config/system-ota-resume.conf" 2>/dev/null | head -n1; }
LOG() { cat "$MODDIR/logs/fontswitch.log" 2>/dev/null || true; }

# setup NAME: fresh module with an applied Demo font on build fp-old.
setup() {
  CASE="$1"
  MODDIR="$TMP/$1/module"
  PAYLOAD="$MODDIR/.luoshu-payload"
  STOCK="$TMP/$1/stock"
  mkdir -p "$MODDIR/common" "$MODDIR/config" "$PAYLOAD/system/etc" "$PAYLOAD/system/fonts" \
           "$PAYLOAD/product/etc" "$STOCK/system/fonts" "$STOCK/product/fonts"
  printf 'id=LuoShu\n' > "$MODDIR/module.prop"
  cp "$ROOT/common/system_ota_guard.sh" "$MODDIR/common/system_ota_guard.sh"
  printf '<familyset><family><font weight="400">LuoShu-400.ttf</font></family></familyset>\n' \
    > "$PAYLOAD/system/etc/fonts.xml"
  printf '<familyset><family><font>Roboto-Regular.ttf</font></family></familyset>\n' \
    > "$PAYLOAD/product/etc/fonts_customization.xml"
  sed -i 's#<familyset>#<familyset><!-- LuoShu -->#' \
    "$PAYLOAD/system/etc/fonts.xml" "$PAYLOAD/product/etc/fonts_customization.xml"
  dd if=/dev/zero of="$PAYLOAD/system/fonts/LuoShu-400.ttf" bs=1024 count=1 2>/dev/null
  dd if=/dev/zero of="$STOCK/system/fonts/Roboto-Regular.ttf" bs=1024 count=1 2>/dev/null
  printf 'Demo\n' > "$MODDIR/config/active_font.conf"
  printf 'font=Demo\nfile=a\n' > "$MODDIR/config/font-payload-manifest.conf"
  printf 'fingerprint=fp-old\nincremental=1\n' > "$MODDIR/config/system-build.conf"
  LUOSHU_SYSTEM_OTA_STOCK_ROOT="$STOCK"
  MODULE_DIR="$MODDIR"
  export MODDIR MODULE_DIR LUOSHU_SYSTEM_OTA_STOCK_ROOT
  unset LUOSHU_BOOTLOOP_BOOT_ID || true
  . "$MODDIR/common/system_ota_guard.sh"
}

# early BOOT: post-fs-data on the new ROM. Returns the guard's status.
early() {
  FIXTURE_FINGERPRINT="${FP:-fp-new}" LUOSHU_BOOTLOOP_BOOT_ID="$1" \
    luoshu_system_ota_early_boot "$MODDIR" "$1"
}
# post BOOT MOUNT_STATE: boot completed, module_status.sh -> luoshu_system_ota_check.
post() {
  printf 'state=%s\n' "$2" > "$MODDIR/config/self-mount.conf"
  printf 'completedBootId=%s\n' "$1" > "$MODDIR/config/boot-loop-guard.conf"
  FIXTURE_FINGERPRINT="${FP:-fp-new}" LUOSHU_BOOTLOOP_BOOT_ID="$1" \
    luoshu_system_ota_check "$MODDIR" "$(head -n1 "$MODDIR/config/active_font.conf")" "$2" || true
}
# rescan: the stock scan ran on this build and consumed the marker (after the
# first post-boot check, which re-requests the scan when it records the build).
rescan() {
  rm -f "$MODDIR/config/stock_inventory_scan_pending"
  printf '{"schema":1,"buildFingerprint": "%s","fonts":[]}\n' "${FP:-fp-new}" \
    > "$MODDIR/config/device_font_inventory.json"
}
held() { [ -f "$MODDIR/.luoshu-ota-held-xml/system/etc/fonts.xml" ]; }
in_payload() { [ -f "$PAYLOAD/system/etc/fonts.xml" ]; }

# Owned disable written by an earlier LuoShu protection path.
own_disable() {
  printf 'luoshu-system-ota-v1:%s\n' "$1" > "$MODDIR/disable"
  printf 'schema=luoshu-ota-disable-owner-v1\ntoken=luoshu-system-ota-v1:%s\n' "$1" \
    > "$MODDIR/config/system-ota-disable-owner.conf"
}

# full_flow NAME: OTA -> hold -> trusted rescan -> resume -> applied.
full_flow() {
  setup "$1"
  own_disable "$1"
  early b1 || fail 'OTA not held on the first boot'
  held || fail 'XML not held'
  [ "$(STATE_OF)" = pending ] || fail "expected pending, got $(STATE_OF)"
  # Boot completes before the deferred rescan: still pending.
  post b1 mounted
  [ "$(STATE_OF)" = pending ] || fail "untrusted rescan advanced: $(STATE_OF)"
  grep -qx 'fingerprint=fp-new' "$MODDIR/config/system-build.conf" || fail 'post check did not record the build'
  # Second boot, scan still pending: hold continues.
  early b2 || fail 'XML released before a trusted rescan'
  held || fail 'held XML lost'
  rescan
  post b2 mounted
  [ "$(STATE_OF)" = apply-ready ] || fail "trusted rescan did not reach apply-ready: $(STATE_OF)"
  LOG | grep -q '\[SYSTEM-OTA-RESUME\].*原厂字体重扫可信' || fail 'rescan-trusted not logged'
  # Third boot resumes.
  if early b3; then fail 'apply-ready boot still held'; fi
  in_payload || fail 'XML not put back on the resume boot'
  [ ! -e "$MODDIR/.luoshu-ota-held-xml" ] || fail 'held directory left after resume'
  [ "$(VALUE_OF applyBootId)" = b3 ] || fail 'resume boot not recorded'
  [ -f "$MODDIR/disable" ] || fail 'owned disable removed before the resume was confirmed'
  post b3 mounted
  [ "$(STATE_OF)" = applied ] || fail "resume not confirmed: $(STATE_OF)"
  [ ! -e "$MODDIR/disable" ] || fail 'owned disable not removed after applied'
  [ ! -e "$MODDIR/config/system-ota-disable-owner.conf" ] || fail 'owner record left behind'
  # Later boots: nothing held.
  if early b4; then fail 'held after applied'; fi
  in_payload || fail 'XML missing after applied'
  [ "$(STATE_OF)" = applied ] || fail "applied state changed: $(STATE_OF)"
}

# 1. Full flow.
full_flow full
LOG | grep -q '\[SYSTEM-OTA-RESUME\].*系统更新后的字体已恢复（mounted）' || fail 'applied not logged'

# 2. Held XML names a font the new ROM does not have: keep holding.
setup missing-font
printf '<familyset><!-- LuoShu --><family><font>LuoShu-400.ttf</font><font>Gone-Regular.ttf</font></family></familyset>\n' \
  > "$PAYLOAD/system/etc/fonts.xml"
early m1 || fail 'OTA not held'
post m1 mounted
rescan
post m1 mounted
[ "$(STATE_OF)" = rescan-trusted ] || fail "missing font did not stop at rescan-trusted: $(STATE_OF)"
LOG | grep -q '\[SYSTEM-OTA-RESUME\].*不存在的字体：.*Gone-Regular.ttf' || fail 'missing font not logged'
early m2 || fail 'XML released although a referenced font is missing'
held || fail 'held XML lost'
early m3 || fail 'XML released on a later boot although the font is still missing'
[ "$(grep -c '不存在的字体' "$MODDIR/logs/fontswitch.log")" = 1 ] || fail 'missing-font message repeated every boot'
# Absolute paths and stock fonts resolve; the font appearing on the ROM resumes.
dd if=/dev/zero of="$STOCK/product/fonts/Gone-Regular.ttf" bs=1024 count=1 2>/dev/null
post m3 mounted
[ "$(STATE_OF)" = apply-ready ] || fail "font now present but not apply-ready: $(STATE_OF)"

# 3. The resume boot fails: hold again, never retry the same XML.
setup failed
early f1 || fail 'OTA not held'
post f1 mounted
rescan
post f1 mounted
[ "$(STATE_OF)" = apply-ready ] || fail "not apply-ready: $(STATE_OF)"
if early f2; then fail 'resume boot held'; fi
post f2 failed
[ "$(STATE_OF)" = rescan-trusted ] || fail "failed resume did not fall back: $(STATE_OF)"
[ "$(VALUE_OF applyFailedReason)" = mount-failed ] || fail 'failure reason missing'
LOG | grep -q '\[SYSTEM-OTA-RESUME\].*重新暂停；不会自动重试' || fail 'failed resume not logged'
# The XML is in the payload after the failed boot; the next boot holds it again.
early f3 || fail 'failed resume not re-held'
held || fail 'XML not held after the failed resume'
post f3 mounted
[ "$(STATE_OF)" = rescan-trusted ] || fail "failed XML retried automatically: $(STATE_OF)"
early f4 || fail 'failed XML released on a later boot'
# Boot that never completes (no module_status): judged on the next early boot.
setup unfinished
early u1 || fail 'OTA not held'
post u1 mounted
rescan
post u1 mounted
if early u2; then fail 'resume boot held'; fi
# u2 never completed: boot-loop-guard.conf still names u1.
early u3 || fail 'unfinished resume boot not re-held'
held || fail 'XML not held after the unfinished resume'
[ "$(VALUE_OF applyFailedReason)" = boot-not-completed ] || fail "unexpected reason $(VALUE_OF applyFailedReason)"

# 4. User re-applies after the failure.
CASE=failed
MODDIR="$TMP/failed/module"; PAYLOAD="$MODDIR/.luoshu-payload"; MODULE_DIR="$MODDIR"
printf '<familyset><!-- LuoShu --><family><font>LuoShu-700.ttf</font></family></familyset>\n' \
  > "$PAYLOAD/system/etc/fonts.xml"
printf 'font=Demo\nfile=b\n' > "$MODDIR/config/font-payload-manifest.conf"
if early f5; then fail 'held after the user re-applied'; fi
grep -q 'LuoShu-700' "$PAYLOAD/system/etc/fonts.xml" || fail 'held XML overwrote the re-applied XML'
[ ! -e "$MODDIR/.luoshu-ota-held-xml" ] || fail 'stale held XML left after re-apply'
[ "$(STATE_OF)" = applied ] || fail "re-apply did not end the hold: $(STATE_OF)"
[ "$(VALUE_OF reason)" = user-reapply ] || fail 're-apply reason missing'
# Manifest identity alone (switch to another font while pending) also ends it.
setup reapply-identity
early r1 || fail 'OTA not held'
post r1 mounted
printf 'Other\n' > "$MODDIR/config/active_font.conf"
if early r2; then fail 'held after switching font'; fi
[ "$(VALUE_OF reason)" = user-reapply ] || fail 'identity change not treated as re-apply'

# 5. Only LuoShu's own disable is removed.
check_disable() { # NAME DISABLE_CONTENT OWNER_CONTENT EXPECT(kept|removed)
  full_flow_prep "$1"
  printf "%s\n" "$2" > "$MODDIR/disable"
  if [ -n "$3" ]; then printf '%s' "$3" > "$MODDIR/config/system-ota-disable-owner.conf"; fi
  post d2 mounted
  [ "$(STATE_OF)" = applied ] || fail "not applied: $(STATE_OF)"
  case "$4" in
    kept) [ -f "$MODDIR/disable" ] || fail 'foreign disable removed' ;;
    removed) [ ! -e "$MODDIR/disable" ] || fail 'owned disable not removed' ;;
  esac
}
full_flow_prep() {
  setup "$1"
  early d0 || fail 'OTA not held'
  post d0 mounted
  rescan
  post d0 mounted
  early d2 || true
}
check_disable disable-user '' '' kept
check_disable disable-manager 'manager' '' kept
check_disable disable-foreign-token 'luoshu-system-ota-v1:other' \
  "$(printf 'schema=luoshu-ota-disable-owner-v1\ntoken=luoshu-system-ota-v1:mine\n')" kept
[ ! -e "$MODDIR/config/system-ota-disable-owner.conf" ] || fail 'stale owner record kept'
check_disable disable-bad-schema 'luoshu-system-ota-v1:x' \
  "$(printf 'schema=other\ntoken=luoshu-system-ota-v1:x\n')" kept
check_disable disable-foreign-prefix 'other-module:x' \
  "$(printf 'schema=luoshu-ota-disable-owner-v1\ntoken=other-module:x\n')" kept
check_disable disable-owned 'luoshu-system-ota-v1:mine' \
  "$(printf 'schema=luoshu-ota-disable-owner-v1\ntoken=luoshu-system-ota-v1:mine\n')" removed
# Symlinked owner record is never trusted.
full_flow_prep disable-symlink
printf 'luoshu-system-ota-v1:s\n' > "$MODDIR/disable"
printf 'schema=luoshu-ota-disable-owner-v1\ntoken=luoshu-system-ota-v1:s\n' > "$TMP/owner-elsewhere"
ln -s "$TMP/owner-elsewhere" "$MODDIR/config/system-ota-disable-owner.conf"
post d2 mounted
[ -f "$MODDIR/disable" ] || fail 'disable removed via a symlinked owner record'
# The guard itself never creates a disable.
setup no-create
early n1 || true; post n1 mounted; rescan; post n1 mounted; early n2 || true; post n2 failed; early n3 || true
[ ! -e "$MODDIR/disable" ] || fail 'guard created a disable file'

# 6. Root managers: the same result under Magisk, KernelSU, KernelSU late-load
#    and APatch. Late-load runs post-fs-data and module_status in one boot after
#    boot completed, so the rescan can be trusted within the held boot.
for mgr in magisk ksu apatch; do
  (
    case "$mgr" in
      magisk) MAGISK_VER=27.0; MAGISK_VER_CODE=27000; export MAGISK_VER MAGISK_VER_CODE ;;
      ksu) KSU=true; KSU_VER_CODE=12000; export KSU KSU_VER_CODE ;;
      apatch) APATCH=true; APATCH_VER_CODE=11000; export APATCH APATCH_VER_CODE ;;
    esac
    full_flow "mgr-$mgr"
  ) || fail "full flow failed under $mgr"
done
(
  KSU=true; KSU_VER_CODE=12000; KSU_LATE_LOAD=1; export KSU KSU_VER_CODE KSU_LATE_LOAD
  setup mgr-ksu-late
  early l1 || fail 'late-load: OTA not held'
  post l1 mounted
  rescan
  post l1 mounted
  [ "$(STATE_OF)" = apply-ready ] || fail "late-load: not apply-ready in the held boot: $(STATE_OF)"
  # Repeated late post-fs-data in the same boot keeps the hold for that boot.
  early l1 || fail 'late-load: repeated post-fs-data lost the hold'
  if early l2; then fail 'late-load: resume boot held'; fi
  in_payload || fail 'late-load: XML not put back'
  post l2 mounted
  [ "$(STATE_OF)" = applied ] || fail "late-load: not applied: $(STATE_OF)"
) || fail 'KernelSU late-load flow failed'

# 7. A second OTA while pending restarts tracking for the newer build.
setup second-ota
early s1 || fail 'OTA not held'
post s1 mounted
FP=fp-newer early s2 || fail 'second OTA not held'
[ "$(VALUE_OF fingerprint)" = fp-newer ] || fail 'second OTA did not restart the record'
[ "$(STATE_OF)" = pending ] || fail "second OTA state $(STATE_OF)"

printf 'System OTA resume checks passed.\n'
