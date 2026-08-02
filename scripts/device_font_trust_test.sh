#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/payload.json" <<'EOF_PAYLOAD'
{"schema":"device-font-payload-v1","slots":[{"family":"sans-serif","familyNormalized":"sans-serif","weight":400,"generatedFile":"LuoShuSlot.ttf"}]}
EOF_PAYLOAD
cat > "$TMP/overlay.json" <<'EOF_OVERLAY'
{"schema":"device-font-overlay-v1","copiedFonts":[{"path":"system/fonts/Roboto-Regular.ttf"}],"dynamic":[{"removedFamilies":["OEM Dynamic Sans"]}],"summary":{"mappedSlots":1}}
EOF_OVERLAY
: > "$TMP/font-dump.txt"
printf '%s\n' 'system/fonts/Roboto-Regular.ttf|/system/fonts/Roboto-Regular.ttf|ok|abc|abc|8192' > "$TMP/mounts.conf"
printf '%s\n' 'state=installed' > "$TMP/engine.conf"
set +e
python3 "$ROOT/common/device_font_load_verify.py" \
    --payload "$TMP/payload.json" \
    --overlay "$TMP/overlay.json" \
    --font-dump "$TMP/font-dump.txt" \
    --mount-evidence "$TMP/mounts.conf" \
    --engine-state "$TMP/engine.conf" \
    --active-font test \
    --output "$TMP/result.json" >/dev/null
VERIFY_RC=$?
set -e
test "$VERIFY_RC" -eq 2
python3 - "$TMP/result.json" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload["state"] == "unverified", payload
assert payload["mode"] == "mount-only", payload
assert "visible-mounts-do-not-prove-font-selection" in payload["reasons"], payload
assert "dynamic-family-unconfirmed" in payload["reasons"], payload
assert "android-render-probe-unavailable" in payload["reasons"], payload
PY

# Read-only status may observe a confirmed mount transaction, but it must not
# claim that Android selected the generated font without renderer/FontManager proof.
AUTO_MOD="$TMP/auto-module"
mkdir -p "$AUTO_MOD/common" "$AUTO_MOD/config" "$AUTO_MOD/logs"
cp "$ROOT/common/device_font_load_verify.sh" "$AUTO_MOD/common/"
printf 'Composite Font\n' > "$AUTO_MOD/config/active_font.conf"
printf 'state=confirmed\nfont=Composite Font\n' > "$AUTO_MOD/config/font-payload-boot.conf"
set +e
MODDIR="$AUTO_MOD" MODULE_DIR="$AUTO_MOD" \
    sh "$AUTO_MOD/common/device_font_load_verify.sh" status
STATUS_RC=$?
set -e
test "$STATUS_RC" -eq 2
grep -q '^state=unverified$' "$AUTO_MOD/config/device-font-load-verification.conf"
grep -q '^mode=mount-only$' "$AUTO_MOD/config/device-font-load-verification.conf"
grep -q '^reason=visible-mounts-do-not-prove-font-selection$' "$AUTO_MOD/config/device-font-load-verification.conf"

# Explicit diagnostics with a visible mount but no aligned manifest remain
# unverified rather than inventing a successful runtime state.
COMPAT_MOD="$TMP/compat-module"
mkdir -p "$COMPAT_MOD/common" "$COMPAT_MOD/config" "$COMPAT_MOD/logs"
cp "$ROOT/common/device_font_load_verify.sh" "$COMPAT_MOD/common/"
cat > "$COMPAT_MOD/common/mount_compat.sh" <<'EOF_MOUNT_OK'
luoshu_mount_verify_active() { return 0; }
EOF_MOUNT_OK
printf 'Composite Font\n' > "$COMPAT_MOD/config/active_font.conf"
set +e
MODDIR="$COMPAT_MOD" MODULE_DIR="$COMPAT_MOD" \
    sh "$COMPAT_MOD/common/device_font_load_verify.sh" verify
VERIFY_RC=$?
set -e
test "$VERIFY_RC" -eq 2
grep -q '^state=unverified$' "$COMPAT_MOD/config/device-font-load-verification.conf"
grep -q '^mode=mount-only$' "$COMPAT_MOD/config/device-font-load-verification.conf"
grep -q '^reason=aligned-manifest-unavailable$' "$COMPAT_MOD/config/device-font-load-verification.conf"

# A missing/partial PID 1 mount remains a hard failure in explicit diagnostics.
cat > "$COMPAT_MOD/common/mount_compat.sh" <<'EOF_MOUNT_FAIL'
luoshu_mount_verify_active() { return 1; }
EOF_MOUNT_FAIL
set +e
MODDIR="$COMPAT_MOD" MODULE_DIR="$COMPAT_MOD" \
    sh "$COMPAT_MOD/common/device_font_load_verify.sh" verify
VERIFY_RC=$?
set -e
test "$VERIFY_RC" -eq 1
grep -q '^state=failed$' "$COMPAT_MOD/config/device-font-load-verification.conf"
grep -q '^mode=compatibility$' "$COMPAT_MOD/config/device-font-load-verification.conf"
grep -q '^reason=self-mount-not-visible$' "$COMPAT_MOD/config/device-font-load-verification.conf"

# The legacy worker remains callable for manual diagnostics, but boot scripts must not schedule it.
MOD="$TMP/module"
mkdir -p "$MOD/common" "$MOD/config" "$MOD/logs" "$TMP/bin"
cp "$ROOT/common/device_font_boot_verify.sh" "$MOD/common/"
cp "$ROOT/common/background_task.sh" "$MOD/common/"
cat > "$MOD/common/device_font_load_verify.sh" <<'EOF_VERIFY'
#!/bin/sh
printf 'state=verified\nmode=aligned\nactiveFont=test\n' > "$MODDIR/config/device-font-load-verification.conf"
exit 0
EOF_VERIFY
chmod +x "$MOD/common/"*.sh
cat > "$TMP/bin/getprop" <<'EOF_GETPROP'
#!/bin/sh
[ "${1:-}" = sys.boot_completed ] && printf '1\n'
EOF_GETPROP
chmod +x "$TMP/bin/getprop"
PATH="$TMP/bin:$PATH" MODDIR="$MOD" \
    LUOSHU_BOOT_VERIFY_SETTLE_SECONDS=0 \
    LUOSHU_BOOT_VERIFY_IDLE_WAIT_LIMIT=1 \
    LUOSHU_BOOT_VERIFY_POLL_SECONDS=1 \
    sh "$MOD/common/device_font_boot_verify.sh" run trust-test
grep -q '^state=verified$' "$MOD/config/device-font-load-verification.conf"
! grep -q 'device_font_boot_verify.sh.*schedule' "$ROOT/post-fs-data.sh" "$ROOT/.luoshu-runtime/post-fs-data-v227.sh"

echo 'device_font_trust_test: PASS'
