#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/module"
BIN="$TMP/bin"
CALLS="$TMP/pm.calls"
mkdir -p "$MOD/bundled" "$MOD/common" "$MOD/config" "$MOD/logs" "$BIN"
cp "$ROOT/common/app_installer.sh" "$MOD/common/app_installer.sh"
printf 'fake-apk\n' > "$MOD/bundled/LuoShu-App.apk"
APK_HASH=$(sha256sum "$MOD/bundled/LuoShu-App.apk" | awk '{print $1}')
cat > "$MOD/bundled/app.prop" <<'EOF'
package=io.github.xgl34222220.luoshu.debug
versionCode=1432001
sha256=APP_HASH
EOF
sed -i "s/APP_HASH/$APK_HASH/" "$MOD/bundled/app.prop"
cat > "$MOD/module.prop" <<'EOF'
version=v14.3 Alpha1.10
versionCode=14320
EOF

cat > "$BIN/dumpsys" <<'EOF'
#!/bin/sh
printf 'Packages:\n  versionCode=%s minSdk=28 targetSdk=36\n' "${MOCK_VERSION:-0}"
EOF
chmod 0755 "$BIN/dumpsys"

cat > "$BIN/pm" <<'EOF'
#!/bin/sh
case "$1" in
  dump)
    printf 'versionCode=%s minSdk=28 targetSdk=36\n' "${MOCK_VERSION:-0}"
    ;;
  install)
    printf '%s\n' "$*" >> "$MOCK_PM_CALLS"
    case "${MOCK_PM_FAIL:-0}" in
      1)
        echo 'Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE]'
        exit 1
        ;;
      2)
        echo 'Failure [INSTALL_FAILED_INTERNAL_ERROR]'
        exit 1
        ;;
    esac
    echo 'Success'
    ;;
  *) exit 1 ;;
esac
EOF
chmod 0755 "$BIN/pm"

cat > "$MOD/config/app_install_state.conf" <<EOF
status=installed
package=io.github.xgl34222220.luoshu.debug
versionCode=1432001
apkSha256=$APK_HASH
EOF

rm -f "$CALLS"
MOCK_VERSION=1432001 MOCK_PM_CALLS="$CALLS" \
APP_INSTALL_PM_BIN="$BIN/pm" APP_INSTALL_DUMPSYS_BIN="$BIN/dumpsys" \
MODDIR="$MOD" sh "$MOD/common/app_installer.sh" test-current > "$TMP/current.out"
grep -qx 'already-current' "$TMP/current.out"
grep -q '^status=up_to_date$' "$MOD/config/app_install_state.conf"
test ! -e "$CALLS"

cat > "$MOD/config/app_install_state.conf" <<'EOF'
status=installed
package=io.github.xgl34222220.luoshu.debug
versionCode=1432001
apkSha256=old-alpha-build
EOF
MOCK_VERSION=1432001 MOCK_PM_CALLS="$CALLS" \
APP_INSTALL_PM_BIN="$BIN/pm" APP_INSTALL_DUMPSYS_BIN="$BIN/dumpsys" \
MODDIR="$MOD" sh "$MOD/common/app_installer.sh" test-same-version-new-build > "$TMP/same-version.out"
grep -qx 'installed' "$TMP/same-version.out"
grep -q 'install -r -d --user 0' "$CALLS"
grep -q '^status=installed$' "$MOD/config/app_install_state.conf"
grep -q "^apkSha256=$APK_HASH$" "$MOD/config/app_install_state.conf"

rm -f "$CALLS" "$MOD/config/app_install_pending"
MOCK_VERSION=1431901 MOCK_PM_CALLS="$CALLS" \
APP_INSTALL_PM_BIN="$BIN/pm" APP_INSTALL_DUMPSYS_BIN="$BIN/dumpsys" \
MODDIR="$MOD" sh "$MOD/common/app_installer.sh" test-upgrade > "$TMP/upgrade.out"
grep -qx 'installed' "$TMP/upgrade.out"
grep -q 'install -r -d --user 0' "$CALLS"
grep -q '^status=installed$' "$MOD/config/app_install_state.conf"
test ! -e "$MOD/config/app_install_pending"

