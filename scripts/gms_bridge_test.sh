#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-gms-test)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MOD="$TMP/LuoShu"
mkdir -p "$MOD/common" "$MOD/config" "$MOD/source"
cp "$ROOT/common/db_engine" "$MOD/common/db_engine"
cp "$ROOT/common/rom_adapters.sh" "$MOD/common/rom_adapters.sh"
cp "$ROOT/common/play_font_bridge" "$MOD/common/play_font_bridge"

for weight in regular medium bold; do
    file="$MOD/source/${weight}.ttf"
    : > "$file"
    while [ "$(wc -c < "$file")" -lt 2048 ]; do
        printf '%s-font-data-0123456789abcdef\n' "$weight" >> "$file"
    done
done

MODDIR="$MOD" MODULE_DIR="$MOD" sh -c '
    . "$MODDIR/common/rom_adapters.sh"
    get_weight_file() {
        case "$2" in
            medium|bold) printf "%s/source/%s.ttf\n" "$MODDIR" "$2" ;;
            *) printf "%s/source/regular.ttf\n" "$MODDIR" ;;
        esac
    }
    _prepare_gms_bridge_sources "$MODDIR/source/regular.ttf" Demo
'

test -s "$MOD/config/gms_bridge/regular.font"
test -s "$MOD/config/gms_bridge/medium.font"
test -s "$MOD/config/gms_bridge/bold.font"
test "$(MODDIR="$MOD" sh "$MOD/common/play_font_bridge" resolve GoogleSans-Regular.ttf)" = "$MOD/config/gms_bridge/regular.font"
test "$(MODDIR="$MOD" sh "$MOD/common/play_font_bridge" resolve GoogleSans-Medium.ttf)" = "$MOD/config/gms_bridge/medium.font"
test "$(MODDIR="$MOD" sh "$MOD/common/play_font_bridge" resolve GoogleSans-Bold.ttf)" = "$MOD/config/gms_bridge/bold.font"

echo "GMS bridge tests passed."
