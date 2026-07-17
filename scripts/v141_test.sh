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

grep -q 'APatch.*source' "$ROOT/customize.sh"
! grep -q '^exit 0$' "$ROOT/customize.sh"
! grep -q 'touch .*magic' "$ROOT/customize.sh"
grep -q 'post-fs-data.*阻塞' "$ROOT/post-fs-data.sh"
grep -q 'font_transaction.sh' "$ROOT/common/font_switch_v141.sh"
grep -q 'font_transaction.sh' "$ROOT/common/font_mix.sh"
grep -q '默认卸载模块' "$ROOT/webroot/v14_1.js"
grep -q 'digitIndependent' "$ROOT/common/device_capabilities.sh"
echo 'LuoShu v14.1 behavior checks passed.'
