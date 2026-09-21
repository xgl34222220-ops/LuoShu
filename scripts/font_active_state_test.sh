#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-active-state)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/module"
CFG="$MOD/config"
PUB="$TMP/public"
mkdir -p "$CFG" "$MOD/common" "$PUB/fonts"

for file in font_active_state.sh font_provenance.sh util_functions.sh util_functions_core.sh; do
    cp "$ROOT/common/$file" "$MOD/common/$file"
done
printf 'engine-v1\n' > "$MOD/common/provenance-engine-marker.py"
printf '{"schema":"device-font-inventory-v1","state":"ready"}\n' > "$CFG/device_font_inventory.json"
printf 'system\n' > "$CFG/device_font_partitions.conf"
printf 'demo-source-A\n' > "$PUB/fonts/Demo-Regular.ttf"

MODDIR="$MOD"
MODULE_DIR="$MOD"
LUOSHU_PUBLIC_DIR="$PUB"
export MODDIR MODULE_DIR LUOSHU_PUBLIC_DIR
. "$MOD/common/util_functions.sh"
. "$MOD/common/font_provenance.sh"
. "$MOD/common/font_active_state.sh"

write_direct_proof() {
    _proof=$(luoshu_provenance_direct_proof "$PUB/fonts/Demo-Regular.ttf" Demo)
    cat > "$CFG/font-payload-activated.conf" <<EOF_PROOF
font=Demo
provenanceSchema=font-provenance-v1
proofKind=direct
directProof=$_proof
EOF_PROOF
}

printf 'Demo\n' > "$CFG/active_font.conf"
printf 'state=confirmed\nfont=Demo\n' > "$CFG/font-payload-boot.conf"
printf 'system/fonts/Demo.ttf|hash|1234\n' > "$CFG/font-payload-manifest.conf"
printf 'state=verified\nmode=mount-confirmed\nactiveFont=Demo\n' > "$CFG/device-font-load-verification.conf"
printf 'state=mounted\n' > "$CFG/self-mount.conf"
write_direct_proof

luoshu_active_payload_verified Demo "$PUB/fonts/Demo-Regular.ttf"
if luoshu_active_payload_verified Demo; then
    echo 'direct payload reused without a source proof input' >&2
    exit 1
fi
if luoshu_active_payload_verified Other "$PUB/fonts/Demo-Regular.ttf"; then
    echo 'different font reused verified payload' >&2
    exit 1
fi

DIRECT_RESULT=$(MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PUBLIC_DIR="$PUB"     sh "$ROOT/common/font_manager.sh" action switch Demo)
printf '%s\n' "$DIRECT_RESULT" | grep -q '"status":"ok"'
printf '%s\n' "$DIRECT_RESULT" | grep -q '"font":"Demo"'
printf '%s\n' "$DIRECT_RESULT" | grep -q '"reused":true'
printf '%s\n' "$DIRECT_RESULT" | grep -q '"rebootRequired":false'
test ! -e "$CFG/text_reboot_required.conf"

# Same path/family but different bytes must invalidate a direct no-op.
printf 'demo-source-B\n' > "$PUB/fonts/Demo-Regular.ttf"
if luoshu_active_payload_verified Demo "$PUB/fonts/Demo-Regular.ttf"; then
    echo 'changed direct source bytes reused active payload' >&2
    exit 1
fi
printf 'demo-source-A\n' > "$PUB/fonts/Demo-Regular.ttf"
write_direct_proof

# Engine and inventory changes must invalidate the active proof as well.
printf 'engine-v2\n' > "$MOD/common/provenance-engine-marker.py"
if luoshu_active_payload_verified Demo "$PUB/fonts/Demo-Regular.ttf"; then
    echo 'changed generation engine reused active payload' >&2
    exit 1
fi
printf 'engine-v1\n' > "$MOD/common/provenance-engine-marker.py"
write_direct_proof
printf 'system\nproduct\n' > "$CFG/device_font_partitions.conf"
if luoshu_active_payload_verified Demo "$PUB/fonts/Demo-Regular.ttf"; then
    echo 'changed inventory reused active payload' >&2
    exit 1
fi
printf 'system\n' > "$CFG/device_font_partitions.conf"
write_direct_proof

printf 'state=awaiting-explicit-apply\n' > "$CFG/font-payload-rebuild-pending.conf"
if luoshu_active_payload_verified Demo "$PUB/fonts/Demo-Regular.ttf"; then
    echo 'schema rebuild marker was ignored' >&2
    exit 1
fi
rm -f "$CFG/font-payload-rebuild-pending.conf"

