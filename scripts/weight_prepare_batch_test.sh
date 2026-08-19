#!/bin/sh
# A variable source has one file behind all nine weights, so the per-weight form started the
# embedded interpreter eighteen times over the same font: nine instancings plus nine identity
# normalizations. On a phone an interpreter cold start costs more than either step.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/scripts/assert.sh"
CASE='九档准备的批量化'

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MOD="$TMP/module"
mkdir -p "$MOD/common" "$MOD/config" "$MOD/system/fonts/.luoshu-font-store"
CALLS="$TMP/calls"
: > "$CALLS"

# A variable source: is_variable_font is stubbed, so the bytes only need to be a plausible font.
for w in regular wght-100 wght-200 wght-300 wght-400 wght-500 wght-600 wght-700 wght-800 wght-900; do
    dd if=/dev/zero of="$MOD/system/fonts/.luoshu-font-store/$w.font" bs=4096 count=1 2>/dev/null
done
touch "$MOD/common/font_instance.py" "$MOD/common/font_name_normalize.py"

export MODDIR="$MOD" MODULE_DIR="$MOD" CONFIG_DIR="$MOD/config"
_log_step() { :; }
is_variable_font() { return 0; }

# Record every backend invocation and satisfy it, so the test measures the call shape rather than
# the font maths.
_luoshu_font_config_exec() {
    _tool="${1##*/}"
    printf '%s %s\n' "$_tool" "${2:-}" >> "$CALLS"
    _jobs=''
    _out=''
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --batch) _jobs="$2"; shift 2 ;;
            --output) _out="$2"; shift 2 ;;
            *) shift ;;
        esac
    done
    if [ -n "$_out" ]; then
        dd if=/dev/zero of="$_out" bs=4096 count=1 2>/dev/null
    fi
    [ -n "$_jobs" ] || return 0
    while IFS="$(printf '\t')" read -r _a _b _rest; do
        [ -n "$_b" ] || continue
        dd if=/dev/zero of="$_b" bs=4096 count=1 2>/dev/null
    done < "$_jobs"
    return 0
}

. "$ROOT/common/font_config_weights.sh"
. "$ROOT/common/font_finalize_hotfix.sh"

ok font_config_prepare_payload_weights

CASE='九档 UI 与九档等宽都必须产出'
for w in 100 200 300 400 500 600 700 800 900; do
    ok test -s "$MOD/system/fonts/LuoShu-${w}.ttf"
    ok test -s "$MOD/system/fonts/LuoShuMono-${w}.ttf"
done

CASE='实例化必须批量：一次调用而不是九次'
eq "$(grep -c '^font_instance.py' "$CALLS" | tr -d '[:space:]')" 1
ok grep -q '^font_instance.py --batch' "$CALLS"

CASE='身份归一必须批量：不得逐档调用'
# One batch for the nine UI weights, one for the single monospace weight.
_names=$(grep -c '^font_name_normalize.py' "$CALLS" | tr -d '[:space:]')
[ "$_names" -le 2 ] || fail "font_name_normalize.py 调用了 $_names 次，应当批量"

CASE='总调用次数必须是常数，不随字重数量增长'
_total=$(awk 'NF' "$CALLS" | wc -l | tr -d '[:space:]')
[ "$_total" -le 4 ] || fail "后端调用 $_total 次，九档准备应当只需常数次"

CASE='语法'
ok sh -n "$ROOT/common/font_finalize_hotfix.sh"
ok python3 -c 'import ast,sys; ast.parse(open(sys.argv[1]).read())' "$ROOT/common/font_instance.py"
ok python3 -c 'import ast,sys; ast.parse(open(sys.argv[1]).read())' "$ROOT/common/font_name_normalize.py"
printf 'Nine-weight preparation batching tests passed.\n'
