#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ENGINE="$ROOT/common/legacy_v14_4/v143_auto_multiweight_mix.sh"
BRIDGE="$ROOT/common/legacy_v14_4/v14_mix.sh"
MODE="$ROOT/common/legacy_v14_4/mix_weight_mode.sh"

test -f "$ENGINE"
test -f "$MODE"
sh -n "$ENGINE"
sh -n "$BRIDGE"
sh -n "$MODE"

grep -q 'for _weight in \$_weights' "$ENGINE"
grep -q 'build_composite_cached' "$ENGINE"
# The production engine caches complete composites by immutable input hashes.
# The real worker/source/cache behavior is exercised by mix_inventory_source_test.py.
grep -q 'auto-multiweight-v4-provenance' "$ENGINE"
grep -q 'MIX_ENGINE_IDENTITY' "$ENGINE"
grep -q 'prepare_source() (' "$ENGINE"
grep -q 'build_composite_cached() (' "$ENGINE"
grep -q '_family=LuoShuAutoMix' "$ENGINE"
grep -q 'Regular.ttf' "$ENGINE"
grep -q '\${_family}-\${_role}.otf' "$ENGINE"
grep -q 'cjkMode=%s' "$ENGINE"
grep -q 'stage_auto_sources "$_root"' "$ENGINE"
grep -q 'write_auto_source_weights' "$ENGINE"
grep -q 'prepare_compat_payload' "$ENGINE"
! grep -q 'action switch' "$ENGINE"
! grep -qE 'rom_adapters|IS_HYPEROS|IS_COLOROS' "$ENGINE"
grep -q 'v143_auto_multiweight_mix.sh' "$BRIDGE"
grep -q 'infer_mix_weight_mode' "$BRIDGE"
grep -q 'AUTO_WEIGHTED.*status' "$BRIDGE"
grep -q 'AUTO_WEIGHTED.*recover' "$BRIDGE"

echo 'Automatic multiweight engine contract passed.'
