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
  --bind) cp "$2" "$3"; exit $? ;;
  -o)
    case "$2" in
      bind) cp "$3" "$4"; exit $? ;;
      *) exit 0 ;;
    esac
    ;;
esac
exit 0
SH
cat > "$TMP/fake-umount.sh" <<'SH'
#!/bin/sh
exit 0
SH
chmod 0755 "$TMP/system-mount-ok.sh" "$TMP/system-rollback.sh" "$TMP/fake-mount.sh" "$TMP/fake-umount.sh"

run_manager() {
  manager="$1"; hook="$2"
  rm -f "$TMP/system-mounted" "$TMP/system-rollback"
  rm -rf "$TMP/state"; mkdir -p "$TMP/state"
  printf 'stock\n' > "$VISIBLE/data/fonts/files/runtime.ttf"
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

echo "universal_mount_runtime_test: PASS"
