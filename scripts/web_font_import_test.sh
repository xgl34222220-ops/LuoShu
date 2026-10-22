#!/bin/sh
# PR-G: WOFF / WOFF2 web fonts and font ZIP archives are converted / safely extracted before the
# normal TTF/OTF/TTC validation. Covers:
#   1. font_check.sh keeps the old rejection without a conversion dir, converts-then-validates with one;
#   2. WOFF (FontTools/zlib) and WOFF2 via the bundled decoder path (FontTools forced off, as on-device);
#   3. a clear error when the WOFF2 decoder is missing;
#   4. native App import bridge (native_import.sh) for .woff2, duplicate detection on re-import;
#   5. ZIP import with nested WOFF2 + WOFF + macOS resource forks, and same-stem SFNT preference;
#   6. font_zip_extract.py rejects path traversal, symlinks, zip bombs and empty archives.
# WOFF2 cases need a decoder: LUOSHU_TEST_WOFF2_DECODER (e.g. the shipped ARM64 binary under qemu),
# or LUOSHU_WOFF2_TEST_BUILD=1 to build one for the host from the pinned sources; WOFF2 fixtures
# need the Python brotli module. check.sh runs the WOFF/ZIP subset; web-font-import.yml runs all.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

fail() { echo "web font import test: $*" >&2; exit 1; }

FONT="${LUOSHU_TEST_FONT:-$(find /usr/share/fonts -type f -iname 'DejaVuSans.ttf' -print -quit 2>/dev/null || true)}"
if [ ! -s "$FONT" ]; then
    echo 'Web font import test skipped: DejaVu Sans is unavailable.'
    exit 0
fi
BUNDLED_SITE="$ROOT/common/python/lib/python3.14/site-packages"
[ -d "$BUNDLED_SITE/fontTools" ] && PYTHONPATH="$BUNDLED_SITE${PYTHONPATH:+:$PYTHONPATH}" && export PYTHONPATH
python3 -c 'import fontTools' 2>/dev/null || fail 'FontTools is required'
HAVE_BROTLI=false
python3 -c 'import brotli' 2>/dev/null && HAVE_BROTLI=true

DECODER="${LUOSHU_TEST_WOFF2_DECODER:-}"
if [ -z "$DECODER" ] && [ "${LUOSHU_WOFF2_TEST_BUILD:-0}" = 1 ]; then
    DECODER="$TMP/host-woff2-decode"
    sh "$ROOT/scripts/build_woff2_decoder.sh" "$DECODER" >/dev/null || fail 'host WOFF2 decoder build failed'
fi

make_flavor() {
    python3 - "$1" "$2" "$3" <<'PY'
import sys
from fontTools.ttLib import TTFont
font = TTFont(sys.argv[1])
font.flavor = sys.argv[3]
font.save(sys.argv[2])
PY
}

# Glyph outlines and cmap must survive the round trip (glyf bytes may legally differ after WOFF2).
same_font() {
    python3 - "$1" "$2" <<'PY'
import sys
from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont
a, b = TTFont(sys.argv[1]), TTFont(sys.argv[2])
assert a.getBestCmap() == b.getBestCmap(), "cmap differs"
assert a.getGlyphOrder() == b.getGlyphOrder(), "glyph order differs"
ga, gb = a.getGlyphSet(), b.getGlyphSet()
for name in a.getGlyphOrder()[:400]:
    pa, pb = RecordingPen(), RecordingPen()
    ga[name].draw(pa); gb[name].draw(pb)
    assert pa.value == pb.value, f"outline differs: {name}"
    assert ga[name].width == gb[name].width, f"advance differs: {name}"
PY
}

make_flavor "$FONT" "$TMP/Web Sans.woff" woff

check_env() {
    # shellcheck disable=SC2016
    sh -c '
        MODULE_DIR="$1"; LUOSHU_IMPORT_PYTHON=python3; export LUOSHU_IMPORT_PYTHON
        . "$1/common/font_check.sh"
        FONT_CHECK_CONVERT_DIR="$3"
        if font_validate "$2" text; then rc=0; else rc=1; fi
        printf "%s|%s|%s|%s|%s\n" "$rc" "$FONT_CHECK_FORMAT" "$FONT_CHECK_SOURCE_FORMAT" "$FONT_CHECK_CONVERTED" "$FONT_CHECK_ERROR"
    ' sh "$ROOT" "$1" "${2:-}"
}

# 1. Read-only callers keep the historical rejection.
OUT=$(check_env "$TMP/Web Sans.woff")
case "$OUT" in '1|WOFF|||检测到网页字体 WOFF，不能仅修改扩展名后作为系统字体') ;; *) fail "read-only WOFF rejection changed: $OUT" ;; esac

