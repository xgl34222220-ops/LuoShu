#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-update-state)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
SCHEMA=device-template-v2-baseline-v9-rolegraph-v2
BAD_SCHEMA=device-template-v2-baseline-v10-latin-coverage-v1
LUOSHU_PAYLOAD_SCHEMA_CURRENT="$SCHEMA"
export LUOSHU_PAYLOAD_SCHEMA_CURRENT
OEM_PARTITIONS='system_ext product vendor odm oem my_product my_engineering my_company my_preload my_region my_stock oplus_product oplus_engineering oplus_version oplus_region mi_ext cust hw_product'

. "$ROOT/common/module_update_state.sh"

# Recovery boundary remains one-shot.
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

# Regression: a v10 Latin-coverage payload must NEVER be mounted by the v9 rollback/hotfix.
OLD="$TMP/old-bad"
NEW="$TMP/new-safe"
mkdir -p "$OLD/config/device-font-cache/stale" "$OLD/system/fonts/.luoshu-font-store" "$OLD/system/etc" "$NEW/config" "$NEW/system/bin"
printf 'id=LuoShu\nversion=v4.0.0\nversionCode=40000\n' > "$OLD/module.prop"
printf 'Qsal\n' > "$OLD/config/active_font.conf"
printf 'cjk=Qsal\nlatin=Latin\ndigit=Digit\n' > "$OLD/config/font_mix.conf"
printf 'schema=%s\nfont=Qsal\n' "$BAD_SCHEMA" > "$OLD/config/font-payload-schema.conf"
printf 'font=Qsal\nstate=confirmed\n' > "$OLD/config/font-payload-boot.conf"
printf 'system/fonts/Qsal-Regular.ttf\n' > "$OLD/config/font-payload-manifest.conf"
printf 'bad system payload\n' > "$OLD/system/fonts/Qsal-Regular.ttf"
printf 'anchor\n' > "$OLD/system/fonts/.luoshu-font-store/qsal.font"
printf '<familyset/>\n' > "$OLD/system/etc/fonts.xml"
printf 'state=ready\n' > "$OLD/config/device-font-cache/stale/cache.conf"
for partition in $OEM_PARTITIONS; do
    mkdir -p "$OLD/$partition/fonts"
    printf 'bad %s payload\n' "$partition" > "$OLD/$partition/fonts/LuoShu-OEM.ttf"
done
printf 'new notes\n' > "$NEW/config/version_notes.conf"
printf '#!/bin/sh\n' > "$NEW/system/bin/洛书"

luoshu_migrate_active_install "$OLD" "$NEW"

test "$(cat "$NEW/config/active_font.conf")" = Qsal
grep -q '^cjk=Qsal$' "$NEW/config/font_mix.conf"
test -f "$NEW/system/bin/洛书"
test "$(cat "$NEW/config/version_notes.conf")" = 'new notes'
test "$LUOSHU_UPDATE_REBUILD_REQUIRED" = true
test "$LUOSHU_UPDATE_PAYLOAD_PRESERVED" = false

test ! -e "$NEW/system/fonts/Qsal-Regular.ttf"
test ! -e "$NEW/system/fonts/.luoshu-font-store/qsal.font"
test ! -e "$NEW/system/etc/fonts.xml"
for partition in $OEM_PARTITIONS; do
    test ! -e "$NEW/$partition/fonts/LuoShu-OEM.ttf"
done
test ! -e "$NEW/config/device-font-cache/stale/cache.conf"
test ! -e "$NEW/config/font-payload-schema.conf"
test ! -e "$NEW/config/font-payload-manifest.conf"
test ! -e "$NEW/config/font-payload-boot.conf"

grep -q '^state=awaiting-explicit-apply$' "$NEW/config/font-payload-rebuild-pending.conf"
grep -q '^mode=safe-stock$' "$NEW/config/font-payload-rebuild-pending.conf"
grep -q '^reason=schema-mismatch$' "$NEW/config/font-payload-rebuild-pending.conf"
grep -q '^payloadPreserved=false$' "$NEW/config/font-payload-rebuild-pending.conf"
grep -q '^font=Qsal$' "$NEW/config/font-payload-rebuild-pending.conf"
grep -q "^oldSchema=$BAD_SCHEMA$" "$NEW/config/font-payload-rebuild-pending.conf"
grep -q "^newSchema=$SCHEMA$" "$NEW/config/font-payload-rebuild-pending.conf"

