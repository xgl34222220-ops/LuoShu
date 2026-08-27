#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-v4-update)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

OLD="$TMP/old"
NEW="$TMP/new"
mkdir -p "$OLD/config" "$OLD/system/fonts" "$OLD/vendor/fonts" "$NEW/config" "$NEW/system/fonts"
printf 'id=LuoShu\nversion=v4.0.0\nversionCode=40000\n' > "$OLD/module.prop"
printf 'id=LuoShu\nversion=v4.0.0\nversionCode=40000\n' > "$NEW/module.prop"
printf 'mix\n' > "$OLD/config/active_font.conf"
printf 'cjk=CJK\nlatin=Latin\ndigit=Digit\n' > "$OLD/config/font_mix.conf"
printf 'schema=old-incompatible-schema\n' > "$OLD/config/font-payload-schema.conf"
dd if=/dev/zero of="$OLD/system/fonts/Roboto-Regular.ttf" bs=2048 count=1 2>/dev/null
dd if=/dev/zero of="$OLD/vendor/fonts/BadBoot.ttf" bs=2048 count=1 2>/dev/null

LUOSHU_PAYLOAD_SCHEMA_CURRENT='new-safe-schema'
export LUOSHU_PAYLOAD_SCHEMA_CURRENT
. "$ROOT/common/module_update_state.sh"

# A schema mismatch must preserve the currently working payload. The update may
# mark it for one explicit foreground re-apply after reboot, but the Root manager
# flashing process itself must never rebuild or discard the active font.
luoshu_migrate_active_install "$OLD" "$NEW"
[ "$(cat "$NEW/config/active_font.conf")" = mix ]
[ "$LUOSHU_UPDATE_REBUILD_REQUIRED" = true ]
[ -s "$NEW/system/fonts/Roboto-Regular.ttf" ]
[ -s "$NEW/vendor/fonts/BadBoot.ttf" ]
grep -q '^mode=preserve-current$' "$NEW/config/font-payload-rebuild-pending.conf"
grep -q '^font=mix$' "$NEW/config/font-payload-rebuild-pending.conf"

# Same-schema migration also preserves the validated payload and needs no
# explicit engine migration marker.
rm -rf "$NEW"
mkdir -p "$NEW/config" "$NEW/system/fonts"
printf 'id=LuoShu\nversion=v4.0.0\nversionCode=40000\n' > "$NEW/module.prop"
printf 'schema=%s\n' "$LUOSHU_PAYLOAD_SCHEMA_CURRENT" > "$OLD/config/font-payload-schema.conf"
luoshu_migrate_active_install "$OLD" "$NEW"
[ "$(cat "$NEW/config/active_font.conf")" = mix ]
[ "$LUOSHU_UPDATE_REBUILD_REQUIRED" = false ]
[ -s "$NEW/system/fonts/Roboto-Regular.ttf" ]
[ -s "$NEW/vendor/fonts/BadBoot.ttf" ]
[ ! -f "$NEW/config/font-payload-rebuild-pending.conf" ]

# Regression guard for the real-device v4.0.0 installer stall: customize.sh may
# report a deferred rebuild, but it must not source the hotfix override nor call
# any synchronous update rebuild worker while the module is being flashed.
! grep -q 'module_update_hotfix_v4.sh' "$ROOT/customize.sh"
! grep -q 'luoshu_v4_update_rebuild_selected' "$ROOT/customize.sh"
! grep -q 'font_mix.sh.*worker' "$ROOT/customize.sh"
! grep -q 'font_manager.sh.*action switch' "$ROOT/customize.sh"
grep -q '不会同步重建字体' "$ROOT/customize.sh"
! grep -q "printf 'default\\n'.*active_font.conf" "$ROOT/customize.sh"

echo 'v4 update preserve test: ok'
