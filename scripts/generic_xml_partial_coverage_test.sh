#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MOD="$TMP/module"
mkdir -p \
    "$MOD/config/font-config-source/system" \
    "$MOD/system/fonts" \
    "$MOD/common" \
    "$TMP/real-fonts"

dd if=/dev/zero of="$MOD/system/fonts/LuoShu-400.ttf" bs=2048 count=1 2>/dev/null
printf '<familyset/>\n' > "$MOD/config/font-config-source/system/fonts.xml"
printf 'stock-good\n' > "$TMP/real-fonts/Good.ttf"
printf 'stock-bad\n' > "$TMP/real-fonts/Bad.ttf"
: > "$MOD/common/font_config_targets.py"

MODULE_DIR="$MOD"
MODDIR="$MOD"
CONFIG_DIR="$MOD/config"
export MODULE_DIR MODDIR CONFIG_DIR

. "$ROOT/common/font_safety.sh"
. "$ROOT/common/hyperos_coverage_floor.sh"
set -eu

_luoshu_font_real_path() {
    printf '%s/%s\n' "$TMP/real-fonts" "$1"
}

_luoshu_font_config_specs() {
    printf 'system/fonts.xml|%s|%s|%s\n' \
        "$TMP/real-fonts.xml" \
        "$MOD/system/etc/fonts.xml" \
        "$MOD/system/fonts"
}

font_config_capture_original() { :; }

# Generic ROMs retain the existing batch behavior: one TARGET line per discovered slot, then one
# DOC status line per document. Partial physical-slot installation is still reported honestly.
_luoshu_font_config_exec() {
    _stub_jobs=''
    while [ "$#" -gt 0 ]; do
        case "$1" in --batch) _stub_jobs="$2"; shift 2 ;; *) shift ;; esac
    done
    [ -n "$_stub_jobs" ] || return 1
    while IFS= read -r _stub_input; do
        [ -n "$_stub_input" ] || continue
        printf 'TARGET\t%s\tGood.ttf\t400\tsans-serif\n' "$_stub_input"
        printf 'TARGET\t%s\tBad.ttf\t400\tsans-serif\n' "$_stub_input"
        printf 'DOC\t%s\tok\t2\t\n' "$_stub_input"
    done < "$_stub_jobs"
}

_luoshu_safety_log() { :; }
IS_HYPEROS=false
export IS_HYPEROS

# Deliberately make only Bad.ttf fail. Good.ttf must still commit as partial coverage on generic ROMs.
ln() {
    case "$2" in *Bad.ttf) return 1 ;; esac
    command ln "$@"
}
cp() {
    # Runtime fallback uses: cp -f SOURCE DEST, so DEST is the third argument.
    case "${3:-}" in *Bad.ttf) return 1 ;; esac
    command cp "$@"
}

luoshu_dynamic_targets_apply

test -s "$MOD/config/font-target-coverage.conf"
grep -qx 'discovered=2' "$MOD/config/font-target-coverage.conf"
grep -qx 'targets=2' "$MOD/config/font-target-coverage.conf"
grep -qx 'mapped=1' "$MOD/config/font-target-coverage.conf"
grep -qx 'status=partial' "$MOD/config/font-target-coverage.conf"
grep -qx 'mode=batch' "$MOD/config/font-target-coverage.conf"
# scanFailed tracks XML discovery/parser failures, not target install failures.
grep -qx 'scanFailed=0' "$MOD/config/font-target-coverage.conf"
test "$(awk 'NF { n++ } END { print n+0 }' "$MOD/config/font-target-aliases.conf")" -eq 1
test -s "$MOD/system/fonts/Good.ttf"
test ! -e "$MOD/system/fonts/Bad.ttf"

# Zero usable mappings remains a hard failure and must not leave stale coverage metadata behind.
rm -f "$MOD/system/fonts/LuoShu-400.ttf"
if luoshu_dynamic_targets_apply; then
    echo 'zero dynamic mappings unexpectedly succeeded' >&2
    exit 1
fi
test ! -e "$MOD/config/font-target-coverage.conf"
test ! -e "$MOD/config/font-target-aliases.conf"

# HyperOS regression: simulate the 2.9+ batch protocol losing one otherwise valid UI target. The
# v2.8 per-document path must be replayed, union the missing slot, and finish as full coverage.
dd if=/dev/zero of="$MOD/system/fonts/LuoShu-400.ttf" bs=2048 count=1 2>/dev/null
rm -f "$MOD/system/fonts/Good.ttf" "$MOD/system/fonts/Bad.ttf" "$MOD/system/fonts/Recovered.ttf"
IS_HYPEROS=true
export IS_HYPEROS

ln() { command ln "$@"; }
cp() { command cp "$@"; }

_luoshu_font_config_exec() {
    _stub_mode=''
    _stub_value=''
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --batch) _stub_mode=batch; _stub_value="$2"; shift 2 ;;
            --input) _stub_mode=input; _stub_value="$2"; shift 2 ;;
            *) shift ;;
        esac
    done
    case "$_stub_mode" in
        batch)
            while IFS= read -r _stub_input; do
                [ -n "$_stub_input" ] || continue
                printf 'TARGET\t%s\tGood.ttf\t400\tsans-serif\n' "$_stub_input"
                printf 'DOC\t%s\tok\t1\t\n' "$_stub_input"
            done < "$_stub_value"
            ;;
        input)
            printf 'Good.ttf|400|sans-serif\n'
            printf 'Recovered.ttf|400|sans-serif\n'
            ;;
        *) return 1 ;;
    esac
}

luoshu_dynamic_targets_apply

grep -qx 'discovered=2' "$MOD/config/font-target-coverage.conf"
grep -qx 'targets=2' "$MOD/config/font-target-coverage.conf"
grep -qx 'mapped=2' "$MOD/config/font-target-coverage.conf"
grep -qx 'status=full' "$MOD/config/font-target-coverage.conf"
grep -qx 'scanFailed=0' "$MOD/config/font-target-coverage.conf"
grep -qx 'mode=hyperos-v28-union' "$MOD/config/font-target-coverage.conf"
grep -qx 'fallbackAdded=1' "$MOD/config/font-target-coverage.conf"
test -s "$MOD/system/fonts/Good.ttf"
test -s "$MOD/system/fonts/Recovered.ttf"

# HyperOS must never silently accept partial coverage. If one union target cannot be installed, the
# function returns failure and leaves status=partial diagnostics for the surrounding transaction.
ln() {
    case "$2" in *Recovered.ttf) return 1 ;; esac
    command ln "$@"
}
cp() {
    case "${3:-}" in *Recovered.ttf) return 1 ;; esac
    command cp "$@"
}
if luoshu_dynamic_targets_apply; then
    echo 'HyperOS partial coverage unexpectedly succeeded' >&2
    exit 1
fi
grep -qx 'targets=2' "$MOD/config/font-target-coverage.conf"
grep -qx 'mapped=1' "$MOD/config/font-target-coverage.conf"
grep -qx 'status=partial' "$MOD/config/font-target-coverage.conf"
grep -qx 'mode=hyperos-v28-union' "$MOD/config/font-target-coverage.conf"

printf 'Generic XML partial coverage and HyperOS v2.8 floor tests passed.\n'
