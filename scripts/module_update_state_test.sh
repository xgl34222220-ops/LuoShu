#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-update-state)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
SCHEMA=device-template-v2-baseline-v9-rolegraph-v2
LUOSHU_PAYLOAD_SCHEMA_CURRENT="$SCHEMA"
export LUOSHU_PAYLOAD_SCHEMA_CURRENT
OEM_PARTITIONS='my_engineering my_company my_preload my_region my_stock oplus_product oplus_engineering oplus_version oplus_region mi_ext cust hw_product'

OLD="$TMP/old"
NEW="$TMP/new"
mkdir -p \
    "$OLD/config" "$OLD/system/fonts/.luoshu-font-store" "$OLD/system/etc" "$OLD/product/fonts" \
    "$OLD/cache/full-composite-v5" "$OLD/cache/auto-multiweight-mix/composites-v2" \
    "$OLD/config/device-font-cache/stale" \
    "$NEW/config" "$NEW/system/bin"
for partition in $OEM_PARTITIONS; do
    mkdir -p "$OLD/$partition/fonts"
    printf '%s payload\n' "$partition" >"$OLD/$partition/fonts/LuoShu-OEM.ttf"
done

printf 'id=LuoShu\nversion=old\n' >"$OLD/module.prop"
printf 'Qsal\n' >"$OLD/config/active_font.conf"
printf 'Twemoji\n' >"$OLD/config/active_emoji.conf"
printf 'cjk=Qsal\nlatin=Qsal\ndigit=Qsal\n' >"$OLD/config/font_mix.conf"
printf 'old notes\n' >"$OLD/config/version_notes.conf"
printf 'state=running\n' >"$OLD/config/switch_task.conf"
printf 'font=Qsal\n' >"$OLD/config/text_reboot_required.conf"
printf '123\n' >"$OLD/config/axes_worker.pid"
printf '2\n' >"$OLD/config/font-boot-failures"
printf 'state=quarantined\n' >"$OLD/config/font-payload-quarantine.conf"
printf 'state=degraded\n' >"$OLD/config/self-mount.conf"
printf '/old/source|/system/fonts|overlay\n' >"$OLD/config/self-mount-required.conf"
printf 'state=verified\nactiveFont=Qsal\n' >"$OLD/config/device-font-load-verification.conf"
printf 'Qsal payload\n' >"$OLD/system/fonts/Qsal-Regular.ttf"
printf 'anchor\n' >"$OLD/system/fonts/.luoshu-font-store/qsal.font"
printf '<familyset/>\n' >"$OLD/system/etc/fonts.xml"
printf 'OEM payload\n' >"$OLD/product/fonts/OEM-Regular.ttf"
printf 'cached composite\n' >"$OLD/cache/full-composite-v5/test.otf"
printf 'cached auto composite\n' >"$OLD/cache/auto-multiweight-mix/composites-v2/test.font"
printf 'state=ready\n' >"$OLD/config/device-font-cache/stale/cache.conf"

printf 'new notes\n' >"$NEW/config/version_notes.conf"
printf '#!/bin/sh\n' >"$NEW/system/bin/洛书"

. "$ROOT/common/module_update_state.sh"

RECOVERY_OLD="$TMP/recovery-old"
RECOVERY_NEW="$TMP/recovery-new"
mkdir -p "$RECOVERY_OLD" "$RECOVERY_NEW"
printf 'id=LuoShu\nversionCode=30303\n' > "$RECOVERY_OLD/module.prop"
printf 'id=LuoShu\nversionCode=30304\n' > "$RECOVERY_NEW/module.prop"
luoshu_runtime_recovery_required "$RECOVERY_OLD" "$RECOVERY_NEW"
printf 'id=LuoShu\nversionCode=30304\n' > "$RECOVERY_OLD/module.prop"
if luoshu_runtime_recovery_required "$RECOVERY_OLD" "$RECOVERY_NEW"; then
    echo 'same-version recovery reinstall unexpectedly reset its payload' >&2
    exit 1
fi
printf 'id=LuoShu\nversionCode=30305\n' > "$RECOVERY_NEW/module.prop"
if luoshu_runtime_recovery_required "$RECOVERY_OLD" "$RECOVERY_NEW"; then
    echo 'post-recovery upgrade unexpectedly reset its clean payload' >&2
    exit 1
fi
printf 'id=LuoShu\nversionCode=30303\n' > "$RECOVERY_OLD/module.prop"
luoshu_runtime_recovery_required "$RECOVERY_OLD" "$RECOVERY_NEW"

luoshu_migrate_active_install "$OLD" "$NEW"

test "$(cat "$NEW/config/active_font.conf")" = Qsal
test "$(cat "$NEW/config/active_emoji.conf")" = Twemoji
grep -q '^cjk=Qsal$' "$NEW/config/font_mix.conf"
test "$(cat "$NEW/config/version_notes.conf")" = 'new notes'
test -f "$NEW/system/fonts/Qsal-Regular.ttf"
test -f "$NEW/system/fonts/.luoshu-font-store/qsal.font"
test -f "$NEW/system/etc/fonts.xml"
test -f "$NEW/product/fonts/OEM-Regular.ttf"
for partition in $OEM_PARTITIONS; do
    test -f "$NEW/$partition/fonts/LuoShu-OEM.ttf"
