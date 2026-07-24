#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export MODULE_DIR="$TMP/module"
export MODDIR="$MODULE_DIR"
mkdir -p "$MODULE_DIR/config"
. "$ROOT/common/font_validation_cache.sh"
calls="$TMP/calls"
font_validate_global() {
    printf 'call\n' >> "$calls"
    FONT_CHECK_FORMAT=TTF
    FONT_CHECK_SIZE=8192
    FONT_CHECK_VARIABLE=false
    FONT_CHECK_COLOR=false
    FONT_CHECK_WARNING=''
    FONT_CHECK_COVERAGE=ok
    FONT_CHECK_ERROR=''
    return 0
}
font_detect_format() { printf 'TTF\n'; }
is_variable_font() { return 1; }

font="$TMP/font.ttf"
dd if=/dev/zero of="$font" bs=4096 count=2 status=none
luoshu_font_validate_global_cached "$font"
[ "${LUOSHU_FONT_VALIDATION_CACHE_HIT:-false}" = false ]
luoshu_font_validate_global_cached "$font"
[ "${LUOSHU_FONT_VALIDATION_CACHE_HIT:-false}" = true ]
[ "$(wc -l < "$calls" | tr -d ' ')" -eq 1 ]
printf x >> "$font"
luoshu_font_validate_global_cached "$font"
[ "${LUOSHU_FONT_VALIDATION_CACHE_HIT:-false}" = false ]
[ "$(wc -l < "$calls" | tr -d ' ')" -eq 2 ]

# App preflight only checks file identity/format and must not run the expensive global validator.
preflight="$TMP/preflight.ttf"
dd if=/dev/zero of="$preflight" bs=4096 count=2 status=none
LUOSHU_VALIDATION_MODE=preflight
export LUOSHU_VALIDATION_MODE
luoshu_font_validate_global_cached "$preflight"
[ "$FONT_CHECK_COVERAGE" = deferred ]
printf '%s\n' "$FONT_CHECK_WARNING" | grep -q '后台切换任务'
[ "$(wc -l < "$calls" | tr -d ' ')" -eq 2 ]
unset LUOSHU_VALIDATION_MODE
luoshu_font_validate_global_cached "$preflight"
[ "$(wc -l < "$calls" | tr -d ' ')" -eq 3 ]

# Direct switch still performs the full cached validator inside font_manager.
grep -q 'luoshu_font_validate_global_cached "$_source"' "$ROOT/common/font_manager.sh"
echo 'font_validation_cache_test: PASS'