# 2a. WOFF converts with FontTools and is validated as the resulting TTF.
OUT=$(check_env "$TMP/Web Sans.woff" "$TMP/conv-woff")
case "$OUT" in "0|TTF|WOFF|$TMP/conv-woff/Web-Sans.ttf|") ;; *) fail "WOFF convert-then-validate failed: $OUT" ;; esac
same_font "$FONT" "$TMP/conv-woff/Web-Sans.ttf"

# A renamed extension is not conversion: random bytes behind a .woff name stay rejected.
head -c 8192 /dev/urandom > "$TMP/fake.woff"
OUT=$(check_env "$TMP/fake.woff" "$TMP/conv-fake")
case "$OUT" in 1\|UNKNOWN\|*) ;; *) fail "fake WOFF was accepted: $OUT" ;; esac

if [ "$HAVE_BROTLI" = true ]; then
    make_flavor "$FONT" "$TMP/Web Sans.woff2" woff2
    # 2b. FontTools path (hosts that have brotli).
    OUT=$(check_env "$TMP/Web Sans.woff2" "$TMP/conv-ft")
    case "$OUT" in "0|TTF|WOFF2|$TMP/conv-ft/Web-Sans.ttf|") ;; *) fail "WOFF2 FontTools conversion failed: $OUT" ;; esac
    same_font "$FONT" "$TMP/conv-ft/Web-Sans.ttf"

    # 3. On-device runtime (no brotli) without a decoder: explicit, actionable error.
    OUT=$(LUOSHU_WOFF2_FORCE_NATIVE=1 LUOSHU_WOFF2_DECODER="$TMP/missing-decoder" check_env "$TMP/Web Sans.woff2" "$TMP/conv-missing")
    case "$OUT" in
        *'检测到网页字体 WOFF2，不能仅修改扩展名后作为系统字体；转换失败：WOFF2 需要 Brotli 解码'*'luoshu-woff2-decode'*) ;;
        *) fail "missing decoder error is unclear: $OUT" ;;
    esac
    ! ls "$TMP/conv-missing"/*.ttf >/dev/null 2>&1 || fail 'failed conversion left a font behind'

    if [ -n "$DECODER" ]; then
        export LUOSHU_WOFF2_DECODER="$DECODER"
        # 2c. Bundled decoder path, exactly as on-device (FontTools has no brotli there).
        OUT=$(LUOSHU_WOFF2_FORCE_NATIVE=1 check_env "$TMP/Web Sans.woff2" "$TMP/conv-native")
        case "$OUT" in "0|TTF|WOFF2|$TMP/conv-native/Web-Sans.ttf|") ;; *) fail "WOFF2 native conversion failed: $OUT" ;; esac
        same_font "$FONT" "$TMP/conv-native/Web-Sans.ttf"
        JSON=$(LUOSHU_WOFF2_FORCE_NATIVE=1 python3 "$ROOT/common/font_web_convert.py" --input "$TMP/Web Sans.woff2" --output-dir "$TMP/conv-json")
        printf '%s' "$JSON" | grep -q '"decodeMethod":"native"' || fail "decoder was not used: $JSON"
        # Corrupt WOFF2 payload: decoder fails cleanly and nothing is kept.
        python3 - "$TMP/Web Sans.woff2" "$TMP/broken.woff2" <<'PY'
import sys
data = bytearray(open(sys.argv[1], 'rb').read())
for i in range(len(data) // 2, len(data)):
    data[i] ^= 0x5A
open(sys.argv[2], 'wb').write(bytes(data))
PY
        OUT=$(LUOSHU_WOFF2_FORCE_NATIVE=1 check_env "$TMP/broken.woff2" "$TMP/conv-broken")
        case "$OUT" in 1\|WOFF2\|*'转换失败'*) ;; *) fail "corrupt WOFF2 was not rejected: $OUT" ;; esac
        ! ls "$TMP/conv-broken"/*.ttf >/dev/null 2>&1 || fail 'corrupt WOFF2 left a font behind'
    else
        echo 'web font import test: no WOFF2 decoder given, bundled-decoder cases skipped'
    fi
else
    echo 'web font import test: python brotli unavailable, WOFF2 fixtures skipped'
fi

# 4. App import bridge accepts a web font, imports the converted SFNT and dedups a re-import.
WEB_SAMPLE="$TMP/Web Sans.woff"
WEB_EXT=woff
if [ "$HAVE_BROTLI" = true ] && [ -n "$DECODER" ]; then
    WEB_SAMPLE="$TMP/Web Sans.woff2"; WEB_EXT=woff2
fi
# Throwaway module root: common/ is the real code, config/ and state stay inside $TMP.
mkdir -p "$TMP/mod/config" "$TMP/public/fonts" "$TMP/state-tmp"
ln -s "$ROOT/common" "$TMP/mod/common"
# A .git marker makes util_functions treat it as a source checkout (no on-device path migration).
: > "$TMP/mod/.git"
# The bridge only trusts the App cache and schedules a real prewarm; stub exactly those two hooks.
sed -e 's#^trusted_source() {#trusted_source() { return 0; }\
trusted_source_original() {#' \
    -e 's#^schedule_font_prewarm() {#schedule_font_prewarm() { return 0; }\
schedule_font_prewarm_original() {#' \
    "$ROOT/common/native_import.sh" > "$TMP/native_import_under_test.sh"
grep -q '^trusted_source() { return 0; }$' "$TMP/native_import_under_test.sh" || fail 'trusted_source stub not applied'
grep -q '^schedule_font_prewarm() { return 0; }$' "$TMP/native_import_under_test.sh" || fail 'prewarm stub not applied'
native_import() {
    MODDIR="$TMP/mod" LUOSHU_PUBLIC_DIR="$TMP/public" LUOSHU_TMP_DIR="$TMP/state-tmp" \
        LUOSHU_IMPORT_PYTHON=python3 LUOSHU_WOFF2_FORCE_NATIVE=1 \
        sh "$TMP/native_import_under_test.sh" "$1" "$2"
}
OUT=$(native_import "$WEB_SAMPLE" "Web Sans.$WEB_EXT")
printf '%s\n' "$OUT" | grep -q '"status":"ok"' || fail "native import of $WEB_EXT failed: $OUT"
printf '%s\n' "$OUT" | grep -q '"format":"TTF"' || fail "native import did not store a TTF: $OUT"
printf '%s\n' "$OUT" | grep -q '"duplicate":false' || fail "first import reported duplicate: $OUT"
test -s "$TMP/public/fonts/Web Sans.ttf" || fail 'converted TTF missing from the font library'
! ls "$TMP/public/fonts" | grep -qi 'woff' || fail 'web font container copied into the library'
same_font "$FONT" "$TMP/public/fonts/Web Sans.ttf"
OUT=$(native_import "$WEB_SAMPLE" "Web Sans.$WEB_EXT")
printf '%s\n' "$OUT" | grep -q '"duplicate":true' || fail "re-import was not detected as duplicate: $OUT"
[ -z "$(ls -A "$TMP/state-tmp" 2>/dev/null | grep native-import-web || true)" ] || fail 'conversion scratch left behind'
OUT=$(native_import "$TMP/fake.woff" "fake.woff")
printf '%s\n' "$OUT" | grep -q '"status":"error"' || fail "fake web font imported: $OUT"
grep -q 'woff|woff2' "$ROOT/common/native_import.sh" || fail 'native import dispatcher lacks woff/woff2'

# 5. ZIP: nested web fonts are extracted, converted and grouped; resource forks are ignored and a
#    same-stem TTF wins over its WOFF copy.
python3 - "$FONT" "$TMP/zip-src" "$HAVE_BROTLI" <<'PY'
import os, sys
from fontTools.ttLib import TTFont
src, out, have_brotli = sys.argv[1], sys.argv[2], sys.argv[3] == "true"
os.makedirs(os.path.join(out, "web", "fonts"), exist_ok=True)
def variant(weight, flavor, path):
    font = TTFont(src)
    font["OS/2"].usWeightClass = weight
    font.flavor = flavor
    font.save(path)
variant(400, "woff2" if have_brotli else "woff", os.path.join(out, "web", "fonts", "Zippy-Regular." + ("woff2" if have_brotli else "woff")))
variant(700, "woff", os.path.join(out, "web", "fonts", "Zippy-Bold.woff"))
variant(300, None, os.path.join(out, "Zippy-Light.ttf"))
variant(300, "woff", os.path.join(out, "Zippy-Light.woff"))
PY
mkdir -p "$TMP/public/import" "$TMP/cache"
(cd "$TMP/zip-src" && python3 - "$TMP/public/import/webfonts.zip" <<'PY'
import os, sys, zipfile
with zipfile.ZipFile(sys.argv[1], "w", zipfile.ZIP_DEFLATED) as z:
    for base, _, files in os.walk("."):
        for name in files:
            z.write(os.path.join(base, name), os.path.relpath(os.path.join(base, name), "."))
    z.writestr("__MACOSX/web/fonts/._Zippy-Bold.woff", b"\0" * 5000)
    z.writestr("README.txt", "not a font")
PY
)
zip_import() {
    sh -c '
        set -eu
        MODDIR="$1"; MODULE_DIR="$1"; CONFIG_DIR="$2/config"
        LUOSHU_PUBLIC_DIR="$2/public"; USER_FONTS_DIR="$2/public/fonts-zip"
        USER_IMPORT_DIR="$2/public/import"; IMPORT_CACHE_DIR="$2/cache"
        LUOSHU_IMPORT_PYTHON=python3; LUOSHU_WOFF2_FORCE_NATIVE=1
        export LUOSHU_IMPORT_PYTHON LUOSHU_WOFF2_FORCE_NATIVE
        json_escape() { printf "%s" "$1" | sed "s/\\\\/\\\\\\\\/g; s/\"/\\\\\"/g" | tr "\n\r" "  "; }
        . "$1/common/util_functions.sh"
        . "$1/common/font_check.sh"
        . "$1/common/font_import.sh"
        . "$1/common/font_import_compat.sh"
        import_zip_package "$3"
    ' sh "$ROOT" "$TMP" "$1"
}
if command -v unzip >/dev/null 2>&1 || command -v busybox >/dev/null 2>&1; then
    mkdir -p "$TMP/public/fonts-zip"
    OUT=$(zip_import webfonts.zip)
    printf '%s\n' "$OUT" | grep -q '"status":"ok"' || fail "web font ZIP import failed: $OUT"
    printf '%s\n' "$OUT" | grep -q '"mode":"family"' || fail "web font ZIP was not grouped as a family: $OUT"
    printf '%s\n' "$OUT" | grep -q '"importedText":3' || fail "expected Light/Regular/Bold: $OUT"
    printf '%s\n' "$OUT" | grep -q '"ignored":1' || fail "same-stem WOFF copy should be ignored: $OUT"
    printf '%s\n' "$OUT" | grep -q '"invalid":0' || fail "resource fork or README counted as a font: $OUT"
    ! ls "$TMP/public/fonts-zip" | grep -qi 'woff' || fail 'web font container copied into the library'
    [ -z "$(ls -A "$TMP/cache")" ] || fail 'ZIP scratch directory left behind'

    # Traversal entries are refused outright instead of being flattened by unzip -j.
    python3 - "$FONT" "$TMP/public/import/evil.zip" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[2], "w") as z:
    z.write(sys.argv[1], "fonts/Good.ttf")
    z.write(sys.argv[1], "../../escape.ttf")
PY
    OUT=$(zip_import evil.zip)
    printf '%s\n' "$OUT" | grep -q '字体包解压被拒绝：ZIP 条目包含不安全路径' || fail "traversal ZIP not refused: $OUT"
    test ! -e "$TMP/escape.ttf" && test ! -e "$TMP/public/escape.ttf" || fail 'traversal entry escaped'
else
    echo 'web font import test: unzip unavailable, ZIP bridge cases skipped'
fi

# 6. Extractor unit checks.
EXTRACT="$ROOT/common/font_zip_extract.py"
python3 - "$FONT" "$TMP/x" <<'PY'
import os, stat, sys, zipfile
font, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
with zipfile.ZipFile(os.path.join(out, "link.zip"), "w") as z:
    info = zipfile.ZipInfo("evil.ttf")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    z.writestr(info, "/etc/passwd")
with zipfile.ZipFile(os.path.join(out, "abs.zip"), "w") as z:
    # ZipFile.write() strips a leading slash; a hostile archive can still carry one.
    z.writestr(zipfile.ZipInfo("/tmp/abs.ttf"), open(font, "rb").read())
with zipfile.ZipFile(os.path.join(out, "bomb.zip"), "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("Big.ttf", b"\0" * (4 * 1024 * 1024))
with zipfile.ZipFile(os.path.join(out, "none.zip"), "w") as z:
    z.writestr("readme.md", "x")
with zipfile.ZipFile(os.path.join(out, "dupe.zip"), "w") as z:
    z.write(font, "a/Same.ttf")
    z.write(font, "b/Same.ttf")
    z.write(font, "c/Same.WOFF2")
PY
expect_reject() {
    _dest="$TMP/x/out-$1"
    if python3 "$EXTRACT" "$TMP/x/$1.zip" "$_dest" 128 "${3:-536870912}" 2>"$TMP/x/err"; then
        fail "$1.zip should be rejected"
    fi
    grep -q "$2" "$TMP/x/err" || fail "$1.zip: unexpected error $(cat "$TMP/x/err")"
    [ -z "$(ls -A "$_dest" 2>/dev/null)" ] || fail "$1.zip left files behind"
}
expect_reject link '符号链接'
expect_reject abs '绝对路径'
expect_reject bomb '超过' 1048576
expect_reject none 'WOFF2 字体'
COUNT=$(python3 "$EXTRACT" "$TMP/x/dupe.zip" "$TMP/x/out-dupe" 128 536870912)
[ "$COUNT" = 3 ] || fail "dupe.zip extracted $COUNT files"
[ "$(ls "$TMP/x/out-dupe" | wc -l | tr -d ' ')" = 3 ] || fail 'duplicate names were overwritten'

echo 'Web font (WOFF/WOFF2) and font ZIP import tests passed.'