set +e
MOCK_VERSION=0 APP_INSTALL_PM_BIN="$TMP/missing-pm" APP_INSTALL_DUMPSYS_BIN="$BIN/dumpsys" \
MODDIR="$MOD" sh "$MOD/common/app_installer.sh" test-defer > "$TMP/defer.out"
DEFER_CODE=$?
set -e
test "$DEFER_CODE" -eq 10
grep -qx 'deferred' "$TMP/defer.out"
test -f "$MOD/config/app_install_pending"
grep -q '^status=deferred$' "$MOD/config/app_install_state.conf"

rm -f "$MOD/config/app_install_pending"
set +e
MOCK_VERSION=1431901 MOCK_PM_FAIL=2 MOCK_PM_CALLS="$CALLS" \
APP_INSTALL_PM_BIN="$BIN/pm" APP_INSTALL_DUMPSYS_BIN="$BIN/dumpsys" \
MODDIR="$MOD" sh "$MOD/common/app_installer.sh" test-transient-failure > "$TMP/transient.out"
TRANSIENT_CODE=$?
set -e
test "$TRANSIENT_CODE" -eq 11
grep -qx 'failed' "$TMP/transient.out"
test -f "$MOD/config/app_install_pending"
grep -q '^status=failed$' "$MOD/config/app_install_state.conf"

rm -f "$MOD/config/app_install_pending"
set +e
MOCK_VERSION=1431901 MOCK_PM_FAIL=1 MOCK_PM_CALLS="$CALLS" \
APP_INSTALL_PM_BIN="$BIN/pm" APP_INSTALL_DUMPSYS_BIN="$BIN/dumpsys" \
MODDIR="$MOD" sh "$MOD/common/app_installer.sh" test-permanent-failure > "$TMP/permanent.out"
PERMANENT_CODE=$?
set -e
test "$PERMANENT_CODE" -eq 12
grep -qx 'permanent-failure' "$TMP/permanent.out"
test -f "$MOD/config/app_install_pending"
grep -q '^status=blocked$' "$MOD/config/app_install_state.conf"
grep -q 'INSTALL_FAILED_UPDATE_INCOMPATIBLE' "$MOD/logs/app-install.log"

# Flashing must bound both binder queries and package installation. The fake
# timeout records budgets and can model a stuck query without sleeping in tests.
cat > "$BIN/timeout" <<'EOF'
#!/bin/sh
printf '%s %s\n' "$1" "$3" >> "$MOCK_TIMEOUT_CALLS"
shift
case "${MOCK_TIMEOUT_MODE:-}:$2" in
  query:package|query:dump) exit 124 ;;
  install:install) exit 124 ;;
esac
exec "$@"
EOF
chmod 0755 "$BIN/timeout"
rm -f "$CALLS" "$TMP/timeout.calls"
set +e
MOCK_VERSION=0 MOCK_PM_CALLS="$CALLS" MOCK_TIMEOUT_CALLS="$TMP/timeout.calls" MOCK_TIMEOUT_MODE=query \
APP_INSTALL_PM_BIN="$BIN/pm" APP_INSTALL_DUMPSYS_BIN="$BIN/dumpsys" APP_INSTALL_TIMEOUT_BIN="$BIN/timeout" \
MODDIR="$MOD" sh "$MOD/common/app_installer.sh" flash > "$TMP/flash-query.out"
FLASH_QUERY_CODE=$?
set -e
test "$FLASH_QUERY_CODE" -eq 10
grep -qx deferred "$TMP/flash-query.out"
grep -qx '5 package' "$TMP/timeout.calls"
test "$(wc -l < "$TMP/timeout.calls" | tr -d ' ')" -eq 1
test ! -e "$CALLS"

