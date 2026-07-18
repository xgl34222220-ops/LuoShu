#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
. "$ROOT/scripts/version.sh"
VERSION="$LUOSHU_ARTIFACT_VERSION"
VARIANT=$(printf '%s' "${LUOSHU_VARIANT:-full}" | tr '[:upper:]' '[:lower:]')
case "$VARIANT" in
  full) VARIANT_LABEL="Full" ;;
  lite) VARIANT_LABEL="Lite" ;;
  *) echo "Unknown LUOSHU_VARIANT: $VARIANT (expected full or lite)" >&2; exit 64 ;;
esac
OUT="$ROOT/dist"
STAGE="$OUT/LuoShu-${VARIANT_LABEL}"
ZIP="$OUT/LuoShu-${VERSION}-${VARIANT_LABEL}.zip"
ZIP_NAME=$(basename "$ZIP")
APP_APK="${LUOSHU_APP_APK:-$ROOT/android-app/app/build/outputs/apk/debug/app-debug.apk}"

sh "$ROOT/scripts/check.sh"
rm -rf "$STAGE"
mkdir -p "$STAGE" "$OUT"
for path in common config fonts system webroot licenses LICENSE NOTICE.md THIRD_PARTY_NOTICES.md README.md README.txt CHANGELOG.md customize.sh module.prop post-fs-data.sh service.sh uninstall.sh action.sh magic 兼容与目录说明.txt; do
  [ ! -e "$ROOT/$path" ] || cp -a "$ROOT/$path" "$STAGE/"
done
sh "$ROOT/scripts/prepare_webui.sh" "$STAGE/webroot"
[ ! -f "$STAGE/config/version_notes.conf" ] || sed -i "s/^version=.*/version=$LUOSHU_VERSION/" "$STAGE/config/version_notes.conf"

if [ "$VARIANT" = "full" ] && [ -s "$APP_APK" ]; then
  mkdir -p "$STAGE/bundled"
  cp -f "$APP_APK" "$STAGE/bundled/LuoShu-App.apk"
  chmod 0644 "$STAGE/bundled/LuoShu-App.apk"
fi
find "$STAGE" -type f -name '*.log' -delete
find "$STAGE" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$STAGE" -type f -name '*.pyc' -delete
rm -rf "$STAGE/webroot/fonts" "$STAGE/logs" "$STAGE/backup" "$STAGE/config/recovery"
mkdir -p "$STAGE/webroot/fonts"
rm -rf "$STAGE/webroot/emoji"
rm -f "$STAGE/config/webui_font_list.json" "$STAGE/config/webui_font_list.key" \
  "$STAGE/config/recent_fonts.conf" "$STAGE/config/previous_font.conf" \
  "$STAGE/config/switch_task.conf" "$STAGE/config/mix_task.conf" \
  "$STAGE/config/font_mix.conf" "$STAGE/config/active_emoji.conf" \
  "$STAGE/config/emoji_task.conf" "$STAGE/config/emoji_reboot_required.conf" \
  "$STAGE/config/font_weight_reboot_required.conf" "$STAGE/config/mount_compat.conf"
rm -f "$STAGE/system/fonts/NotoColorEmoji.ttf" "$STAGE/system/fonts/NotoColorEmojiLegacy.ttf"
rm -f "$STAGE/common/stability.sh" "$STAGE/webroot/stability.js" "$STAGE/webroot/stability.css" \
  "$STAGE/common/fonts_xml_template.sh" "$STAGE/common/play_font_bridge.sh" "$STAGE/common/wechat_xweb_bridge.sh"
find "$STAGE/common" -maxdepth 1 -type f -exec chmod 0755 {} +
chmod 0755 "$STAGE"/*.sh "$STAGE/system/bin/luoshud" "$STAGE/common/python/bin/luoshu-python"
find "$STAGE/webroot" -type f -exec chmod 0644 {} +
find "$STAGE/system/fonts" -type f -exec chmod 0644 {} + 2>/dev/null || true

# 成品目录门禁：旧功能即使被其他构建步骤重新带回，也禁止生成 ZIP。
for forbidden in \
  webroot/emoji config/active_emoji.conf config/emoji_task.conf config/emoji_reboot_required.conf \
  system/fonts/NotoColorEmoji.ttf system/fonts/NotoColorEmojiLegacy.ttf \
  common/stability.sh webroot/stability.js webroot/stability.css common/fonts_xml_template.sh \
  common/play_font_bridge.sh common/wechat_xweb_bridge.sh; do
  [ ! -e "$STAGE/$forbidden" ] || { echo "forbidden payload: $forbidden" >&2; exit 88; }
done

rm -f "$ZIP" "$ZIP.sha256"
(cd "$STAGE" && zip -9 -r -q "$ZIP" .)
(cd "$OUT" && sha256sum "$ZIP_NAME" > "$ZIP_NAME.sha256")
unzip -t "$ZIP" >/dev/null
unzip -Z1 "$ZIP" | grep -Eq '(^|/)(__pycache__|emoji)(/|$)|\.pyc$|NotoColorEmoji|active_emoji|emoji_task|stability\.(js|css)|common/stability\.sh|fonts_xml_template|play_font_bridge\.sh|wechat_xweb_bridge\.sh' && {
  echo 'forbidden legacy path found in final ZIP' >&2
  exit 89
} || true
printf 'Built: %s\n' "$ZIP"
[ ! -s "$STAGE/bundled/LuoShu-App.apk" ] || printf 'Bundled App: %s\n' "$STAGE/bundled/LuoShu-App.apk"
[ "$VARIANT" != "lite" ] || printf 'Lite package: App is intentionally not bundled.\n'
