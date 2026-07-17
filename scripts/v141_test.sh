#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-v141); trap 'rm -rf "$TMP"' EXIT HUP INT TERM

# 1. 事务提交与失败保护。
MODDIR="$TMP/txn-module"; mkdir -p "$MODDIR/common" "$MODDIR/system/fonts"
cp "$ROOT/common/font_transaction.sh" "$MODDIR/common/"
printf old-data > "$MODDIR/system/fonts/old.ttf"
. "$MODDIR/common/font_transaction.sh"
font_validate(){ return 0; }
luoshu_txn_begin test; dd if=/dev/zero of="$LUOSHU_TXN_FONTS/new.ttf" bs=4096 count=2 2>/dev/null; luoshu_txn_verify font; luoshu_txn_commit
test -f "$MODDIR/system/fonts/new.ttf"; test ! -e "$MODDIR/system/fonts/old.ttf"
luoshu_txn_begin failed; printf bad > "$LUOSHU_TXN_FONTS/bad.ttf"; if luoshu_txn_verify font; then exit 1; fi; test -f "$MODDIR/system/fonts/new.ttf"; luoshu_txn_abort

# 2. 预览缓存只保留最近 3 个字体家族，且只写 module.prop 指定目录。
PCMOD="$TMP/preview-module"; PUB="$TMP/public"; mkdir -p "$PCMOD/common" "$PCMOD/webroot_v14103" "$PCMOD/webroot/fonts" "$PUB/fonts"
cp "$ROOT/common/preview_cache.sh" "$ROOT/common/util_functions.sh" "$PCMOD/common/"
printf 'id=LuoShu\nwebroot=webroot_v14103\n' > "$PCMOD/module.prop"
printf stale > "$PCMOD/webroot/fonts/stale.ttf"
for fam in A B C D; do dd if=/dev/zero of="$PUB/fonts/${fam}-Regular.ttf" bs=4096 count=2 2>/dev/null; MODDIR="$PCMOD" LUOSHU_PUBLIC_DIR="$PUB" sh "$PCMOD/common/preview_cache.sh" prepare "$fam" >/dev/null; done
test ! -d "$PCMOD/webroot/fonts"
test "$(wc -l < "$PCMOD/config/preview_cache.conf")" -eq 3
find "$PCMOD/webroot_v14103/fonts" -type f | grep -q .
_storage=$(MODDIR="$PCMOD" LUOSHU_PUBLIC_DIR="$PUB" sh "$PCMOD/common/preview_cache.sh" storage)
printf '%s' "$_storage" | grep -q '"actualBytes"'; printf '%s' "$_storage" | grep -q '"apparentBytes"'

