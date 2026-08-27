#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-customize)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

OLD="$TMP/active/LuoShu"
NEW="$TMP/update/LuoShu"
mkdir -p "$OLD/config" "$NEW/config" "$NEW/common"
printf 'id=LuoShu\nversion=v2.0.2\nversionCode=20002\n' > "$NEW/module.prop"
touch "$OLD/disable" "$NEW/disable"
printf '2\n' > "$OLD/config/font-boot-failures"
printf 'state=quarantined\n' > "$OLD/config/font-payload-quarantine.conf"

# customize.sh intentionally tolerates unavailable Android commands during host-side tests. The
# regression contract is that a flash immediately re-enables both the active and staged trees.
if ! MODPATH="$NEW" LUOSHU_OLD_MOD="$OLD" sh "$ROOT/customize.sh" >"$TMP/direct.log" 2>&1; then
    cat "$TMP/direct.log" >&2
    echo 'direct customize execution failed' >&2
    exit 1
fi

test ! -e "$OLD/disable"
test ! -e "$NEW/disable"
test ! -e "$OLD/config/font-boot-failures"
test ! -e "$OLD/config/font-payload-quarantine.conf"

# APatch sources customize.sh. The wrapper must return to the manager instead of
# exiting its parent shell before the staged module is committed.
SOURCED_MARKER="$TMP/source-continued"
if ! MODPATH="$NEW" LUOSHU_OLD_MOD="$OLD" sh -c '
    . "$1" >"$3" 2>&1
    printf "continued\n" > "$2"
' sh "$ROOT/customize.sh" "$SOURCED_MARKER" "$TMP/sourced.log"; then
    cat "$TMP/sourced.log" >&2 || true
    echo 'sourced customize execution failed' >&2
    exit 1
fi
test "$(cat "$SOURCED_MARKER")" = continued

echo 'Module flash re-enable and APatch source-safety checks passed.'
