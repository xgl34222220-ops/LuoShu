#!/bin/sh
# KernelSU emulated-soft-reboot stage regression.
# Drives the real router + core with a fake mountinfo and a fake umount that
# pops the most recent mount at a path, so ownership/order rules are exercised.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/scripts/assert.sh"
TMP=$(mktemp -d "${TMPDIR:-/tmp}/luoshu-softreboot.XXXXXX")
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

BOOT=boot-1111
MOD="$TMP/data/adb/modules/LuoShu"
STATE="$TMP/data/adb/luoshu/self-mount"
PRIV="$TMP/data/adb/luoshu/private-payload"
MI="$TMP/mountinfo"
CALLS="$TMP/umount.calls"
BIN="$TMP/bin"

# Fake umount: records the call and removes the LAST mountinfo line at the
# target. FAKE_BUSY targets need -l; FAKE_STUCK targets never unmount.
mkdir -p "$BIN"
cat > "$BIN/fake-umount" <<'EOF'
#!/bin/sh
lazy=0
[ "$1" = -l ] && { lazy=1; shift; }
target="$1"
printf '%s%s\n' "$([ "$lazy" = 1 ] && echo '-l ')" "$target" >> "$FAKE_CALLS"
case " ${FAKE_STUCK:-} " in *" $target "*) exit 1 ;; esac
if [ "$lazy" = 0 ]; then
  case " ${FAKE_BUSY:-} " in *" $target "*) exit 16 ;; esac
fi
awk -v t="$target" '{ l[NR]=$0; if ($5 == t) last=NR } END { if (!last) exit 1; for (i=1;i<=NR;i++) if (i!=last) print l[i] }' \
  "$FAKE_MOUNTINFO" > "$FAKE_MOUNTINFO.new" || { rm -f "$FAKE_MOUNTINFO.new"; exit 1; }
mv "$FAKE_MOUNTINFO.new" "$FAKE_MOUNTINFO"
EOF
chmod 0755 "$BIN/fake-umount"

setup() {
  unset KSU_VALUE FAKE_BUSY FAKE_STUCK 2>/dev/null || true
  rm -rf "$TMP/data" "$MI" "$CALLS"
  mkdir -p "$MOD/.luoshu-runtime/core" "$MOD/config" "$MOD/logs" "$STATE/lower" "$PRIV"
  cp "$ROOT/emulated-soft-reboot.sh" "$MOD/emulated-soft-reboot.sh"
  cp "$ROOT/.luoshu-runtime/core/emulated-soft-reboot.sh" "$MOD/.luoshu-runtime/core/emulated-soft-reboot.sh"
  printf '%s\n' "$BOOT" > "$STATE/boot-id"
  printf 'state=mounted\nbackend=self-overlay-bind\nmounted=system/fonts:overlay\nfailed=\n' > "$MOD/config/self-mount.conf"
  printf 'x|/system/fonts|overlay\n' > "$MOD/config/self-mount-required.conf"
  : > "$CALLS"
  # Journal order as written by luoshu_self_mount_ensure: lower bind, then
  # overlay target; per-file bind lower + file bind for product.
  cat > "$STATE/mounts.list" <<EOF
$STATE/lower/system-fonts
/system/fonts
$STATE/lower/product-fonts
/product/fonts/Roboto.ttf
EOF
  printf '%s/system\n' "$MOD" > "$PRIV/module-view.mounts"
  # Base system + a foreign module layer under ours at /system/fonts.
  cat > "$MI" <<EOF
20 1 253:1 / /system ro shared:1 - ext4 /dev/block/dm-0 ro
30 20 0:40 / /system/fonts ro shared:5 - overlay KSU ro,lowerdir=/data/adb/metamodule/mnt/Other/system/fonts:/system/fonts
41 1 254:5 /adb/modules/LuoShu/.luoshu-payload/system $MOD/system rw - f2fs /dev/block/dm-5 rw
42 1 253:1 /fonts $STATE/lower/system-fonts ro - ext4 /dev/block/dm-0 ro
43 30 0:41 / /system/fonts ro - overlay KSU ro,lowerdir=$MOD/.luoshu-payload/system/fonts:$STATE/lower/system-fonts
44 1 253:2 /fonts $STATE/lower/product-fonts ro - ext4 /dev/block/dm-1 ro
45 1 254:5 /adb/modules/LuoShu/.luoshu-payload/product/fonts/Roboto.ttf /product/fonts/Roboto.ttf ro - f2fs /dev/block/dm-5 rw
50 1 254:5 /adb/modules/Other/system/bin/tool /system/bin/tool ro - f2fs /dev/block/dm-5 rw
EOF
}

run_stage() {
  env KSU="${KSU_VALUE-true}" LUOSHU_TEST_BOOT_ID="$BOOT" \
    LUOSHU_SELF_MOUNT_STATE_ROOT="$STATE" LUOSHU_PRIVATE_STATE_ROOT="$PRIV" \
    LUOSHU_SOFT_REBOOT_MOUNTINFO="$MI" LUOSHU_SELF_UMOUNT_COMMAND="$BIN/fake-umount" \
    FAKE_MOUNTINFO="$MI" FAKE_CALLS="$CALLS" FAKE_BUSY="${FAKE_BUSY:-}" FAKE_STUCK="${FAKE_STUCK:-}" \
    LUOSHU_SOFT_REBOOT_DATA_ROOT="$TMP/data" MODDIR='' MODULE_DIR='' sh "$MOD/emulated-soft-reboot.sh"
}

stage_value() { sed -n "s/^$1=//p" "$MOD/config/ksu-soft-reboot.conf" | head -n1; }

