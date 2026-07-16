#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VERSION=$(sed -n 's/^version=//p' "$ROOT/module.prop" | head -n 1 | sed 's#[ /]#-#g')
OUT_DIR="$ROOT/dist"
STAGE="$OUT_DIR/LuoShu"
ZIP="$OUT_DIR/LuoShu-${VERSION}.zip"

sh "$ROOT/scripts/check.sh"
rm -rf "$STAGE"
mkdir -p "$STAGE" "$OUT_DIR"

for path in common config fonts system webroot customize.sh module.prop post-fs-data.sh service.sh uninstall.sh magic 兼容与目录说明.txt; do
    cp -R "$ROOT/$path" "$STAGE/"
done

sh "$ROOT/scripts/prepare_webui.sh" "$STAGE/webroot"
sh "$ROOT/scripts/prepare_mount_compat.sh" "$STAGE"

find "$STAGE" -type f -name '*.log' -delete
rm -rf "$STAGE/webroot/fonts" "$STAGE/webroot/emoji" "$STAGE/logs" "$STAGE/backup" "$STAGE/config/recovery" "$STAGE/direct_map"
mkdir -p "$STAGE/webroot/fonts" "$STAGE/webroot/emoji" "$STAGE/config/recovery"
rm -f "$STAGE/config/webui_font_list.json" \
      "$STAGE/config/webui_font_list.key" \
      "$STAGE/config/recent_fonts.conf" \
      "$STAGE/config/previous_font.conf" \
      "$STAGE/config/switch_task.conf" \
      "$STAGE/config/emoji_task.conf" \
      "$STAGE/config/font_weight.conf" \
      "$STAGE/config/font_weight_original.conf" \
      "$STAGE/config/font_weight_reboot_required.conf" \
      "$STAGE/config/mount_compat.conf" \
      "$STAGE/config/meta_compat.conf" \
      "$STAGE/config/direct_map_status.conf"

chmod 755 "$STAGE/customize.sh" "$STAGE/post-fs-data.sh" "$STAGE/service.sh" "$STAGE/uninstall.sh"
find "$STAGE/common" -type f -exec chmod 755 {} \;
chmod 755 "$STAGE/system/bin/luoshud"

test ! -e "$STAGE/skip_mount"
test ! -e "$STAGE/skip_mountify"
test -f "$STAGE/common/meta_overlay_compat"
test -f "$STAGE/common/font_report"
test -f "$STAGE/common/db_engine"
test -f "$STAGE/config/mount_mode.conf"
test ! -e "$STAGE/common/mount_compat.sh"
test ! -e "$STAGE/common/font_report.sh"
test ! -e "$STAGE/common/play_font_bridge.sh"
test ! -e "$STAGE/common/wechat_xweb_bridge.sh"
grep -q 'common/meta_overlay_compat' "$STAGE/common/font_manager.sh"
grep -q 'luoshu_db_use_direct' "$STAGE/common/rom_adapters.sh"
grep -q 'db_engine.*apply' "$STAGE/post-fs-data.sh"
grep -q 'db_engine.*verify' "$STAGE/service.sh"
grep -q 'command mkdir' "$STAGE/customize.sh"
grep -q 'stability-critical-style' "$STAGE/webroot/index.html"
! grep -R -n --include='*.sh' -E '(^|[;&|[:space:]])(mount|umount|mountpoint)([[:space:]]|$)|/proc/mounts' "$STAGE"

rm -f "$ZIP"
(cd "$STAGE" && zip -qry "$ZIP" .)
sha256sum "$ZIP" > "$ZIP.sha256"
echo "Built: $ZIP"
