#!/bin/sh
set -eu

APK=${1:-android-app/app/build/outputs/apk/release/app-release.apk}
PACKAGE=${2:-io.github.xgl34222220.luoshu}
DIAGNOSTICS=${3:-dist/startup-smoke}

mkdir -p "$DIAGNOSTICS"
adb install -r "$APK" > "$DIAGNOSTICS/install.txt" 2>&1
adb shell am force-stop "$PACKAGE"
adb logcat -c
adb shell am start -W -n "$PACKAGE/.MainActivity" > "$DIAGNOSTICS/am-start.txt" 2>&1 || true
sleep 8
adb shell pidof "$PACKAGE" > "$DIAGNOSTICS/pid.txt" 2>&1 || true
adb logcat -d -v threadtime > "$DIAGNOSTICS/logcat.txt"

if grep -nE 'FATAL EXCEPTION|AndroidRuntime.*Process: io\.github\.xgl34222220\.luoshu' "$DIAGNOSTICS/logcat.txt"; then
  echo 'LuoShu crashed during cold start.' >&2
  exit 1
fi

if [ ! -s "$DIAGNOSTICS/pid.txt" ]; then
  echo 'LuoShu process did not survive cold start.' >&2
  exit 1
fi

printf 'LuoShu cold start survived with PID %s\n' "$(cat "$DIAGNOSTICS/pid.txt")"
