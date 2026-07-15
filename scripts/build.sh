#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VERSION=$(sed -n 's/^version=//p' "$ROOT/module.prop" | head -n 1 | tr ' /' '__')
OUT_DIR="$ROOT/dist"
STAGE="$OUT_DIR/LuoShu"
ZIP="$OUT_DIR/LuoShu-${VERSION}.zip"

"$ROOT/scripts/check.sh"
rm -rf "$STAGE"
mkdir -p "$STAGE" "$OUT_DIR"

for path in common config fonts system webroot customize.sh module.prop post-fs-data.sh service.sh uninstall.sh; do
    cp -R "$ROOT/$path" "$STAGE/"
done

find "$STAGE" -type f -name '*.log' -delete
rm -rf "$STAGE/webroot/fonts" "$STAGE/logs" "$STAGE/backup"
rm -f "$STAGE/config/webui_font_list.json" \
      "$STAGE/config/webui_font_list.key" \
      "$STAGE/config/recent_fonts.conf" \
      "$STAGE/config/previous_font.conf"

chmod 755 "$STAGE/customize.sh" "$STAGE/post-fs-data.sh" \
          "$STAGE/service.sh" "$STAGE/uninstall.sh"
find "$STAGE/common" -type f -name '*.sh' -exec chmod 755 {} \;
[ ! -f "$STAGE/system/bin/luoshud" ] || chmod 755 "$STAGE/system/bin/luoshud"

rm -f "$ZIP"
(cd "$STAGE" && zip -qr "$ZIP" .)
echo "Built: $ZIP"
