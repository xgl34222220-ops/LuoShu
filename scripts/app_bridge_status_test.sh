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

printf 'DemoFont\n' >"$CONFIG/active_font.conf"
printf 'state=failed\nbackend=rollback\nfailed=oplus_product/fonts\n' >"$CONFIG/self-mount.conf"
printf 'state=failed\nmode=compatibility\nreason=self-mount-not-visible\nactiveFont=DemoFont\n' \
    >"$CONFIG/device-font-load-verification.conf"
assert_status default failed self-mount-failed
assert_mount_failure oplus_product/fonts

printf 'state=mounted\nbackend=self-overlay\n' >"$CONFIG/self-mount.conf"
printf 'state=verified\nmode=mount-confirmed\nreason=mount-transaction-active\nactiveFont=DemoFont\n' \
    >"$CONFIG/device-font-load-verification.conf"
# An old global flag alone has no boot/manifest/visible-byte proof.
assert_status unknown unverified verification-evidence-unavailable

mkdir -p "$MODULE/common/python/bin" "$MODULE/.luoshu-payload/system/fonts" "$TMP/visible/system/fonts"
cp "$ROOT/common/physical_font_load_verify.py" "$ROOT/common/device_font_load_verify.sh" "$MODULE/common/"
cat > "$MODULE/common/python/bin/luoshu-python" <<'PYTHON'
#!/bin/sh
unset PYTHONHOME PYTHONPATH
exec python3 "$@"
PYTHON
chmod 0755 "$MODULE/common/python/bin/luoshu-python"
printf 'selected-font-bytes\n' > "$MODULE/.luoshu-payload/system/fonts/Demo.ttf"
cp "$MODULE/.luoshu-payload/system/fonts/Demo.ttf" "$TMP/visible/system/fonts/Demo.ttf"
python3 - "$MODULE/.luoshu-payload" <<'MANIFEST'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1])
(root / '.luoshu-inventory-output-manifest.json').write_text(json.dumps({
    'schema': 'inventory-font-output-v1', 'files': {'/system/fonts/Demo.ttf':
        hashlib.sha256((root / 'system/fonts/Demo.ttf').read_bytes()).hexdigest()}}))
MANIFEST
export LUOSHU_VISIBLE_ROOT="$TMP/visible"
MODDIR="$MODULE" sh "$MODULE/common/device_font_load_verify.sh" verify
assert_status DemoFont verified visible-font-files-match

# One mismatched target does not establish that all fonts became ROM defaults.
printf 'stock-default-font\n' > "$TMP/visible/system/fonts/Demo.ttf"
MODDIR="$MODULE" sh "$MODULE/common/device_font_load_verify.sh" verify && exit 1
assert_status unknown failed visible-font-files-mismatch

printf 'state=failed\nbackend=rollback\nfailed=system/etc\n' >"$CONFIG/self-mount.conf"
assert_status default failed self-mount-failed
printf 'state=mounted\nbackend=self-overlay\n' >"$CONFIG/self-mount.conf"

printf 'DifferentFont\n' >"$CONFIG/active_font.conf"
assert_status unknown unverified verification-cache-identity-changed

touch "$CONFIG/text_reboot_required.conf"
assert_status unknown pending-reboot verification-cache-identity-changed

printf 'LuoShu App bridge distinguishes selected, verified, partial failure and rollback.\n'
