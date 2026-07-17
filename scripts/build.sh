#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VERSION=$(sed -n 's/^version=//p' "$ROOT/module.prop" | head -n1 | sed 's#[ /]#-#g')
WEBROOT_NAME=$(sed -n 's/^webroot=//p' "$ROOT/module.prop" | head -n1)
OUT_DIR="$ROOT/dist"; STAGE="$OUT_DIR/LuoShu"; ZIP="$OUT_DIR/LuoShu-${VERSION}.zip"
rm -rf "$STAGE"; mkdir -p "$STAGE" "$OUT_DIR"
for path in common config fonts system webroot customize.sh module.prop post-fs-data.sh post-mount.sh service.sh uninstall.sh; do cp -R "$ROOT/$path" "$STAGE/"; done
sh "$ROOT/scripts/patch_test3_runtime.sh" "$STAGE"
[ ! -f "$ROOT/兼容与目录说明.txt" ] || cp "$ROOT/兼容与目录说明.txt" "$STAGE/"
sh "$ROOT/scripts/prepare_v14_package.sh" "$STAGE"
sh "$ROOT/scripts/prepare_webui.sh" "$STAGE/webroot"
sh "$ROOT/scripts/prepare_mount_compat.sh" "$STAGE"

# 正式包只保留 module.prop 指定的活动 WebUI，避免旧目录和双份预览缓存。
rm -rf "$STAGE/$WEBROOT_NAME" "$STAGE/webroot_v141" 2>/dev/null || true
mv "$STAGE/webroot" "$STAGE/$WEBROOT_NAME"
find "$STAGE" -type f -name '*.log' -delete
rm -rf "$STAGE/$WEBROOT_NAME/fonts" "$STAGE/logs" "$STAGE/backup" "$STAGE/config/recovery" "$STAGE/.font-transaction"
mkdir -p "$STAGE/$WEBROOT_NAME/fonts"
rm -f "$STAGE/config/webui_font_list.json" "$STAGE/config/webui_font_list.key" "$STAGE/config/recent_fonts.conf" \
      "$STAGE/config/previous_font.conf" "$STAGE/config/switch_task.conf" "$STAGE/config/mix_task.conf" "$STAGE/config/font_mix.conf" \
      "$STAGE/config/active_emoji.conf" "$STAGE/config/emoji_task.conf" "$STAGE/config/emoji_reboot_required.conf" \
      "$STAGE/config/font_weight.conf" "$STAGE/config/font_weight_original.conf" "$STAGE/config/font_weight_reboot_required.conf" "$STAGE/config/mount_compat.conf" "$STAGE/config/preview_cache.conf"
chmod 755 "$STAGE/customize.sh" "$STAGE/post-fs-data.sh" "$STAGE/post-mount.sh" "$STAGE/service.sh" "$STAGE/uninstall.sh"
find "$STAGE/common" -type f -exec chmod 755 {} \;
chmod 755 "$STAGE/system/bin/luoshud"
for flag in magic skip_mount skip_mountify remove disable; do test ! -e "$STAGE/$flag"; done
test ! -d "$STAGE/webroot"
test ! -d "$STAGE/webroot_v141"
test -d "$STAGE/$WEBROOT_NAME"
test -f "$STAGE/common/preview_cache.sh"
grep -q 'preview_prepare' "$STAGE/common/font_manager.sh"
grep -q 'resolve_slot_file' "$STAGE/common/font_mix.sh"
grep -q 'v14.js?v=14103' "$STAGE/$WEBROOT_NAME/index.html"
! find "$STAGE" -type d -path '*/emoji' | grep -q .
rm -f "$ZIP"; (cd "$STAGE" && zip -qr "$ZIP" .); sha256sum "$ZIP" > "$ZIP.sha256"; echo "Built: $ZIP"
