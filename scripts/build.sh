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
for path in common config fonts system licenses LICENSE NOTICE.md THIRD_PARTY_NOTICES.md README.md README.txt CHANGELOG.md customize.sh module.prop post-fs-data.sh service.sh uninstall.sh action.sh magic 兼容与目录说明.txt; do
  [ ! -e "$ROOT/$path" ] || cp -a "$ROOT/$path" "$STAGE/"
done
[ ! -f "$STAGE/config/version_notes.conf" ] || sed -i "s/^version=.*/version=$LUOSHU_VERSION/" "$STAGE/config/version_notes.conf"

if [ "$VARIANT" = "full" ] && [ -s "$APP_APK" ]; then
  mkdir -p "$STAGE/bundled"
  cp -f "$APP_APK" "$STAGE/bundled/LuoShu-App.apk"

  APP_PACKAGE="${LUOSHU_APP_PACKAGE:-}"
  APP_VERSION_CODE="${LUOSHU_APP_VERSION_CODE:-}"
  if command -v apkanalyzer >/dev/null 2>&1; then
    [ -n "$APP_PACKAGE" ] || APP_PACKAGE=$(apkanalyzer manifest application-id "$APP_APK" 2>/dev/null || true)
    [ -n "$APP_VERSION_CODE" ] || APP_VERSION_CODE=$(apkanalyzer manifest version-code "$APP_APK" 2>/dev/null || true)
  fi
  if [ -z "$APP_PACKAGE" ]; then
    case "$(basename "$APP_APK" | tr '[:upper:]' '[:lower:]')" in
      *debug*.apk) APP_PACKAGE="io.github.xgl34222220.luoshu.debug" ;;
      *) APP_PACKAGE="io.github.xgl34222220.luoshu" ;;
    esac
  fi
  case "$APP_VERSION_CODE" in
    ''|*[!0-9]*) APP_VERSION_CODE=$((LUOSHU_VERSION_CODE * 100 + 1)) ;;
  esac
  APP_SHA256=$(sha256sum "$STAGE/bundled/LuoShu-App.apk" | awk '{print $1}')
  {
    printf 'package=%s\n' "$APP_PACKAGE"
    printf 'versionCode=%s\n' "$APP_VERSION_CODE"
    printf 'versionName=%s\n' "$LUOSHU_VERSION"
    printf 'sha256=%s\n' "$APP_SHA256"
  } > "$STAGE/bundled/app.prop"
  chmod 0644 "$STAGE/bundled/LuoShu-App.apk" "$STAGE/bundled/app.prop"
fi
find "$STAGE" -type f -name '*.log' -delete
find "$STAGE" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$STAGE" -type f -name '*.pyc' -delete
rm -rf "$STAGE/webroot" "$STAGE/logs" "$STAGE/backup" "$STAGE/config/recovery"
rm -f "$STAGE/config/webui_font_list.json" "$STAGE/config/webui_font_list.key" \
  "$STAGE/config/recent_fonts.conf" "$STAGE/config/previous_font.conf" \
  "$STAGE/config/switch_task.conf" "$STAGE/config/mix_task.conf" "$STAGE/config/axes_task.conf" \
  "$STAGE/config/font_mix.conf" "$STAGE/config/active_emoji.conf" \
  "$STAGE/config/emoji_task.conf" "$STAGE/config/emoji_reboot_required.conf" \
  "$STAGE/config/font_weight_reboot_required.conf" "$STAGE/config/mount_compat.conf" \
  "$STAGE/config/app_install_pending" "$STAGE/config/app_install_state.conf"
rm -f "$STAGE/system/fonts/NotoColorEmoji.ttf" "$STAGE/system/fonts/NotoColorEmojiLegacy.ttf"
rm -f "$STAGE/common/stability.sh" "$STAGE/common/fonts_xml_template.sh" \
  "$STAGE/common/play_font_bridge.sh" "$STAGE/common/wechat_xweb_bridge.sh"
find "$STAGE/common" -maxdepth 1 -type f -exec chmod 0755 {} +
chmod 0755 "$STAGE"/*.sh "$STAGE/system/bin/luoshud" "$STAGE/common/python/bin/luoshu-python"
find "$STAGE/system/fonts" -type f -exec chmod 0644 {} + 2>/dev/null || true

# App-only 成品门禁：模块 ZIP 不再包含或声明 WebUI。
test ! -e "$STAGE/webroot"
! grep -q '^webroot=' "$STAGE/module.prop"

# 成品目录门禁：旧功能即使被其他构建步骤重新带回，也禁止生成 ZIP。
for forbidden in \
  webroot config/active_emoji.conf config/emoji_task.conf config/emoji_reboot_required.conf \
  system/fonts/NotoColorEmoji.ttf system/fonts/NotoColorEmojiLegacy.ttf \
  common/stability.sh common/fonts_xml_template.sh common/play_font_bridge.sh common/wechat_xweb_bridge.sh; do
  [ ! -e "$STAGE/$forbidden" ] || { echo "forbidden payload: $forbidden" >&2; exit 88; }
done

if [ "$VARIANT" = "full" ] && [ -s "$APP_APK" ]; then
  test -s "$STAGE/bundled/LuoShu-App.apk"
  test -s "$STAGE/bundled/app.prop"
  grep -q '^package=io.github.xgl34222220.luoshu' "$STAGE/bundled/app.prop"
  grep -Eq '^versionCode=[0-9]+$' "$STAGE/bundled/app.prop"
  grep -Eq '^sha256=[0-9a-f]{64}$' "$STAGE/bundled/app.prop"
fi

rm -f "$ZIP" "$ZIP.sha256"
(cd "$STAGE" && zip -9 -r -q "$ZIP" .)
(cd "$OUT" && sha256sum "$ZIP_NAME" > "$ZIP_NAME.sha256")
unzip -t "$ZIP" >/dev/null
unzip -Z1 "$ZIP" | grep -Eq '(^|/)webroot(/|$)|(^|/)(__pycache__|emoji)(/|$)|\.pyc$|NotoColorEmoji|active_emoji|emoji_task|common/stability\.sh|fonts_xml_template|play_font_bridge\.sh|wechat_xweb_bridge\.sh' && {
  echo 'forbidden legacy or WebUI path found in final ZIP' >&2
  exit 89
} || true
printf 'Built: %s\n' "$ZIP"
[ ! -s "$STAGE/bundled/LuoShu-App.apk" ] || printf 'Bundled App: %s (%s)\n' "$STAGE/bundled/LuoShu-App.apk" "$(sed -n 's/^package=//p' "$STAGE/bundled/app.prop")"
[ "$VARIANT" != "lite" ] || printf 'Lite package: App is intentionally not bundled.\n'
rm -rf "$STAGE"
