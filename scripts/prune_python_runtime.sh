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
# library, but remove the unused duplicate OpenSSL ABI and the complete SSL client stack. LuoShu
# only computes local hashes; it never opens TLS connections or loads legacy crypto providers.
rm -f \
  "$LIB/libcrypto.so" \
  "$LIB/libssl.so" \
  "$LIB/libssl_python.so" \
  "$DYN"/_ssl.*.so \
  "$PYLIB/ssl.py"
rm -rf "$LIB/engines-3" "$LIB/ossl-modules"

# LuoShu stores its state in small text/JSON files. No font path imports sqlite3, so shipping three
# SQLite library aliases plus the extension module wastes several compressed megabytes.
rm -f \
  "$LIB/libsqlite3.so" \
  "$LIB/libsqlite3.so.0" \
  "$LIB/libsqlite3_python.so" \
  "$DYN"/_sqlite3.*.so
rm -rf "$PYLIB/sqlite3"

# Android font input is restricted to TTF/OTF/TTC. Zstandard is a two-megabyte extension used only
# for optional archive compression and is absent from every LuoShu/FontTools execution trace.
rm -f "$DYN"/_zstd.*.so
rm -rf "$PYLIB/compression/zstd"

# The on-device tools are synchronous, offline command-line programs. Remove networking, servers,
# multiprocessing and interpreter-debugging components that are unrelated to font parsing. The
# retained runtime still includes threading, subprocess, XML, zlib/bz2/lzma and all codecs needed by
# font name tables and FontTools.
rm -rf \
  "$PYLIB/asyncio" \
  "$PYLIB/concurrent" \
  "$PYLIB/multiprocessing" \
  "$PYLIB/email" \
  "$PYLIB/http" \
  "$PYLIB/urllib" \
  "$PYLIB/html" \
  "$PYLIB/xmlrpc" \
  "$PYLIB/wsgiref" \
  "$PYLIB/unittest"
rm -f \
  "$DYN"/_asyncio.*.so \
  "$DYN"/_remote_debugging.*.so \
  "$DYN"/_interpchannels.*.so \
  "$DYN"/_interpreters.*.so \
  "$PYLIB/imaplib.py" \
  "$PYLIB/ftplib.py" \
  "$PYLIB/smtplib.py" \
  "$PYLIB/mailbox.py" \
  "$PYLIB/webbrowser.py" \
  "$PYLIB/socketserver.py" \
  "$PYLIB/ipaddress.py" \
  "$PYLIB/doctest.py" \
  "$PYLIB/trace.py" \
  "$PYLIB/modulefinder.py" \
  "$PYLIB/compileall.py"

# Package metadata is only used by installers and importlib.metadata queries. LuoShu imports the
# vendored FontTools package directly and never performs package discovery on-device.
rm -rf "$PYLIB/site-packages/fonttools-4.63.0.dist-info"

# CPython test/demo extensions and build metadata are never needed on-device. Match the complete
# families instead of maintaining an error-prone list that misses new test modules between releases.
find "$DYN" -maxdepth 1 -type f \( \
  -name '_test*.so' -o \
  -name '_xxtest*.so' -o \
  -name '_ctypes_test*.so' -o \
  -name 'xxlimited*.so' -o \
  -name 'xxsubtype*.so' \
\) -delete 2>/dev/null || true
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
