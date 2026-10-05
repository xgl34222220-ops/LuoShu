#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/module"
VISIBLE="$TMP/visible"
mkdir -p "$MOD/common" "$MOD/config" "$MOD/.luoshu-payload/.luoshu-runtime/deployment" "$MOD/.luoshu-payload/.luoshu-dynamic" "$MOD/.luoshu-payload/system/fonts" "$VISIBLE/data/fonts/files"
cp "$ROOT/common/universal_mount_runtime.sh" "$MOD/common/"
printf 'system-font-content\n' > "$MOD/.luoshu-payload/system/fonts/Fake.ttf"
printf '{}\n' > "$MOD/.luoshu-payload/.luoshu-runtime/deployment/deployment.json"
cat > "$MOD/common/luoshu_payload.py" <<'PY'
#!/usr/bin/env python3
import sys
# Mount runtime only needs a zero/non-zero integrity verdict here; the real
# payload validator is covered by luoshu_engine_test.py and luoshu_verify_test.py.
raise SystemExit(0 if "--validate-payload-only" in sys.argv else 2)
PY
printf 'dynamic-font-content\n' > "$MOD/.luoshu-payload/.luoshu-dynamic/test.ttf"
HASH=$(sha256sum "$MOD/.luoshu-payload/.luoshu-dynamic/test.ttf" | awk '{print $1}')
printf '.luoshu-dynamic/test.ttf|/data/fonts/files/runtime.ttf|%s\n' "$HASH" > "$MOD/.luoshu-payload/.luoshu-runtime/deployment/dynamic-mounts.conf"
printf 'stock\n' > "$VISIBLE/data/fonts/files/runtime.ttf"
cat > "$MOD/config/universal-font-runtime.conf" <<'EOF'
state=active
pipeline=universal-font-deployment-v1
font=DemoFamily
deploymentId=sha256:test
payloadDigest=sha256:payload
EOF

