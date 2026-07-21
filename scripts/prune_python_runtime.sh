#!/bin/sh
# Remove CPython components that LuoShu's offline font tools never import.
set -eu

STAGE_ROOT="${1:?usage: prune_python_runtime.sh <module-stage>}"
RUNTIME="$STAGE_ROOT/common/python"
LIB="$RUNTIME/lib"
PYLIB="$LIB/python3.14"
DYN="$PYLIB/lib-dynload"

[ -d "$PYLIB" ] || { echo "Python runtime not found: $PYLIB" >&2; exit 1; }

# hashlib is used for font/cache identities and links to libcrypto_python.so. Keep that private
# library, but remove the unused duplicate OpenSSL ABI and the complete SSL client stack.
rm -f \
  "$LIB/libcrypto.so" \
  "$LIB/libssl.so" \
  "$LIB/libssl_python.so" \
  "$DYN"/_ssl.*.so \
  "$PYLIB/ssl.py"

# LuoShu stores its state in small text/JSON files. No font path imports sqlite3, so shipping three
# SQLite library aliases plus the extension module wastes several compressed megabytes.
rm -f \
  "$LIB/libsqlite3.so" \
  "$LIB/libsqlite3.so.0" \
  "$LIB/libsqlite3_python.so" \
  "$DYN"/_sqlite3.*.so
rm -rf "$PYLIB/sqlite3"

# CPython test extensions and build metadata are never needed on-device and expose a large native
# surface unrelated to font parsing or generation.
rm -f \
  "$DYN"/_testcapi.*.so \
  "$DYN"/_testlimitedcapi.*.so \
  "$DYN"/_testinternalcapi.*.so \
  "$DYN"/_testclinic.*.so \
  "$DYN"/_testbuffer.*.so \
  "$DYN"/_testmultiphase.*.so \
  "$DYN"/_testsinglephase.*.so
rm -rf "$PYLIB/config-3.14-aarch64-linux-android"

# Interactive demonstrations/debug helpers are pure development payload. Keep argparse, pathlib,
# tempfile, XML, encodings, hashlib and all FontTools packages used by LuoShu.
rm -rf "$PYLIB/__phello__" "$PYLIB/_pyrepl"
rm -f \
  "$PYLIB/__hello__.py" \
  "$PYLIB/antigravity.py" \
  "$PYLIB/bdb.py" \
  "$PYLIB/cProfile.py" \
  "$PYLIB/pdb.py" \
  "$PYLIB/profile.py" \
  "$PYLIB/pstats.py" \
  "$PYLIB/pydoc.py" \
  "$PYLIB/rlcompleter.py" \
  "$PYLIB/this.py" \
  "$PYLIB/turtle.py"

find "$RUNTIME" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$RUNTIME" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true

# Hard requirements for all current LuoShu Python tools.
test -s "$LIB/libpython3.14.so"
test -s "$LIB/libcrypto_python.so"
find "$DYN" -maxdepth 1 -type f -name '_hashlib.*.so' -print -quit | grep -q .
test -d "$PYLIB/site-packages/fontTools"
test -s "$PYLIB/argparse.py"
test -s "$PYLIB/hashlib.py"
test -s "$PYLIB/tempfile.py"
test -s "$PYLIB/xml/etree/ElementTree.py"
