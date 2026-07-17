#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-v141)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MODDIR="$TMP/module"; mkdir -p "$MODDIR/common" "$MODDIR/system/fonts"
cp "$ROOT/common/font_transaction.sh" "$MODDIR/common/"
printf old-data > "$MODDIR/system/fonts/old.ttf"
. "$MODDIR/common/font_transaction.sh"
font_validate(){ return 0; }
luoshu_txn_begin test
# 生成一个超过 4 KiB 的可控测试文件。
dd if=/dev/zero of="$LUOSHU_TXN_FONTS/new.ttf" bs=4096 count=2 2>/dev/null
luoshu_txn_verify font
luoshu_txn_commit
test -f "$MODDIR/system/fonts/new.ttf"
test ! -e "$MODDIR/system/fonts/old.ttf"

# 验证失败不得破坏当前有效目录。
luoshu_txn_begin failed
printf bad > "$LUOSHU_TXN_FONTS/bad.ttf"
if luoshu_txn_verify font; then echo 'tiny transaction should fail' >&2; exit 1; fi
test -f "$MODDIR/system/fonts/new.ttf"
luoshu_txn_abort

# 模拟 APatch source customize.sh：安装脚本结束后外层安装器必须继续执行。
APMOD="$TMP/apatch-module"
mkdir -p "$APMOD/system/bin" "$APMOD/system/fonts" "$APMOD/webroot/fonts" "$APMOD/webroot_v141/fonts" "$APMOD/config" "$APMOD/logs"
cp -R "$ROOT/common" "$APMOD/common"
cp -R "$ROOT/webroot/." "$APMOD/webroot/"
cp -R "$ROOT/webroot/." "$APMOD/webroot_v141/"
cp "$ROOT/module.prop" "$APMOD/module.prop"
cp "$ROOT/customize.sh" "$APMOD/customize.sh"
cp "$ROOT/post-fs-data.sh" "$ROOT/post-mount.sh" "$ROOT/service.sh" "$ROOT/uninstall.sh" "$APMOD/"
sh -c '
    ui_print(){ :; }
    MODPATH="$1"; APATCH=true; KERNELPATCH=false
    . "$MODPATH/customize.sh"
    printf source-returned > "$MODPATH/source-returned"
' sh "$APMOD"
test -f "$APMOD/source-returned"
test -f "$APMOD/config/install_environment.conf"
test ! -e "$APMOD/magic"
test ! -e "$APMOD/remove"

grep -q 'APatch.*source' "$ROOT/customize.sh"
! grep -q '^exit 0$' "$ROOT/customize.sh"
! grep -q 'touch .*magic' "$ROOT/customize.sh"
grep -q 'post-fs-data.*阻塞' "$ROOT/post-fs-data.sh"
grep -q 'font_transaction.sh' "$ROOT/common/font_switch_v141.sh"
grep -q 'font_transaction.sh' "$ROOT/common/font_mix.sh"
grep -q '默认卸载模块' "$ROOT/customize.sh"
grep -q '^webroot=webroot_v141$' "$ROOT/module.prop"
test ! -e "$ROOT/webroot/v14_1.js"
test ! -e "$ROOT/webroot/v14_1.css"
grep -q 'digitIndependent' "$ROOT/common/device_capabilities.sh"
echo 'LuoShu v14.1 behavior checks passed.'
