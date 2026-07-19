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
cp -f "$FONT" "$TMP/pkg/Regression-Regular.ttf"
cat > "$TMP/pkg/module.prop" <<'PROP'
id=luoshu_zip_regression
name=洛书 ZIP 回归字体
version=1.0
versionCode=1
author=LuoShu CI
PROP
(cd "$TMP/pkg" && zip -q -r "$TMP/public/import/regression.zip" .)

# 回归真机问题：font_check.sh 被 source 时，即使父脚本的位置参数是 ZIP，
# 也只能定义函数，不能把 ZIP 当成 CLI 字体检查后退出父进程。
SOURCE_RESULT=$(sh -c '
    set -- "$1"
    . "$2"
    printf sourced-ok
' sh "$TMP/public/import/regression.zip" "$ROOT/common/font_check.sh")
test "$SOURCE_RESULT" = sourced-ok

# 使用与模块相同的函数装配方式运行安全 ZIP 导入器。
OUTPUT=$(sh -c '
    set -eu
    MODDIR="$1"; MODULE_DIR="$1"; CONFIG_DIR="$2/config"
    LUOSHU_PUBLIC_DIR="$2/public"; USER_FONTS_DIR="$2/public/fonts"
    USER_IMPORT_DIR="$2/public/import"; IMPORT_CACHE_DIR="$2/cache"
    json_escape() {
        printf "%s" "$1" | sed "s/\\\\/\\\\\\\\/g; s/\"/\\\\\"/g" | tr "\n\r" "  "
    }
    . "$1/common/util_functions.sh"
    . "$1/common/font_check.sh"
    . "$1/common/font_import.sh"
    import_zip_package regression.zip
' sh "$ROOT" "$TMP")
printf '%s\n' "$OUTPUT" | grep -q '"status":"ok"'
find "$TMP/public/fonts" -maxdepth 1 -type f \( -iname '*.ttf' -o -iname '*.otf' -o -iname '*.ttc' \) -print -quit | grep -q .
echo 'Native font-module ZIP import regression test passed.'
