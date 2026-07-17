#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-mount); trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MODULE="$TMP/modules/LuoShu"; META="$TMP/meta"
mkdir -p "$MODULE/common" "$MODULE/system/fonts" "$MODULE/product/fonts" "$MODULE/config" "$MODULE/logs" "$META"
cp "$ROOT/common/mount_compat.sh" "$MODULE/common/mount_compat.sh"
printf 'id=LuoShu\nversion=v14.1 Test3\nversionCode=14103\n' > "$MODULE/module.prop"
printf 'font-a' > "$MODULE/system/fonts/Roboto-Regular.ttf"; printf 'product-a' > "$MODULE/product/fonts/Test.ttf"
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ROOT="$META" sh -c '. "$MODDIR/common/mount_compat.sh"; luoshu_sync_mount_payload'
test -f "$META/LuoShu/system/fonts/Roboto-Regular.ttf"; test -f "$META/LuoShu/product/fonts/Test.ttf"; grep -q '^engine=test-meta$' "$MODULE/config/mount_compat.conf"
rm -f "$MODULE/system/fonts/Roboto-Regular.ttf"; printf stale > "$META/LuoShu/system/fonts/Old.ttf"
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ROOT="$META" sh -c '. "$MODDIR/common/mount_compat.sh"; luoshu_sync_mount_payload'
test ! -e "$META/LuoShu/system/fonts/Old.ttf"; test ! -e "$META/LuoShu/system/fonts/Roboto-Regular.ttf"
STAGE="$TMP/stage"; mkdir -p "$STAGE/common"
for file in font_manager.sh mount_compat.sh font_switch_v141.sh font_mix.sh; do cp "$ROOT/common/$file" "$STAGE/common/$file"; done
cp "$ROOT/post-fs-data.sh" "$STAGE/post-fs-data.sh"; cp "$ROOT/post-mount.sh" "$STAGE/post-mount.sh"; cp "$ROOT/service.sh" "$STAGE/service.sh"
sh "$ROOT/scripts/prepare_mount_compat.sh" "$STAGE"
grep -q 'common/mount_compat.sh' "$STAGE/common/font_manager.sh"; grep -q 'luoshu_sync_mount_payload' "$STAGE/common/font_switch_v141.sh"; grep -q 'luoshu_sync_mount_payload' "$STAGE/common/font_mix.sh"; grep -q 'luoshu_sync_mount_payload' "$STAGE/post-mount.sh"; grep -q 'luoshu_sync_mount_payload' "$STAGE/service.sh"; ! grep -q 'luoshu_sync_mount_payload' "$STAGE/post-fs-data.sh"
for file in "$STAGE/common/font_manager.sh" "$STAGE/common/font_switch_v141.sh" "$STAGE/common/font_mix.sh" "$STAGE/post-fs-data.sh" "$STAGE/post-mount.sh" "$STAGE/service.sh"; do sh -n "$file"; done
echo 'LuoShu v14.1 Test3 mount compatibility checks passed.'
