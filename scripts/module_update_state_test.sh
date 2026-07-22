#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-update-state)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

OLD="$TMP/old"
NEW="$TMP/new"
mkdir -p \
    "$OLD/config" "$OLD/system/fonts/.luoshu-font-store" "$OLD/system/etc" "$OLD/product/fonts" \
    "$NEW/config" "$NEW/system/bin"

printf 'id=LuoShu\nversion=old\n' >"$OLD/module.prop"
printf 'Qsal\n' >"$OLD/config/active_font.conf"
printf 'Twemoji\n' >"$OLD/config/active_emoji.conf"
printf 'cjk=Qsal\nlatin=Qsal\ndigit=Qsal\n' >"$OLD/config/font_mix.conf"
printf 'old notes\n' >"$OLD/config/version_notes.conf"
printf 'state=running\n' >"$OLD/config/switch_task.conf"
printf 'font=Qsal\n' >"$OLD/config/text_reboot_required.conf"
printf '123\n' >"$OLD/config/axes_worker.pid"
printf 'Qsal payload\n' >"$OLD/system/fonts/Qsal-Regular.ttf"
printf 'anchor\n' >"$OLD/system/fonts/.luoshu-font-store/qsal.font"
printf '<familyset/>\n' >"$OLD/system/etc/fonts.xml"
printf 'OEM payload\n' >"$OLD/product/fonts/OEM-Regular.ttf"

printf 'new notes\n' >"$NEW/config/version_notes.conf"
printf '#!/bin/sh\n' >"$NEW/system/bin/洛书"

. "$ROOT/common/module_update_state.sh"
luoshu_migrate_active_install "$OLD" "$NEW"

test "$(cat "$NEW/config/active_font.conf")" = Qsal
test "$(cat "$NEW/config/active_emoji.conf")" = Twemoji
grep -q '^cjk=Qsal$' "$NEW/config/font_mix.conf"
test "$(cat "$NEW/config/version_notes.conf")" = 'new notes'
test -f "$NEW/system/fonts/Qsal-Regular.ttf"
test -f "$NEW/system/fonts/.luoshu-font-store/qsal.font"
test -f "$NEW/system/etc/fonts.xml"
test -f "$NEW/product/fonts/OEM-Regular.ttf"
test -f "$NEW/system/bin/洛书"
test ! -e "$NEW/config/switch_task.conf"
test ! -e "$NEW/config/text_reboot_required.conf"
test ! -e "$NEW/config/axes_worker.pid"

INVALID="$TMP/invalid"
TARGET="$TMP/invalid-target"
mkdir -p "$INVALID/config" "$TARGET/config"
printf 'id=LuoShu\n' >"$INVALID/module.prop"
printf 'MissingFont\n' >"$INVALID/config/active_font.conf"
if luoshu_migrate_active_install "$INVALID" "$TARGET"; then
    echo 'invalid active payload was migrated' >&2
    exit 1
fi
test ! -e "$TARGET/config/active_font.conf"

FRESH="$TMP/fresh"
mkdir -p "$FRESH"
set +e
luoshu_migrate_active_install "$TMP/not-installed" "$FRESH"
FRESH_CODE=$?
set -e
test "$FRESH_CODE" -eq 2

echo 'Module updates preserve active font payload and require one reboot.'
