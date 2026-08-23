#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
. "$ROOT/scripts/assert.sh"
CASE='字体切换锁'
TMP="$(mktemp -d)"
LIVE_PID=''
cleanup() {
    if [ -n "$LIVE_PID" ]; then
        kill "$LIVE_PID" 2>/dev/null || true
        wait "$LIVE_PID" 2>/dev/null || true
    fi
    rm -rf "$TMP"
}
trap cleanup EXIT

MODDIR="$TMP/module"
PUBLIC_DIR="$TMP/public"
MARKER="$TMP/transaction-started"
ABORT_MARKER="$TMP/transaction-aborted"
LOCK="$MODDIR/.font_switch.lock"
mkdir -p "$MODDIR/common" "$MODDIR/config" "$PUBLIC_DIR/fonts"
cp "$ROOT/common/util_functions.sh" "$MODDIR/common/util_functions.sh"
cat >> "$MODDIR/common/util_functions.sh" <<'EOF_STUBS'
luoshu_payload_transaction_begin() {
    : > "${LOCK_TEST_MARKER:?}"
    while [ ! -f "${LOCK_TEST_RELEASE:?}" ]; do sleep 1; done
}
luoshu_payload_transaction_abort() {
    printf '%s\n' aborted >> "${LOCK_TEST_ABORT_MARKER:?}"
}
luoshu_payload_validate_current() { return 0; }
luoshu_payload_transaction_commit() { return 0; }
EOF_STUBS

wait_for_file() {
    _wff_file="$1"
    _wff_count=0
    while [ "$_wff_count" -lt 50 ]; do
        [ -e "$_wff_file" ] && return 0
        sleep 0.1
        _wff_count=$((_wff_count + 1))
    done
    echo "timed out waiting for $_wff_file" >&2
    return 1
}

# Load the real lock helpers and validate identity semantics independently of the
# font-switch transaction worker.
MODULE_DIR="$MODDIR"
. "$ROOT/common/util_functions.sh"
IDENTITY_LOCK="$TMP/identity.lock"
# A dedicated owner remains visible in /proc even under nested CI/container
# launchers where the shell's $$ can refer to a short-lived outer process.
sleep 300 &
LIVE_PID=$!
LIVE_START="$(luoshu_process_starttime "$LIVE_PID")"
if [ -z "$LIVE_START" ]; then
    echo 'font_switch_lock_test: SKIP (/proc starttime unavailable)'
    exit 0
fi
LIVE_BOOT="$(luoshu_current_boot_id)"

# PID reuse: the PID is alive, but the recorded start time belongs to another
# process incarnation. This must be stale rather than blocking forever.
mkdir "$IDENTITY_LOCK"
printf '%s\nstarttime=0\nboot_id=%s\n' "$LIVE_PID" "$LIVE_BOOT" > "$IDENTITY_LOCK/pid"
if luoshu_font_lock_active "$IDENTITY_LOCK"; then
    echo 'PID reuse was incorrectly treated as an active font lock' >&2
    exit 1
fi
luoshu_font_lock_reap_stale "$IDENTITY_LOCK"
no test -e "$IDENTITY_LOCK"

# A previous-boot lock must be stale even if the PID and starttime happen to
# collide with a live process on the current boot.
mkdir "$IDENTITY_LOCK"
printf '%s\nstarttime=%s\nboot_id=00000000-0000-0000-0000-000000000000\n' \
    "$LIVE_PID" "$LIVE_START" > "$IDENTITY_LOCK/pid"
if luoshu_font_lock_active "$IDENTITY_LOCK"; then
    echo 'previous-boot identity was incorrectly treated as active' >&2
    exit 1
fi
luoshu_font_lock_reap_stale "$IDENTITY_LOCK"
no test -e "$IDENTITY_LOCK"

# Legacy locks remain readable during upgrades. A pid-only directory and the
# older flat pid file both continue to protect a live owner.
mkdir "$IDENTITY_LOCK"
printf '%s\n' "$LIVE_PID" > "$IDENTITY_LOCK/pid"
luoshu_font_lock_active "$IDENTITY_LOCK"
luoshu_font_lock_release "$IDENTITY_LOCK" "$LIVE_PID"
no test -e "$IDENTITY_LOCK"
printf '%s\n' "$LIVE_PID" > "$IDENTITY_LOCK"
luoshu_font_lock_active "$IDENTITY_LOCK"
luoshu_font_lock_release "$IDENTITY_LOCK" "$LIVE_PID"
no test -e "$IDENTITY_LOCK"

# Release is ownership-aware beyond PID equality. A reused PID cannot remove a
# lock created by the earlier process incarnation.
luoshu_font_lock_acquire "$IDENTITY_LOCK" "$LIVE_PID"
printf '%s\nstarttime=0\nboot_id=%s\n' "$LIVE_PID" "$LIVE_BOOT" > "$IDENTITY_LOCK/pid"
if luoshu_font_lock_release "$IDENTITY_LOCK" "$LIVE_PID"; then
    echo 'mismatched process identity released the lock' >&2
    exit 1
fi
rm -rf "$IDENTITY_LOCK"

# Protect the tiny mkdir -> metadata rename window. A reaper that encounters an
# empty lock directory waits briefly, then recognizes the owner once metadata
# appears instead of deleting a lock that is still being initialized.
mkdir "$IDENTITY_LOCK"
(
    sleep 0.05
    printf '%s\nstarttime=%s\nboot_id=%s\n' "$LIVE_PID" "$LIVE_START" "$LIVE_BOOT" > "$IDENTITY_LOCK/pid"
) &
identity_writer=$!
LUOSHU_FONT_LOCK_INIT_GRACE_SECONDS=0.2
export LUOSHU_FONT_LOCK_INIT_GRACE_SECONDS
if luoshu_font_lock_reap_stale "$IDENTITY_LOCK"; then
    echo 'initializing lock was incorrectly reaped' >&2
    exit 1
