#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MODDIR="$TMP/module"
PUBLIC_DIR="$TMP/public"
LOCK="$MODDIR/.font_switch.lock"
mkdir -p "$MODDIR/common" "$MODDIR/config" "$MODDIR/logs" "$PUBLIC_DIR/fonts" \
    "$MODDIR/.luoshu-payload/system/fonts"
cp "$ROOT/common/font_manager.sh" "$MODDIR/common/font_manager.sh"
cp "$ROOT/common/legacy_v14_4_switch.sh" "$MODDIR/common/legacy_v14_4_switch.sh"
cp "$ROOT/common/font_switch_lock.sh" "$MODDIR/common/font_switch_lock.sh"
ln -s "$ROOT/common/legacy_v14_4" "$MODDIR/common/legacy_v14_4"
printf 'live-payload-must-not-change\n' > "$MODDIR/.luoshu-payload/live-marker"
printf 'BeforeSwitch\n' > "$MODDIR/config/active_font.conf"

MODULE_DIR="$MODDIR"
. "$ROOT/common/font_switch_lock.sh"

LIVE_PID="$$"
if [ ! -r "/proc/$LIVE_PID/stat" ] && [ -n "${PPID:-}" ] && [ -r "/proc/$PPID/stat" ]; then
    LIVE_PID="$PPID"
fi
LIVE_START="$(luoshu_process_starttime "$LIVE_PID")"
LIVE_BOOT="$(luoshu_current_boot_id)"

# A live PID with a mismatched process birth time is stale unless a fresh token
# explicitly bridges a Root/PID namespace visibility gap.
IDENTITY_LOCK="$TMP/identity.lock"
mkdir "$IDENTITY_LOCK"
printf '%s\nstarttime=0\nboot_id=%s\n' "$LIVE_PID" "$LIVE_BOOT" > "$IDENTITY_LOCK/pid"
if luoshu_font_lock_active "$IDENTITY_LOCK"; then
    echo 'PID reuse was incorrectly treated as active' >&2
    exit 1
fi
luoshu_font_lock_reap_stale "$IDENTITY_LOCK"
test ! -e "$IDENTITY_LOCK"

mkdir "$IDENTITY_LOCK"
printf '%s\nstarttime=0\nboot_id=%s\ntoken=fixture\ncreated=%s\n' \
    "$LIVE_PID" "$LIVE_BOOT" "$(date +%s)" > "$IDENTITY_LOCK/pid"
luoshu_font_lock_active "$IDENTITY_LOCK"
sed -i 's/^created=.*/created=0/' "$IDENTITY_LOCK/pid"
if luoshu_font_lock_active "$IDENTITY_LOCK"; then
    echo 'expired token lease was incorrectly treated as active' >&2
    exit 1
fi
luoshu_font_lock_reap_stale "$IDENTITY_LOCK"
test ! -e "$IDENTITY_LOCK"

# A previous-boot identity is always stale even if PID/starttime collide.
mkdir "$IDENTITY_LOCK"
printf '%s\nstarttime=%s\nboot_id=00000000-0000-0000-0000-000000000000\n' \
    "$LIVE_PID" "$LIVE_START" > "$IDENTITY_LOCK/pid"
if luoshu_font_lock_active "$IDENTITY_LOCK"; then
    echo 'previous-boot identity was incorrectly treated as active' >&2
    exit 1
fi
luoshu_font_lock_reap_stale "$IDENTITY_LOCK"
test ! -e "$IDENTITY_LOCK"

