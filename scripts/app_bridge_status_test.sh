#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-app-status)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MODULE="$TMP/module"
CONFIG="$MODULE/config"
mkdir -p "$CONFIG" "$MODULE/common"
cp "$ROOT/common/app_bridge.sh" "$ROOT/common/task_scope.sh" \
    "$ROOT/common/task_scope.py" "$ROOT/common/runtime_paths.sh" \
    "$ROOT/common/runtime_paths_lock.py" "$MODULE/common/"
HOST_PYTHON=$(python3 -c 'import sys; print(sys.executable)')
export LUOSHU_TASK_SCOPE_PYTHON="$HOST_PYTHON"
export LUOSHU_RUNTIME_PATHS_PYTHON="$HOST_PYTHON"
# Exercise real request ownership; an inherited test marker must not bypass it.
unset LUOSHU_TASK_SCOPE_PID
printf 'id=LuoShu\nversion=test\nversionCode=1\n' >"$MODULE/module.prop"

assert_status() {
    _expected_effective="$1"
    _expected_state="$2"
    _expected_reason="$3"
    _output=$(MODDIR="$MODULE" sh "$MODULE/common/app_bridge.sh" status 2>>"$TMP/request-cleanup.stderr")
    printf '%s' "$_output" | python3 -c '
import json
import sys

root = json.load(sys.stdin)
data = root["data"]
expected_effective, expected_state, expected_reason = sys.argv[1:]
assert data["effectiveActive"] == expected_effective, data
assert data["fontEffectState"] == expected_state, data
assert data["verificationReason"] == expected_reason, data
' "$_expected_effective" "$_expected_state" "$_expected_reason"
}

assert_mount_failure() {
    _expected="$1"
    _output=$(MODDIR="$MODULE" sh "$MODULE/common/app_bridge.sh" status 2>>"$TMP/request-cleanup.stderr")
    printf '%s' "$_output" | python3 -c '
import json, sys
data = json.load(sys.stdin)["data"]
assert data["verificationReason"] == "self-mount-failed", data
assert data["mountFailure"] == sys.argv[1], data
' "$_expected"
}

printf 'default\n' >"$CONFIG/active_font.conf"
assert_status default system ''

printf 'DemoFont\n' >"$CONFIG/active_font.conf"
printf 'state=failed\nbackend=rollback\nfailed=oplus_product/fonts\n' >"$CONFIG/self-mount.conf"
printf 'state=failed\nmode=compatibility\nreason=self-mount-not-visible\nactiveFont=DemoFont\n' \
    >"$CONFIG/device-font-load-verification.conf"
assert_status default failed self-mount-failed
assert_mount_failure oplus_product/fonts

printf 'state=mounted\nbackend=self-overlay\n' >"$CONFIG/self-mount.conf"
printf 'state=verified\nmode=mount-verified\nreason=\nactiveFont=DemoFont\n' \
    >"$CONFIG/device-font-load-verification.conf"
assert_status DemoFont verified ''

printf 'state=verified\nmode=mount-confirmed\nreason=mount-transaction-active\nactiveFont=DemoFont\n' \
    >"$CONFIG/device-font-load-verification.conf"
assert_status DemoFont verified mount-transaction-active

printf 'state=failed\nbackend=rollback\nfailed=system/etc\n' >"$CONFIG/self-mount.conf"
assert_status default failed self-mount-failed

printf 'state=mounted\nbackend=self-overlay\n' >"$CONFIG/self-mount.conf"
printf 'state=verified\nmode=mount-verified\nreason=\nactiveFont=OldFont\n' \
    >"$CONFIG/device-font-load-verification.conf"
assert_status unknown pending stale-verification

touch "$CONFIG/text_reboot_required.conf"
assert_status unknown pending-reboot ''

[ "$(readlink "$CONFIG")" = '.luoshu-state/config' ]
"$HOST_PYTHON" - "$MODULE/.luoshu-state/tasks" <<'PY'
import json
from pathlib import Path
import sys

tasks = Path(sys.argv[1])
proofs = list(tasks.glob('request-*.pid.cleanup.json'))
assert len(proofs) == 8, proofs
for path in proofs:
    proof = json.loads(path.read_text())
    assert proof['cleaned'] and not proof['leftoverPids'] and proof['result'] == 0, proof
for pattern in ('request-*.pid', 'request-*.pid.owner.json', 'request-*.pid.task',
                'request-*.pid.boot', 'request-*.pid.start'):
    assert not list(tasks.glob(pattern)), pattern
PY

printf 'LuoShu App bridge distinguishes configured and effective fonts.\n'
