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
cat > "$MOD/bundled/app.prop" <<'EOF'
package=io.github.xgl34222220.luoshu.debug
versionCode=1432001
sha256=unknown
EOF
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
    if [ "${MOCK_PM_FAIL:-0}" = 1 ]; then
      echo 'Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE]'
      exit 1
    fi
    echo 'Success'
    ;;
  *) exit 1 ;;
esac
EOF
chmod 0755 "$BIN/pm"

rm -f "$CALLS"
MOCK_VERSION=1432001 MOCK_PM_CALLS="$CALLS" \
APP_INSTALL_PM_BIN="$BIN/pm" APP_INSTALL_DUMPSYS_BIN="$BIN/dumpsys" \
MODDIR="$MOD" sh "$MOD/common/app_installer.sh" test-current > "$TMP/current.out"
grep -qx 'already-current' "$TMP/current.out"
grep -q '^status=up_to_date$' "$MOD/config/app_install_state.conf"
test ! -e "$CALLS"

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
MOCK_VERSION=1431901 MOCK_PM_FAIL=1 MOCK_PM_CALLS="$CALLS" \
APP_INSTALL_PM_BIN="$BIN/pm" APP_INSTALL_DUMPSYS_BIN="$BIN/dumpsys" \
MODDIR="$MOD" sh "$MOD/common/app_installer.sh" test-failure > "$TMP/failure.out"
FAIL_CODE=$?
set -e
test "$FAIL_CODE" -eq 11
grep -qx 'failed' "$TMP/failure.out"
test -f "$MOD/config/app_install_pending"
grep -q '^status=failed$' "$MOD/config/app_install_state.conf"
grep -q 'INSTALL_FAILED_UPDATE_INCOMPATIBLE' "$MOD/logs/app-install.log"

printf 'Bundled App installer tests passed.\n'
