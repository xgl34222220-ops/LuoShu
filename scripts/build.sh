#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VERSION=$(sed -n 's/^version=//p' "$ROOT/module.prop" | head -n1 | sed 's#[ /]#-#g')
OUT="$ROOT/dist"
STAGE="$OUT/LuoShu"
ZIP="$OUT/LuoShu-${VERSION}.zip"

sh "$ROOT/scripts/check.sh"
rm -rf "$STAGE"
mkdir -p "$STAGE" "$OUT"
for path in common config fonts system webroot licenses LICENSE NOTICE.md THIRD_PARTY_NOTICES.md README.md README.txt CHANGELOG.md customize.sh module.prop post-fs-data.sh service.sh uninstall.sh magic 兼容与目录说明.txt; do
  [ ! -e "$ROOT/$path" ] || cp -a "$ROOT/$path" "$STAGE/"
done
find "$STAGE" -type f -name '*.log' -delete
rm -rf "$STAGE/webroot/fonts" "$STAGE/webroot/emoji" "$STAGE/logs" "$STAGE/backup" "$STAGE/config/recovery"
mkdir -p "$STAGE/webroot/fonts" "$STAGE/webroot/emoji"
rm -f "$STAGE/config/webui_font_list.json" "$STAGE/config/webui_font_list.key" \
  "$STAGE/config/recent_fonts.conf" "$STAGE/config/previous_font.conf" \
  "$STAGE/config/switch_task.conf" "$STAGE/config/mix_task.conf" \
  "$STAGE/config/font_mix.conf" "$STAGE/config/emoji_task.conf" \
  "$STAGE/config/font_weight_reboot_required.conf" "$STAGE/config/mount_compat.conf"
find "$STAGE/common" -maxdepth 1 -type f -exec chmod 0755 {} +
chmod 0755 "$STAGE"/*.sh "$STAGE/system/bin/luoshud" "$STAGE/common/python/bin/luoshu-python"
find "$STAGE/webroot" -type f -exec chmod 0644 {} +
find "$STAGE/system/fonts" -type f -exec chmod 0644 {} + 2>/dev/null || true
rm -f "$ZIP" "$ZIP.sha256"
(cd "$STAGE" && zip -9 -r -q "$ZIP" .)
sha256sum "$ZIP" > "$ZIP.sha256"
unzip -t "$ZIP" >/dev/null
printf 'Built: %s\n' "$ZIP"
