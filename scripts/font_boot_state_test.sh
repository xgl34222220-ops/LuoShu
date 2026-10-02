#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-boot-state)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MODULE="$TMP/module"
CONFIG="$MODULE/config"
mkdir -p "$MODULE/common" "$CONFIG"
cp "$ROOT/common/font_boot_state.sh" "$MODULE/common/font_boot_state.sh"

cat >"$MODULE/common/device_font_load_verify.sh" <<'EOF_VERIFY'
#!/bin/sh
mkdir -p "$MODDIR/config"
cat >"$MODDIR/config/device-font-load-verification.conf" <<'EOF_STATE'
state=mounted
mode=mount-confirmed
reason=mount-transaction-active
activeFont=DemoFont
EOF_STATE
printf 'bootId=%s\ngeneration=test-generation\n' "$LUOSHU_TEST_BOOT_ID" >> "$MODDIR/config/device-font-load-verification.conf"
exit 0
EOF_VERIFY
chmod 0755 "$MODULE/common/device_font_load_verify.sh"

# A new transaction must retain its marker during the boot that created it.
MODDIR="$MODULE" LUOSHU_TEST_BOOT_ID=boot-a sh "$MODULE/common/font_boot_state.sh" mark DemoFont
grep -q '^bootId=boot-a$' "$CONFIG/text_reboot_required.conf"
cat >"$CONFIG/font-payload-boot.conf" <<'EOF_BOOT'
state=booting
font=DemoFont
generation=test-generation
time=20
EOF_BOOT
if MODDIR="$MODULE" LUOSHU_TEST_BOOT_ID=boot-a sh "$MODULE/common/font_boot_state.sh" reconcile; then
    echo 'same-boot reboot marker was consumed' >&2
    exit 1
fi
test -s "$CONFIG/text_reboot_required.conf"

# On the next complete boot, the boot router seals the current boot identity.
printf 'DemoFont\n' > "$CONFIG/active_font.conf"
printf 'bootId=boot-b\n' >> "$CONFIG/font-payload-boot.conf"
# A visible mount confirms the transaction exactly once.
MODDIR="$MODULE" LUOSHU_TEST_BOOT_ID=boot-b sh "$MODULE/common/font_boot_state.sh" reconcile
test ! -e "$CONFIG/text_reboot_required.conf"
grep -q '^state=confirmed$' "$CONFIG/font-payload-boot.conf"
grep -q '^bootId=boot-b$' "$CONFIG/font-payload-boot.conf"

# A successful newer payload commit invalidates an older migration marker.
printf 'DemoFont\n' >"$CONFIG/active_font.conf"
printf 'schema=device-template-v2-baseline-v9-rolegraph-v2\n' >"$CONFIG/font-payload-schema.conf"
printf 'system/fonts/Demo.ttf|hash|1234\n' >"$CONFIG/font-payload-manifest.conf"
cat >"$CONFIG/font-payload-boot.conf" <<'EOF_PREPARED'
state=prepared
font=DemoFont
generation=new-commit
time=200
EOF_PREPARED
cat >"$CONFIG/font-payload-rebuild-pending.conf" <<'EOF_PENDING'
font=DemoFont
reason=schema-upgrade
time=100
EOF_PENDING
MODDIR="$MODULE" sh "$MODULE/common/font_boot_state.sh" reconcile-rebuild
test ! -e "$CONFIG/font-payload-rebuild-pending.conf"

# Default restoration clears once after a full boot without a custom generation.
printf 'default\n' > "$CONFIG/active_font.conf"
MODDIR="$MODULE" LUOSHU_TEST_BOOT_ID=boot-b sh "$MODULE/common/font_boot_state.sh" mark default
rm -f "$CONFIG/font-payload-boot.conf"
if MODDIR="$MODULE" LUOSHU_TEST_BOOT_ID=boot-b sh "$MODULE/common/font_boot_state.sh" reconcile; then exit 1; fi
if MODDIR="$MODULE" LUOSHU_TEST_BOOT_ID=unknown sh "$MODULE/common/font_boot_state.sh" reconcile; then exit 1; fi
MODDIR="$MODULE" LUOSHU_TEST_BOOT_ID=boot-c sh "$MODULE/common/font_boot_state.sh" reconcile
test ! -e "$CONFIG/text_reboot_required.conf"

echo 'Font reboot state converges once across a complete boot.'
