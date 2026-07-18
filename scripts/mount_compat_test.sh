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

# 当前安全架构只允许在字体事务成功后同步元模块镜像。
# 禁止重新向 post-fs-data/service 注入早期全量同步，避免半成品字体在开机阶段
# 被元模块挂载后造成 SystemUI 黑屏或应用批量崩溃。
grep -q 'common/mount_compat.sh' "$ROOT/common/font_mix.sh"
grep -q 'luoshu_sync_mount_payload' "$ROOT/common/font_mix.sh"
! grep -q 'luoshu_sync_mount_payload' "$ROOT/post-fs-data.sh"
! grep -q 'luoshu_sync_mount_payload' "$ROOT/service.sh"
! grep -q 'prepare_mount_compat.sh' "$ROOT/scripts/build.sh"

# 发布包不得携带会让 Mountify/Hybrid Mount 跳过模块的标记。
STAGE="$TMP/stage"
mkdir -p "$STAGE"
cp -R "$ROOT/." "$STAGE/"
rm -rf "$STAGE/.git" "$STAGE/dist" "$STAGE/common/python" 2>/dev/null || true
! find "$STAGE" -type f \( -name skip_mount -o -name skip_mountify \) | grep -q .
sh -n "$ROOT/common/font_mix.sh"
sh -n "$ROOT/post-fs-data.sh"
sh -n "$ROOT/service.sh"

echo 'LuoShu mount compatibility checks passed.'
