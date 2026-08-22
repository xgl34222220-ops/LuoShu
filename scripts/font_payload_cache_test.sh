#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/module"
LIB="$TMP/fonts"
mkdir -p "$MOD/common" "$MOD/system/fonts" "$MOD/config" "$LIB"
cp -f "$ROOT/common/font_config_weights.sh" "$MOD/common/font_config_weights.sh"

SRC="$LIB/Demo-Regular.ttf"
dd if=/dev/zero of="$SRC" bs=2048 count=1 2>/dev/null
printf 'demo-font-v1\n' >> "$SRC"

export MODDIR="$MOD"
export MODULE_DIR="$MOD"
export CONFIG_DIR="$MOD/config"
export USER_FONTS_DIR="$LIB"

get_weight_file() { printf '%s\n' "$SRC"; }
_font_source_digest() { sha256sum "$1" | awk '{print $1}'; }
. "$MOD/common/font_config_weights.sh"
set -eu

# Host test substitutes cheap builders; the cache contract must not depend on FontTools.
_luoshu_config_normalize_weight() { cp -f "$1" "$2"; }
_luoshu_config_make_mono_weight() { cp -f "$1" "$2"; }

KEY1=$(_luoshu_config_weight_cache_key Demo "$SRC")
font_config_prewarm_payload_weights Demo "$SRC"
CACHE=$(_luoshu_config_weight_cache_dir "$KEY1")
_luoshu_config_weight_cache_valid "$CACHE"

# Mono aliases share one cached inode instead of serializing the same outlines nine times.
MONO_INODE=$(stat -c '%i' "$CACHE/LuoShuMono-400.ttf")
for weight in 100 200 300 500 600 700 800 900; do
    test "$(stat -c '%i' "$CACHE/LuoShuMono-${weight}.ttf")" = "$MONO_INODE"
done

# Prewarm is side-effect free for the currently active payload.
test ! -e "$MOD/system/fonts/LuoShu-400.ttf"
test ! -e "$MOD/system/fonts/LuoShuMono-400.ttf"

MARKER="$TMP/generator-called"
_luoshu_config_normalize_weight() { printf 'called\n' >> "$MARKER"; return 99; }
_luoshu_config_make_mono_weight() { printf 'called\n' >> "$MARKER"; return 99; }
font_config_prepare_payload_weights Demo "$SRC"
test ! -e "$MARKER"

for weight in 100 200 300 400 500 600 700 800 900; do
    test -s "$MOD/system/fonts/LuoShu-${weight}.ttf"
    test -s "$MOD/system/fonts/LuoShuMono-${weight}.ttf"
done

# Changing source bytes must invalidate the complete payload key.
printf 'changed\n' >> "$SRC"
KEY2=$(_luoshu_config_weight_cache_key Demo "$SRC")
test "$KEY1" != "$KEY2"

printf 'Font payload cache tests passed.\n'
