#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-mount)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MODULE="$TMP/modules/LuoShu"
META="$TMP/meta"
mkdir -p "$MODULE/common" "$MODULE/system/fonts" "$MODULE/product/fonts" "$MODULE/config" "$MODULE/logs" "$META"
cp "$ROOT/common/mount_compat.sh" "$MODULE/common/mount_compat.sh"
printf 'id=LuoShu\nversion=v2.0.0\nversionCode=20000\n' > "$MODULE/module.prop"
printf 'font-a' > "$MODULE/system/fonts/Roboto-Regular.ttf"
printf 'product-a' > "$MODULE/product/fonts/Test.ttf"

MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=meta-overlayfs LUOSHU_META_TEST_ROOT="$META" sh -c '
    . "$MODDIR/common/mount_compat.sh"
    luoshu_sync_mount_payload Demo
'

test -f "$META/LuoShu/system/fonts/Roboto-Regular.ttf"
test -f "$META/LuoShu/product/fonts/Test.ttf"
grep -q 'font-a' "$META/LuoShu/system/fonts/Roboto-Regular.ttf"
grep -q '^engine=meta-overlayfs$' "$MODULE/config/mount_compat.conf"
grep -q '^state=prepared$' "$MODULE/config/mount_compat.conf"
test -s "$MODULE/system/etc/luoshu/mount-probe.conf"

# A second real-content update must replace the whole partition, not retain stale files.
rm -f "$MODULE/system/fonts/Roboto-Regular.ttf"
printf stale > "$META/LuoShu/system/fonts/Old.ttf"
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=meta-overlayfs LUOSHU_META_TEST_ROOT="$META" sh -c '
    . "$MODDIR/common/mount_compat.sh"
    luoshu_sync_mount_payload Demo
'
test ! -e "$META/LuoShu/system/fonts/Old.ttf"
test ! -e "$META/LuoShu/system/fonts/Roboto-Regular.ttf"
test -s "$META/LuoShu/system/etc/luoshu/mount-probe.conf"

# Direct-source engines must not create a second module tree.
rm -rf "$META/LuoShu"
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=mountify LUOSHU_META_TEST_ROOT="$META" sh -c '
    . "$MODDIR/common/mount_compat.sh"
    luoshu_sync_mount_payload Demo
'
test ! -e "$META/LuoShu"
grep -q '^engine=mountify$' "$MODULE/config/mount_compat.conf"

# Runtime syncing remains transaction-only. Never mirror from early boot scripts.
grep -q 'common/mount_compat.sh' "$ROOT/common/font_mix.sh"
grep -q 'luoshu_sync_mount_payload' "$ROOT/common/font_mix.sh"
! grep -q 'luoshu_sync_mount_payload' "$ROOT/post-fs-data.sh"
! grep -q 'luoshu_sync_mount_payload' "$ROOT/service.sh"
! grep -q 'prepare_mount_compat.sh' "$ROOT/scripts/build.sh"

# Release packages must not contain markers that exclude LuoShu from mount planning.
STAGE="$TMP/stage"
mkdir -p "$STAGE"
cp -R "$ROOT/." "$STAGE/"
rm -rf "$STAGE/.git" "$STAGE/dist" "$STAGE/common/python" 2>/dev/null || true
! find "$STAGE" -type f \( -name skip_mount -o -name skip_mountify \) | grep -q .
sh -n "$ROOT/common/font_mix.sh"
sh -n "$ROOT/post-fs-data.sh"
sh -n "$ROOT/service.sh"

echo 'LuoShu metamodule compatibility checks passed.'
