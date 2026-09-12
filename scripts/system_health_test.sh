#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/adb/modules/LuoShu"
OTHER="$TMP/adb/modules/OtherFont"
EMPTY="$TMP/adb/modules/EmptyFont"
mkdir -p "$MOD/common" "$MOD/config" "$MOD/logs" "$MOD/system/fonts" "$OTHER/system/fonts" "$EMPTY/system/fonts"
printf 'id=LuoShu\nversion=v-test\nversionCode=999\n' > "$MOD/module.prop"
printf 'custom-font\n' > "$MOD/config/active_font.conf"
printf 'state=ready\n' > "$MOD/config/device-font-engine.conf"
printf 'state=ready\n' > "$MOD/config/device-font-template.state"
printf 'state=verified\nmode=strict\n' > "$MOD/config/device-font-load-verification.conf"
printf 'state=mounted\nbackend=overlay\n' > "$MOD/config/self-mount.conf"
printf 'x' > "$MOD/system/fonts/Test.ttf"
printf '[x] [ERROR] failed sample\n' > "$MOD/logs/fontswitch.log"
printf 'id=OtherFont\nname=其它字体模块\n' > "$OTHER/module.prop"
printf 'id=EmptyFont\nname=空目录模块\n' > "$EMPTY/module.prop"
printf 'x' > "$OTHER/system/fonts/Other.ttf"
mkdir -p "$MOD/.font_switch.lock"
printf '99999999\n' > "$MOD/.font_switch.lock/pid"
cat > "$MOD/common/util_functions.sh" <<'UTIL'
luoshu_font_lock_active() {
  _pid=$(cat "$1/pid" 2>/dev/null || true)
  [ "$_pid" = "$$" ]
}
luoshu_font_lock_reap_stale() {
  rm -rf "$1"
}
UTIL

OUT=$(MODDIR="$MOD" LUOSHU_ADB_ROOT="$TMP/adb" LUOSHU_MODULES_ROOT="$TMP/adb/modules" LUOSHU_ROOT_MANAGER=TestRoot sh "$ROOT/system/bin/luoshu-health" report)
printf '%s\n' "$OUT" | grep -qx 'modulePresent=true'
printf '%s\n' "$OUT" | grep -qx 'rootManager=TestRoot'
printf '%s\n' "$OUT" | grep -qx 'activeFont=custom-font'
printf '%s\n' "$OUT" | grep -qx 'payloadFonts=1'
printf '%s\n' "$OUT" | grep -qx 'lockState=stale'
printf '%s\n' "$OUT" | grep -qx 'conflictCount=1'
printf '%s\n' "$OUT" | grep -q '^conflict=OtherFont|其它字体模块|system/fonts|directory|1$'

printf '99999999\n' > "$MOD/config/dead.pid"
REPAIR=$(MODDIR="$MOD" LUOSHU_ADB_ROOT="$TMP/adb" LUOSHU_MODULES_ROOT="$TMP/adb/modules" sh "$ROOT/system/bin/luoshu-health" repair-stale)
printf '%s\n' "$REPAIR" | grep -qx 'status=ok'
test ! -e "$MOD/.font_switch.lock"
test ! -e "$MOD/config/dead.pid"

# Repair must keep a live task's nonnumeric identity rather than parsing it as
# a PID, and clean stale boot records even if their PID has since been recycled.
cp "$ROOT/common/background_task.sh" "$MOD/common/background_task.sh"
printf '%s\n' "$$" > "$MOD/config/live.pid"
printf 'active-task-123\n' > "$MOD/config/live.pid.task"
printf '%s\n' "$$" > "$MOD/config/stale-boot.pid"
printf 'active-task-123\n' > "$MOD/config/stale-boot.pid.task"
printf 'previous-boot\n' > "$MOD/config/stale-boot.pid.boot"
printf 'orphan-task\n' > "$MOD/config/orphan.pid.task"
# Keep this fixture independent of the executor's unusual /proc PID namespace;
# use the actual identity helper for boot checks and an exact synthetic cmdline.
sed 's@/proc/$_ltpa_pid/cmdline@'"$TMP"'/proc/$_ltpa_pid/cmdline@g' \
    "$ROOT/common/background_task.sh" > "$MOD/common/background_task.sh"
mkdir -p "$TMP/proc/$$"
printf 'sh\000worker\000active-task-123\000' > "$TMP/proc/$$/cmdline"
MODDIR="$MOD" sh "$ROOT/system/bin/luoshu-health" repair-stale >/dev/null
test -s "$MOD/config/live.pid"
test "$(cat "$MOD/config/live.pid.task")" = active-task-123
test ! -e "$MOD/config/stale-boot.pid"
test ! -e "$MOD/config/stale-boot.pid.task"
test ! -e "$MOD/config/stale-boot.pid.boot"
test ! -e "$MOD/config/orphan.pid.task"

mkdir -p "$OTHER/disable"
OUT2=$(MODDIR="$MOD" LUOSHU_ADB_ROOT="$TMP/adb" LUOSHU_MODULES_ROOT="$TMP/adb/modules" sh "$ROOT/system/bin/luoshu-health" report)
printf '%s\n' "$OUT2" | grep -qx 'conflictCount=0'
printf 'system health tests passed\n'
