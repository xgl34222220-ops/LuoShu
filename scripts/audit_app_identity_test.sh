#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/module"
mkdir -p "$MOD/bundled" "$MOD/common" "$MOD/config" "$MOD/logs"
cp "$ROOT/common/app_installer.sh" "$MOD/common/"
cp "$ROOT/action.sh" "$MOD/action.sh"
printf 'test APK bytes\n' > "$MOD/bundled/LuoShu-App.apk"
HASH=$(sha256sum "$MOD/bundled/LuoShu-App.apk" | awk '{print $1}')
printf 'testBuildId=umix-test\nversionCode=70000\n' > "$MOD/module.prop"
cat > "$MOD/bundled/app.prop" <<META
package=io.github.xgl34222220.luoshu.audit
versionCode=7000001
sha256=$HASH
installPolicy=manual-only
testBuildId=umix-test
META
cat > "$TMP/pm" <<'PM'
#!/bin/sh
printf '%s\n' "$*" >> "$AUDIT_PM_CALLS"
exit 1
PM
chmod +x "$TMP/pm"
export APP_INSTALL_PM_BIN="$TMP/pm" APP_INSTALL_DUMPSYS_BIN="$TMP/pm" AUDIT_PM_CALLS="$TMP/pm.calls"
printf 'old private settings\n' > "$TMP/old-app-data"
for mode in auto first-boot service-retry manual; do
    touch "$MOD/config/app_install_pending"
    MODDIR="$MOD" sh "$MOD/common/app_installer.sh" "$mode" > "$TMP/result"
    grep -qx audit-manual-only "$TMP/result"
    test ! -f "$MOD/config/app_install_pending"
    test ! -f "$AUDIT_PM_CALLS"
done
sh "$MOD/action.sh" > "$TMP/action"
grep -q '保留原 App' "$TMP/action"
! grep -q '请先卸载' "$ROOT/action.sh"
test "$(cat "$TMP/old-app-data")" = 'old private settings'
grep -q '^status=manual_only$' "$MOD/config/app_install_state.conf"
# Audit package claims without matching module build identity are not accepted.
sed -i 's/testBuildId=umix-test/testBuildId=wrong/' "$MOD/bundled/app.prop"
if MODDIR="$MOD" sh "$MOD/common/app_installer.sh" auto > "$TMP/invalid"; then exit 1; fi
grep -qx invalid-package "$TMP/invalid"
test ! -f "$AUDIT_PM_CALLS"
grep -Fq 'applicationIdSuffix = if (auditApp) ".audit" else ".debug"' "$ROOT/android-app/app/build.gradle.kts"
grep -Fq '洛书·核心验收测试' "$ROOT/android-app/app/build.gradle.kts"
grep -Fq 'android:label="${luoshuAppLabel}"' "$ROOT/android-app/app/src/main/AndroidManifest.xml"
grep -Fq 'io.github.xgl34222220.luoshu.audit)' "$ROOT/common/app_cache_guard.sh"
grep -Fq 'luoshu_app_cache_guard "$1" native_import' "$ROOT/common/native_import.sh"
grep -Fq 'luoshu_app_cache_guard "$dest" font_archive' "$ROOT/common/font_archive_export.sh"
grep -Fq 'Audit App packaging requires explicit experimental build flags.' "$ROOT/scripts/read_app_identity.sh"
grep -Fq 'scripts/read_app_identity.sh' "$ROOT/scripts/build.sh"
# Execute the service's actual result branch: manual-only must not schedule retries.
python3 - "$ROOT/.luoshu-runtime/core/service.sh" "$TMP/service-case.sh" <<'PYCASE'
from pathlib import Path
import sys
text=Path(sys.argv[1]).read_text()
body=text.split('            case "$_app_result" in',1)[1].split('\n            esac',1)[0]
Path(sys.argv[2]).write_text('log_service() { :; }\ncase "$_app_result" in'+body+'\nesac\n')
PYCASE
touch "$MOD/config/app_install_pending" "$MOD/config/app_install_retry_count"
MODDIR="$MOD" _app_retry_file="$MOD/config/app_install_retry_count" _app_result=audit-manual-only sh "$TMP/service-case.sh"
test ! -e "$MOD/config/app_install_pending"
test ! -e "$MOD/config/app_install_retry_count"
printf 'audit_app_identity_test: PASS (separate package, manual-only, no package-manager calls, no uninstall)\n'
