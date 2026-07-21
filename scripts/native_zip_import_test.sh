#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

FONT=$(find /usr/share/fonts -type f -iname 'DejaVuSans.ttf' -print -quit 2>/dev/null || true)
if [ ! -s "$FONT" ]; then
    echo 'Native ZIP import test skipped: DejaVu Sans is unavailable.'
    exit 0
fi
mkdir -p "$TMP/pkg" "$TMP/public/import" "$TMP/public/fonts" "$TMP/cache" "$TMP/config"

# 文件名故意不含任何字重提示；导入器必须读取 OS/2.usWeightClass。
PYTHONPATH="$ROOT/common/python/lib/python3.14/site-packages" python3 -S - "$FONT" "$TMP/pkg/Mystery-A.ttf" 200 <<'PY'
import sys
from fontTools.ttLib import TTFont
font = TTFont(sys.argv[1])
font['OS/2'].usWeightClass = int(sys.argv[3])
font.save(sys.argv[2])
PY
PYTHONPATH="$ROOT/common/python/lib/python3.14/site-packages" python3 -S - "$FONT" "$TMP/pkg/Mystery-B.ttf" 800 <<'PY'
import sys
from fontTools.ttLib import TTFont
font = TTFont(sys.argv[1])
font['OS/2'].usWeightClass = int(sys.argv[3])
font.save(sys.argv[2])
PY

test "$(PYTHONPATH="$ROOT/common/python/lib/python3.14/site-packages" python3 -S "$ROOT/common/font_import_probe.py" "$TMP/pkg/Mystery-A.ttf" | cut -d'|' -f3)" = 200
test "$(PYTHONPATH="$ROOT/common/python/lib/python3.14/site-packages" python3 -S "$ROOT/common/font_import_probe.py" "$TMP/pkg/Mystery-B.ttf" | cut -d'|' -f3)" = 800

cat > "$TMP/pkg/module.prop" <<'PROP'
id=luoshu_zip_regression
name=洛书 ZIP 回归字体
version=1.0
versionCode=1
author=LuoShu CI
PROP
(cd "$TMP/pkg" && zip -q -r "$TMP/public/import/regression.zip" .)

SOURCE_RESULT=$(sh -c '
    zip_path="$1"
    checker="$2"
    set -- "$zip_path"
    . "$checker"
    printf sourced-ok
' sh "$TMP/public/import/regression.zip" "$ROOT/common/font_check.sh")
test "$SOURCE_RESULT" = sourced-ok

# App 的原生导入桥必须直接装配安全 ZIP 导入器，不能再调用不存在的 font_manager action。
grep -q 'common/font_import.sh' "$ROOT/common/native_import.sh"
grep -q 'import_zip_package "$(basename "$_target")"' "$ROOT/common/native_import.sh"
! grep -q 'action import_zip' "$ROOT/common/native_import.sh"

OUTPUT=$(sh -c '
    set -eu
    MODDIR="$1"; MODULE_DIR="$1"; CONFIG_DIR="$2/config"
    LUOSHU_PUBLIC_DIR="$2/public"; USER_FONTS_DIR="$2/public/fonts"
    USER_IMPORT_DIR="$2/public/import"; IMPORT_CACHE_DIR="$2/cache"
    LUOSHU_IMPORT_PYTHON=python3
    PYTHONPATH="$1/common/python/lib/python3.14/site-packages"
    export LUOSHU_IMPORT_PYTHON PYTHONPATH
    json_escape() {
        printf "%s" "$1" | sed "s/\\\\/\\\\\\\\/g; s/\"/\\\\\"/g" | tr "\n\r" "  "
    }
    . "$1/common/util_functions.sh"
    . "$1/common/font_check.sh"
    . "$1/common/font_import.sh"
    import_zip_package regression.zip
' sh "$ROOT" "$TMP")
printf '%s\n' "$OUTPUT" | grep -q '"status":"ok"'
printf '%s\n' "$OUTPUT" | grep -q '"mode":"family"'
printf '%s\n' "$OUTPUT" | grep -q '"importedText":2'
find "$TMP/public/fonts" -maxdepth 1 -type f -name '*-ExtraLight.ttf' -print -quit | grep -q .
find "$TMP/public/fonts" -maxdepth 1 -type f -name '*-ExtraBold.ttf' -print -quit | grep -q .
echo 'Native font-module ZIP import bridge and internal-weight regression test passed.'
