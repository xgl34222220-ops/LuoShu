#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
WORK=${LUOSHU_RUNTIME_WORK:-"$ROOT/.runtime-work"}
PY_VERSION=${PY_VERSION:-3.14.6}
PY_ARCHIVE=${PY_ARCHIVE:-python-3.14.6-aarch64-linux-android.tar.gz}
PY_SHA256=${PY_SHA256:-38bbe77d3167b5cd554e03b1021324926f09f3825202b065951dd7638e9c37e5}
FONTTOOLS_VERSION=${FONTTOOLS_VERSION:-4.63.0}
NDK=${ANDROID_NDK_LATEST_HOME:-}

rm -rf "$WORK" "$ROOT/common/python"
mkdir -p "$WORK/runtime" "$WORK/download" "$ROOT/common/python" "$ROOT/licenses"

curl --silent --show-error --fail --location --retry 4 --retry-delay 3 \
  "https://www.python.org/ftp/python/$PY_VERSION/$PY_ARCHIVE" \
  -o "$WORK/download/$PY_ARCHIVE"
printf '%s  %s\n' "$PY_SHA256" "$WORK/download/$PY_ARCHIVE" | sha256sum -c -
tar -xzf "$WORK/download/$PY_ARCHIVE" -C "$WORK/runtime"
R="$WORK/runtime/prefix"
test -d "$R/lib/python3.14"
test -f "$R/lib/libpython3.14.so"
mkdir -p "$R/bin" "$R/lib/python3.14/site-packages"

if [ -z "$NDK" ] || [ ! -d "$NDK" ]; then
  NDK="$ANDROID_HOME/ndk/$(ls "$ANDROID_HOME/ndk" | sort -V | tail -1)"
fi
CC="$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android26-clang"
STRIP="$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip"
test -x "$CC"
cat > "$WORK/luoshu_python.c" <<'C'
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
typedef int (*py_bytes_main_fn)(int, char **);
int main(int argc, char **argv) {
    void *handle = dlopen("libpython3.14.so", RTLD_NOW | RTLD_GLOBAL);
    if (!handle) {
        const char *home = getenv("PYTHONHOME");
        if (home && *home) {
            char path[4096];
            snprintf(path, sizeof(path), "%s/lib/libpython3.14.so", home);
            handle = dlopen(path, RTLD_NOW | RTLD_GLOBAL);
        }
    }
    if (!handle) { fprintf(stderr, "LuoShu: %s\n", dlerror()); return 126; }
    py_bytes_main_fn run = (py_bytes_main_fn)dlsym(handle, "Py_BytesMain");
    if (!run) { fprintf(stderr, "LuoShu: %s\n", dlerror()); return 127; }
    return run(argc, argv);
}
C
"$CC" -O2 -fPIE -pie -Wl,--build-id=none -Wl,-z,relro,-z,now \
  "$WORK/luoshu_python.c" -ldl -o "$R/bin/luoshu-python"
"$STRIP" "$R/bin/luoshu-python"
file "$R/bin/luoshu-python" | grep -q 'ARM aarch64'

python3 -m venv "$WORK/host-venv"
"$WORK/host-venv/bin/python" -m pip install --disable-pip-version-check --no-cache-dir -q "fonttools==$FONTTOOLS_VERSION"
FT_DIR=$("$WORK/host-venv/bin/python" - <<'PY'
import fontTools, os
print(os.path.dirname(fontTools.__file__))
PY
)
HOST_SITE=$(dirname "$FT_DIR")
cp -a "$FT_DIR" "$R/lib/python3.14/site-packages/fontTools"
DIST=$(find "$HOST_SITE" -maxdepth 1 -type d -iname 'fonttools-*.dist-info' -print -quit)
test -n "$DIST"
cp -a "$DIST" "$R/lib/python3.14/site-packages/"

# Remove files not needed by LuoShu's offline font builder.
rm -rf \
  "$R/include" "$R/share" "$R/lib/pkgconfig" \
  "$R/lib/python3.14/test" "$R/lib/python3.14/idlelib" \
  "$R/lib/python3.14/ensurepip" "$R/lib/python3.14/tkinter" \
  "$R/lib/python3.14/turtledemo" "$R/lib/python3.14/pydoc_data" \
  "$R/lib/python3.14/venv" "$R/lib/python3.14/lib2to3/tests" \
  "$R/lib/python3.14/site-packages/fontTools/ttLib/tables/otConverters.pyx" \
  2>/dev/null || true
find "$R" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "$R" -type f \( -name '*.a' -o -name '*.la' -o -name '*.pyc' -o -name '*.c' -o -name '*.h' -o -name '*.pyx' \) -delete
find "$R/lib/python3.14/site-packages" -type f -name '*.so' -delete

cp -a "$R"/. "$ROOT/common/python/"
chmod 0755 "$ROOT/common/python/bin/luoshu-python"

PY_LICENSE=$(find "$WORK/runtime" -type f -iname 'LICENSE*' -print -quit)
test -n "$PY_LICENSE"
cp "$PY_LICENSE" "$ROOT/licenses/CPython-LICENSE.txt"
FT_LICENSE=$(find "$ROOT/common/python/lib/python3.14/site-packages" -path '*fonttools*.dist-info*' -type f -iname 'LICENSE*' -print -quit)
test -n "$FT_LICENSE"
cp "$FT_LICENSE" "$ROOT/licenses/FontTools-LICENSE.txt"

# Validate pure-Python imports using the exact pruned payload.
PYTHONPATH="$ROOT/common/python/lib/python3.14/site-packages" \
  python3 -S - <<'PY'
from fontTools.ttLib import TTFont, TTCollection
from fontTools.pens.ttGlyphPen import TTGlyphPen
print('FontTools payload import OK')
PY

rm -rf "$WORK"
echo 'Composite runtime prepared.'
