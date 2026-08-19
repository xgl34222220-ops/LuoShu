#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/scripts/assert.sh"
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-variable-weights)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MODULE="$TMP/module"
mkdir -p "$MODULE/common" "$MODULE/system/fonts" "$MODULE/config"
cp "$ROOT/common/font_config_weights.sh" "$MODULE/common/font_config_weights.sh"
# _luoshu_config_normalize_weight gates on the presence of these two backends before it will call
# the (stubbed) executor. Without them it silently falls through to `return 1` and the weight is
# never materialized, which is exactly the failure this test is supposed to catch.
touch "$MODULE/common/font_instance.py" "$MODULE/common/font_name_normalize.py"
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
CASE='可变字体九档实例化'
ok _luoshu_config_normalize_weight "$TMP/source.ttf" "$TMP/LuoShu-700.ttf" 700
ok test -s "$TMP/LuoShu-700.ttf"
ok grep -q 'font_instance.py .*--role cjk .*--weight 700 .*--axes wght=700' "$TMP/calls"
ok grep -q 'font_name_normalize.py .*--weight 700' "$TMP/calls"
echo 'Variable direct-apply weight materialization passed.'
