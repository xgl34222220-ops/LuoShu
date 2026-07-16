#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VERSION=$(sed -n 's/^version=//p' "$ROOT/module.prop" | head -n1 | sed 's#[ /]#-#g')
OUT_DIR="$ROOT/dist"; STAGE="$OUT_DIR/LuoShu"; ZIP="$OUT_DIR/LuoShu-${VERSION}.zip"
sh "$ROOT/scripts/check.sh"
rm -rf "$STAGE"; mkdir -p "$STAGE" "$OUT_DIR"
for path in common config fonts system webroot customize.sh module.prop post-fs-data.sh service.sh uninstall.sh magic 兼容与目录说明.txt; do cp -R "$ROOT/$path" "$STAGE/"; done
sh "$ROOT/scripts/prepare_v14_package.sh" "$STAGE"
sh "$ROOT/scripts/prepare_webui.sh" "$STAGE/webroot"
sh "$ROOT/scripts/prepare_mount_compat.sh" "$STAGE"
find "$STAGE" -type f -name '*.log' -delete
rm -rf "$STAGE/webroot/fonts" "$STAGE/webroot/emoji" "$STAGE/logs" "$STAGE/backup" "$STAGE/config/recovery"
mkdir -p "$STAGE/webroot/fonts" "$STAGE/webroot/emoji"
rm -f "$STAGE/config/webui_font_list.json" "$STAGE/config/webui_font_list.key" "$STAGE/config/recent_fonts.conf" "$STAGE/config/previous_font.conf" "$STAGE/config/switch_task.conf" "$STAGE/config/mix_task.conf" "$STAGE/config/font_mix.conf" "$STAGE/config/emoji_task.conf" "$STAGE/config/font_weight.conf" "$STAGE/config/font_weight_original.conf" "$STAGE/config/font_weight_reboot_required.conf" "$STAGE/config/mount_compat.conf"
chmod 755 "$STAGE/customize.sh" "$STAGE/post-fs-data.sh" "$STAGE/service.sh" "$STAGE/uninstall.sh"
find "$STAGE/common" -type f -exec chmod 755 {} \;
chmod 755 "$STAGE/system/bin/luoshud"
test ! -e "$STAGE/skip_mount"; test ! -e "$STAGE/skip_mountify"
grep -q 'common/mount_compat.sh' "$STAGE/common/font_manager.sh"
grep -q 'v14.js?v=14000' "$STAGE/webroot/index.html"; grep -q 'v14.css?v=14000' "$STAGE/webroot/index.html"
! grep -q 'stability.js?v=' "$STAGE/webroot/index.html"; ! grep -q 'stability-critical-style' "$STAGE/webroot/index.html"
test -f "$STAGE/common/font_mix.sh"; test -f "$STAGE/common/v14_mix.sh"
grep -q '^version=v14$' "$STAGE/module.prop"; grep -q '^description=Android 全局字体管理，当前字体：系统默认字体$' "$STAGE/module.prop"
rm -f "$ZIP"; (cd "$STAGE" && zip -qr "$ZIP" .); sha256sum "$ZIP" > "$ZIP.sha256"; echo "Built: $ZIP"
