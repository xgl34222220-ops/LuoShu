#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-variable-weights)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MODULE="$TMP/module"
mkdir -p "$MODULE/common" "$MODULE/system/fonts" "$MODULE/config"
cp "$ROOT/common/font_config_weights.sh" "$MODULE/common/font_config_weights.sh"
printf 'variable-source-%05000d' 1 > "$TMP/source.ttf"
: > "$TMP/calls"
MODULE_DIR="$MODULE"
is_variable_font() { return 0; }
_luoshu_font_config_exec() {
    script="$1"; shift
    printf '%s %s\n' "${script##*/}" "$*" >> "$TMP/calls"
    input=''; output=''
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --input) input="$2"; shift 2 ;;
            --output) output="$2"; shift 2 ;;
            *) shift ;;
        esac
    done
    cp -f "$input" "$output"
}
. "$MODULE/common/font_config_weights.sh"
_luoshu_config_normalize_weight "$TMP/source.ttf" "$TMP/LuoShu-700.ttf" 700
test -s "$TMP/LuoShu-700.ttf"
grep -q 'font_instance.py .*--role cjk .*--weight 700 .*--axes wght=700' "$TMP/calls"
grep -q 'font_name_normalize.py .*--weight 700' "$TMP/calls"
echo 'Variable direct-apply weight materialization passed.'
