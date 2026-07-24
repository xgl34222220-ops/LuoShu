#!/bin/sh
set -e

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export MODDIR="$TMP/module"
export MODULE_DIR="$MODDIR"
mkdir -p "$MODDIR/common" "$MODDIR/config" "$MODDIR/system/fonts"

# Runtime files intentionally use permissive Android sh semantics. Re-enable errexit after
# sourcing so every assertion below remains a hard test failure.
. "$ROOT/common/device_font_payload_policy.sh"
set -e

IS_HYPEROS=true
IS_COLOROS=false
export IS_HYPEROS IS_COLOROS

# A quick switch must never enter any of the old expensive paths.
copy_as_hyperos() { touch "$TMP/called-copy-as-hyperos"; return 99; }
_hyperos_compact_normalize() { touch "$TMP/called-normalize"; return 99; }
_hyperos_materialize_variable_weight() { touch "$TMP/called-instance"; return 99; }
_hyperos_weight_anchor() { touch "$TMP/called-weight-anchor"; return 99; }
font_config_enable_for_payload() { return 0; }
get_all_hyperos_files() { printf '%s\n' 'MiSansVF.ttf 100.ttf 400.ttf 700.ttf Roboto-Regular.ttf GoogleSansText-Regular.ttf'; }

SOURCE="$TMP/Single-Regular.ttf"
dd if=/dev/zero of="$SOURCE" bs=1M count=4 status=none
printf 'OTTO' | dd of="$SOURCE" conv=notrunc status=none

apply_font_by_rom "$SOURCE" "$MODDIR/system/fonts" quick Single

for marker in called-copy-as-hyperos called-normalize called-instance called-weight-anchor; do
    test ! -e "$TMP/$marker"
done

ANCHOR="$MODDIR/system/fonts/.luoshu-font-store/regular.font"
test -s "$ANCHOR"
anchor_inode="$(stat -c '%d:%i' "$ANCHOR")"
for weight in 100 200 300 400 500 600 700 800 900; do
    for prefix in LuoShu LuoShuMono; do
        file="$MODDIR/system/fonts/${prefix}-${weight}.ttf"
        test -s "$file"
        test "$(stat -c '%d:%i' "$file")" = "$anchor_inode"
    done
done

echo 'device_font_foreground_quick_test: PASS'
