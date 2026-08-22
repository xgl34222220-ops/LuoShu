#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/module"
mkdir -p "$MOD/common" "$MOD/system/fonts" "$MOD/config"
cp -f "$ROOT/common/font_config_weights.sh" "$MOD/common/font_config_weights.sh"

export MODDIR="$MOD"
export MODULE_DIR="$MOD"
. "$MOD/common/font_config_weights.sh"
set -eu

# A collection under a .ttf alias is unsafe because the generated XML intentionally removes the
# source ROM's collection index. It must fail before invoking the name normalizer.
TTC="$TMP/collection.ttc"
printf 'ttcf' > "$TTC"
dd if=/dev/zero bs=2048 count=1 >> "$TTC" 2>/dev/null
OUTPUT="$TMP/LuoShu-400.ttf"
if _luoshu_config_normalize_weight "$TTC" "$OUTPUT" 400; then
    echo 'TTC collection unexpectedly entered deterministic XML weights' >&2
    exit 1
fi
test ! -e "$OUTPUT"
test ! -e "$OUTPUT.raw"

# Unchanged inputs must reuse the complete generated payload instead of running the
# expensive 9 UI + 9 monospace Python conversions again. Any source identity change
# must invalidate the key and re-enter preparation.
printf '# engine\n' > "$MOD/common/font_instance.py"
printf '# normalizer\n' > "$MOD/common/font_name_normalize.py"
for weight in 100 200 300 400 500 600 700 800 900; do
    dd if=/dev/zero of="$MOD/system/fonts/${weight}.ttf" bs=2048 count=1 2>/dev/null
    dd if=/dev/zero of="$MOD/system/fonts/LuoShu-${weight}.ttf" bs=2048 count=1 2>/dev/null
    dd if=/dev/zero of="$MOD/system/fonts/LuoShuMono-${weight}.ttf" bs=2048 count=1 2>/dev/null
done
KEY=$(_luoshu_config_weights_key Demo)
test -n "$KEY"
printf '%s\n' "$KEY" > "$MOD/config/font-config-weights.key"
PREP_LOG="$TMP/prepare.log"
GEN_LOG="$TMP/generate.log"
font_config_prepare_payload_weights() { printf 'prepare\n' >> "$PREP_LOG"; return 0; }
font_config_generate() { printf '%s\n' "$1" >> "$GEN_LOG"; return 0; }
font_config_enable_for_payload Demo
! test -s "$PREP_LOG"
grep -qx Demo "$GEN_LOG"

printf 'x' >> "$MOD/system/fonts/400.ttf"
: > "$GEN_LOG"
font_config_enable_for_payload Demo
grep -qx prepare "$PREP_LOG"
grep -qx Demo "$GEN_LOG"
NEW_KEY=$(cat "$MOD/config/font-config-weights.key")
test -n "$NEW_KEY"
test "$NEW_KEY" != "$KEY"

printf 'Font configuration weight safety tests passed.\n'