done
test ! -e "$NEW/cache/full-composite-v5/test.otf"
test ! -e "$NEW/cache/auto-multiweight-mix/composites-v2/test.font"
test ! -e "$NEW/config/device-font-cache/stale/cache.conf"
test -f "$NEW/system/bin/洛书"
test ! -e "$NEW/config/switch_task.conf"
test ! -e "$NEW/config/text_reboot_required.conf"
test ! -e "$NEW/config/axes_worker.pid"
test ! -e "$NEW/config/font-boot-failures"
test ! -e "$NEW/config/font-payload-quarantine.conf"
test ! -e "$NEW/config/self-mount.conf"
test ! -e "$NEW/config/self-mount-required.conf"
test ! -e "$NEW/config/device-font-load-verification.conf"
test "$LUOSHU_UPDATE_ACTIVE" = Qsal
test "$LUOSHU_UPDATE_REBUILD_REQUIRED" = true
grep -q '^state=awaiting-explicit-apply$' "$NEW/config/font-payload-rebuild-pending.conf"
grep -q '^mode=preserve-current$' "$NEW/config/font-payload-rebuild-pending.conf"
grep -q '^reason=schema-upgrade$' "$NEW/config/font-payload-rebuild-pending.conf"
grep -q '^oldSchema=missing$' "$NEW/config/font-payload-rebuild-pending.conf"
grep -q "^newSchema=$SCHEMA$" "$NEW/config/font-payload-rebuild-pending.conf"

# Current-schema updates keep only current cache generations and do not request a rebuild.
CURRENT="$TMP/current"
CURRENT_NEW="$TMP/current-new"
mkdir -p "$CURRENT/config" "$CURRENT/system/fonts" \
    "$CURRENT/cache/full-composite-v11" "$CURRENT/cache/auto-multiweight-mix/composites-v8" \
    "$CURRENT/cache/auto-multiweight-mix/prepared-v8" "$CURRENT/config/device-font-cache/current/payload" \
    "$CURRENT/config/device-font-cache/current/overlay" "$CURRENT/config/metrics_cache" "$CURRENT_NEW/config"
printf 'id=LuoShu\nversion=current\n' >"$CURRENT/module.prop"
printf 'mix\n' >"$CURRENT/config/active_font.conf"
printf 'cjk=Qsal\nlatin=Latin\ndigit=Digit\n' >"$CURRENT/config/font_mix.conf"
printf 'schema=%s\nfont=mix\n' "$SCHEMA" >"$CURRENT/config/font-payload-schema.conf"
printf 'payload\n' >"$CURRENT/system/fonts/Qsal-Regular.ttf"
printf 'v11\n' >"$CURRENT/cache/full-composite-v11/current.font"
printf 'v8\n' >"$CURRENT/cache/auto-multiweight-mix/composites-v8/current.font"
printf 'prepared\n' >"$CURRENT/cache/auto-multiweight-mix/prepared-v8/current.font"
printf '{}\n' >"$CURRENT/config/device-font-cache/current/payload/manifest.json"
printf '{}\n' >"$CURRENT/config/device-font-cache/current/overlay/overlay-manifest.json"
printf 'state=ready\nfont=mix\n' >"$CURRENT/config/device-font-cache/current/cache.conf"
printf 'metric\n' >"$CURRENT/config/metrics_cache/current.font"
luoshu_migrate_active_install "$CURRENT" "$CURRENT_NEW"
test "$LUOSHU_UPDATE_REBUILD_REQUIRED" = false
test "$(cat "$CURRENT_NEW/config/active_font.conf")" = mix
grep -q '^cjk=Qsal$' "$CURRENT_NEW/config/font_mix.conf"
test -f "$CURRENT_NEW/cache/full-composite-v11/current.font"
test -f "$CURRENT_NEW/cache/auto-multiweight-mix/composites-v8/current.font"
test -f "$CURRENT_NEW/cache/auto-multiweight-mix/prepared-v8/current.font"
test -f "$CURRENT_NEW/config/device-font-cache/current/cache.conf"
test -f "$CURRENT_NEW/config/device-font-cache/current/payload/manifest.json"
test -f "$CURRENT_NEW/config/metrics_cache/current.font"
test ! -e "$CURRENT_NEW/config/font-payload-rebuild-pending.conf"

# A valid active payload may live only in an OEM partition. It must still be
# recognized and preserved instead of silently resetting the selected font.
OPLUS_ONLY="$TMP/oplus-only"
OPLUS_ONLY_NEW="$TMP/oplus-only-new"
mkdir -p "$OPLUS_ONLY/config" "$OPLUS_ONLY/oplus_product/fonts" "$OPLUS_ONLY_NEW/config"
printf 'id=LuoShu\nversion=oplus-only\n' >"$OPLUS_ONLY/module.prop"
printf 'Qsal\n' >"$OPLUS_ONLY/config/active_font.conf"
printf 'schema=%s\nfont=Qsal\n' "$SCHEMA" >"$OPLUS_ONLY/config/font-payload-schema.conf"
printf 'oplus-only payload\n' >"$OPLUS_ONLY/oplus_product/fonts/OPPOSans-Regular.ttf"
luoshu_migrate_active_install "$OPLUS_ONLY" "$OPLUS_ONLY_NEW"
test -f "$OPLUS_ONLY_NEW/oplus_product/fonts/OPPOSans-Regular.ttf"
test "$LUOSHU_UPDATE_REBUILD_REQUIRED" = false

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

echo 'Module updates preserve current payloads; stale schemas wait for one explicit foreground apply.'