rm -f "$CALLS" "$TMP/timeout.calls"
set +e
MOCK_VERSION=0 MOCK_PM_CALLS="$CALLS" MOCK_TIMEOUT_CALLS="$TMP/timeout.calls" MOCK_TIMEOUT_MODE=install \
APP_INSTALL_PM_BIN="$BIN/pm" APP_INSTALL_DUMPSYS_BIN="$BIN/dumpsys" APP_INSTALL_TIMEOUT_BIN="$BIN/timeout" \
MODDIR="$MOD" sh "$MOD/common/app_installer.sh" flash > "$TMP/flash-timeout.out"
FLASH_TIMEOUT_CODE=$?
set -e
test "$FLASH_TIMEOUT_CODE" -eq 10
grep -qx '20 install' "$TMP/timeout.calls"
grep -qx deferred "$TMP/flash-timeout.out"
test -f "$MOD/config/app_install_pending"
grep -q '^status=deferred$' "$MOD/config/app_install_state.conf"
test ! -e "$CALLS"

# A recovery lacking timeout must defer before even querying the package manager.
rm -f "$CALLS" "$TMP/timeout.calls"
set +e
MOCK_VERSION=0 MOCK_PM_CALLS="$CALLS" MOCK_TIMEOUT_CALLS="$TMP/timeout.calls" \
APP_INSTALL_PM_BIN="$BIN/pm" APP_INSTALL_DUMPSYS_BIN="$BIN/dumpsys" APP_INSTALL_TIMEOUT_BIN="$TMP/no-timeout" \
MODDIR="$MOD" sh "$MOD/common/app_installer.sh" flash > "$TMP/no-timeout.out"
NO_TIMEOUT_CODE=$?
set -e
test "$NO_TIMEOUT_CODE" -eq 10
grep -qx deferred "$TMP/no-timeout.out"
test ! -e "$CALLS"
test ! -e "$TMP/timeout.calls"
test -z "$(find "$MOD/config" -name 'app_install_state.conf.tmp.*' -print)"

# A stable preview identity coexists with old debug installations. It still
# verifies the exact APK hash and never removes another package.
sed -i 's/luoshu.debug/luoshu.preview/' "$MOD/bundled/app.prop"
rm -f "$CALLS"
MOCK_VERSION=0 MOCK_PM_CALLS="$CALLS" \
APP_INSTALL_PM_BIN="$BIN/pm" APP_INSTALL_DUMPSYS_BIN="$BIN/dumpsys" \
MODDIR="$MOD" sh "$MOD/common/app_installer.sh" test-preview > "$TMP/preview.out"
grep -qx installed "$TMP/preview.out"
grep -qx 'package=io.github.xgl34222220.luoshu.preview' "$MOD/config/app_install_state.conf"
! grep -q uninstall "$CALLS"
sed -i 's/^sha256=.*/sha256=broken/' "$MOD/bundled/app.prop"
rm -f "$CALLS"
set +e
MOCK_VERSION=0 MOCK_PM_CALLS="$CALLS" \
APP_INSTALL_PM_BIN="$BIN/pm" APP_INSTALL_DUMPSYS_BIN="$BIN/dumpsys" \
MODDIR="$MOD" sh "$MOD/common/app_installer.sh" test-preview-bad-hash > "$TMP/preview-bad.out"
PREVIEW_CODE=$?
set -e
test "$PREVIEW_CODE" -eq 22
grep -qx invalid-apk "$TMP/preview-bad.out"
test ! -e "$CALLS"

# Root-manager action resolves the actual bundled package, including the full
# activity class because the preview application ID differs from its namespace.
cp "$ROOT/action.sh" "$MOD/action.sh"
cat > "$BIN/am" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" > "$MOCK_AM_CALLS"
EOF
chmod 0755 "$BIN/am"
cat > "$MOD/common/app_installer.sh" <<'EOF'
#!/bin/sh
echo installed
EOF
PATH="$BIN:$PATH" MOCK_AM_CALLS="$TMP/am.calls" sh "$MOD/action.sh" > "$TMP/action.out"
grep -qx 'start -n io.github.xgl34222220.luoshu.preview/io.github.xgl34222220.luoshu.MainActivity' "$TMP/am.calls"

printf 'Bundled App installer tests passed.\n'
