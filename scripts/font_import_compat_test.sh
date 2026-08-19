#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/scripts/assert.sh"

MODULE_DIR="$ROOT"
LUOSHU_PUBLIC_DIR="${TMPDIR:-/tmp}/luoshu-font-import-compat-$$"
USER_FONTS_DIR="$LUOSHU_PUBLIC_DIR/fonts"
mkdir -p "$USER_FONTS_DIR"
trap 'rm -rf "$LUOSHU_PUBLIC_DIR"' EXIT HUP INT TERM

. "$ROOT/common/util_functions.sh"
. "$ROOT/common/font_import.sh"
. "$ROOT/common/font_import_compat.sh"

CASE='导入家族名归一'
eq "$(import_detect_family 'RobotoFake-BlackItalic.ttf')" RobotoFake
eq "$(import_detect_family 'RobotoFake-Italic-Black.ttf')" RobotoFake
eq "$(import_detect_family 'RobotoFake-Black-Italic.ttf')" RobotoFake
eq "$(import_detect_family 'RobotoFake_Italic_Black.ttf')" RobotoFake
eq "$(import_detect_family 'RobotoFake-Thin.ttf')" RobotoFake
# A family with no weight hint must be left alone rather than eaten by the style stripper.
eq "$(import_detect_family 'SourceHanSans.ttf')" SourceHanSans
CASE='导入字重标签'
_italic=italic
eq "$(import_weight_label black)" Italic-Black
_italic=false
eq "$(import_weight_label thin)" Thin
# The compat layer deliberately disables name-based italic detection: italic is carried inside the
# weight label (Italic-Black) so detect_font_family still folds it into the upright family.
no import_is_italic_name 'RobotoFake-BlackItalic.ttf'

echo 'Font import compatibility helper smoke checks passed.'
