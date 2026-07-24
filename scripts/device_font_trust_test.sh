#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/payload.json" <<'EOF_PAYLOAD'
{"schema":"device-font-payload-v1","slots":[{"family":"sans-serif","familyNormalized":"sans-serif","weight":400,"generatedFile":"LuoShuSlot.ttf"}]}
EOF_PAYLOAD
cat > "$TMP/overlay.json" <<'EOF_OVERLAY'
{"schema":"device-font-overlay-v1","copiedFonts":[{"path":"system/fonts/Roboto-Regular.ttf"}],"dynamic":[],"summary":{"mappedSlots":1}}
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
PY

# The post-fs scheduler must run the verifier only after boot and must not block startup.
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
grep -q 'device_font_boot_verify.sh" schedule' "$ROOT/post-fs-data.sh"

echo 'device_font_trust_test: PASS'
