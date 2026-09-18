#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-app-status)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MODULE="$TMP/module"
CONFIG="$MODULE/config"
mkdir -p "$CONFIG"
printf 'id=LuoShu\nversion=test\nversionCode=1\n' >"$MODULE/module.prop"

assert_status() {
    _expected_effective="$1"
    _expected_state="$2"
    _expected_reason="$3"
    _output=$(MODDIR="$MODULE" sh "$ROOT/common/app_bridge.sh" status)
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
    _output=$(MODDIR="$MODULE" sh "$ROOT/common/app_bridge.sh" status)
    printf '%s' "$_output" | python3 -c '
import json, sys
data = json.load(sys.stdin)["data"]
assert data["verificationReason"] == "self-mount-failed", data
assert data["mountFailure"] == sys.argv[1], data
' "$_expected"
}

printf 'default\n' >"$CONFIG/active_font.conf"
assert_status default system ''

# Switch status must expose the worker's actual stage percent instead of the old
# hard-coded 10%, so 22/48/76/98 stalls can be diagnosed from the UI.
cat >"$CONFIG/switch_task.conf" <<'EOF_SWITCH_PROGRESS'
task=switch-progress
state=running
font=DemoFont
message=24% · 正在建立安全暂存区
started=1
finished=
pid=
heartbeat=1
timeout=360
elapsed=2
percent=24
bootId=test
reused=false
EOF_SWITCH_PROGRESS
_progress_output=$(MODDIR="$MODULE" sh "$ROOT/common/app_bridge.sh" status)
printf '%s' "$_progress_output" | python3 -c '
import json, sys
data = json.load(sys.stdin)["data"]
assert data["taskType"] == "switch", data
assert data["taskProgress"] == 24, data
assert data["taskState"] == "running", data
'
rm -f "$CONFIG/switch_task.conf"

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

printf 'LuoShu App bridge distinguishes configured and effective fonts.\n'
