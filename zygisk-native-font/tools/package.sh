#!/bin/sh
# Assemble the companion module ZIP from per-ABI build directories.
#   package.sh BUILD_ROOT OUT_DIR VERSION VERSION_CODE
# BUILD_ROOT/<abi>/ must contain libluoshu_native_font.so and lsnf-config.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
build_root="$1"
out_dir="$2"
version="$3"
version_code="$4"
abis='arm64-v8a armeabi-v7a x86_64 x86'

stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
cp -R "$here/module/." "$stage/"
sed -e "s/@VERSION@/$version/" -e "s/@VERSION_CODE@/$version_code/" "$here/module/module.prop.in" > "$stage/module.prop"
rm -f "$stage/module.prop.in"
touch "$stage/skip_mount"
mkdir -p "$stage/zygisk" "$stage/licenses"
for abi in $abis; do
  so="$build_root/$abi/libluoshu_native_font.so"
  tool="$build_root/$abi/lsnf-config"
  test -s "$so" || { echo "missing $so" >&2; exit 1; }
  test -s "$tool" || { echo "missing $tool" >&2; exit 1; }
  cp "$so" "$stage/zygisk/$abi.so"
  mkdir -p "$stage/bin/$abi"
  cp "$tool" "$stage/bin/$abi/lsnf-config"
  chmod 0755 "$stage/bin/$abi/lsnf-config"
done
cp "$here/third_party/zygisk/LICENSE" "$stage/licenses/zygisk.hpp.txt"
cp "$here/README.md" "$stage/README.md"
chmod 0755 "$stage/customize.sh" "$stage/post-fs-data.sh" "$stage/uninstall.sh" \
  "$stage/META-INF/com/google/android/update-binary"

mkdir -p "$out_dir"
zip_path="$out_dir/LuoShuNativeFont-$version.zip"
rm -f "$zip_path"
(cd "$stage" && find . -type f | LC_ALL=C sort | sed 's#^\./##' | TZ=UTC zip -X -q -9 "$zip_path" -@)
unzip -l "$zip_path"
echo "zip=$zip_path"
