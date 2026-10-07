#!/bin/sh
# Build a separate, debuggable instrumentation APK using the installed Android SDK.
# It instruments only itself and reads the current foreground accessibility tree.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SDK=${ANDROID_SDK_ROOT:-${ANDROID_HOME:-}}
OUTPUT=${1:?Usage: build_ui_snapshot_helper.sh OUTPUT_APK}
test -n "$SDK" || { echo 'Android SDK directory is not configured' >&2; exit 1; }
PLATFORM=$(find "$SDK/platforms" -mindepth 1 -maxdepth 1 -type d -name 'android-*' | sort -V | tail -n 1)
BUILD_TOOLS=$(find "$SDK/build-tools" -mindepth 1 -maxdepth 1 -type d | sort -V | tail -n 1)
test -f "$PLATFORM/android.jar"
for TOOL in d8 aapt2 zipalign apksigner; do test -x "$BUILD_TOOLS/$TOOL"; done
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT HUP INT TERM
mkdir -p "$WORK/classes" "$WORK/dex" "$(dirname "$OUTPUT")"
javac -source 8 -target 8 -bootclasspath "$PLATFORM/android.jar" -d "$WORK/classes" \
    "$ROOT/scripts/ui_snapshot/SnapshotInstrumentation.java"
jar cf "$WORK/classes.jar" -C "$WORK/classes" .
"$BUILD_TOOLS/d8" --min-api 28 --lib "$PLATFORM/android.jar" --output "$WORK/dex" "$WORK/classes.jar"
"$BUILD_TOOLS/aapt2" link -I "$PLATFORM/android.jar" \
    --manifest "$ROOT/scripts/ui_snapshot/AndroidManifest.xml" -o "$WORK/unsigned.apk"
(cd "$WORK/dex" && zip -q "$WORK/unsigned.apk" classes.dex)
"$BUILD_TOOLS/zipalign" -f 4 "$WORK/unsigned.apk" "$WORK/aligned.apk"
# A throwaway key is limited to this test helper, never the production App.
keytool -genkeypair -keystore "$WORK/helper.keystore" -storepass android -keypass android \
    -alias snapshot -keyalg RSA -keysize 2048 -validity 1 -dname 'CN=LuoShu UI snapshot test'
"$BUILD_TOOLS/apksigner" sign --ks "$WORK/helper.keystore" --ks-key-alias snapshot \
    --ks-pass pass:android --key-pass pass:android --out "$OUTPUT" "$WORK/aligned.apk"
"$BUILD_TOOLS/apksigner" verify "$OUTPUT"
echo "Built independent UI snapshot test APK: $OUTPUT"
