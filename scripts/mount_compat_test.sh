#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-meta)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MODULE="$TMP/modules/LuoShu"
META="$TMP/meta"
mkdir -p "$MODULE/common" "$MODULE/system/fonts" "$MODULE/product/fonts" "$MODULE/config" "$MODULE/logs" "$META"
cp "$ROOT/common/meta_overlay_compat" "$MODULE/common/meta_overlay_compat"
printf 'id=LuoShu\nversion=v13.5 Stable Hotfix3\nversionCode=13503\n' > "$MODULE/module.prop"
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

rm -f "$MODULE/system/fonts/Roboto-Regular.ttf"
printf stale > "$META/LuoShu/system/fonts/Old.ttf"
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ROOT="$META" sh -c '
    . "$MODDIR/common/meta_overlay_compat"
    luoshu_sync_meta_payload
'
test ! -e "$META/LuoShu/system/fonts/Old.ttf"
test ! -e "$META/LuoShu/system/fonts/Roboto-Regular.ttf"

STAGE="$TMP/stage"
mkdir -p "$STAGE/common"
cp "$ROOT/common/font_manager.sh" "$STAGE/common/font_manager.sh"
cp "$ROOT/common/meta_overlay_compat" "$STAGE/common/meta_overlay_compat"
cp "$ROOT/post-fs-data.sh" "$STAGE/post-fs-data.sh"
cp "$ROOT/service.sh" "$STAGE/service.sh"
cp "$ROOT/customize.sh" "$STAGE/customize.sh"
cp "$ROOT/common/stability.sh" "$STAGE/common/stability.sh"
printf legacy > "$STAGE/common/play_font_bridge.sh"
printf legacy > "$STAGE/common/wechat_xweb_bridge.sh"
printf legacy > "$STAGE/common/mount_compat.sh"
sh "$ROOT/scripts/prepare_mount_compat.sh" "$STAGE"
grep -q 'common/meta_overlay_compat' "$STAGE/common/font_manager.sh"
test "$(grep -c 'luoshu_sync_meta_payload' "$STAGE/common/font_manager.sh")" -ge 2
grep -q 'luoshu_sync_meta_payload' "$STAGE/post-fs-data.sh"
grep -q 'luoshu_sync_meta_payload' "$STAGE/service.sh"
test ! -e "$STAGE/common/play_font_bridge.sh"
test ! -e "$STAGE/common/wechat_xweb_bridge.sh"
test ! -e "$STAGE/common/mount_compat.sh"
sh -n "$STAGE/common/font_manager.sh"
sh -n "$STAGE/post-fs-data.sh"
sh -n "$STAGE/service.sh"
sh -n "$STAGE/common/meta_overlay_compat"

echo 'LuoShu meta compatibility checks passed.'
