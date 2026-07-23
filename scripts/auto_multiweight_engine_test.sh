#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ENGINE="$ROOT/common/multiweight_mix_task.sh"
BRIDGE="$ROOT/common/font_mix_controller.sh"
MODE="$ROOT/common/mix_weight_mode.sh"

test -f "$ENGINE"
test -f "$MODE"
sh -n "$ENGINE"
sh -n "$BRIDGE"
sh -n "$MODE"

grep -q 'for _weight in 100 200 300 400 500 600 700 800 900' "$ENGINE"
grep -q 'build_composite_cached' "$ENGINE"
grep -q 'source_metadata' "$ENGINE"
grep -q 'prepared-v6' "$ENGINE"
grep -q '\.source-key' "$ENGINE"
grep -q '_cjk_key.*_latin_key.*_digit_key' "$ENGINE"
grep -q '_family=LuoShuAutoMix' "$ENGINE"
grep -q 'Regular.ttf' "$ENGINE"
grep -q '\${_family}-\${_role}.otf' "$ENGINE"
grep -q 'cjkMode=%s' "$ENGINE"
grep -q 'LUOSHU_PUBLIC_DIR=.*FONT_MANAGER.*action switch' "$ENGINE"
grep -q 'multiweight_mix_task.sh' "$BRIDGE"
grep -q 'infer_mix_weight_mode' "$BRIDGE"
grep -q 'AUTO_WEIGHTED.*status' "$BRIDGE"
grep -q 'AUTO_WEIGHTED.*recover' "$BRIDGE"

echo 'Automatic multiweight engine contract passed.'
