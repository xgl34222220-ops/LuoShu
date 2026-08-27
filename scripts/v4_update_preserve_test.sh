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
. "$ROOT/common/module_update_hotfix_v4.sh"

luoshu_migrate_active_install "$OLD" "$NEW"
[ "$(cat "$NEW/config/active_font.conf")" = mix ]
[ "$LUOSHU_UPDATE_REBUILD_REQUIRED" = true ]
[ ! -f "$NEW/system/fonts/Roboto-Regular.ttf" ]
[ ! -f "$NEW/vendor/fonts/BadBoot.ttf" ]
grep -q '^mode=preserve-selection$' "$NEW/config/font-payload-rebuild-pending.conf"
grep -q '^font=mix$' "$NEW/config/font-payload-rebuild-pending.conf"

# Same-schema migration still preserves an already validated payload.
rm -rf "$NEW"
mkdir -p "$NEW/config" "$NEW/system/fonts"
printf 'id=LuoShu\nversion=v4.0.0\nversionCode=40000\n' > "$NEW/module.prop"
printf 'schema=%s\n' "$LUOSHU_PAYLOAD_SCHEMA_CURRENT" > "$OLD/config/font-payload-schema.conf"
luoshu_migrate_active_install "$OLD" "$NEW"
[ "$(cat "$NEW/config/active_font.conf")" = mix ]
[ "$LUOSHU_UPDATE_REBUILD_REQUIRED" = false ]
[ -s "$NEW/system/fonts/Roboto-Regular.ttf" ]
[ -s "$NEW/vendor/fonts/BadBoot.ttf" ]

grep -q 'luoshu_v4_update_rebuild_selected' "$ROOT/customize.sh"
grep -q '未切换为系统默认字体' "$ROOT/customize.sh"
! grep -q "printf 'default\\n'.*active_font.conf" "$ROOT/customize.sh"

echo 'v4 update preserve test: ok'