cat > "$TMP/system-mount-ok.sh" <<EOF
#!/bin/sh
printf mounted > "$TMP/system-mounted"
exit 0
EOF
cat > "$TMP/system-rollback.sh" <<EOF
#!/bin/sh
printf rollback > "$TMP/system-rollback"
exit 0
EOF
cat > "$TMP/fake-mount.sh" <<'SH'
#!/bin/sh
if [ "${FAIL_DYNAMIC:-0}" = 1 ]; then exit 1; fi
case "$1" in
  --bind)
    case "$3" in */data/system/*)
      [ "${FAIL_THEME_BIND:-0}" != 1 ] || exit 1
      [ "${SILENT_THEME_BIND:-0}" != 1 ] || exit 0
      ;;
    esac
    cp "$2" "$3"; exit $? ;;
  -o)
    case "$2" in
      bind)
        case "$4" in */data/system/*)
          [ "${FAIL_THEME_BIND:-0}" != 1 ] || exit 1
          [ "${SILENT_THEME_BIND:-0}" != 1 ] || exit 0
          ;;
        esac
        cp "$3" "$4"; exit $? ;;
      *)
        case "$3" in */data/system/*) [ "${FAIL_THEME_RO:-0}" != 1 ] || exit 1 ;; esac
        exit 0 ;;
    esac
    ;;
esac
exit 0
SH
cat > "$TMP/fake-umount.sh" <<'SH'
#!/bin/sh
[ -z "${FAKE_UMOUNT_LOG:-}" ] || printf '%s\n' "$1" >> "$FAKE_UMOUNT_LOG"
exit 0
SH
chmod 0755 "$TMP/system-mount-ok.sh" "$TMP/system-rollback.sh" "$TMP/fake-mount.sh" "$TMP/fake-umount.sh"

run_manager() {
  manager="$1"; hook="$2"
  rm -f "$TMP/system-mounted" "$TMP/system-rollback"
  rm -rf "$TMP/state"; mkdir -p "$TMP/state"
  printf 'stock\n' > "$VISIBLE/data/fonts/files/runtime.ttf"
  # HyperOS theme font view built at stage time, keyed by deployment id.
  mkdir -p "$VISIBLE/data/system/theme/fonts" "$VISIBLE/data/system/fonts/theme_webview" "$MOD/config/hyperos-theme-font-early"
  printf 'theme-stub\n' > "$VISIBLE/data/system/theme/fonts/Roboto-Regular.ttf"
  printf 'router-stub\n' > "$VISIBLE/data/system/fonts/theme_webview/Roboto-Regular.ttf"
  printf 'theme-view\n' > "$MOD/config/hyperos-theme-font-early/test.ttf"
  printf 'router-view\n' > "$MOD/config/hyperos-theme-font-early/test.1.ttf"
  THEME_HASH=$(sha256sum "$MOD/config/hyperos-theme-font-early/test.ttf" | awk '{print $1}')
  ROUTER_HASH=$(sha256sum "$MOD/config/hyperos-theme-font-early/test.1.ttf" | awk '{print $1}')
  printf 'test.ttf|/data/system/theme/fonts/Roboto-Regular.ttf|%s\ntest.1.ttf|/data/system/fonts/theme_webview/Roboto-Regular.ttf|%s\n' \
    "$THEME_HASH" "$ROUTER_HASH" > "$MOD/config/hyperos-theme-font-early/test.mounts"
  MODDIR="$MOD" MODULE_DIR="$MOD" CONFIG_DIR="$MOD/config" \
  LUOSHU_PYTHON=python3 \
  LUOSHU_UNIVERSAL_TEST_MANAGER="$manager" \
  LUOSHU_UNIVERSAL_TEST_ASSUME_RO=1 \
  LUOSHU_UNIVERSAL_TEST_VISIBLE_ROOT="$VISIBLE" \
  LUOSHU_UNIVERSAL_MOUNT_STATE_ROOT="$TMP/state" \
  LUOSHU_UNIVERSAL_TEST_SYSTEM_MOUNT_COMMAND="$TMP/system-mount-ok.sh" \
  LUOSHU_UNIVERSAL_TEST_SYSTEM_ROLLBACK_COMMAND="$TMP/system-rollback.sh" \
  LUOSHU_UNIVERSAL_MOUNT_COMMAND="$TMP/fake-mount.sh" \
  LUOSHU_UNIVERSAL_UMOUNT_COMMAND="$TMP/fake-umount.sh" \
    sh "$MOD/common/universal_mount_runtime.sh" hook "$hook"
  test -s "$TMP/system-mounted"
  cmp -s "$MOD/.luoshu-payload/.luoshu-dynamic/test.ttf" "$VISIBLE/data/fonts/files/runtime.ttf"
  grep -q "^manager=$manager$" "$MOD/config/universal-font-mount.conf"
  grep -q "^stage=$hook$" "$MOD/config/universal-font-mount.conf"
  cmp -s "$MOD/config/hyperos-theme-font-early/test.ttf" "$VISIBLE/data/system/theme/fonts/Roboto-Regular.ttf"
  cmp -s "$MOD/config/hyperos-theme-font-early/test.1.ttf" "$VISIBLE/data/system/fonts/theme_webview/Roboto-Regular.ttf"
  grep -q 'data/system/theme/fonts/Roboto-Regular.ttf' "$TMP/state/theme.mounts"
  grep -q '^themeState=mounted$' "$MOD/config/universal-font-mount.conf"
  grep -q '^themeMounted=2$' "$MOD/config/universal-font-mount.conf"
}

echo "PHASE7_MOUNT Magisk"
run_manager Magisk post-fs-data
echo "PHASE7_MOUNT KernelSU"
run_manager KernelSU post-mount
echo "PHASE7_MOUNT APatch"
run_manager APatch post-mount

echo "PHASE7_MOUNT wrong-hook"
# Wrong hook is a no-op, not a mount failure.
set +e
MODDIR="$MOD" MODULE_DIR="$MOD" CONFIG_DIR="$MOD/config" LUOSHU_PYTHON=python3 \
  LUOSHU_UNIVERSAL_TEST_MANAGER=KernelSU LUOSHU_UNIVERSAL_TEST_ASSUME_RO=1 \
  sh "$MOD/common/universal_mount_runtime.sh" hook post-fs-data >/dev/null 2>&1
RC=$?
set -e
test "$RC" -eq 2

echo "PHASE7_MOUNT dynamic-only"
# Dynamic-only payloads must not require the system self-mount path.
rm -rf "$MOD/.luoshu-payload/system"
rm -f "$TMP/system-mounted"
printf 'stock\n' > "$VISIBLE/data/fonts/files/runtime.ttf"
MODDIR="$MOD" MODULE_DIR="$MOD" CONFIG_DIR="$MOD/config" LUOSHU_PYTHON=python3 \
  LUOSHU_UNIVERSAL_TEST_MANAGER=Magisk \
  LUOSHU_UNIVERSAL_TEST_ASSUME_RO=1 \
  LUOSHU_UNIVERSAL_TEST_VISIBLE_ROOT="$VISIBLE" \
  LUOSHU_UNIVERSAL_MOUNT_STATE_ROOT="$TMP/state-dynamic-only" \
  LUOSHU_UNIVERSAL_TEST_SYSTEM_MOUNT_COMMAND="$TMP/system-mount-ok.sh" \
  LUOSHU_UNIVERSAL_TEST_SYSTEM_ROLLBACK_COMMAND="$TMP/system-rollback.sh" \
  LUOSHU_UNIVERSAL_MOUNT_COMMAND="$TMP/fake-mount.sh" \
  LUOSHU_UNIVERSAL_UMOUNT_COMMAND="$TMP/fake-umount.sh" \
    sh "$MOD/common/universal_mount_runtime.sh" hook post-fs-data
test ! -e "$TMP/system-mounted"
cmp -s "$MOD/.luoshu-payload/.luoshu-dynamic/test.ttf" "$VISIBLE/data/fonts/files/runtime.ttf"

# Restore a partition payload for the rollback transaction case.
mkdir -p "$MOD/.luoshu-payload/system/fonts"
printf 'system-font-content\n' > "$MOD/.luoshu-payload/system/fonts/Fake.ttf"

echo "PHASE7_MOUNT rollback"
# Dynamic failure must roll back the system payload transaction.
rm -f "$TMP/system-rollback"
printf 'stock\n' > "$VISIBLE/data/fonts/files/runtime.ttf"
set +e
FAIL_DYNAMIC=1 MODDIR="$MOD" MODULE_DIR="$MOD" CONFIG_DIR="$MOD/config" LUOSHU_PYTHON=python3 \
  LUOSHU_UNIVERSAL_TEST_MANAGER=Magisk \
  LUOSHU_UNIVERSAL_TEST_ASSUME_RO=1 \
  LUOSHU_UNIVERSAL_TEST_VISIBLE_ROOT="$VISIBLE" \
  LUOSHU_UNIVERSAL_MOUNT_STATE_ROOT="$TMP/state-fail" \
  LUOSHU_UNIVERSAL_TEST_SYSTEM_MOUNT_COMMAND="$TMP/system-mount-ok.sh" \
  LUOSHU_UNIVERSAL_TEST_SYSTEM_ROLLBACK_COMMAND="$TMP/system-rollback.sh" \
  LUOSHU_UNIVERSAL_MOUNT_COMMAND="$TMP/fake-mount.sh" \
  LUOSHU_UNIVERSAL_UMOUNT_COMMAND="$TMP/fake-umount.sh" \
    sh "$MOD/common/universal_mount_runtime.sh" hook post-fs-data >/dev/null 2>&1
RC=$?
set -e
test "$RC" -eq 1
test -s "$TMP/system-rollback"
grep -q '^state=failed$' "$MOD/config/universal-font-mount.conf"
grep -q '^error=dynamic-mount-failed$' "$MOD/config/universal-font-mount.conf"

run_theme_hook() {
  MODDIR="$MOD" MODULE_DIR="$MOD" CONFIG_DIR="$MOD/config" LUOSHU_PYTHON=python3 \
    LUOSHU_UNIVERSAL_TEST_MANAGER=Magisk LUOSHU_UNIVERSAL_TEST_ASSUME_RO="${LUOSHU_UNIVERSAL_TEST_ASSUME_RO:-1}" \
    LUOSHU_UNIVERSAL_TEST_VISIBLE_ROOT="$VISIBLE" \
    LUOSHU_UNIVERSAL_MOUNT_STATE_ROOT="$TMP/state-theme" \
    LUOSHU_UNIVERSAL_TEST_SYSTEM_MOUNT_COMMAND="$TMP/system-mount-ok.sh" \
    LUOSHU_UNIVERSAL_TEST_SYSTEM_ROLLBACK_COMMAND="$TMP/system-rollback.sh" \
    LUOSHU_UNIVERSAL_MOUNT_COMMAND="$TMP/fake-mount.sh" \
    LUOSHU_UNIVERSAL_UMOUNT_COMMAND="$TMP/fake-umount.sh" \
      sh "$MOD/common/universal_mount_runtime.sh" hook post-fs-data
}

expect_theme_failure() {
  reason="$1"
  rm -f "$TMP/system-rollback"
  set +e
  run_theme_hook
  RC=$?
  set -e
  test "$RC" -eq 1
  test ! -e "$TMP/system-rollback"
  grep -q '^state=mounted$' "$MOD/config/universal-font-mount.conf"
  grep -q '^themeState=failed$' "$MOD/config/universal-font-mount.conf"
  grep -q "^themeError=$reason$" "$MOD/config/universal-font-mount.conf"
}

echo "PHASE7_THEME missing-view"
mv "$MOD/config/hyperos-theme-font-early/test.ttf" "$TMP/theme-saved.ttf"
expect_theme_failure view-integrity-failed
mv "$TMP/theme-saved.ttf" "$MOD/config/hyperos-theme-font-early/test.ttf"

echo "PHASE7_THEME stale-cache"
cp "$MOD/config/hyperos-theme-font-early/test.ttf" "$TMP/theme-saved.ttf"
printf 'stale-cache\n' > "$MOD/config/hyperos-theme-font-early/test.ttf"
expect_theme_failure view-integrity-failed
mv "$TMP/theme-saved.ttf" "$MOD/config/hyperos-theme-font-early/test.ttf"

echo "PHASE7_THEME bind-failed"
FAIL_THEME_BIND=1 expect_theme_failure bind-failed
echo "PHASE7_THEME remount-failed"
FAIL_THEME_RO=1 expect_theme_failure bind-verification-failed
echo "PHASE7_THEME bind-false-success"
printf 'wrong-theme\n' > "$VISIBLE/data/system/theme/fonts/Roboto-Regular.ttf"
SILENT_THEME_BIND=1 expect_theme_failure bind-verification-failed

echo "PHASE7_THEME existing-mount-mismatch"
printf '1 0 0:1 / %s ro - ext4 fake ro\n' "$VISIBLE/data/system/theme/fonts/Roboto-Regular.ttf" > "$TMP/theme-mountinfo"
LUOSHU_UNIVERSAL_MOUNTINFO="$TMP/theme-mountinfo" run_theme_hook
cmp -s "$MOD/config/hyperos-theme-font-early/test.ttf" "$VISIBLE/data/system/theme/fonts/Roboto-Regular.ttf"
grep -q '^themeState=mounted$' "$MOD/config/universal-font-mount.conf"

echo "PHASE7_THEME existing-mount-verified"
cp "$MOD/config/hyperos-theme-font-early/test.ttf" "$VISIBLE/data/system/theme/fonts/Roboto-Regular.ttf"
LUOSHU_UNIVERSAL_MOUNTINFO="$TMP/theme-mountinfo" run_theme_hook
grep -q '^themeState=mounted$' "$MOD/config/universal-font-mount.conf"

echo "PHASE7_THEME top-rw-lower-ro"
printf '1 0 0:1 / %s ro - ext4 fake ro\n' "$VISIBLE/data/fonts/files/runtime.ttf" > "$TMP/top-rw-mountinfo"
printf '2 0 0:1 / %s ro - ext4 fake ro\n3 2 0:1 / %s rw - ext4 fake rw\n' \
  "$VISIBLE/data/system/theme/fonts/Roboto-Regular.ttf" "$VISIBLE/data/system/theme/fonts/Roboto-Regular.ttf" >> "$TMP/top-rw-mountinfo"
LUOSHU_UNIVERSAL_TEST_ASSUME_RO=0 LUOSHU_UNIVERSAL_MOUNTINFO="$TMP/top-rw-mountinfo" \
  expect_theme_failure bind-verification-failed

echo "PHASE7_THEME pid1-top-rw-lower-ro"
printf '1 0 0:1 / %s ro - ext4 fake ro\n2 0 0:1 / %s ro - ext4 fake ro\n' \
  "$VISIBLE/data/fonts/files/runtime.ttf" "$VISIBLE/data/system/theme/fonts/Roboto-Regular.ttf" > "$TMP/self-ro-mountinfo"
printf '2 0 0:1 / /data/system/theme/fonts/Roboto-Regular.ttf ro - ext4 fake ro\n3 2 0:1 / /data/system/theme/fonts/Roboto-Regular.ttf rw - ext4 fake rw\n' > "$TMP/pid1-rw-mountinfo"
LUOSHU_UNIVERSAL_TEST_ASSUME_RO=0 LUOSHU_UNIVERSAL_MOUNTINFO="$TMP/self-ro-mountinfo" \
  LUOSHU_UNIVERSAL_TEST_PID1_MOUNTINFO="$TMP/pid1-rw-mountinfo" expect_theme_failure pid1-visibility-mismatch

echo "PHASE7_THEME pid1-visibility-mismatch"
mkdir -p "$TMP/pid1/data/system/theme/fonts"
printf 'stock-pid1-view\n' > "$TMP/pid1/data/system/theme/fonts/Roboto-Regular.ttf"
LUOSHU_UNIVERSAL_TEST_PID1_VISIBLE_ROOT="$TMP/pid1" expect_theme_failure pid1-visibility-mismatch

echo "PHASE7_THEME route-changed"
rm -f "$VISIBLE/data/system/theme/fonts/Roboto-Regular.ttf"
ln -s "$VISIBLE/data/system/fonts/theme_webview/Roboto-Regular.ttf" "$VISIBLE/data/system/theme/fonts/Roboto-Regular.ttf"
expect_theme_failure target-changed
test -L "$VISIBLE/data/system/theme/fonts/Roboto-Regular.ttf"

echo "PHASE7_THEME not-applicable"
rm -f "$VISIBLE/data/system/theme/fonts/Roboto-Regular.ttf" "$VISIBLE/data/system/fonts/theme_webview/Roboto-Regular.ttf"
: > "$MOD/config/hyperos-theme-font-early/test.mounts"
run_theme_hook
grep -q '^themeState=not-applicable$' "$MOD/config/universal-font-mount.conf"
grep -q '^themeMounted=0$' "$MOD/config/universal-font-mount.conf"

echo "PHASE7_THEME legacy-cache-targets-gone"
rm -f "$MOD/config/hyperos-theme-font-early/test.mounts"
run_theme_hook
grep -q '^themeState=not-applicable$' "$MOD/config/universal-font-mount.conf"

echo "PHASE7_THEME rollback-preserves-foreign-inode"
run_manager Magisk post-fs-data
# A theme manager can replace a mount with a new inode containing the same
# bytes. The recorded hash alone must not grant ownership of that replacement.
cp "$VISIBLE/data/system/theme/fonts/Roboto-Regular.ttf" "$TMP/new-theme-inode.ttf"
mv "$TMP/new-theme-inode.ttf" "$VISIBLE/data/system/theme/fonts/Roboto-Regular.ttf"
FAKE_UMOUNT_LOG="$TMP/theme-umounts" MODDIR="$MOD" MODULE_DIR="$MOD" CONFIG_DIR="$MOD/config" \
  LUOSHU_UNIVERSAL_MOUNT_STATE_ROOT="$TMP/state" \
  LUOSHU_UNIVERSAL_UMOUNT_COMMAND="$TMP/fake-umount.sh" \
    sh "$MOD/common/universal_mount_runtime.sh" rollback
test -s "$TMP/theme-umounts"
grep -q 'data/system/fonts/theme_webview/Roboto-Regular.ttf' "$TMP/theme-umounts"
if grep -q 'data/system/theme/fonts/Roboto-Regular.ttf' "$TMP/theme-umounts"; then exit 1; fi

echo "universal_mount_runtime_test: PASS"
