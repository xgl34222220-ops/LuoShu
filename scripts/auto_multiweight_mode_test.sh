#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP="${TMPDIR:-/tmp}/luoshu-auto-weight-test.$$"
trap 'rm -rf "$TMP"' EXIT INT TERM
mkdir -p "$TMP/fonts"
: > "$TMP/fonts/Family-Regular.ttf"
: > "$TMP/fonts/Family-Bold.ttf"
: > "$TMP/fonts/Single-Regular.ttf"

USER_FONTS_DIR="$TMP/fonts"
MODDIR="$ROOT"
detect_font_family() {
  _name=${1%.*}
  printf '%s\n' "${_name%-*}"
}
detect_font_weight() {
  case "$1" in *-Bold.*) echo bold ;; *) echo regular ;; esac
}
is_variable_font() { return 1; }
scan_family_weights() {
  case "$1" in Family) echo regular,bold ;; Single) echo regular ;; *) echo '' ;; esac
}
. "$ROOT/common/mix_weight_mode.sh"

[ "$(infer_mix_weight_mode Family wght=400)" = auto ]
[ "$(infer_mix_weight_mode Family wght=700)" = fixed ]
[ "$(infer_mix_weight_mode Single wght=400)" = fixed ]
[ "$(mix_axis_weight 'wdth=95,wght=400')" = 400 ]
[ "$(mix_static_default_weight Family)" = 400 ]

echo 'Automatic multiweight mode tests passed.'
