#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-provenance)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/module"
PUB="$TMP/public"
mkdir -p "$MOD/common/legacy_v14_4" "$MOD/config" "$PUB/fonts"
cp "$ROOT/common/font_provenance.sh" "$MOD/common/font_provenance.sh"
printf 'engine-one\n' > "$MOD/common/engine-marker.py"
printf 'legacy-one\n' > "$MOD/common/legacy_v14_4/legacy-marker.sh"
printf '{"schema":"device-font-inventory-v1"}\n' > "$MOD/config/device_font_inventory.json"
printf 'system\n' > "$MOD/config/device_font_partitions.conf"
printf 'product|vivo/fonts|product-nested-fixture\n' > "$MOD/config/device_font_roots.conf"
printf 'AAAA\n' > "$PUB/fonts/Demo-Regular.ttf"
printf 'CJK-A\n' > "$PUB/fonts/CJK-Regular.ttf"
printf 'LAT-A\n' > "$PUB/fonts/Latin-Regular.ttf"
printf 'DIG-A\n' > "$PUB/fonts/Digit-Regular.ttf"

MODDIR="$MOD"
MODULE_DIR="$MOD"
LUOSHU_PUBLIC_DIR="$PUB"
export MODDIR MODULE_DIR LUOSHU_PUBLIC_DIR
. "$MOD/common/font_provenance.sh"

S1=$(luoshu_provenance_source_signature "$PUB/fonts/Demo-Regular.ttf")
printf 'BBBB\n' > "$PUB/fonts/Demo-Regular.ttf"
S2=$(luoshu_provenance_source_signature "$PUB/fonts/Demo-Regular.ttf")
[ "$S1" != "$S2" ] || { echo 'same-size source byte change did not change provenance' >&2; exit 1; }

printf 'AAAA\n' > "$PUB/fonts/Demo-Regular.ttf"
F1=$(luoshu_provenance_family_signature Demo "$PUB/fonts")
printf 'AAAA-bold\n' > "$PUB/fonts/Demo-Bold.ttf"
F2=$(luoshu_provenance_family_signature Demo "$PUB/fonts")
[ "$F1" != "$F2" ] || { echo 'family member change did not invalidate family signature' >&2; exit 1; }

E1=$(luoshu_provenance_engine_identity)
printf 'engine-two\n' > "$MOD/common/engine-marker.py"
E2=$(luoshu_provenance_engine_identity)
[ "$E1" != "$E2" ] || { echo 'engine change did not invalidate provenance' >&2; exit 1; }
printf 'engine-one\n' > "$MOD/common/engine-marker.py"

I1=$(luoshu_provenance_inventory_identity)
printf 'system\nproduct\n' > "$MOD/config/device_font_partitions.conf"
I2=$(luoshu_provenance_inventory_identity)
[ "$I1" != "$I2" ] || { echo 'partition inventory change did not invalidate provenance' >&2; exit 1; }
printf 'system\n' > "$MOD/config/device_font_partitions.conf"

R1=$(luoshu_provenance_inventory_identity)
printf 'product|vivo/fonts|product-nested-changed\n' > "$MOD/config/device_font_roots.conf"
R2=$(luoshu_provenance_inventory_identity)
[ "$R1" != "$R2" ] || { echo 'nested font root change did not invalidate provenance' >&2; exit 1; }
printf 'product|vivo/fonts|product-nested-fixture\n' > "$MOD/config/device_font_roots.conf"

D1=$(luoshu_provenance_direct_proof "$PUB/fonts/Demo-Regular.ttf" Demo)
printf 'CCCC\n' > "$PUB/fonts/Demo-Regular.ttf"
D2=$(luoshu_provenance_direct_proof "$PUB/fonts/Demo-Regular.ttf" Demo)
[ "$D1" != "$D2" ] || { echo 'direct proof ignored source content' >&2; exit 1; }

M1=$(luoshu_provenance_mix_proof CJK Latin Digit wght=400 wght=500 wght=600 fixed auto fixed "$PUB/fonts")
printf 'LAT-B\n' > "$PUB/fonts/Latin-Regular.ttf"
M2=$(luoshu_provenance_mix_proof CJK Latin Digit wght=400 wght=500 wght=600 fixed auto fixed "$PUB/fonts")
[ "$M1" != "$M2" ] || { echo 'mix proof ignored selected family bytes' >&2; exit 1; }

# Cache keys must carry engine provenance; old cache namespaces are never reused.
grep -Fq 'COMPOSITE_CACHE="$CACHE_ROOT/composites-v10"' "$ROOT/common/multiweight_mix_task.sh"
grep -Fq 'PREPARED_CACHE="$CACHE_ROOT/prepared-v9"' "$ROOT/common/multiweight_mix_task.sh"
grep -Fq 'SOURCE_META_CACHE="$CACHE_ROOT/source-meta-v2"' "$ROOT/common/multiweight_mix_task.sh"
grep -q 'instance-v5-provenance' "$ROOT/common/multiweight_mix_task.sh"
grep -q 'auto-multiweight-v6-provenance' "$ROOT/common/multiweight_mix_task.sh"
grep -q 'MIX_ENGINE_IDENTITY' "$ROOT/common/multiweight_mix_task.sh"

grep -Fq 'COMPOSITE_CACHE="$CACHE_ROOT/composites-v4"' "$ROOT/common/legacy_v14_4/v143_auto_multiweight_mix.sh"
grep -q 'auto-multiweight-v4-provenance' "$ROOT/common/legacy_v14_4/v143_auto_multiweight_mix.sh"
grep -q 'font_provenance.sh' "$ROOT/common/legacy_v14_4/v143_auto_multiweight_mix.sh"
grep -q 'font_provenance.sh' "$ROOT/common/legacy_v14_4/v142_weighted_mix.sh"

grep -q 'router_verified_noop' "$ROOT/common/font_manager.sh"
grep -q 'directProof=' "$ROOT/common/legacy_v14_4/font_switch_safe.sh"
grep -q 'directProof=' "$ROOT/common/next_boot_payload.sh"
grep -q 'mixProof' "$ROOT/common/font_active_state.sh"

# The compatibility runtime must expose scanner-discovered partitions and proof helper.
test "$(grep -F -c 'luoshu_payload_partitions "$REALMOD"' "$ROOT/common/legacy_v14_4/mix_router.sh")" -ge 2
grep -Fq 'font_provenance.sh" "$RUNTIME/common/font_provenance.sh' "$ROOT/common/legacy_v14_4/mix_router.sh"

sh -n "$ROOT/common/font_provenance.sh"
sh -n "$ROOT/common/weighted_mix_task.sh"
sh -n "$ROOT/common/multiweight_mix_task.sh"
sh -n "$ROOT/common/legacy_v14_4/v142_weighted_mix.sh"
sh -n "$ROOT/common/legacy_v14_4/v143_auto_multiweight_mix.sh"
sh -n "$ROOT/common/legacy_v14_4/mix_router.sh"
echo 'Font provenance, active reuse and composite cache invalidation checks passed.'
