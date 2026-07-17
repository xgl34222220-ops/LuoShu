#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VERSION=$(sed -n 's/^version=//p' "$ROOT/module.prop" | head -n1 | sed 's#[ /]#-#g')
OUT_DIR="$ROOT/dist"; STAGE="$OUT_DIR/LuoShu"; ZIP="$OUT_DIR/LuoShu-${VERSION}.zip"
sh "$ROOT/scripts/check.sh"
rm -rf "$STAGE"; mkdir -p "$STAGE" "$OUT_DIR"
for path in common config fonts system webroot customize.sh module.prop post-fs-data.sh post-mount.sh service.sh uninstall.sh 兼容与目录说明.txt; do cp -R "$ROOT/$path" "$STAGE/"; done
sh "$ROOT/scripts/prepare_v14_package.sh" "$STAGE"
sh "$ROOT/scripts/prepare_webui.sh" "$STAGE/webroot"
sh "$ROOT/scripts/prepare_mount_compat.sh" "$STAGE"

# v14.1 不再加载实验前端。保留一份默认目录，并复制到全新的 webroot_v141 路径，
# 让 Root 管理器绕过旧 index.html / CSS / JS 缓存，避免新旧页面混用。
rm -f "$STAGE/webroot/v14_1.js" "$STAGE/webroot/v14_1.css"
rm -rf "$STAGE/webroot_v141"
cp -R "$STAGE/webroot" "$STAGE/webroot_v141"

find "$STAGE" -type f -name '*.log' -delete
rm -rf "$STAGE/webroot/fonts" "$STAGE/webroot/emoji" "$STAGE/webroot_v141/fonts" "$STAGE/webroot_v141/emoji" \
       "$STAGE/logs" "$STAGE/backup" "$STAGE/config/recovery" "$STAGE/.font-transaction"
mkdir -p "$STAGE/webroot/fonts" "$STAGE/webroot_v141/fonts"
rm -f "$STAGE/config/webui_font_list.json" "$STAGE/config/webui_font_list.key" "$STAGE/config/recent_fonts.conf" \
      "$STAGE/config/previous_font.conf" "$STAGE/config/switch_task.conf" "$STAGE/config/mix_task.conf" "$STAGE/config/font_mix.conf" \
      "$STAGE/config/active_emoji.conf" "$STAGE/config/emoji_task.conf" "$STAGE/config/emoji_reboot_required.conf" \
      "$STAGE/config/font_weight.conf" "$STAGE/config/font_weight_original.conf" "$STAGE/config/font_weight_reboot_required.conf" "$STAGE/config/mount_compat.conf"
chmod 755 "$STAGE/customize.sh" "$STAGE/post-fs-data.sh" "$STAGE/post-mount.sh" "$STAGE/service.sh" "$STAGE/uninstall.sh"
find "$STAGE/common" -type f -exec chmod 755 {} \;
chmod 755 "$STAGE/system/bin/luoshud"
for flag in magic skip_mount skip_mountify remove disable; do test ! -e "$STAGE/$flag"; done

test ! -d "$STAGE/webroot/emoji"; test ! -d "$STAGE/webroot_v141/emoji"
test -f "$STAGE/common/font_transaction.sh"; test -f "$STAGE/common/font_switch_v141.sh"; test -f "$STAGE/common/device_capabilities.sh"
grep -q 'v14.js?v=14100' "$STAGE/webroot/index.html"; grep -q 'v14.css?v=14100' "$STAGE/webroot/index.html"
grep -q 'v14.js?v=14100' "$STAGE/webroot_v141/index.html"; grep -q 'v14.css?v=14100' "$STAGE/webroot_v141/index.html"
! grep -q 'v14_1.js?v=' "$STAGE/webroot/index.html"; ! grep -q 'v14_1.css?v=' "$STAGE/webroot/index.html"
grep -q 'id="emojiSection"' "$STAGE/webroot/index.html"; grep -q '#emojiSection' "$STAGE/webroot/v14.css"
! grep -q 'stability.js?v=' "$STAGE/webroot/index.html"
! grep -q '^exit 0$' "$STAGE/customize.sh"
grep -q 'APatch.*source' "$STAGE/customize.sh"; grep -q 'post-fs-data.*阻塞' "$STAGE/post-fs-data.sh"
grep -q '^version=v14.1$' "$STAGE/module.prop"; grep -q '^versionCode=14100$' "$STAGE/module.prop"
grep -q '^webroot=webroot_v141$' "$STAGE/module.prop"
grep -q '^description=Android 全局字体管理，当前字体：系统默认字体$' "$STAGE/module.prop"
rm -f "$ZIP"; (cd "$STAGE" && zip -qr "$ZIP" .); sha256sum "$ZIP" > "$ZIP.sha256"; echo "Built: $ZIP"