# 3. 字体组合记录精确源路径；未修改槽位不再按家族名重新猜文件；缺失字重复用基础锚点。
MX="$TMP/mix-module"; MPUB="$TMP/mix-public"; mkdir -p "$MX/common" "$MX/system/fonts" "$MX/config" "$MX/logs" "$MPUB/fonts"
cp "$ROOT/common/font_mix.sh" "$ROOT/common/font_transaction.sh" "$MX/common/"
cat > "$MX/common/util_functions.sh" <<'EOS'
detect_font_family(){ n="${1%.*}"; echo "${n%-*}"; }
detect_font_weight(){ case "$1" in *Bold*) echo bold;; *Light*) echo light;; *) echo regular;; esac; }
get_weight_file(){ f="$1"; w="$2"; for p in "$USER_FONTS_DIR"/"$f"-*.ttf; do [ -f "$p" ] || continue; [ "$(detect_font_weight "$(basename "$p")")" = "$w" ] && { echo "$p"; return; }; done; }
check_coloros(){ IS_COLOROS=true; }
check_hyperos(){ IS_HYPEROS=false; }
get_all_coloros_names(){ echo 'SysFont-Hans-Regular SysSans-En-Regular DINPro-Regular'; }
EOS
cat > "$MX/common/font_check.sh" <<'EOS'
font_validate(){ return 0; }
EOS
cat > "$MX/common/rom_adapters.sh" <<'EOS'
_font_store_reset(){ rm -rf "$1/.luoshu-font-store"; mkdir -p "$1/.luoshu-font-store"; }
_font_anchor(){ cp -f "$1" "$2/.luoshu-font-store/$3.font"; echo "$2/.luoshu-font-store/$3.font"; }
_font_alias(){ rm -f "$2"; ln "$1" "$2" 2>/dev/null || cp -f "$1" "$2"; }
_rom_exact_target_exists(){ return 0; }
link_or_copy_font(){ rm -f "$2"; ln "$1" "$2" 2>/dev/null || cp -f "$1" "$2"; }
EOS
printf 'luoshu_sync_mount_payload(){ :; }\n' > "$MX/common/mount_compat.sh"
for spec in A-Bold A-Regular B-Regular C-Regular; do dd if=/dev/zero of="$MPUB/fonts/$spec.ttf" bs=4096 count=2 2>/dev/null; done
MODDIR="$MX" LUOSHU_PUBLIC_DIR="$MPUB" sh "$MX/common/font_mix.sh" apply A B C "$MPUB/fonts/A-Bold.ttf" "$MPUB/fonts/B-Regular.ttf" "$MPUB/fonts/C-Regular.ttf"
grep -q "^cjk_path=$MPUB/fonts/A-Bold.ttf$" "$MX/config/font_mix.conf"
test "$(find "$MX/system/fonts/.luoshu-font-store" -type f | wc -l)" -le 4
rm -f "$MX/config/text_reboot_required.conf"
MODDIR="$MX" LUOSHU_PUBLIC_DIR="$MPUB" sh "$MX/common/font_mix.sh" apply A B C '' '' ''
grep -q "^cjk_path=$MPUB/fonts/A-Bold.ttf$" "$MX/config/font_mix.conf"

# 4. APatch source customize.sh 后，外层安装器必须继续执行。
APMOD="$TMP/apatch-module"; mkdir -p "$APMOD/system/bin" "$APMOD/system/fonts" "$APMOD/webroot_v14103/fonts" "$APMOD/config" "$APMOD/logs"
cp -R "$ROOT/common" "$APMOD/common"; cp "$ROOT/module.prop" "$APMOD/module.prop"; cp "$ROOT/customize.sh" "$APMOD/customize.sh"; cp "$ROOT/post-fs-data.sh" "$ROOT/post-mount.sh" "$ROOT/service.sh" "$ROOT/uninstall.sh" "$APMOD/"
sh -c 'ui_print(){ :; }; MODPATH="$1"; APATCH=true; KERNELPATCH=false; . "$MODPATH/customize.sh"; printf source-returned > "$MODPATH/source-returned"' sh "$APMOD"
test -f "$APMOD/source-returned"; test -f "$APMOD/config/install_environment.conf"; test ! -e "$APMOD/magic"; test ! -e "$APMOD/remove"

PATCH_STAGE="$TMP/patched-stage"; mkdir -p "$PATCH_STAGE/common" "$PATCH_STAGE/webroot"
cp "$ROOT/common/font_manager.sh" "$PATCH_STAGE/common/font_manager.sh"
for f in app.js v14.js v14.css; do cp "$ROOT/webroot/$f" "$PATCH_STAGE/webroot/$f"; done
sh "$ROOT/scripts/patch_test3_runtime.sh" "$PATCH_STAGE"
grep -q 'resolve_slot_file' "$ROOT/common/font_mix.sh"; grep -q 'preview_prepare' "$PATCH_STAGE/common/font_manager.sh"; grep -q '角色检测' "$PATCH_STAGE/webroot/v14.js"; grep -q 'webroot_v14103' "$ROOT/module.prop"
echo 'LuoShu v14.1 Test3 behavior checks passed.'