CASE='non-KernelSU caller is a no-op'
setup
cp "$MI" "$TMP/mi.before"
rc=0; KSU_VALUE='' run_stage || rc=$?
eq "$rc" 0
ok cmp -s "$MI" "$TMP/mi.before"
ok test ! -s "$CALLS"
ok test -s "$STATE/mounts.list"
ok test ! -e "$MOD/config/ksu-soft-reboot.conf"

CASE='releases only LuoShu layers, newest first, then resets same-boot decision'
setup
rc=0; run_stage || rc=$?
eq "$rc" 0
eq "$(stage_value state)" ready
eq "$(stage_value released)" 5
eq "$(cat "$CALLS" | tr '\n' ',')" "/product/fonts/Roboto.ttf,$STATE/lower/product-fonts,/system/fonts,$STATE/lower/system-fonts,$MOD/system,"
contains "$MI" 'lowerdir=/data/adb/metamodule/mnt/Other/system/fonts'
contains "$MI" '/system/bin/tool'
contains "$MI" ' /system ro shared:1'
lacks "$MI" "$STATE/"
lacks "$MI" '.luoshu-payload'
ok test ! -s "$STATE/mounts.list"
ok test ! -s "$PRIV/module-view.mounts"
ok test ! -e "$STATE/boot-id"
ok test ! -e "$MOD/config/self-mount-required.conf"
contains "$MOD/config/self-mount.conf" 'state=idle'
contains "$MOD/config/self-mount.conf" 'reason=ksu-soft-reboot'

CASE='busy target falls back to lazy detach'
setup
rc=0; FAKE_BUSY='/system/fonts' run_stage || rc=$?
eq "$rc" 0
eq "$(stage_value state)" ready
ok grep -Fxq -e '-l /system/fonts' "$CALLS"
contains "$MOD/logs/soft-reboot.log" 'detached lazily: /system/fonts'

CASE='stuck target stays journaled and keeps same-boot state'
setup
rc=0; FAKE_STUCK='/system/fonts' run_stage || rc=$?
eq "$rc" 1
eq "$(stage_value state)" failed
eq "$(stage_value reason)" self-mount-release-failed
eq "$(stage_value remaining)" 1
eq "$(cat "$STATE/mounts.list" | tr '\n' ',')" "/system/fonts,"
eq "$(cat "$STATE/boot-id")" "$BOOT"
contains "$MOD/config/self-mount.conf" 'state=mounted'
contains "$MI" 'lowerdir=/data/adb/metamodule/mnt/Other/system/fonts'

CASE='foreign layer stacked above LuoShu is never popped'
setup
printf '60 43 0:50 / /system/fonts ro - overlay KSU ro,lowerdir=/data/adb/metamodule/mnt/Late/system/fonts\n' >> "$MI"
rc=0; run_stage || rc=$?
eq "$rc" 1
eq "$(stage_value state)" failed
contains "$MI" '/data/adb/metamodule/mnt/Late/system/fonts'
contains "$MI" 'lowerdir=/data/adb/metamodule/mnt/Other/system/fonts'
lacks "$CALLS" '/system/fonts'
contains "$STATE/mounts.list" '/system/fonts'
contains "$MOD/logs/soft-reboot.log" 'foreign mount stacked above LuoShu layer'

CASE='duplicate LuoShu layers stacked at one target are all released'
setup
printf '46 43 0:42 / /system/fonts ro - overlay KSU ro,lowerdir=%s/.luoshu-payload/system/fonts:%s/lower/system-fonts\n' "$MOD" "$STATE" >> "$MI"
rc=0; run_stage || rc=$?
eq "$rc" 0
eq "$(grep -cx '/system/fonts' "$CALLS")" 2
lacks "$MI" '.luoshu-payload'
contains "$MI" 'lowerdir=/data/adb/metamodule/mnt/Other/system/fonts'

CASE='journal from an older boot is never replayed'
setup
printf 'boot-0000\n' > "$STATE/boot-id"
# Only the private view remains live; the self-mount layers are gone.
grep -v "$STATE/\|/product/fonts/Roboto.ttf\|lowerdir=$MOD" "$MI" > "$MI.n"; mv "$MI.n" "$MI"
rc=0; run_stage || rc=$?
eq "$rc" 0
eq "$(stage_value state)" ready
lacks "$CALLS" '/system/fonts'
eq "$(cat "$CALLS" | tr '\n' ',')" "$MOD/system,"

CASE='untracked LuoShu mount is reported, not touched'
setup
: > "$STATE/mounts.list"
: > "$PRIV/module-view.mounts"
rc=0; run_stage || rc=$?
eq "$rc" 1
eq "$(stage_value reason)" untracked-luoshu-mount-remains
ok test ! -s "$CALLS"
eq "$(cat "$STATE/boot-id")" "$BOOT"

CASE='module-view journal never reaches outside the module'
setup
: > "$STATE/mounts.list"
grep -v "$STATE/\|/product/fonts/Roboto.ttf\|lowerdir=$MOD" "$MI" > "$MI.n"; mv "$MI.n" "$MI"
printf '/system/bin/tool\n%s/system\n' "$MOD" > "$PRIV/module-view.mounts"
rc=0; run_stage || rc=$?
eq "$rc" 0
lacks "$CALLS" '/system/bin/tool'
contains "$MI" '/system/bin/tool'

CASE='static wiring'
contains "$ROOT/scripts/module_payload_manifest.txt" 'emulated-soft-reboot.sh'
contains "$ROOT/THIRD_PARTY_NOTICES.md" 'Ziyu'
sh -n "$ROOT/emulated-soft-reboot.sh"
sh -n "$ROOT/.luoshu-runtime/core/emulated-soft-reboot.sh"

printf 'KernelSU emulated-soft-reboot checks passed.\n'
