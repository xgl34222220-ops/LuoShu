#!/bin/sh
# Build the offline WOFF2 decoder from the exact upstream Brotli source.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT HUP INT TERM
NDK=${ANDROID_NDK_LATEST_HOME:-${ANDROID_NDK_HOME:-}}
if [ -z "$NDK" ] && [ -n "${ANDROID_HOME:-}" ] && [ -d "$ANDROID_HOME/ndk" ]; then
    NDK="$ANDROID_HOME/ndk/$(ls "$ANDROID_HOME/ndk" | sort -V | tail -1)"
fi
CC="$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android26-clang"
STRIP="$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip"
test -x "$CC" || { echo 'Android NDK is required to build the ARM64 WOFF2 decoder' >&2; exit 1; }
COMMIT=028fb5a23661f123017c060daa546b55cf4bde29
SHA256=0afe09a53c8bad9861c8dd1fc1284308d54f19d2979ba3541cfdcc9b05fe360f
curl --silent --show-error --fail --location --retry 4 \
    "https://github.com/google/brotli/archive/$COMMIT.tar.gz" -o "$WORK/brotli.tar.gz"
printf '%s  %s\n' "$SHA256" "$WORK/brotli.tar.gz" | sha256sum -c -
tar --no-same-owner -xzf "$WORK/brotli.tar.gz" -C "$WORK"
SOURCE="$WORK/brotli-$COMMIT"
RUNTIME="$ROOT/common/python"
mkdir -p "$RUNTIME/bin" "$RUNTIME/lib/python3.14/site-packages" "$ROOT/licenses"
# Static Bionic removes loader/shared-library version dependencies. Android API 26
# is below the app's API 28 floor; no host executable or Python ABI extension ships.
"$CC" -Oz -static -fPIE -fstack-protector-strong -ffunction-sections -fdata-sections \
    -Wl,--build-id=none -Wl,--gc-sections -Wl,-z,relro,-z,now \
    -I"$SOURCE/c/include" "$ROOT/scripts/runtime/luoshu_brotli.c" \
    "$SOURCE"/c/common/*.c "$SOURCE"/c/dec/*.c -o "$WORK/luoshu-brotli"
"$STRIP" "$WORK/luoshu-brotli"
file "$WORK/luoshu-brotli" | grep -q 'ARM aarch64'
cp "$WORK/luoshu-brotli" "$RUNTIME/bin/luoshu-brotli"
chmod 0755 "$RUNTIME/bin/luoshu-brotli"
cp "$ROOT/scripts/runtime/brotli.py" "$RUNTIME/lib/python3.14/site-packages/brotli.py"
cp "$SOURCE/LICENSE" "$ROOT/licenses/Brotli-LICENSE.txt"
# Static Bionic and compiler builtins are redistributed inside the executable.
# Carry the exact NDK notices as well as Brotli's own license.
cp "$NDK/toolchains/llvm/prebuilt/linux-x86_64/sysroot/NOTICE" "$ROOT/licenses/Android-NDK-sysroot-NOTICE.txt"
cp "$NDK/toolchains/llvm/prebuilt/linux-x86_64/NOTICE" "$ROOT/licenses/Android-NDK-toolchain-NOTICE.txt"
printf 'Brotli 1.2.0 (%s), Android ARM64 API 26 decoder prepared.\n' "$COMMIT"
