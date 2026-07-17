#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-mount)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MODULE="$TMP/modules/LuoShu"
META="$TMP/meta"
mkdir -p "$MODULE/common" "$MODULE/system/fonts" "$MODULE/product/fonts" "$MODULE/config" "$MODULE/logs" "$META"
cp "$ROOT/common/mount_compat.sh" "$MODULE/common/mount_compat.sh"
printf 'id=LuoShu\nversion=v13.5 Stable Hotfix1\nversionCode=13501\n' > "$MODULE/module.prop"
printf 'font-a' > "$MODULE/system/fonts/Roboto-Regular.ttf"
printf 'product-a' > "$MODULE/product/fonts/Test.ttf"

MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ROOT="$META" sh -c '
    . "$MODDIR/common/mount_compat.sh"
    luoshu_sync_mount_payload
'

test -f "$META/LuoShu/system/fonts/Roboto-Regular.ttf"
test -f "$META/LuoShu/product/fonts/Test.ttf"
grep -q 'font-a' "$META/LuoShu/system/fonts/Roboto-Regular.ttf"
grep -q '^engine=test-meta$' "$MODULE/config/mount_compat.conf"

# 第二次镜像必须删除元模块内容目录中的旧字体，防止恢复默认后仍挂载旧文件。
rm -f "$MODULE/system/fonts/Roboto-Regular.ttf"
printf stale > "$META/LuoShu/system/fonts/Old.ttf"
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ROOT="$META" sh -c '
    . "$MODDIR/common/mount_compat.sh"
    luoshu_sync_mount_payload
'
test ! -e "$META/LuoShu/system/fonts/Old.ttf"
test ! -e "$META/LuoShu/system/fonts/Roboto-Regular.ttf"

# 验证构建阶段能把钩子注入字体切换、Emoji、post-fs-data 与 service。
STAGE="$TMP/stage"
mkdir -p "$STAGE/common"
cp "$ROOT/common/font_manager.sh" "$STAGE/common/font_manager.sh"
cp "$ROOT/common/mount_compat.sh" "$STAGE/common/mount_compat.sh"
cp "$ROOT/post-fs-data.sh" "$STAGE/post-fs-data.sh"
cp "$ROOT/service.sh" "$STAGE/service.sh"
sh "$ROOT/scripts/prepare_mount_compat.sh" "$STAGE"
grep -q 'common/mount_compat.sh' "$STAGE/common/font_manager.sh"
test "$(grep -c 'luoshu_sync_mount_payload' "$STAGE/common/font_manager.sh")" -ge 2
grep -q 'luoshu_sync_mount_payload' "$STAGE/post-fs-data.sh"
grep -q 'luoshu_sync_mount_payload' "$STAGE/service.sh"
sh -n "$STAGE/common/font_manager.sh"
sh -n "$STAGE/post-fs-data.sh"
sh -n "$STAGE/service.sh"

echo 'LuoShu mount compatibility checks passed.'
