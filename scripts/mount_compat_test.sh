#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-meta)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MODULE="$TMP/modules/LuoShu"
META="$TMP/meta"
mkdir -p "$MODULE/common" "$MODULE/system/fonts" "$MODULE/product/fonts" "$MODULE/config" "$MODULE/logs" "$META"
cp "$ROOT/common/meta_overlay_compat" "$MODULE/common/meta_overlay_compat"
printf 'id=LuoShu\nversion=v13.6 Beta4\nversionCode=13604\n' > "$MODULE/module.prop"
printf 'font-a' > "$MODULE/system/fonts/Roboto-Regular.ttf"
printf 'product-a' > "$MODULE/product/fonts/Test.ttf"

MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ROOT="$META" sh -c '
    . "$MODDIR/common/meta_overlay_compat"
    luoshu_sync_meta_payload
'

test -f "$META/LuoShu/system/fonts/Roboto-Regular.ttf"
test -f "$META/LuoShu/product/fonts/Test.ttf"
grep -q 'font-a' "$META/LuoShu/system/fonts/Roboto-Regular.ttf"
grep -q '^engine=test-meta$' "$MODULE/config/meta_compat.conf"

# Only LuoShu's own stale marker may be cleared. This lets Hybrid Mount retry
# without modifying another module or the meta engine's global state.
printf stale > "$MODULE/mount.error"
MODDIR="$MODULE" MODULE_DIR="$MODULE" sh -c '
    . "$MODDIR/common/meta_overlay_compat"
    luoshu_clear_own_meta_errors
'
test ! -e "$MODULE/mount.error"
OTHER="$TMP/modules/OtherModule"
mkdir -p "$OTHER"
printf keep > "$OTHER/mount.error"
MODDIR="$OTHER" MODULE_DIR="$OTHER" sh -c '
    . "$1/common/meta_overlay_compat"
    luoshu_clear_own_meta_errors
' sh "$MODULE"
test -e "$OTHER/mount.error"

rm -f "$MODULE/system/fonts/Roboto-Regular.ttf"
printf stale > "$META/LuoShu/system/fonts/Old.ttf"
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ROOT="$META" sh -c '
    . "$MODDIR/common/meta_overlay_compat"
    luoshu_sync_meta_payload
'
test ! -e "$META/LuoShu/system/fonts/Old.ttf"
test ! -e "$META/LuoShu/system/fonts/Roboto-Regular.ttf"

# A Direct Bind module with no partition payload must remove old staging and
# must not recreate an empty content directory.
rm -rf "$MODULE/system" "$MODULE/product"
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ROOT="$META" sh -c '
    . "$MODDIR/common/meta_overlay_compat"
    luoshu_sync_meta_payload
'
test ! -e "$META/LuoShu"

STAGE="$TMP/stage"
mkdir -p "$STAGE/common" "$STAGE/config"
cp "$ROOT/common/font_manager.sh" "$STAGE/common/font_manager.sh"
cp "$ROOT/common/rom_adapters.sh" "$STAGE/common/rom_adapters.sh"
cp "$ROOT/common/meta_overlay_compat" "$STAGE/common/meta_overlay_compat"
cp "$ROOT/common/db_engine" "$STAGE/common/db_engine"
cp "$ROOT/post-fs-data.sh" "$STAGE/post-fs-data.sh"
cp "$ROOT/service.sh" "$STAGE/service.sh"
cp "$ROOT/customize.sh" "$STAGE/customize.sh"
cp "$ROOT/uninstall.sh" "$STAGE/uninstall.sh"
cp "$ROOT/common/stability.sh" "$STAGE/common/stability.sh"
printf direct > "$STAGE/config/mount_mode.conf"
printf legacy > "$STAGE/common/play_font_bridge.sh"
printf legacy > "$STAGE/common/wechat_xweb_bridge.sh"
printf legacy > "$STAGE/common/mount_compat.sh"
sh "$ROOT/scripts/prepare_mount_compat.sh" "$STAGE"

grep -q 'common/meta_overlay_compat' "$STAGE/common/font_manager.sh"
test "$(grep -c 'luoshu_sync_meta_payload' "$STAGE/common/font_manager.sh")" -ge 2
grep -q 'luoshu_sync_meta_payload' "$STAGE/post-fs-data.sh"
test ! -e "$STAGE/common/play_font_bridge.sh"
test ! -e "$STAGE/common/wechat_xweb_bridge.sh"
test ! -e "$STAGE/common/mount_compat.sh"
grep -q 'luoshu_db_use_direct' "$STAGE/common/rom_adapters.sh"
grep -q 'db_engine.*apply' "$STAGE/post-fs-data.sh"
grep -q 'db_engine.*verify' "$STAGE/service.sh"
grep -q 'command mkdir' "$STAGE/customize.sh"
grep -q 'command mkdir' "$STAGE/post-fs-data.sh"
grep -q 'command mkdir' "$STAGE/uninstall.sh"

# Traditional mode must remain safe: targets are ordinary files/hard links, never symbolic links.
mkdir -p "$STAGE/system/fonts/.luoshu-font-store"
printf '0123456789font-data' > "$STAGE/system/fonts/.luoshu-font-store/regular.font"
STAGE="$STAGE" LUOSHU_DB_MODE=module sh -c '
    MODULE_DIR="$STAGE"
    . "$STAGE/common/rom_adapters.sh"
    anchor="$STAGE/system/fonts/.luoshu-font-store/regular.font"
    _font_alias "$anchor" "$STAGE/system/fonts/SysFont-Regular.ttf"
    test -f "$STAGE/system/fonts/SysFont-Regular.ttf"
    test ! -L "$STAGE/system/fonts/SysFont-Regular.ttf"
    test "$(stat -c %i "$anchor")" = "$(stat -c %i "$STAGE/system/fonts/SysFont-Regular.ttf")"
'

sh -n "$STAGE/common/font_manager.sh"
sh -n "$STAGE/common/rom_adapters.sh"
sh -n "$STAGE/common/db_engine"
sh -n "$STAGE/post-fs-data.sh"
sh -n "$STAGE/service.sh"
sh -n "$STAGE/customize.sh"
sh -n "$STAGE/uninstall.sh"
sh -n "$STAGE/common/meta_overlay_compat"

echo 'LuoShu compatibility checks passed.'
