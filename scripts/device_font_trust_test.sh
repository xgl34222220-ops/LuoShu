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

# Normal boot status is constant-time but must be strict: a completed payload transaction
# alone is not proof that this boot mounted the payload into Android's root namespace.
AUTO_MOD="$TMP/auto-module"
mkdir -p "$AUTO_MOD/common" "$AUTO_MOD/config" "$AUTO_MOD/logs"
cp "$ROOT/common/device_font_load_verify.sh" "$AUTO_MOD/common/"
printf 'Composite Font\n' > "$AUTO_MOD/config/active_font.conf"
printf 'state=confirmed\nfont=Composite Font\n' > "$AUTO_MOD/config/font-payload-boot.conf"
set +e
LUOSHU_BOOT_ID=test-boot MODDIR="$AUTO_MOD" MODULE_DIR="$AUTO_MOD" \
    sh "$AUTO_MOD/common/device_font_load_verify.sh"
AUTO_RC=$?
set -e
test "$AUTO_RC" -eq 2
grep -q '^state=pending$' "$AUTO_MOD/config/device-font-load-verification.conf"
grep -q '^reason=self-mount-not-confirmed$' "$AUTO_MOD/config/device-font-load-verification.conf"

# Only a current-boot atomic mount with its required manifest may become verified.
printf 'state=mounted\nbackend=self-overlay\nmounted=system/fonts:overlay\nfailed=\nbootId=test-boot\n' \
    > "$AUTO_MOD/config/self-mount.conf"
printf '%s\n' '/module/system/fonts|/system/fonts|overlay' \
    > "$AUTO_MOD/config/self-mount-required.conf"
LUOSHU_BOOT_ID=test-boot MODDIR="$AUTO_MOD" MODULE_DIR="$AUTO_MOD" \
    sh "$AUTO_MOD/common/device_font_load_verify.sh"
grep -q '^state=verified$' "$AUTO_MOD/config/device-font-load-verification.conf"
grep -q '^mode=mount-verified$' "$AUTO_MOD/config/device-font-load-verification.conf"
grep -q '^reason=current-boot-mount-confirmed$' "$AUTO_MOD/config/device-font-load-verification.conf"

# A mount record from a previous boot must never survive as an applied-font claim.
sed -i 's/^bootId=.*/bootId=old-boot/' "$AUTO_MOD/config/self-mount.conf"
set +e
LUOSHU_BOOT_ID=test-boot MODDIR="$AUTO_MOD" MODULE_DIR="$AUTO_MOD" \
    sh "$AUTO_MOD/common/device_font_load_verify.sh"
STALE_RC=$?
set -e
test "$STALE_RC" -eq 2
grep -q '^state=pending$' "$AUTO_MOD/config/device-font-load-verification.conf"
grep -q '^reason=stale-self-mount$' "$AUTO_MOD/config/device-font-load-verification.conf"
sed -i 's/^bootId=.*/bootId=test-boot/' "$AUTO_MOD/config/self-mount.conf"

# Dynamic /data/fonts contracts are part of activation. OEM replacement is a real failure,
# while a released view from this boot is accepted without running the deep verifier.
printf 'state=prepared\n' > "$AUTO_MOD/config/device-font-dynamic-mount.conf"
printf 'state=overridden\nreason=dynamic-config-changed\nbootId=test-boot\n' \
    > "$AUTO_MOD/config/device-font-dynamic-runtime.conf"
set +e
LUOSHU_BOOT_ID=test-boot MODDIR="$AUTO_MOD" MODULE_DIR="$AUTO_MOD" \
    sh "$AUTO_MOD/common/device_font_load_verify.sh"
DYNAMIC_RC=$?
set -e
test "$DYNAMIC_RC" -eq 1
grep -q '^state=failed$' "$AUTO_MOD/config/device-font-load-verification.conf"
grep -q '^reason=dynamic-config-overridden$' "$AUTO_MOD/config/device-font-load-verification.conf"
printf 'state=released\nreason=font-manager-initialized\nbootId=test-boot\n' \
    > "$AUTO_MOD/config/device-font-dynamic-runtime.conf"
LUOSHU_BOOT_ID=test-boot MODDIR="$AUTO_MOD" MODULE_DIR="$AUTO_MOD" \
    sh "$AUTO_MOD/common/device_font_load_verify.sh"
grep -q '^state=verified$' "$AUTO_MOD/config/device-font-load-verification.conf"

