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

printf 'default\n' >"$CONFIG/active_font.conf"
assert_status default system ''

printf 'DemoFont\n' >"$CONFIG/active_font.conf"
printf 'state=failed\nbackend=rollback\nfailed=oplus_product/fonts\n' >"$CONFIG/self-mount.conf"
printf 'state=failed\nmode=compatibility\nreason=self-mount-not-visible\nactiveFont=DemoFont\n' \
    >"$CONFIG/device-font-load-verification.conf"
assert_status default failed self-mount-not-visible

printf 'state=mounted\nbackend=self-overlay\n' >"$CONFIG/self-mount.conf"
printf 'state=verified\nmode=mount-verified\nreason=\nactiveFont=DemoFont\n' \
    >"$CONFIG/device-font-load-verification.conf"
assert_status DemoFont verified ''

printf 'state=verified\nmode=mount-confirmed\nreason=mount-active-visible-layout-differs\nactiveFont=DemoFont\n' \
    >"$CONFIG/device-font-load-verification.conf"
assert_status DemoFont verified mount-active-visible-layout-differs

# An explicit atomic rollback wins over a stale mount-confirmed record and the
# App must show the actionable mount failure instead of an internal layout code.
printf 'state=failed\nbackend=rollback\nfailed=system_ext/fonts-target-missing\n' >"$CONFIG/self-mount.conf"
assert_status default failed self-mount-failed

printf 'state=failed\nbackend=rollback\nfailed=system/etc\n' >"$CONFIG/self-mount.conf"
assert_status default failed self-mount-failed

printf 'state=mounted\nbackend=self-overlay\n' >"$CONFIG/self-mount.conf"
printf 'state=verified\nmode=mount-verified\nreason=\nactiveFont=OldFont\n' \
    >"$CONFIG/device-font-load-verification.conf"
assert_status unknown pending stale-verification

touch "$CONFIG/text_reboot_required.conf"
assert_status unknown pending-reboot ''

printf 'LuoShu App bridge distinguishes configured and effective fonts.\n'
