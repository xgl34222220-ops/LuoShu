#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP="${TMPDIR:-/tmp}/luoshu-auto-weight-test.$$"
trap 'rm -rf "$TMP"' EXIT INT TERM
mkdir -p "$TMP/fonts"
: > "$TMP/fonts/Family-Regular.ttf"
: > "$TMP/fonts/Family-Bold.ttf"
: > "$TMP/fonts/Single-Regular.ttf"
: > "$TMP/fonts/Variable.ttf"

USER_FONTS_DIR="$TMP/fonts"
MODDIR="$ROOT"
detect_font_family() {
  _name=${1%.*}
  case "$_name" in Variable) echo Variable ;; *) printf '%s\n' "${_name%-*}" ;; esac
}
detect_font_weight() {
  case "$1" in *-Bold.*) echo bold ;; *) echo regular ;; esac
}
is_variable_font() { case "$1" in *Variable.ttf) return 0 ;; *) return 1 ;; esac; }
scan_family_weights() {
  case "$1" in Family) echo regular,bold ;; Single) echo regular ;; *) echo '' ;; esac
}
. "$ROOT/common/mix_weight_mode.sh"
# 单元测试不解析真实 fvar，仅固定模拟默认轴位置。
mix_variable_default_weight() { echo 400; }

# 静态多字重默认走当前所选字重的快速组合，不再静默生成九档字体。
[ "$(infer_mix_weight_mode Family wght=400)" = fixed ]
[ "$(infer_mix_weight_mode Family wght=700)" = fixed ]
[ "$(infer_mix_weight_mode Single wght=400)" = fixed ]
# 真正的可变字体在默认轴位置仍可使用自动多字重引擎。
[ "$(infer_mix_weight_mode Variable wght=400)" = auto ]
[ "$(infer_mix_weight_mode Variable wght=500)" = fixed ]
[ "$(mix_axis_weight 'wdth=95,wght=400')" = 400 ]
[ "$(mix_static_default_weight Family)" = 400 ]

echo 'Automatic multiweight mode tests passed.'
