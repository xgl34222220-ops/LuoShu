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

_luoshu_font_config_exec() {
    printf '%s\n' \
        'Good.ttf|400|sans-serif' \
        'Bad.ttf|400|sans-serif'
}

_luoshu_safety_log() { :; }

# Deliberately make only Bad.ttf fail. Good.ttf must still commit as partial coverage.
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

printf 'Generic XML partial coverage tests passed.\n'
