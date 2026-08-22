#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
FONT=$(find /usr/share/fonts -type f -iname 'DejaVuSans.ttf' -print -quit 2>/dev/null || true)
[ -s "$FONT" ] || { echo 'Font import limit test skipped: DejaVu Sans is unavailable.'; exit 0; }

mkdir -p "$TMP/public/import" "$TMP/public/fonts" "$TMP/cache" "$TMP/pkg/a" "$TMP/pkg/b"
cp "$FONT" "$TMP/pkg/a/Same.ttf"
cp "$FONT" "$TMP/pkg/b/Same.ttf"
(cd "$TMP/pkg" && zip -q -r "$TMP/public/import/duplicate.zip" .)

run_import() {
    _name="$1"; _max_font="$2"
    sh -c '
        set -eu
        MODULE_DIR="$1"; LUOSHU_PUBLIC_DIR="$2/public"; USER_FONTS_DIR="$2/public/fonts"
        USER_IMPORT_DIR="$2/public/import"; IMPORT_CACHE_DIR="$2/cache"
        . "$1/common/font_import.sh"
        IMPORT_MAX_FONT_BYTES="$4"
        import_zip_package "$3"
    ' sh "$ROOT" "$TMP" "$_name" "$_max_font"
}

OUTPUT=$(run_import duplicate.zip 268435456)
printf '%s\n' "$OUTPUT" | grep -q '重名字体或解压结果不完整'
test -z "$(find "$TMP/public/fonts" -type f -print -quit)"

rm -rf "$TMP/pkg"; mkdir -p "$TMP/pkg"
cp "$FONT" "$TMP/pkg/Large.ttf"
(cd "$TMP/pkg" && zip -q "$TMP/public/import/oversized.zip" Large.ttf)
OUTPUT=$(run_import oversized.zip 1)
printf '%s\n' "$OUTPUT" | grep -q '解压后的真实内容超过安全限制'
test -z "$(find "$TMP/public/fonts" -type f -print -quit)"

echo 'Post-extraction font import safety limit tests passed.'
