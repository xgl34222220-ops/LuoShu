#!/bin/sh
# Build LuoShu's WOFF2 decoder from pinned upstream sources.
#
#   CC=... CXX=... sh scripts/build_woff2_decoder.sh OUTPUT [extra link flags...]
#
# Sources are fixed commits with sha256-checked archives:
#   google/woff2  fb9c3379f2605b10f3e8f1d9636664ab5576775c (MIT, licenses/WOFF2-LICENSE.txt)
#   google/brotli ed738e842d2fbdf2d6459e39267a633c4a9b2f5d = v1.1.0 (MIT, licenses/Brotli-LICENSE.txt)
# Only the Brotli *decoder* and the WOFF2 *decoder* are compiled. The release
# runtime uses an Android ARM64 static build; tests build the same sources for
# the CI host so the identical decoder code path can be exercised there.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OUTPUT="${1:?usage: build_woff2_decoder.sh OUTPUT [extra link flags...]}"
shift
CC="${CC:-cc}"
CXX="${CXX:-c++}"

WOFF2_COMMIT=fb9c3379f2605b10f3e8f1d9636664ab5576775c
WOFF2_SHA256=f32f80941d621632fd668a00f3e30b00cde69df04ccb4730afb1809144bc6299
BROTLI_COMMIT=ed738e842d2fbdf2d6459e39267a633c4a9b2f5d
BROTLI_SHA256=aaa739962a45b508b2e783b915e6b2b57ed3b12bd4b0feac73acfb144dffa54f
CACHE="${LUOSHU_WOFF2_SRC_CACHE:-${TMPDIR:-/tmp}/luoshu-woff2-src}"

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT HUP INT TERM
mkdir -p "$CACHE"

fetch() {
    _repo="$1"; _commit="$2"; _sha="$3"; _archive="$CACHE/$_repo-$_commit.tar.gz"
    if [ ! -s "$_archive" ] || ! printf '%s  %s\n' "$_sha" "$_archive" | sha256sum -c - >/dev/null 2>&1; then
        curl --silent --show-error --fail --location --retry 4 --retry-delay 3 \
            "https://codeload.github.com/google/$_repo/tar.gz/$_commit" -o "$_archive.part"
        mv -f "$_archive.part" "$_archive"
    fi
    printf '%s  %s\n' "$_sha" "$_archive" | sha256sum -c - >/dev/null
    tar --no-same-owner -xzf "$_archive" -C "$WORK"
}
fetch woff2 "$WOFF2_COMMIT" "$WOFF2_SHA256"
fetch brotli "$BROTLI_COMMIT" "$BROTLI_SHA256"
W="$WORK/woff2-$WOFF2_COMMIT"
B="$WORK/brotli-$BROTLI_COMMIT"

# Release licenses must be the exact upstream texts of what is linked in.
cmp -s "$W/LICENSE" "$ROOT/licenses/WOFF2-LICENSE.txt" || { echo 'licenses/WOFF2-LICENSE.txt differs from upstream' >&2; exit 1; }
cmp -s "$B/LICENSE" "$ROOT/licenses/Brotli-LICENSE.txt" || { echo 'licenses/Brotli-LICENSE.txt differs from upstream' >&2; exit 1; }

OPT="-Os -fPIE -ffunction-sections -fdata-sections -DNDEBUG"
mkdir -p "$WORK/obj"
for _c in common/constants common/context common/dictionary common/platform common/shared_dictionary \
          common/transform dec/bit_reader dec/decode dec/huffman dec/state; do
    # shellcheck disable=SC2086
    "$CC" $OPT -std=c99 -I"$B/c/include" -c "$B/c/$_c.c" -o "$WORK/obj/brotli-$(printf '%s' "$_c" | tr / -).o"
done
for _cc in table_tags variable_length woff2_common woff2_dec woff2_out; do
    # shellcheck disable=SC2086
    "$CXX" $OPT -std=c++11 -fno-exceptions -I"$W/include" -I"$B/c/include" -c "$W/src/$_cc.cc" -o "$WORK/obj/woff2-$_cc.o"
done
# shellcheck disable=SC2086
"$CXX" $OPT -std=c++11 -fno-exceptions -I"$W/include" -c "$ROOT/tools/woff2/luoshu_woff2_decode.cc" -o "$WORK/obj/main.o"

mkdir -p "$(dirname "$OUTPUT")"
# shellcheck disable=SC2086
"$CXX" -Os -Wl,--gc-sections "$WORK"/obj/*.o -o "$OUTPUT" "$@"
chmod 0755 "$OUTPUT"
echo "WOFF2 decoder built: $OUTPUT ($(wc -c < "$OUTPUT" | tr -d '[:space:]') bytes)"