# The dynamic guard must publish the reason when the OEM rewrites its config, and must not
# resurrect the expensive deep verifier after the temporary view is released.
DYN_MOD="$TMP/dynamic-module"
DYN_TARGET="$TMP/data-fonts-config.xml"
mkdir -p "$DYN_MOD/common" "$DYN_MOD/config" "$DYN_MOD/logs" "$DYN_MOD/system/etc"
printf 'Composite Font\n' > "$DYN_MOD/config/active_font.conf"
printf 'luoshu-view\n' > "$DYN_MOD/system/etc/.luoshu-data-fonts-config.xml"
printf 'oem-new-view\n' > "$DYN_TARGET"
_dfpr_module() { printf '%s\n' "$DYN_MOD"; }
_dfpr_hash() { sha256sum "$1" | awk '{print $1}'; }
_dfpr_log() { :; }
_dfpr_launch_pending_cache() { :; }
. "$ROOT/common/device_font_dynamic_guard.sh"
DYN_SOURCE_HASH=$(_dfpr_hash "$DYN_MOD/system/etc/.luoshu-data-fonts-config.xml")
{
    printf 'state=prepared\n'
    printf 'source=system/etc/.luoshu-data-fonts-config.xml\n'
    printf 'target=%s\n' "$DYN_TARGET"
    printf 'targetSha256=old-target-hash\n'
    printf 'sourceSha256=%s\n' "$DYN_SOURCE_HASH"
} > "$DYN_MOD/config/device-font-dynamic-mount.conf"
set +e
LUOSHU_BOOT_ID=test-boot LUOSHU_DATA_FONTS_CONFIG_TARGET="$DYN_TARGET" \
    device_font_dynamic_mount_apply
DYN_RC=$?
set -e
test "$DYN_RC" -eq 2
grep -q '^state=overridden$' "$DYN_MOD/config/device-font-dynamic-runtime.conf"
grep -q '^reason=dynamic-config-changed$' "$DYN_MOD/config/device-font-dynamic-runtime.conf"
grep -q '^bootId=test-boot$' "$DYN_MOD/config/device-font-dynamic-runtime.conf"
DEEP_MARK="$TMP/deep-called"
STATUS_MARK="$TMP/status-called"
device_font_load_verify() { : > "$DEEP_MARK"; }
device_font_load_status() { : > "$STATUS_MARK"; }
_dfpr_template_ensure_after_release
test -f "$STATUS_MARK"
test ! -e "$DEEP_MARK"

# post-mount stays fail-open for boot safety, but it must never hide a missing module view
# or self-mount entry from diagnostics.
PM_MOD="$TMP/post-mount-module"
mkdir -p "$PM_MOD/common" "$PM_MOD/config" "$PM_MOD/logs"
cp "$ROOT/post-mount.sh" "$PM_MOD/post-mount.sh"
cat > "$PM_MOD/common/private_payload.sh" <<'EOF_PM_FAIL'
luoshu_private_mount_module_view() { return 1; }
EOF_PM_FAIL
LUOSHU_BOOT_ID=test-boot sh "$PM_MOD/post-mount.sh"
grep -q '^state=failed$' "$PM_MOD/config/post-mount-hook.conf"
grep -q '^reason=module-view-failed$' "$PM_MOD/config/post-mount-hook.conf"
grep -q '^bootId=test-boot$' "$PM_MOD/config/post-mount-hook.conf"
cat > "$PM_MOD/common/private_payload.sh" <<'EOF_PM_OK'
luoshu_private_mount_module_view() { return 0; }
EOF_PM_OK
: > "$PM_MOD/common/util_functions.sh"
: > "$PM_MOD/common/font_config_runtime.sh"
: > "$PM_MOD/common/font_config_partitions.sh"
cat > "$PM_MOD/common/mount_compat.sh" <<'EOF_PM_MOUNT'
luoshu_private_self_mount_ensure() { return 0; }
EOF_PM_MOUNT
: > "$PM_MOD/common/mount_self_backend.sh"
LUOSHU_BOOT_ID=test-boot sh "$PM_MOD/post-mount.sh"
grep -q '^state=completed$' "$PM_MOD/config/post-mount-hook.conf"
grep -q '^reason=self-mount-complete$' "$PM_MOD/config/post-mount-hook.conf"

# The expensive verifier remains available only as an explicit diagnostic command.
COMPAT_MOD="$TMP/compat-module"
mkdir -p "$COMPAT_MOD/common" "$COMPAT_MOD/config" "$COMPAT_MOD/logs"
cp "$ROOT/common/device_font_load_verify.sh" "$COMPAT_MOD/common/"
cat > "$COMPAT_MOD/common/mount_compat.sh" <<'EOF_MOUNT_OK'
luoshu_mount_verify_active() { return 0; }
EOF_MOUNT_OK
printf 'Composite Font\n' > "$COMPAT_MOD/config/active_font.conf"
MODDIR="$COMPAT_MOD" MODULE_DIR="$COMPAT_MOD" \
    sh "$COMPAT_MOD/common/device_font_load_verify.sh" verify
grep -q '^state=verified$' "$COMPAT_MOD/config/device-font-load-verification.conf"
grep -q '^mode=mount-verified$' "$COMPAT_MOD/config/device-font-load-verification.conf"
grep -q '^reason=verified-by-visible-mounts$' "$COMPAT_MOD/config/device-font-load-verification.conf"

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
