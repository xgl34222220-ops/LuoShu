#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
mkdir -p "$TMP/bin"
printf 'APK fixture\n' > "$TMP/app.apk"
cat > "$TMP/bin/apkanalyzer" <<'TOOL'
#!/bin/sh
case "$2" in application-id) printf '%s\n' "$ACTUAL_PACKAGE" ;; version-code) printf '%s\n' "$ACTUAL_CODE" ;; *) exit 1 ;; esac
TOOL
chmod +x "$TMP/bin/apkanalyzer"
export PATH="$TMP/bin:$PATH" ACTUAL_CODE=7000001 LUOSHU_APP_VERSION_CODE=7000001
export ACTUAL_PACKAGE=io.github.xgl34222220.luoshu.audit LUOSHU_AUDIT_APP=1 LUOSHU_ALLOW_DEBUG_APP=1 LUOSHU_TEST_BUILD_ID=umix-test
sh "$ROOT/scripts/read_app_identity.sh" "$TMP/app.apk" 7000001 > "$TMP/valid"
grep -qx io.github.xgl34222220.luoshu.audit "$TMP/valid"
for pkg in io.github.xgl34222220.luoshu io.github.xgl34222220.luoshu.debug com.other.app; do
    if ACTUAL_PACKAGE="$pkg" sh "$ROOT/scripts/read_app_identity.sh" "$TMP/app.apk" 7000001 >/dev/null 2>&1; then exit 1; fi
done
if LUOSHU_APP_PACKAGE=io.github.xgl34222220.luoshu sh "$ROOT/scripts/read_app_identity.sh" "$TMP/app.apk" 7000001 >/dev/null 2>&1; then exit 1; fi
if ACTUAL_CODE=999 sh "$ROOT/scripts/read_app_identity.sh" "$TMP/app.apk" 7000001 >/dev/null 2>&1; then exit 1; fi
if LUOSHU_AUDIT_APP=0 sh "$ROOT/scripts/read_app_identity.sh" "$TMP/app.apk" 7000001 >/dev/null 2>&1; then exit 1; fi
ACTUAL_PACKAGE=io.github.xgl34222220.luoshu LUOSHU_AUDIT_APP=0 sh "$ROOT/scripts/read_app_identity.sh" "$TMP/app.apk" 7000001 > "$TMP/release"
grep -qx io.github.xgl34222220.luoshu "$TMP/release"
printf 'app_package_metadata_test: PASS (actual package/version, two-way audit identity, no override bypass)\n'
