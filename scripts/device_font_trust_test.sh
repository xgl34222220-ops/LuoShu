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
python3 "$ROOT/common/device_font_load_verify.py" \
    --payload "$TMP/payload.json" \
    --overlay "$TMP/overlay.json" \
    --font-dump "$TMP/font-dump.txt" \
    --mount-evidence "$TMP/mounts.conf" \
    --engine-state "$TMP/engine.conf" \
    --active-font test \
    --output "$TMP/result.json" >/dev/null
python3 - "$TMP/result.json" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload["state"] == "verified", payload
assert payload["mode"] == "mount-verified", payload
assert "verified-by-visible-mounts" in payload["reasons"], payload
assert "dynamic-family-unconfirmed" in payload["reasons"], payload
PY

# Without mount evidence the lightweight path remains pending.
AUTO_MOD="$TMP/auto-module"
mkdir -p "$AUTO_MOD/common" "$AUTO_MOD/config" "$AUTO_MOD/logs"
cp "$ROOT/common/device_font_load_verify.sh" "$AUTO_MOD/common/"
printf 'Composite Font\n' > "$AUTO_MOD/config/active_font.conf"
printf 'state=confirmed\nfont=Composite Font\n' > "$AUTO_MOD/config/font-payload-boot.conf"
set +e
MODDIR="$AUTO_MOD" MODULE_DIR="$AUTO_MOD" \
    sh "$AUTO_MOD/common/device_font_load_verify.sh"
AUTO_RC=$?
set -e
test "$AUTO_RC" -eq 2
grep -q '^state=pending$' "$AUTO_MOD/config/device-font-load-verification.conf"
grep -q '^reason=awaiting-mount-confirmation$' "$AUTO_MOD/config/device-font-load-verification.conf"

# A matching verification record may be reused without rescanning on every App open.
cat > "$AUTO_MOD/config/device-font-load-verification.conf" <<'EOF_VERIFIED'
state=verified
mode=mount-verified
activeFont=Composite Font
reason=visible-font-files-match
EOF_VERIFIED
MODDIR="$AUTO_MOD" MODULE_DIR="$AUTO_MOD" \
    sh "$AUTO_MOD/common/device_font_load_verify.sh"
grep -q '^state=verified$' "$AUTO_MOD/config/device-font-load-verification.conf"
grep -q '^activeFont=Composite Font$' "$AUTO_MOD/config/device-font-load-verification.conf"

# Compatibility verification reads the canonical private payload first.
COMPAT_MOD="$TMP/compat-module"
VISIBLE_ROOT="$TMP/visible-root"
mkdir -p "$COMPAT_MOD/common" "$COMPAT_MOD/config" "$COMPAT_MOD/logs" \
    "$COMPAT_MOD/.luoshu-payload/system/fonts" "$VISIBLE_ROOT/system/fonts"
cp "$ROOT/common/device_font_load_verify.sh" "$COMPAT_MOD/common/"
printf 'Composite Font\n' > "$COMPAT_MOD/config/active_font.conf"
python3 - "$COMPAT_MOD/.luoshu-payload/system/fonts/Roboto-Regular.ttf" "$VISIBLE_ROOT/system/fonts/Roboto-Regular.ttf" <<'PY_FONT'
from pathlib import Path
import sys
payload = (b"LuoShu-visible-font-test" * 4096) + b"END"
Path(sys.argv[1]).write_bytes(payload)
Path(sys.argv[2]).write_bytes(payload)
PY_FONT
printf '%s\n' 'system/fonts/Roboto-Regular.ttf|0|0' > "$COMPAT_MOD/config/font-payload-manifest.conf"
MODDIR="$COMPAT_MOD" MODULE_DIR="$COMPAT_MOD" LUOSHU_VISIBLE_ROOT="$VISIBLE_ROOT" \
    sh "$COMPAT_MOD/common/device_font_load_verify.sh" verify
grep -q '^state=verified$' "$COMPAT_MOD/config/device-font-load-verification.conf"
grep -q '^mode=mount-verified$' "$COMPAT_MOD/config/device-font-load-verification.conf"
grep -q '^reason=visible-font-files-match$' "$COMPAT_MOD/config/device-font-load-verification.conf"

# A different visible inode/path is not a failure only when both halves of the mount
# transaction agree. A bare self-mount marker is not sufficient proof of system visibility.
printf 'different-visible-font\n' > "$VISIBLE_ROOT/system/fonts/Roboto-Regular.ttf"
printf 'state=mounted\n' > "$COMPAT_MOD/config/self-mount.conf"
printf 'state=confirmed\nfont=Composite Font\n' > "$COMPAT_MOD/config/font-payload-boot.conf"
MODDIR="$COMPAT_MOD" MODULE_DIR="$COMPAT_MOD" LUOSHU_VISIBLE_ROOT="$VISIBLE_ROOT" \
    sh "$COMPAT_MOD/common/device_font_load_verify.sh" verify
grep -q '^state=verified$' "$COMPAT_MOD/config/device-font-load-verification.conf"
grep -q '^mode=mount-confirmed$' "$COMPAT_MOD/config/device-font-load-verification.conf"
grep -q '^reason=mount-active-visible-layout-differs$' "$COMPAT_MOD/config/device-font-load-verification.conf"

# Only an explicit mount failure without stronger visible evidence remains a hard failure.
printf 'state=failed\n' > "$COMPAT_MOD/config/self-mount.conf"
set +e
MODDIR="$COMPAT_MOD" MODULE_DIR="$COMPAT_MOD" LUOSHU_VISIBLE_ROOT="$VISIBLE_ROOT" \
    sh "$COMPAT_MOD/common/device_font_load_verify.sh" verify
VERIFY_RC=$?
set -e
test "$VERIFY_RC" -eq 1
grep -q '^state=failed$' "$COMPAT_MOD/config/device-font-load-verification.conf"
grep -q '^reason=self-mount-failed$' "$COMPAT_MOD/config/device-font-load-verification.conf"

# The legacy worker remains callable for manual diagnostics, but boot scripts must not schedule it.
MOD="$TMP/module"
mkdir -p "$MOD/common" "$MOD/config" "$MOD/logs" "$TMP/bin"
cp "$ROOT/common/device_font_boot_verify.sh" "$MOD/common/"
cp "$ROOT/common/background_task.sh" "$MOD/common/"
cat > "$MOD/common/device_font_load_verify.sh" <<'EOF_VERIFY'
#!/bin/sh
printf 'state=verified\nmode=mount-verified\nactiveFont=test\n' > "$MODDIR/config/device-font-load-verification.conf"
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
