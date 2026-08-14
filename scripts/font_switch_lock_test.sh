#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

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
test "$(wc -l < "$RACE_WINNERS")" -eq 1
test ! -e "$RACE_LOCK"

MODDIR="$MODDIR" LUOSHU_PUBLIC_DIR="$PUBLIC_DIR" \
    LOCK_TEST_MARKER="$MARKER" LOCK_TEST_RELEASE="$TMP/release" \
    LOCK_TEST_ABORT_MARKER="$ABORT_MARKER" \
    sh "$ROOT/common/font_manager.sh" action switch default > "$TMP/first.out" 2>&1 &
first_pid=$!
wait_for_file "$MARKER"
test -d "$LOCK"
test "$(cat "$LOCK/pid")" = "$first_pid"

MODDIR="$MODDIR" LUOSHU_PUBLIC_DIR="$PUBLIC_DIR" \
    LOCK_TEST_MARKER="$MARKER" LOCK_TEST_RELEASE="$TMP/release" \
    LOCK_TEST_ABORT_MARKER="$ABORT_MARKER" \
    sh "$ROOT/common/font_manager.sh" action switch default > "$TMP/second.out" 2>&1
grep -q '字体正在切换中' "$TMP/second.out"
test "$(cat "$LOCK/pid")" = "$first_pid"

kill -TERM "$first_pid"
set +e
wait "$first_pid"
first_rc=$?
set -e
test "$first_rc" -eq 143
test ! -e "$LOCK"
test "$(wc -l < "$ABORT_MARKER")" -eq 1

rm -f "$MARKER" "$ABORT_MARKER"
mkdir "$LOCK"
printf '%s\n' 999999 > "$LOCK/pid"
MODDIR="$MODDIR" LUOSHU_PUBLIC_DIR="$PUBLIC_DIR" \
    LOCK_TEST_MARKER="$MARKER" LOCK_TEST_RELEASE="$TMP/release" \
    LOCK_TEST_ABORT_MARKER="$ABORT_MARKER" \
    sh "$ROOT/common/font_manager.sh" action switch default > "$TMP/stale.out" 2>&1 &
stale_pid=$!
wait_for_file "$MARKER"
test "$(cat "$LOCK/pid")" = "$stale_pid"
kill -TERM "$stale_pid"
set +e
wait "$stale_pid"
stale_rc=$?
set -e
test "$stale_rc" -eq 143
test ! -e "$LOCK"
test "$(wc -l < "$ABORT_MARKER")" -eq 1

echo 'font_switch_lock_test: PASS'
