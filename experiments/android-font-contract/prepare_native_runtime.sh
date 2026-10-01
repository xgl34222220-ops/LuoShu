#!/bin/sh
# CI-only Android x86_64 sibling of the shipped ARM64 runtime; never packaged.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
DEST="$ROOT/experiments/android-font-contract/.runtime-x86"
[ ! -e "$DEST" ] || { echo 'CI runtime destination already exists' >&2; exit 1; }
WORK=$(mktemp -d "${RUNNER_TEMP:-/tmp}/luoshu-x86-runtime.XXXXXX")
trap 'rm -rf "$WORK"' EXIT HUP INT TERM
ARCHIVE=python-3.14.6-x86_64-linux-android.tar.gz
DIGEST=e04eb26607627e68d148f89de793372f54a345c91b13628567f24abcdd3bfa3e
curl --fail --silent --show-error --location --max-time 120 --retry 2 \
  "https://www.python.org/ftp/python/3.14.6/$ARCHIVE" -o "$WORK/$ARCHIVE"
printf '%s  %s\n' "$DIGEST" "$WORK/$ARCHIVE" | sha256sum -c -
mkdir "$WORK/extract"
tar --no-same-owner -xzf "$WORK/$ARCHIVE" -C "$WORK/extract"
R="$WORK/extract/prefix"
test -f "$R/lib/libpython3.14.so"
NDK=${ANDROID_NDK_LATEST_HOME:-}
if [ -z "$NDK" ] || [ ! -d "$NDK" ]; then
  NDK="$ANDROID_HOME/ndk/$(ls "$ANDROID_HOME/ndk" | sort -V | tail -1)"
fi
TOOLCHAIN="$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin"
test -x "$TOOLCHAIN/x86_64-linux-android26-clang"
python3 - "$ROOT" "$WORK" "$R" <<'PY'
import pathlib,shutil,sys
import fontTools
assert fontTools.__version__=='4.63.0',fontTools.__version__
root,work,r=map(pathlib.Path,sys.argv[1:])
source=(root/'scripts/prepare_composite_runtime.sh').read_text()
launcher=source.split('cat > "$WORK/luoshu_python.c" <<\'C\'\n',1)[1].split('\nC\n',1)[0]
(work/'launcher.c').write_text(launcher+'\n')
site=r/'lib/python3.14/site-packages';site.mkdir(parents=True,exist_ok=True)
shutil.copytree(pathlib.Path(fontTools.__file__).parent,site/'fontTools')
for path in (site/'fontTools').rglob('*.so'):path.unlink()
PY
mkdir -p "$R/bin"
"$TOOLCHAIN/x86_64-linux-android26-clang" -O2 -fPIE -pie -Wl,--build-id=none,-z,relro,-z,now \
  "$WORK/launcher.c" -ldl -o "$R/bin/luoshu-python"
"$TOOLCHAIN/llvm-strip" "$R/bin/luoshu-python"
file "$R/bin/luoshu-python" | grep -q 'x86-64'
"$TOOLCHAIN/llvm-readelf" -l "$R/bin/luoshu-python" | grep -q '/system/bin/linker64'
python3 - "$ROOT" "$DEST" "$R" "$DIGEST" <<'PY'
import hashlib,json,pathlib,shutil,sys
root,dest,r=map(pathlib.Path,sys.argv[1:4])
shutil.copytree(root/'common',dest/'common',ignore=shutil.ignore_patterns('python','__pycache__'))
shutil.copytree(r,dest/'common/python')
for part in ('core','compat'):
 source=root/'.luoshu-runtime'/part
 if source.is_dir():shutil.copytree(source,dest/'.luoshu-runtime'/part,symlinks=True)
report={'schema':'ci-android-runtime-v1','pythonVersion':'3.14.6','fontToolsVersion':'4.63.0',
        'architecture':'x86_64','shippedArm64RuntimeExecuted':False,'archiveSha256':sys.argv[4],
        'purpose':'actual Android execution of production Python code; no user module packaging'}
(dest/'runtime-origin.json').write_text(json.dumps(report,indent=2))
PY
sh "$ROOT/scripts/prune_python_runtime.sh" "$DEST"
rm -rf "$DEST/common/python/include" "$DEST/common/python/share" \
  "$DEST/common/python/lib/pkgconfig" "$DEST/common/python/lib/python3.14/test" \
  "$DEST/common/python/lib/python3.14/ensurepip" \
  "$DEST/common/python/lib/python3.14/config-3.14-x86_64-linux-android"
find "$DEST/common/python" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$DEST/common/python" -type f \( -name '*.a' -o -name '*.la' -o -name '*.pyc' \) -delete
echo 'CI-only Android x86_64 runtime prepared; not the shipped ARM64 binary.'
