#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ENGINE="$ROOT/common/v143_auto_multiweight_mix.sh"
BRIDGE="$ROOT/common/v14_mix.sh"
MODE="$ROOT/common/mix_weight_mode.sh"

test -f "$ENGINE"
test -f "$MODE"
sh -n "$ENGINE"
sh -n "$BRIDGE"
sh -n "$MODE"

grep -q 'for _weight in 100 200 300 400 500 600 700 800 900' "$ENGINE"
grep -q 'build_composite_cached' "$ENGINE"
grep -q 'LuoShuAutoMix-.*Regular.ttf' "$ENGINE"
grep -q 'LuoShuAutoMix-.*\.otf' "$ENGINE"
grep -q 'cjkMode=%s' "$ENGINE"
grep -q 'LUOSHU_PUBLIC_DIR=.*FONT_MANAGER.*action switch' "$ENGINE"
grep -q 'v143_auto_multiweight_mix.sh' "$BRIDGE"
grep -q 'infer_mix_weight_mode' "$BRIDGE"
grep -q 'AUTO_WEIGHTED.*status' "$BRIDGE"
grep -q 'AUTO_WEIGHTED.*recover' "$BRIDGE"

echo 'Automatic multiweight engine contract passed.'