# Atomic mkdir must produce exactly one winner while all contenders hold the lock
# until every attempt has been recorded.
RACE_LOCK="$TMP/race.lock"
RACE_ATTEMPTS="$TMP/race-attempts"
RACE_WINNERS="$TMP/race-winners"
RACE_GATE="$TMP/race-go"
race_pids=''
for contender in 1 2 3 4 5 6 7 8; do
    (
        MODULE_DIR="$MODDIR"
        . "$ROOT/common/font_switch_lock.sh"
        while [ ! -e "$RACE_GATE" ]; do sleep 0.01; done
        won=false
        luoshu_font_lock_acquire "$RACE_LOCK" "$$" && won=true || true
        printf '%s\n' "$contender" >> "$RACE_ATTEMPTS"
        if [ "$won" = true ]; then
            while [ "$(wc -l < "$RACE_ATTEMPTS")" -lt 8 ]; do sleep 0.01; done
            printf '%s\n' "$contender" >> "$RACE_WINNERS"
            luoshu_font_lock_release "$RACE_LOCK" "$$"
        fi
    ) &
    race_pids="$race_pids $!"
done
: > "$RACE_GATE"
for race_pid in $race_pids; do wait "$race_pid"; done
test "$(wc -l < "$RACE_WINNERS")" -eq 1
test ! -e "$RACE_LOCK"

# Integration: a live lock must stop the actual App-facing switch router before it
# touches either the current-boot payload or the next-boot payload.
luoshu_font_lock_acquire "$LOCK" "$$"
set +e
MODDIR="$MODDIR" LUOSHU_PUBLIC_DIR="$PUBLIC_DIR" \
    sh "$MODDIR/common/font_manager.sh" action switch default > "$TMP/busy.out" 2>&1
busy_rc=$?
set -e
test "$busy_rc" -ne 0
grep -q '字体正在切换中' "$TMP/busy.out"
test -d "$LOCK"
test "$(cat "$MODDIR/.luoshu-payload/live-marker")" = 'live-payload-must-not-change'
test ! -e "$MODDIR/.luoshu-payload-next"
luoshu_font_lock_release "$LOCK" "$$"
test ! -e "$LOCK"

# Dead locks are reaped by the same real entrypoint. A default switch now completes
# through the safe next-boot staging backend: current-boot payload stays byte-for-byte
# available while the replacement is queued for post-fs-data activation.
mkdir "$LOCK"
printf '%s\n' 999999 > "$LOCK/pid"
MODDIR="$MODDIR" LUOSHU_PUBLIC_DIR="$PUBLIC_DIR" \
    sh "$MODDIR/common/font_manager.sh" action switch default > "$TMP/stale.out" 2>&1
grep -q '"status":"ok"' "$TMP/stale.out"
grep -q '"core":"physical-safe-v1"' "$TMP/stale.out"
grep -q '"pipeline":"next-boot-stage"' "$TMP/stale.out"
test ! -e "$LOCK"
test "$(cat "$MODDIR/config/active_font.conf")" = default
test "$(cat "$MODDIR/.luoshu-payload/live-marker")" = 'live-payload-must-not-change'
test -d "$MODDIR/.luoshu-payload-next"
grep -q '^state=prepared$' "$MODDIR/config/font-payload-next.conf"
grep -q '^font=default$' "$MODDIR/config/font-payload-next.conf"
grep -q '^previousFont=BeforeSwitch$' "$MODDIR/config/font-payload-next.conf"

# Keep the safety layer independent from the generation engine. The active backend
# may import the lock helper, but it must never pull the v4 94% pipeline back in or
# mutate the live payload from the foreground switch path.
SAFE_BACKEND="$ROOT/common/legacy_v14_4/font_switch_safe.sh"
grep -q 'font_switch_lock.sh' "$SAFE_BACKEND"
grep -q 'lock_acquire' "$SAFE_BACKEND"
grep -q 'NEXT_PAYLOAD=.*\.luoshu-payload-next' "$SAFE_BACKEND"
! grep -q 'mv "$LIVE_PAYLOAD"' "$SAFE_BACKEND"
! grep -qE 'font_validate_fast_v4|device_font_template|device_font_slot|font_config_overlay|device_font_payload_build' \
    "$SAFE_BACKEND"
sh -n "$ROOT/common/font_switch_lock.sh"
sh -n "$SAFE_BACKEND"

echo 'font_switch_lock_test: PASS'
