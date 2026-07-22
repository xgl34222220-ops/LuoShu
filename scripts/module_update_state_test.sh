#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-update-state)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
SCHEMA=baseline-v6-mono-v1

OLD="$TMP/old"
NEW="$TMP/new"
mkdir -p \
    "$OLD/config" "$OLD/system/fonts/.luoshu-font-store" "$OLD/system/etc" "$OLD/product/fonts" \
    "$OLD/cache/full-composite-v5" "$OLD/cache/auto-multiweight-mix/composites-v2" \
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
printf 'cached composite\n' >"$OLD/cache/full-composite-v5/test.otf"
printf 'cached auto composite\n' >"$OLD/cache/auto-multiweight-mix/composites-v2/test.font"

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
test ! -e "$NEW/cache/full-composite-v5/test.otf"
test ! -e "$NEW/cache/auto-multiweight-mix/composites-v2/test.font"
test -f "$NEW/system/bin/洛书"
test ! -e "$NEW/config/switch_task.conf"
test ! -e "$NEW/config/text_reboot_required.conf"
test ! -e "$NEW/config/axes_worker.pid"
test "$LUOSHU_UPDATE_ACTIVE" = Qsal
test "$LUOSHU_UPDATE_REBUILD_REQUIRED" = true
grep -q '^state=pending$' "$NEW/config/font-payload-rebuild-pending.conf"
grep -q '^oldSchema=missing$' "$NEW/config/font-payload-rebuild-pending.conf"
grep -q "^newSchema=$SCHEMA$" "$NEW/config/font-payload-rebuild-pending.conf"

# Current-schema updates keep only current cache generations and do not request a rebuild.
CURRENT="$TMP/current"
CURRENT_NEW="$TMP/current-new"
mkdir -p "$CURRENT/config" "$CURRENT/system/fonts" \
    "$CURRENT/cache/full-composite-v6" "$CURRENT/cache/auto-multiweight-mix/composites-v3" \
    "$CURRENT/cache/auto-multiweight-mix/prepared-v3" "$CURRENT_NEW/config"
printf 'id=LuoShu\nversion=current\n' >"$CURRENT/module.prop"
printf 'Qsal\n' >"$CURRENT/config/active_font.conf"
printf 'schema=%s\nfont=Qsal\n' "$SCHEMA" >"$CURRENT/config/font-payload-schema.conf"
printf 'payload\n' >"$CURRENT/system/fonts/Qsal-Regular.ttf"
printf 'v6\n' >"$CURRENT/cache/full-composite-v6/current.font"
printf 'v3\n' >"$CURRENT/cache/auto-multiweight-mix/composites-v3/current.font"
printf 'prepared\n' >"$CURRENT/cache/auto-multiweight-mix/prepared-v3/current.font"
luoshu_migrate_active_install "$CURRENT" "$CURRENT_NEW"
test "$LUOSHU_UPDATE_REBUILD_REQUIRED" = false
test -f "$CURRENT_NEW/cache/full-composite-v6/current.font"
test -f "$CURRENT_NEW/cache/auto-multiweight-mix/composites-v3/current.font"
test -f "$CURRENT_NEW/cache/auto-multiweight-mix/prepared-v3/current.font"
test ! -e "$CURRENT_NEW/config/font-payload-rebuild-pending.conf"

# The installer-side direct-font rebuild waits for and accepts only the current schema.
REBUILD="$TMP/rebuild"
mkdir -p "$REBUILD/common" "$REBUILD/config" "$REBUILD/logs"
printf 'FontA\n' >"$REBUILD/config/active_font.conf"
printf 'state=pending\n' >"$REBUILD/config/font-payload-rebuild-pending.conf"
cat >"$REBUILD/common/font_manager.sh" <<'EOS'
#!/bin/sh
mkdir -p "$MODDIR/config"
printf 'schema=baseline-v6-mono-v1\nfont=FontA\n' >"$MODDIR/config/font-payload-schema.conf"
printf '{"status":"ok"}\n'
EOS
chmod 0755 "$REBUILD/common/font_manager.sh"
LUOSHU_UPDATE_ACTIVE=FontA
LUOSHU_UPDATE_REBUILD_TIMEOUT=4
luoshu_rebuild_preserved_payload "$REBUILD"
test "$LUOSHU_UPDATE_REBUILT" = true
test "$LUOSHU_UPDATE_REBUILD_FAILED" = false
test ! -e "$REBUILD/config/font-payload-rebuild-pending.conf"
test "$(luoshu_update_payload_schema "$REBUILD")" = "$SCHEMA"

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

echo 'Module updates preserve current payloads and rebuild stale schemas before the one reboot.'
