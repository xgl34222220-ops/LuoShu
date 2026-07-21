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

printf 'Font configuration weight safety tests passed.\n'
