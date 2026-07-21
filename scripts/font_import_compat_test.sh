#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

MODULE_DIR="$ROOT"
LUOSHU_PUBLIC_DIR="${TMPDIR:-/tmp}/luoshu-font-import-compat-$$"
USER_FONTS_DIR="$LUOSHU_PUBLIC_DIR/fonts"
mkdir -p "$USER_FONTS_DIR"
trap 'rm -rf "$LUOSHU_PUBLIC_DIR"' EXIT HUP INT TERM

. "$ROOT/common/util_functions.sh"
. "$ROOT/common/font_import.sh"
. "$ROOT/common/font_import_compat.sh"

test "$(import_detect_family 'RobotoFake-BlackItalic.ttf')" = RobotoFake
test "$(import_detect_family 'RobotoFake-Italic-Black.ttf')" = RobotoFake
test "$(import_detect_family 'RobotoFake-Thin.ttf')" = RobotoFake
_italic=italic
test "$(import_weight_label black)" = Italic-Black
_italic=false
test "$(import_weight_label thin)" = Thin
import_is_italic_name 'RobotoFake-BlackItalic.ttf' && exit 1 || true

echo 'Font import compatibility helper smoke checks passed.'