printf 'font=Demo\n' > "$CFG/text_reboot_required.conf"
if luoshu_active_payload_verified Demo "$PUB/fonts/Demo-Regular.ttf"; then
    echo 'same-boot reboot marker was ignored' >&2
    exit 1
fi
rm -f "$CFG/text_reboot_required.conf"

# Composite reuse is bound to all selected family bytes plus axes/modes/engine/inventory.
printf 'cjk-A\n' > "$PUB/fonts/CJK-Regular.ttf"
printf 'latin-A\n' > "$PUB/fonts/Latin-Regular.ttf"
printf 'digit-A\n' > "$PUB/fonts/Digit-Regular.ttf"
printf 'mix\n' > "$CFG/active_font.conf"
printf 'state=confirmed\nfont=mix\n' > "$CFG/font-payload-boot.conf"
printf 'state=verified\nmode=mount-confirmed\nactiveFont=mix\n' > "$CFG/device-font-load-verification.conf"
cat > "$CFG/font_mix.conf" <<'EOF_MIX'
cjk=CJK
latin=Latin
digit=Digit
cjkWeight=400
latinWeight=500
digitWeight=600
cjkAxes=wght=400
latinAxes=wght=500
digitAxes=wght=600
cjkMode=fixed
latinMode=auto
digitMode=fixed
EOF_MIX
MIX_PROOF=$(luoshu_provenance_mix_proof CJK Latin Digit wght=400 wght=500 wght=600 fixed auto fixed "$PUB/fonts")
printf 'provenanceSchema=font-provenance-v1\nmixProof=%s\n' "$MIX_PROOF" >> "$CFG/font_mix.conf"
cp "$CFG/font_mix.conf" "$CFG/axes_mix.conf"

luoshu_mix_request_matches_active CJK Latin Digit wght=400 wght=500 wght=600 fixed auto fixed
printf 'latin-B\n' > "$PUB/fonts/Latin-Regular.ttf"
if luoshu_mix_request_matches_active CJK Latin Digit wght=400 wght=500 wght=600 fixed auto fixed; then
    echo 'changed Latin source reused active composite' >&2
    exit 1
fi
printf 'latin-A\n' > "$PUB/fonts/Latin-Regular.ttf"
MIX_PROOF=$(luoshu_provenance_mix_proof CJK Latin Digit wght=400 wght=500 wght=600 fixed auto fixed "$PUB/fonts")
sed -i "s/^mixProof=.*/mixProof=$MIX_PROOF/" "$CFG/font_mix.conf"
cp "$CFG/font_mix.conf" "$CFG/axes_mix.conf"

AUTO_RESULT=$(MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PUBLIC_DIR="$PUB"     sh "$ROOT/common/multiweight_mix_task.sh" start CJK Latin Digit         wght=400 wght=500 wght=600 fixed auto fixed)
printf '%s\n' "$AUTO_RESULT" | grep -q '"reused":true'
grep -q '^state=success$' "$CFG/axes_task.conf"
grep -q '^percent=100$' "$CFG/axes_task.conf"
grep -q '^reused=true$' "$CFG/axes_task.conf"
AUTO_STATUS=$(MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PUBLIC_DIR="$PUB"     sh "$ROOT/common/weighted_mix_task.sh" status "$(sed -n 's/^task=//p' "$CFG/axes_task.conf")")
printf '%s\n' "$AUTO_STATUS" | grep -q '"reused":true'
test ! -e "$CFG/text_reboot_required.conf"

sed -i 's/^latinMode=auto$/latinMode=fixed/' "$CFG/font_mix.conf"
FIXED_PROOF=$(luoshu_provenance_mix_proof CJK Latin Digit wght=400 wght=500 wght=600 fixed fixed fixed "$PUB/fonts")
sed -i "s/^mixProof=.*/mixProof=$FIXED_PROOF/" "$CFG/font_mix.conf"
cp "$CFG/font_mix.conf" "$CFG/axes_mix.conf"
FIXED_RESULT=$(MODDIR="$MOD" MODULE_DIR="$MOD" LUOSHU_PUBLIC_DIR="$PUB"     sh "$ROOT/common/weighted_mix_task.sh" start CJK Latin Digit wght=400 wght=500 wght=600)
printf '%s\n' "$FIXED_RESULT" | grep -q '"reused":true'
grep -q '^state=success$' "$CFG/axes_task.conf"
grep -q '^reused=true$' "$CFG/axes_task.conf"
test ! -e "$CFG/text_reboot_required.conf"

sh -n "$ROOT/common/font_active_state.sh"
sh -n "$ROOT/common/font_provenance.sh"
sh -n "$ROOT/common/font_manager.sh"
echo 'Verified active reuse is bound to source bytes, inventory and generation engine.'
