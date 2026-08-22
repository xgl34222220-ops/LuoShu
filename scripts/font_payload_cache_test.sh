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
printf 'demo-font-v1-fvar\n' >> "$SRC"

export MODDIR="$MOD"
export MODULE_DIR="$MOD"
export CONFIG_DIR="$MOD/config"
export USER_FONTS_DIR="$LIB"

get_weight_file() { printf '%s\n' "$SRC"; }
_font_source_digest() { sha256sum "$1" | awk '{print $1}'; }
. "$MOD/common/font_config_weights.sh"
set -eu

# Host test emulates the two batch backends and one Mono normalization call.
# A variable source containing fvar must not start one interpreter per weight.
touch "$MOD/common/font_instance.py" "$MOD/common/font_name_normalize.py"
CALLS="$TMP/backend-calls"
: > "$CALLS"
_luoshu_font_config_exec() {
    _tool="${1##*/}"
    printf '%s %s\n' "$_tool" "${2:-}" >> "$CALLS"
    _jobs=''
    _output=''
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --batch) _jobs="$2"; shift 2 ;;
            --output) _output="$2"; shift 2 ;;
            *) shift ;;
        esac
    done
    if [ -n "$_jobs" ]; then
        while IFS="$(printf '\t')" read -r _input _ready _rest; do
            [ -n "$_ready" ] || continue
            dd if=/dev/zero of="$_ready" bs=2048 count=1 2>/dev/null
        done < "$_jobs"
        return 0
    fi
    if [ -n "$_output" ]; then
        dd if=/dev/zero of="$_output" bs=2048 count=1 2>/dev/null
        return 0
    fi
    return 1
}

KEY1=$(_luoshu_config_weight_cache_key Demo "$SRC")
font_config_prewarm_payload_weights Demo "$SRC"
BACKEND_CALLS=$(awk 'NF' "$CALLS" | wc -l | tr -d '[:space:]')
[ "$BACKEND_CALLS" -le 3 ] || { echo "prewarm backend calls=$BACKEND_CALLS, expected <=3" >&2; exit 1; }
grep -q '^font_instance.py --batch' "$CALLS"
grep -q '^font_name_normalize.py --batch' "$CALLS"
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
