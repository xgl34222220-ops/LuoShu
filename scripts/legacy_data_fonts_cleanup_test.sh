#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
OLD="$TMP/old"
DATA="$TMP/data-fonts"
mkdir -p "$OLD/system/fonts" "$DATA"

get_all_coloros_names() {
    printf '%s\n' SysFont SysSans-En Unrelated
}
. "$ROOT/common/legacy_data_fonts_cleanup.sh"
set -eu

printf 'same-font\n' > "$OLD/system/fonts/SysFont.ttf"
printf 'same-font\n' > "$DATA/SysFont.ttf"
printf 'old-module-copy\n' > "$OLD/system/fonts/SysSans-En.ttf"
printf 'system-or-user-font\n' > "$DATA/SysSans-En.ttf"
printf 'unrelated\n' > "$DATA/Unrelated.ttf"

_removed=$(luoshu_cleanup_legacy_data_fonts "$OLD" "$DATA")
[ "$_removed" -eq 1 ]
test ! -e "$DATA/SysFont.ttf"
test -f "$DATA/SysSans-En.ttf"
test "$(cat "$DATA/SysSans-En.ttf")" = 'system-or-user-font'
test -f "$DATA/Unrelated.ttf"

# Re-running is idempotent and never removes a file without an old-module counterpart.
_removed=$(luoshu_cleanup_legacy_data_fonts "$OLD" "$DATA")
[ "$_removed" -eq 0 ]
test -f "$DATA/SysSans-En.ttf"
test -f "$DATA/Unrelated.ttf"

printf 'Legacy data-font cleanup tests passed.\n'