fi
wait "$identity_writer"
luoshu_font_lock_active "$IDENTITY_LOCK"
rm -rf "$IDENTITY_LOCK"
unset LUOSHU_FONT_LOCK_INIT_GRACE_SECONDS

# Atomic mkdir still guarantees exactly one winner when several switch requests
# race at once.
RACE_LOCK="$TMP/race.lock"
RACE_ATTEMPTS="$TMP/race-attempts"
RACE_WINNERS="$TMP/race-winners"
RACE_GATE="$TMP/race-go"
race_pids=''
for contender in 1 2 3 4 5 6 7 8; do
    (
        MODULE_DIR="$MODDIR"
        . "$ROOT/common/util_functions.sh"
        while [ ! -e "$RACE_GATE" ]; do sleep 0.01; done
        _won=false
        luoshu_font_lock_acquire "$RACE_LOCK" "$$" && _won=true
        printf '%s\n' "$contender" >> "$RACE_ATTEMPTS"
        if [ "$_won" = true ]; then
            while [ "$(wc -l < "$RACE_ATTEMPTS")" -lt 8 ]; do sleep 0.01; done
            printf '%s\n' "$contender" >> "$RACE_WINNERS"
            luoshu_font_lock_release "$RACE_LOCK" "$$"
        fi
    ) &
    race_pids="$race_pids $!"
done
: > "$RACE_GATE"
for race_pid in $race_pids; do wait "$race_pid"; done
ok test "$(wc -l < "$RACE_WINNERS")" -eq 1
no test -e "$RACE_LOCK"

MODDIR="$MODDIR" LUOSHU_PUBLIC_DIR="$PUBLIC_DIR" \
    LOCK_TEST_MARKER="$MARKER" LOCK_TEST_RELEASE="$TMP/release" \
    LOCK_TEST_ABORT_MARKER="$ABORT_MARKER" \
    sh "$ROOT/common/font_manager.sh" action switch default > "$TMP/first.out" 2>&1 &
first_pid=$!
wait_for_file "$MARKER"
ok test -d "$LOCK"
ok test "$(sed -n '1p' "$LOCK/pid")" = "$first_pid"
ok grep -Eq '^starttime=[0-9]+$' "$LOCK/pid"
ok grep -Eq '^boot_id=.+$' "$LOCK/pid"

MODDIR="$MODDIR" LUOSHU_PUBLIC_DIR="$PUBLIC_DIR" \
    LOCK_TEST_MARKER="$MARKER" LOCK_TEST_RELEASE="$TMP/release" \
    LOCK_TEST_ABORT_MARKER="$ABORT_MARKER" \
    sh "$ROOT/common/font_manager.sh" action switch default > "$TMP/second.out" 2>&1
ok grep -q '字体正在切换中' "$TMP/second.out"
ok test "$(sed -n '1p' "$LOCK/pid")" = "$first_pid"

kill -TERM "$first_pid"
set +e
wait "$first_pid"
first_rc=$?
set -e
ok test "$first_rc" -eq 143
no test -e "$LOCK"
ok test "$(wc -l < "$ABORT_MARKER")" -eq 1

# Dead legacy PID locks are still reaped.
rm -f "$MARKER" "$ABORT_MARKER"
mkdir "$LOCK"
printf '%s\n' 999999 > "$LOCK/pid"
MODDIR="$MODDIR" LUOSHU_PUBLIC_DIR="$PUBLIC_DIR" \
    LOCK_TEST_MARKER="$MARKER" LOCK_TEST_RELEASE="$TMP/release" \
    LOCK_TEST_ABORT_MARKER="$ABORT_MARKER" \
    sh "$ROOT/common/font_manager.sh" action switch default > "$TMP/stale.out" 2>&1 &
stale_pid=$!
wait_for_file "$MARKER"
ok test "$(sed -n '1p' "$LOCK/pid")" = "$stale_pid"
kill -TERM "$stale_pid"
set +e
wait "$stale_pid"
stale_rc=$?
set -e
ok test "$stale_rc" -eq 143
no test -e "$LOCK"
ok test "$(wc -l < "$ABORT_MARKER")" -eq 1

# A live-but-reused PID lock is also reaped by the real switch entrypoint.
rm -f "$MARKER" "$ABORT_MARKER"
mkdir "$LOCK"
printf '%s\nstarttime=0\nboot_id=%s\n' "$LIVE_PID" "$LIVE_BOOT" > "$LOCK/pid"
MODDIR="$MODDIR" LUOSHU_PUBLIC_DIR="$PUBLIC_DIR" \
    LOCK_TEST_MARKER="$MARKER" LOCK_TEST_RELEASE="$TMP/release" \
    LOCK_TEST_ABORT_MARKER="$ABORT_MARKER" \
    sh "$ROOT/common/font_manager.sh" action switch default > "$TMP/reused.out" 2>&1 &
reused_pid=$!
wait_for_file "$MARKER"
ok test "$(sed -n '1p' "$LOCK/pid")" = "$reused_pid"
kill -TERM "$reused_pid"
set +e
wait "$reused_pid"
reused_rc=$?
set -e
ok test "$reused_rc" -eq 143
no test -e "$LOCK"
ok test "$(wc -l < "$ABORT_MARKER")" -eq 1

echo 'font_switch_lock_test: PASS'
