#!/bin/sh
# KernelSU emulated soft reboot stage regression.
# Drives the real root router and core with a fake mountinfo, a stub umount
# and a simulated boot_id; no real mounts are touched.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d "${TMPDIR:-/tmp}/luoshu-softreboot.XXXXXX")
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

fail() {
  printf 'ksu soft reboot regression: %s\n' "$*" >&2
  exit 1
}

BOOT=11111111-2222-3333-4444-555555555555
MOD="$TMP/adb/modules/LuoShu"
SELF="$TMP/adb/luoshu/self-mount"
PRIV="$TMP/adb/luoshu/private-payload"
INFO="$TMP/mountinfo"
CALLS="$TMP/umount.calls"
STUB="$TMP/umount-stub"

cat > "$STUB" <<'STUBEOF'
#!/bin/sh
# Records each call; removes the topmost matching mountinfo line on success.
lazy=''
[ "$1" = -l ] && { lazy='-l '; shift; }
printf '%s%s\n' "$lazy" "$1" >> "$STUB_CALLS"
for bad in $STUB_FAIL; do
  [ "$bad" = "$1" ] && exit 1
done
awk -v want="$1" '{ line[NR] = $0; if ($5 == want) last = NR }
  END { for (i = 1; i <= NR; i++) if (i != last) print line[i] }' "$STUB_INFO" > "$STUB_INFO.new"
mv "$STUB_INFO.new" "$STUB_INFO"
STUBEOF
chmod 0755 "$STUB"

setup() {
  rm -rf "$TMP/adb" "$CALLS"
  mkdir -p "$MOD/.luoshu-runtime/core" "$MOD/config" "$MOD/logs" "$SELF/lower/system" "$PRIV"
  cp "$ROOT/emulated-soft-reboot.sh" "$MOD/emulated-soft-reboot.sh"
  cp "$ROOT/.luoshu-runtime/core/emulated-soft-reboot.sh" "$MOD/.luoshu-runtime/core/emulated-soft-reboot.sh"
  printf 'id=LuoShu\nname=洛书\n' > "$MOD/module.prop"
  printf '%s\n' "$BOOT" > "$SELF/boot-id"
  printf 'fonts=/system/fonts\n' > "$MOD/config/self-mount-required.conf"
  printf 'state=mounted\nbackend=overlay\n' > "$MOD/config/self-mount.conf"
  : > "$CALLS"
  cat > "$INFO" <<INFOEOF
20 1 253:0 / / ro,relatime - ext4 /dev/block/dm-0 ro
30 20 253:5 / /data rw,relatime - f2fs /dev/block/dm-5 rw
40 20 0:30 / $SELF/lower rw - tmpfs tmpfs rw
41 20 0:31 / /system/fonts ro - overlay overlay ro,lowerdir=$SELF/lower/system/fonts:/system/fonts
42 20 253:5 /adb/luoshu/self-mount/lower/product/fonts /product/fonts ro - f2fs /dev/block/dm-5 rw
43 30 253:5 /adb/luoshu/private-payload/root/system $MOD/system rw - f2fs /dev/block/dm-5 rw
44 20 253:0 /etc /etc/hosts ro - ext4 /dev/block/dm-0 ro
INFOEOF
  printf '%s\n%s\n%s\n' "$SELF/lower" /system/fonts /product/fonts > "$SELF/mounts.list"
  printf '%s\n%s\n' "$MOD/system" /etc/hosts > "$PRIV/module-view.mounts"
}

run_stage() {
  env KSU="${1-true}" \
    LUOSHU_SELF_MOUNT_STATE_ROOT="$SELF" \
    LUOSHU_PRIVATE_STATE_ROOT="$PRIV" \
    LUOSHU_MOUNTINFO="$INFO" \
    LUOSHU_SOFT_REBOOT_BOOT_ID="${2:-$BOOT}" \
    LUOSHU_SOFT_REBOOT_UMOUNT="$STUB" \
    STUB_CALLS="$CALLS" STUB_INFO="$INFO" STUB_FAIL="${3:-}" \
    sh "$MOD/emulated-soft-reboot.sh"
}

prop() {
  sed -n "s/^$2=//p" "$1" | head -n1
}

# 1. Not KernelSU: the stage must be a no-op.
setup
run_stage false
[ ! -s "$CALLS" ] || fail 'non-KSU caller unmounted something'
[ -f "$SELF/boot-id" ] || fail 'non-KSU caller reset boot-id'
[ ! -f "$MOD/config/ksu-soft-reboot.conf" ] || fail 'non-KSU caller wrote a result'
run_stage ''
[ ! -s "$CALLS" ] || fail 'empty KSU unmounted something'

