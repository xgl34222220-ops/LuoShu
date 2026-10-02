#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-app-status)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MODULE="$TMP/module"
CONFIG="$MODULE/config"
mkdir -p "$CONFIG"
printf 'state=confirmed\nfont=DemoFont\ngeneration=test-generation\nbootId=%s\n' "$(cat /proc/sys/kernel/random/boot_id)" > "$CONFIG/font-payload-boot.conf"
printf 'id=LuoShu\nversion=test\nversionCode=1\n' >"$MODULE/module.prop"

assert_status() {
    _expected_effective="$1"
    _expected_state="$2"
    _expected_reason="$3"
    if [ -s "$CONFIG/universal-font-runtime-verification.conf" ]; then
        sed '/^bootId=/d; /^deploymentId=/d; /^payloadDigest=/d' "$CONFIG/universal-font-runtime-verification.conf" > "$TMP/verification.current"
        printf 'bootId=%s\n' "$(cat /proc/sys/kernel/random/boot_id)" >> "$TMP/verification.current"
        grep -E '^(deploymentId|payloadDigest)=' "$CONFIG/universal-font-runtime.conf" >> "$TMP/verification.current" || true
        mv "$TMP/verification.current" "$CONFIG/universal-font-runtime-verification.conf"
    fi
    if [ -s "$CONFIG/device-font-load-verification.conf" ]; then
        sed '/^bootId=/d; /^generation=/d' "$CONFIG/device-font-load-verification.conf" > "$TMP/proof"
        printf 'bootId=%s\ngeneration=test-generation\n' "$(cat /proc/sys/kernel/random/boot_id)" >> "$TMP/proof"
        mv "$TMP/proof" "$CONFIG/device-font-load-verification.conf"
    fi
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
    if [ -s "$CONFIG/device-font-load-verification.conf" ]; then
        sed '/^bootId=/d; /^generation=/d' "$CONFIG/device-font-load-verification.conf" > "$TMP/proof"
        printf 'bootId=%s\ngeneration=test-generation\n' "$(cat /proc/sys/kernel/random/boot_id)" >> "$TMP/proof"
        mv "$TMP/proof" "$CONFIG/device-font-load-verification.conf"
    fi
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

printf 'DemoFont\n' >"$CONFIG/active_font.conf"
printf 'state=failed\nbackend=rollback\nfailed=oplus_product/fonts\n' >"$CONFIG/self-mount.conf"
printf 'state=failed\nmode=compatibility\nreason=self-mount-not-visible\nactiveFont=DemoFont\n' \
    >"$CONFIG/device-font-load-verification.conf"
assert_status default failed self-mount-failed
assert_mount_failure oplus_product/fonts

printf 'state=mounted\nbackend=self-overlay\n' >"$CONFIG/self-mount.conf"
printf 'state=verified\nmode=mount-verified\nreason=\nactiveFont=DemoFont\n' \
    >"$CONFIG/device-font-load-verification.conf"
assert_status unknown mount-only ''

printf 'state=verified\nmode=mount-confirmed\nreason=mount-transaction-active\nactiveFont=DemoFont\n' \
    >"$CONFIG/device-font-load-verification.conf"
assert_status unknown mount-only mount-transaction-active

# A previous-generation mount record must never advertise an effective font.
sed -i 's/^generation=.*/generation=previous/' "$CONFIG/device-font-load-verification.conf"
MODDIR="$MODULE" sh "$ROOT/common/app_bridge.sh" status | python3 -c '
import json,sys
d=json.load(sys.stdin)["data"]
assert d["effectiveActive"] == "unknown", d
assert d["fontEffectState"] == "unverified", d
assert d["verificationReason"] == "stale-verification", d
'

printf 'state=failed\nbackend=rollback\nfailed=system/etc\n' >"$CONFIG/self-mount.conf"
assert_status default failed self-mount-failed

printf 'state=mounted\nbackend=self-overlay\n' >"$CONFIG/self-mount.conf"
printf 'state=verified\nmode=mount-verified\nreason=\nactiveFont=OldFont\n' \
    >"$CONFIG/device-font-load-verification.conf"
assert_status unknown pending stale-verification

touch "$CONFIG/text_reboot_required.conf"
assert_status unknown pending-reboot stale-verification

# Universal production mode consumes Phase 8 grade and exposes Phase 9 rollback state.
rm -f "$CONFIG/text_reboot_required.conf" "$CONFIG/device-font-load-verification.conf"
printf 'UniversalFont\n' >"$CONFIG/active_font.conf"
printf 'state=active\nfont=UniversalFont\ndeploymentId=u1\npayloadDigest=d1\n' >"$CONFIG/universal-font-runtime.conf"
printf 'state=mounted\ndeploymentId=u1\npayloadDigest=d1\n' >"$CONFIG/universal-font-mount.conf"
printf 'grade=PASS\nstate=pass\nmode=universal-runtime\nreason=runtime-verified\nactiveFont=UniversalFont\n' \
    >"$CONFIG/universal-font-runtime-verification.conf"
assert_status UniversalFont verified runtime-verified

printf 'grade=FAIL\nstate=fail\nmode=universal-runtime\nreason=coverage-digits-missing\nactiveFont=UniversalFont\n' \
    >"$CONFIG/universal-font-runtime-verification.conf"
printf 'state=staged\ntargetFont=OldFont\ntargetMode=legacy\nreason=runtime-verification-failed\n' \
    >"$CONFIG/universal-font-rollback.conf"
touch "$CONFIG/text_reboot_required.conf"
assert_status unknown rollback-pending coverage-digits-missing
_output=$(MODDIR="$MODULE" sh "$ROOT/common/app_bridge.sh" status)
printf '%s' "$_output" | python3 -c '
import json, sys
data = json.load(sys.stdin)["data"]
assert data["rollbackPending"] is True, data
assert data["rollbackState"] == "staged", data
assert data["rollbackTargetFont"] == "OldFont", data
assert data["rollbackTargetMode"] == "legacy", data
' 


# A Universal verification failure without a staged rollback must remain unknown,
# never masquerade as an already-restored system default.
rm -f "$CONFIG/universal-font-rollback.conf" "$CONFIG/text_reboot_required.conf"
printf 'grade=FAIL\nstate=fail\nmode=universal-runtime\nreason=required-axis-missing\nactiveFont=UniversalFont\n' \
    >"$CONFIG/universal-font-runtime-verification.conf"
assert_status unknown failed required-axis-missing

printf 'LuoShu App bridge distinguishes configured, effective and rollback fonts.\n'