# Same-schema updates may preserve a proven payload and its device cache.
CURRENT="$TMP/current"
CURRENT_NEW="$TMP/current-new"
mkdir -p "$CURRENT/config/device-font-cache/current/payload" \
    "$CURRENT/config/device-font-cache/current/overlay" \
    "$CURRENT/system/fonts" "$CURRENT/product/fonts" "$CURRENT_NEW/config"
printf 'id=LuoShu\nversion=current\n' > "$CURRENT/module.prop"
printf 'mix\n' > "$CURRENT/config/active_font.conf"
printf 'cjk=Qsal\nlatin=Latin\ndigit=Digit\n' > "$CURRENT/config/font_mix.conf"
printf 'schema=%s\nfont=mix\n' "$SCHEMA" > "$CURRENT/config/font-payload-schema.conf"
printf 'payload\n' > "$CURRENT/system/fonts/Qsal-Regular.ttf"
printf 'product payload\n' > "$CURRENT/product/fonts/OEM-Regular.ttf"
printf '{}\n' > "$CURRENT/config/device-font-cache/current/payload/manifest.json"
printf '{}\n' > "$CURRENT/config/device-font-cache/current/overlay/overlay-manifest.json"
printf 'state=ready\nfont=mix\n' > "$CURRENT/config/device-font-cache/current/cache.conf"

luoshu_migrate_active_install "$CURRENT" "$CURRENT_NEW"
test "$LUOSHU_UPDATE_REBUILD_REQUIRED" = false
test "$LUOSHU_UPDATE_PAYLOAD_PRESERVED" = true
test "$(cat "$CURRENT_NEW/config/active_font.conf")" = mix
test -f "$CURRENT_NEW/system/fonts/Qsal-Regular.ttf"
test -f "$CURRENT_NEW/product/fonts/OEM-Regular.ttf"
test -f "$CURRENT_NEW/config/device-font-cache/current/cache.conf"
test ! -e "$CURRENT_NEW/config/font-payload-rebuild-pending.conf"

# Default-font installs never need to carry generated payload trees forward.
DEFAULT_OLD="$TMP/default-old"
DEFAULT_NEW="$TMP/default-new"
mkdir -p "$DEFAULT_OLD/config" "$DEFAULT_OLD/system/fonts" "$DEFAULT_OLD/vendor/fonts" "$DEFAULT_NEW/config"
printf 'id=LuoShu\nversion=current\n' > "$DEFAULT_OLD/module.prop"
printf 'default\n' > "$DEFAULT_OLD/config/active_font.conf"
printf 'schema=%s\nfont=default\n' "$SCHEMA" > "$DEFAULT_OLD/config/font-payload-schema.conf"
printf 'stray\n' > "$DEFAULT_OLD/system/fonts/Stray.ttf"
printf 'stray vendor\n' > "$DEFAULT_OLD/vendor/fonts/Stray.ttf"
luoshu_migrate_active_install "$DEFAULT_OLD" "$DEFAULT_NEW"
test "$(cat "$DEFAULT_NEW/config/active_font.conf")" = default
test "$LUOSHU_UPDATE_PAYLOAD_PRESERVED" = false
test ! -e "$DEFAULT_NEW/system/fonts/Stray.ttf"
test ! -e "$DEFAULT_NEW/vendor/fonts/Stray.ttf"

# A selected font without any payload is invalid and must not be migrated as active.
INVALID="$TMP/invalid"
TARGET="$TMP/invalid-target"
mkdir -p "$INVALID/config" "$TARGET/config"
printf 'id=LuoShu\n' > "$INVALID/module.prop"
printf 'MissingFont\n' > "$INVALID/config/active_font.conf"
printf 'schema=%s\n' "$SCHEMA" > "$INVALID/config/font-payload-schema.conf"
if luoshu_migrate_active_install "$INVALID" "$TARGET"; then
    echo 'invalid active payload was migrated' >&2
    exit 1
fi
test ! -e "$TARGET/config/active_font.conf"

echo 'Module updates preserve only same-schema payloads; incompatible payloads boot safely on ROM fonts while retaining the selected font.'
