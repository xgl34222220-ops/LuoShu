#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT INT TERM

MODULES="$TMP/modules"
MODULES_UPDATE="$TMP/modules_update"
META_MNT="$TMP/metamodule/mnt"
CONTENT_BASE="$TMP/content"
MAGIC_CONFIG="$TMP/magic_mount/config.toml"
MODDIR="$MODULES/LuoShu"

mkdir -p \
  "$MODDIR/logs" \
  "$MODDIR/config" \
  "$MODULES/OtherModule" \
  "$MODULES_UPDATE/LuoShu/system/fonts" \
  "$META_MNT/LuoShu/product/fonts" \
  "$CONTENT_BASE/LuoShu/system/fonts" \
  "${MAGIC_CONFIG%/*}"

cp "$ROOT/uninstall.sh" "$MODDIR/uninstall.sh"
printf '%s\n' 'version=v-test' > "$MODDIR/module.prop"
printf '%s\n' 'old log' > "$MODDIR/logs/fontswitch.log"
printf '%s\n' 'keep sibling' > "$MODULES/OtherModule/module.prop"
printf '%s\n' 'partitions = ["system", "product"]' > "$MAGIC_CONFIG"
printf '%s\n' 'backup' > "$MAGIC_CONFIG.luoshu.bak"
printf '%s\n' '999999' > "$MAGIC_CONFIG.luoshu.lock"
printf '%s\n' 'temp' > "$MAGIC_CONFIG.luoshu.123"

LUOSHU_MODULES_DIR="$MODULES" \
LUOSHU_MODULES_UPDATE_DIR="$MODULES_UPDATE" \
LUOSHU_METAMODULE_MNT="$META_MNT" \
LUOSHU_MAGIC_MOUNT_CONFIG="$MAGIC_CONFIG" \
MODULE_CONTENT_DIR="$CONTENT_BASE" \
sh "$MODDIR/uninstall.sh"

[ ! -e "$MODDIR" ]
[ ! -e "$MODULES_UPDATE/LuoShu" ]
[ ! -e "$META_MNT/LuoShu" ]
[ ! -e "$CONTENT_BASE/LuoShu" ]
[ -f "$MODULES/OtherModule/module.prop" ]
[ -f "$MAGIC_CONFIG" ]
[ ! -e "$MAGIC_CONFIG.luoshu.bak" ]
[ ! -e "$MAGIC_CONFIG.luoshu.lock" ]
[ ! -e "$MAGIC_CONFIG.luoshu.123" ]
grep -q 'partitions = \["system", "product"\]' "$MAGIC_CONFIG"

# 卸载脚本不得再次在模块目录中创建 logs 或任何文件。
[ ! -d "$MODULES/LuoShu/logs" ]

echo 'LuoShu uninstall cleanup checks passed.'
