#!/bin/sh
# Build the main module's Zygisk library (全局字体增强, default off) for four ABIs.
#   build_zygisk.sh OUT_DIR
# OUT_DIR/<abi>/ receives libluoshu_native_font.so and lsnf-config.
# NDK: LUOSHU_NDK, else ANDROID_NDK_HOME, else $ANDROID_HOME/ndk/$LUOSHU_NDK_VERSION.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OUT_DIR="$1"
NDK_VERSION="${LUOSHU_NDK_VERSION:-28.2.13676358}"
SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"
NDK="${LUOSHU_NDK:-}"
if [ -z "$NDK" ] && [ -n "$SDK" ] && [ -f "$SDK/ndk/$NDK_VERSION/build/cmake/android.toolchain.cmake" ]; then
  NDK="$SDK/ndk/$NDK_VERSION"
fi
[ -n "$NDK" ] || NDK="${ANDROID_NDK_HOME:-}"
[ -n "$NDK" ] && [ -f "$NDK/build/cmake/android.toolchain.cmake" ] || {
  echo "Android NDK not found (set LUOSHU_NDK or install ndk;$NDK_VERSION)." >&2
  exit 70
}
command -v cmake >/dev/null 2>&1 || { echo 'cmake is required to build the Zygisk library.' >&2; exit 70; }
generator=''
command -v ninja >/dev/null 2>&1 && generator='-G Ninja'
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
for abi in arm64-v8a armeabi-v7a x86_64 x86; do
  # shellcheck disable=SC2086
  cmake -S "$ROOT/zygisk-native-font" -B "$work/$abi" $generator \
    -DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI="$abi" -DANDROID_PLATFORM=android-26 -DANDROID_STL=c++_static \
    -DCMAKE_BUILD_TYPE=Release >/dev/null
  cmake --build "$work/$abi" --target luoshu_native_font lsnf-config >/dev/null
  mkdir -p "$OUT_DIR/$abi"
  cp -f "$work/$abi/libluoshu_native_font.so" "$work/$abi/lsnf-config" "$OUT_DIR/$abi/"
done
ls -l "$OUT_DIR"/*/libluoshu_native_font.so "$OUT_DIR"/*/lsnf-config
