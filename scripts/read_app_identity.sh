#!/bin/sh
# Read the actual APK. Environment values are consistency expectations, never overrides.
set -eu
APK="$1"
EXPECTED="$2"
[ -s "$APK" ] || { echo 'APK is missing.' >&2; exit 65; }
command -v apkanalyzer >/dev/null 2>&1 || {
    echo 'apkanalyzer is required to verify the actual APK identity.' >&2
    exit 66
}
PACKAGE=$(apkanalyzer manifest application-id "$APK" 2>/dev/null) || exit 66
CODE=$(apkanalyzer manifest version-code "$APK" 2>/dev/null) || exit 66
[ -n "$PACKAGE" ] || exit 66
case "$CODE" in ''|*[!0-9]*) exit 66 ;; esac
[ "$CODE" = "$EXPECTED" ] || { echo 'Actual APK versionCode does not match module.' >&2; exit 67; }
[ -z "${LUOSHU_APP_PACKAGE:-}" ] || [ "$LUOSHU_APP_PACKAGE" = "$PACKAGE" ] || {
    echo 'APK package expectation differs from actual APK.' >&2; exit 68;
}
[ -z "${LUOSHU_APP_VERSION_CODE:-}" ] || [ "$LUOSHU_APP_VERSION_CODE" = "$CODE" ] || {
    echo 'APK version expectation differs from actual APK.' >&2; exit 67;
}
if [ "${LUOSHU_AUDIT_APP:-0}" = 1 ] && [ "$PACKAGE" != io.github.xgl34222220.luoshu.audit ]; then
    echo 'Audit build must contain the actual separate audit package.' >&2
    exit 68
fi
case "$PACKAGE" in
    io.github.xgl34222220.luoshu) ;;
    io.github.xgl34222220.luoshu.debug)
        [ "${LUOSHU_ALLOW_DEBUG_APP:-0}" = 1 ] || exit 68
        ;;
    io.github.xgl34222220.luoshu.audit)
        [ "${LUOSHU_ALLOW_DEBUG_APP:-0}" = 1 ] && [ "${LUOSHU_AUDIT_APP:-0}" = 1 ] && [ -n "${LUOSHU_TEST_BUILD_ID:-}" ] || {
            echo 'Audit App packaging requires explicit experimental build flags.' >&2
            exit 68
        }
        ;;
    *) echo 'Unexpected actual APK package.' >&2; exit 68 ;;
esac
printf '%s\n%s\n' "$PACKAGE" "$CODE"
