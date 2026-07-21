#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SOURCE="$ROOT/common/python"
[ -d "$SOURCE/lib/python3.14" ] || { echo 'embedded Python runtime is missing' >&2; exit 1; }
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
STAGE="$TMP/module"
mkdir -p "$STAGE/common"
cp -a "$SOURCE" "$STAGE/common/python"

_before=$(du -sb "$STAGE/common/python" | awk '{print $1}')
sh "$ROOT/scripts/prune_python_runtime.sh" "$STAGE"
_after=$(du -sb "$STAGE/common/python" | awk '{print $1}')
_saved=$((_before - _after))
[ "$_saved" -ge 10000000 ] || {
    echo "runtime pruning saved too little: $_saved bytes" >&2
    exit 1
}

LIB="$STAGE/common/python/lib"
PYLIB="$LIB/python3.14"
DYN="$PYLIB/lib-dynload"

test -s "$LIB/libcrypto_python.so"
test ! -e "$LIB/libcrypto.so"
test ! -e "$LIB/libssl.so"
test ! -e "$LIB/libssl_python.so"
test ! -e "$LIB/libsqlite3.so"
test ! -e "$LIB/libsqlite3_python.so"
test ! -e "$PYLIB/sqlite3"
test ! -e "$PYLIB/config-3.14-aarch64-linux-android"
! find "$DYN" -maxdepth 1 -type f \( -name '_ssl.*.so' -o -name '_sqlite3.*.so' -o -name '_test*.so' \) -print -quit | grep -q .

# Every retained extension that requests a private OpenSSL/SQLite soname must still find it in the
# runtime library directory. System libraries such as libc/libm/libdl are intentionally ignored.
if command -v readelf >/dev/null 2>&1; then
    _needed="$TMP/needed.txt"
    : > "$_needed"
    find "$STAGE/common/python" -type f -name '*.so' | while IFS= read -r _so; do
        readelf -d "$_so" 2>/dev/null | sed -n 's/^.*Shared library: \[\([^]]*\)\].*$/\1/p'
    done | sort -u > "$_needed"
    while IFS= read -r _name; do
        case "$_name" in
            libcrypto_python.so|libssl_python.so|libsqlite3_python.so)
                test -s "$LIB/$_name" || { echo "missing retained private dependency: $_name" >&2; exit 1; }
                ;;
        esac
    done < "$_needed"
    ! grep -Eq '^libssl_python\.so$|^libsqlite3_python\.so$' "$_needed"
    grep -qx 'libcrypto_python.so' "$_needed"
fi

printf 'Python runtime pruning tests passed; saved %s bytes raw.\n' "$_saved"
