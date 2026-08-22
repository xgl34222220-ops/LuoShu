#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/scripts/runtime_versions.conf"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

mkdir -p \
  "$TMP/repo/scripts" \
  "$TMP/sdk/ndk/$LUOSHU_ANDROID_NDK_VERSION/toolchains/llvm/prebuilt/linux-x86_64/bin" \
  "$TMP/wrong" \
  "$TMP/bin"
cp "$ROOT/scripts/prepare_composite_runtime.sh" "$ROOT/scripts/runtime_versions.conf" "$TMP/repo/scripts/"
printf 'Pkg.Revision = %s\n' "$LUOSHU_ANDROID_NDK_VERSION" > "$TMP/sdk/ndk/$LUOSHU_ANDROID_NDK_VERSION/source.properties"
printf 'Pkg.Revision = 27.3.13750724\n' > "$TMP/wrong/source.properties"

for tool in "aarch64-linux-android${LUOSHU_ANDROID_MIN_API}-clang" llvm-strip; do
  printf '#!/bin/sh\nexit 0\n' > "$TMP/sdk/ndk/$LUOSHU_ANDROID_NDK_VERSION/toolchains/llvm/prebuilt/linux-x86_64/bin/$tool"
  chmod 0755 "$TMP/sdk/ndk/$LUOSHU_ANDROID_NDK_VERSION/toolchains/llvm/prebuilt/linux-x86_64/bin/$tool"
done
cat > "$TMP/bin/curl" <<'EOF_CURL'
#!/bin/sh
echo pinned-ndk-selected >&2
exit 73
EOF_CURL
chmod 0755 "$TMP/bin/curl"

set +e
PATH="$TMP/bin:$PATH" \
ANDROID_HOME="$TMP/sdk" \
ANDROID_NDK_HOME="$TMP/wrong" \
LUOSHU_RUNTIME_WORK="$TMP/work" \
  sh "$TMP/repo/scripts/prepare_composite_runtime.sh" > "$TMP/output" 2>&1
status=$?
set -e

test "$status" -eq 73
grep -q 'pinned-ndk-selected' "$TMP/output"
! grep -q 'NDK mismatch' "$TMP/output"
echo 'Pinned Android NDK selection tests passed.'
