#!/bin/sh
# v4 boot transaction and boot-loop guard share one meaning of "unfinished boot".
#   - previous boot reached sys.boot_completed (guard completedBootId == the
#     boot recorded in font-payload-boot.conf) but the service verification was
#     cut short by a reboot: not a failure, nothing counted;
#   - previous boot never completed: the payload is kept, the guard counts and
#     alone escalates to safe mode; font_safety never quarantines on its own.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d "${TMPDIR:-/tmp}/luoshu-unfinished.XXXXXX")
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

fail() {
  printf 'unfinished-boot semantics regression: %s\n' "$*" >&2
  exit 1
}

MODDIR="$TMP/module"
MODULE_DIR="$MODDIR"
export MODDIR MODULE_DIR
mkdir -p "$MODDIR/common" "$MODDIR/config" "$MODDIR/system/fonts"
printf 'id=LuoShu\n' > "$MODDIR/module.prop"
cp "$ROOT/common/font_safety.sh" "$ROOT/common/boot_loop_guard.sh" "$MODDIR/common/"
. "$MODDIR/common/boot_loop_guard.sh"
. "$MODDIR/common/font_safety.sh"

state() { sed -n "s/^$1=//p" "$MODDIR/config/font-payload-boot.conf" | head -n1; }
guard_boot() { # guard_boot BOOT_ID: what the post-fs-data hook does first
  LUOSHU_BOOTLOOP_BOOT_ID="$1" luoshu_bootloop_begin || return 1
}

dd if=/dev/zero of="$MODDIR/system/fonts/Test.ttf" bs=2048 count=1 2>/dev/null
printf 'Demo\n' > "$MODDIR/config/active_font.conf"

# Applied payload, first boot.
LUOSHU_CURRENT_BOOT_ID=boot-a; export LUOSHU_CURRENT_BOOT_ID
luoshu_payload_arm Demo
guard_boot boot-a || fail 'boot-a in safe mode'
font_config_boot_guard Demo || fail 'boot-a rejected'
[ "$(state state)" = booting ] || fail 'boot-a not booting'

# boot-a reached boot completed (Magisk: provider service waiter), then the
# user rebooted before the service verification. Twice in a row.
for pair in 'boot-a boot-b' 'boot-b boot-c' 'boot-c boot-d'; do
  set -- $pair
  LUOSHU_BOOTLOOP_BOOT_ID="$1" luoshu_bootloop_complete
  LUOSHU_CURRENT_BOOT_ID="$2"; export LUOSHU_CURRENT_BOOT_ID
  guard_boot "$2" || fail "$2 entered safe mode after completed boots"
  font_config_boot_guard Demo || fail "$2: completed-but-unverified boot quarantined the payload"
  [ "$(state reason)" = previous-boot-completed-unverified ] || fail "$2 reason=$(state reason)"
  [ "$(state bootId)" = "$2" ] || fail "$2 bootId not rewritten"
  [ ! -e "$MODDIR/config/font-boot-inconclusive.conf" ] || fail "$2 counted a completed boot as inconclusive"
done
[ -f "$MODDIR/system/fonts/Test.ttf" ] || fail 'payload removed after completed boots'
grep -qx Demo "$MODDIR/config/active_font.conf" || fail 'selection reset after completed boots'

# boot-d never completes (its post-fs-data already counted it), boot-e never
# completes either: the payload is kept and only the guard counts.
LUOSHU_CURRENT_BOOT_ID=boot-e; export LUOSHU_CURRENT_BOOT_ID
guard_boot boot-e || fail 'boot-e (one unfinished boot before it) in safe mode'
font_config_boot_guard Demo || fail 'boot-e: unfinished boot quarantined (guard must decide)'
[ "$(state reason)" = previous-boot-unfinished-guarded ] || fail "boot-e reason=$(state reason)"
[ -f "$MODDIR/system/fonts/Test.ttf" ] || fail 'payload removed before the guard escalated'
[ ! -e "$MODDIR/config/font-payload-quarantine.conf" ] || fail 'font_safety quarantined on its own count'
# Two unfinished boots (d, e): the guard enters safe mode before font_safety runs.
if guard_boot boot-f; then
  fail 'guard did not enter safe mode after LUOSHU_BOOTLOOP_LIMIT unfinished boots'
fi
luoshu_bootloop_safe_mode_active || fail 'safe mode marker missing'
grep -qx Demo "$MODDIR/config/active_font.conf" || fail 'safe mode lost the selection'
[ -f "$MODDIR/system/fonts/Test.ttf" ] || fail 'safe mode lost the payload'

# Without the guard loaded, the historical retry-once rule is unchanged
# (font_safety_test.sh covers it in full).
(
  unset -f luoshu_bootloop_get
  type luoshu_bootloop_get >/dev/null 2>&1 && exit 1
  exit 0
) || fail 'could not unload guard for the fallback check'

printf 'Unfinished-boot semantics checks passed.\n'