# 2. Clean release: newest first (post-mount exposes the module view before
# the self-mount transaction, so the self-mount journal unwinds first),
# module-view scoped, decision reset.
setup
run_stage
expected="/product/fonts
/system/fonts
$SELF/lower
$MOD/system"
[ "$(cat "$CALLS")" = "$expected" ] || fail "unexpected unmount order: $(cat "$CALLS")"
grep -q '/etc/hosts' "$CALLS" && fail 'module-view target outside module was touched'
[ "$(prop "$MOD/config/ksu-soft-reboot.conf" state)" = ready ] || fail 'clean run not ready'
[ "$(prop "$MOD/config/ksu-soft-reboot.conf" released)" = 4 ] || fail 'released count wrong'
[ "$(prop "$MOD/config/ksu-soft-reboot.conf" remaining)" = 0 ] || fail 'remaining count wrong'
[ ! -e "$SELF/boot-id" ] || fail 'boot-id kept after full release'
[ ! -e "$MOD/config/self-mount-required.conf" ] || fail 'required manifest kept'
[ ! -s "$SELF/mounts.list" ] || fail 'journal not cleared'
[ "$(prop "$MOD/config/self-mount.conf" state)" = idle ] || fail 'self-mount state not idle'
[ "$(prop "$MOD/config/self-mount.conf" reason)" = ksu-soft-reboot ] || fail 'self-mount reason missing'
grep -q ' /etc/hosts ' "$INFO" || fail 'unrelated mount removed'
[ -s "$MOD/logs/soft-reboot.log" ] || fail 'no soft reboot log'

# 3. A foreign module stacked on top of a LuoShu target is never popped.
setup
printf '50 20 253:5 /adb/modules/Other/system/fonts /system/fonts ro - f2fs /dev/block/dm-5 rw\n' >> "$INFO"
run_stage
grep -qx '/system/fonts' "$CALLS" && fail 'foreign top mount was unmounted'
[ "$(prop "$MOD/config/ksu-soft-reboot.conf" state)" = failed ] || fail 'foreign top not reported'
[ "$(prop "$MOD/config/ksu-soft-reboot.conf" remaining)" = 1 ] || fail 'foreign remaining count wrong'
[ "$(cat "$SELF/boot-id")" = "$BOOT" ] || fail 'boot-id reset despite remaining mount'
[ "$(cat "$SELF/mounts.list")" = /system/fonts ] || fail 'journal must keep only the unreleased target'
[ -f "$MOD/config/self-mount-required.conf" ] || fail 'required manifest removed on failure'
[ "$(prop "$MOD/config/self-mount.conf" state)" = mounted ] || fail 'self-mount state changed on failure'

# 4. A journal from an older boot is never replayed.
setup
run_stage true 99999999-0000-0000-0000-000000000000
[ ! -s "$CALLS" ] || fail 'stale journal was replayed'
[ "$(prop "$MOD/config/ksu-soft-reboot.conf" reason)" = no-current-journal ] || fail 'stale reason wrong'
[ -s "$SELF/mounts.list" ] || fail 'stale journal modified'

# 5. Busy target: normal umount fails, lazy umount succeeds.
setup
cat > "$TMP/lazy-only" <<LAZYEOF
#!/bin/sh
[ "\$1" = -l ] || { printf '%s\n' "\$1" >> "$CALLS.busy"; exit 1; }
exec "$STUB" "\$@"
LAZYEOF
chmod 0755 "$TMP/lazy-only"
env KSU=true LUOSHU_SELF_MOUNT_STATE_ROOT="$SELF" LUOSHU_PRIVATE_STATE_ROOT="$PRIV" \
  LUOSHU_MOUNTINFO="$INFO" LUOSHU_SOFT_REBOOT_BOOT_ID="$BOOT" LUOSHU_SOFT_REBOOT_UMOUNT="$TMP/lazy-only" \
  STUB_CALLS="$CALLS" STUB_INFO="$INFO" STUB_FAIL='' sh "$MOD/emulated-soft-reboot.sh"
[ "$(grep -c '^-l ' "$CALLS")" = 4 ] || fail 'lazy fallback not used'
[ "$(prop "$MOD/config/ksu-soft-reboot.conf" state)" = ready ] || fail 'lazy release not ready'

# 6. A target that cannot be released keeps the same-boot rollback path.
setup
run_stage true "$BOOT" /product/fonts
[ "$(prop "$MOD/config/ksu-soft-reboot.conf" state)" = failed ] || fail 'stuck target not reported'
[ "$(prop "$MOD/config/ksu-soft-reboot.conf" released)" = 3 ] || fail 'stuck released count wrong'
[ "$(cat "$SELF/mounts.list")" = /product/fonts ] || fail 'stuck target not kept in journal'
[ -f "$SELF/boot-id" ] || fail 'boot-id reset with stuck target'

# 7. Targets already gone count as released.
setup
grep -v ' /product/fonts ' "$INFO" > "$INFO.new" && mv "$INFO.new" "$INFO"
run_stage
grep -qx '/product/fonts' "$CALLS" && fail 'absent target was unmounted'
[ "$(prop "$MOD/config/ksu-soft-reboot.conf" released)" = 4 ] || fail 'absent target not counted'

printf 'ksu soft reboot regression passed\n'
