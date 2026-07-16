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

# 只修改构建暂存目录：统一缓存号、可见版本，并注入独立自救入口。
sh "$ROOT/scripts/prepare_webui.sh" "$STAGE/webroot"

find "$STAGE" -type f -name '*.log' -delete
rm -rf "$STAGE/webroot/fonts" "$STAGE/webroot/emoji" "$STAGE/logs" "$STAGE/backup" "$STAGE/config/recovery"
mkdir -p "$STAGE/webroot/fonts" "$STAGE/webroot/emoji" "$STAGE/config/recovery"
rm -f "$STAGE/config/webui_font_list.json" \
      "$STAGE/config/webui_font_list.key" \
      "$STAGE/config/recent_fonts.conf" \
      "$STAGE/config/previous_font.conf" \
      "$STAGE/config/switch_task.conf" \
      "$STAGE/config/emoji_task.conf" \
      "$STAGE/config/font_weight.conf" \
      "$STAGE/config/font_weight_original.conf" \
      "$STAGE/config/font_weight_reboot_required.conf"

chmod 755 "$STAGE/customize.sh" "$STAGE/post-fs-data.sh" \
          "$STAGE/service.sh" "$STAGE/uninstall.sh"
find "$STAGE/common" -type f -exec chmod 755 {} \;
chmod 755 "$STAGE/system/bin/luoshud"

rm -f "$ZIP"
(cd "$STAGE" && zip -qr "$ZIP" .)
sha256sum "$ZIP" > "$ZIP.sha256"
echo "Built: $ZIP"
