#!/bin/sh
set -eu
STAGE="$1"; CUSTOMIZE="$STAGE/customize.sh"; PROP="$STAGE/module.prop"; MANAGER="$STAGE/common/font_manager.sh"
for file in "$CUSTOMIZE" "$PROP" "$MANAGER" "$STAGE/common/module_status.sh" "$STAGE/common/v14_switch.sh" "$STAGE/common/font_switch_v141.sh" "$STAGE/common/font_transaction.sh" "$STAGE/common/font_mix.sh" "$STAGE/common/v14_mix.sh" "$STAGE/common/device_capabilities.sh" "$STAGE/common/luoshu_cli.sh"; do test -f "$file"; done

# 列表请求只同步文字预览；Emoji 功能从 v14.1 正式运行路径移除。
if ! grep -q 'v141-text-preview-only' "$MANAGER"; then
    sed -i '/    sync_preview_fonts 2>\/dev\/null || true/,/    sync_emoji_preview_fonts 2>\/dev\/null || true/c\    # v141-text-preview-only\n    case "$action" in\n        list|import_list|import_zip|delete) sync_preview_fonts 2>/dev/null || true ;;\n    esac' "$MANAGER"
fi
sed -i -E 's/v13\.4 Beta2 Hotfix6/v14.1/g; s/v13426/v14100/g' "$MANAGER"
sed -i -E 's#^description=.*#description=Android 全局字体管理，当前字体：系统默认字体#' "$PROP"
rm -f "$STAGE/magic" "$STAGE/skip_mount" "$STAGE/skip_mountify" "$STAGE/remove" "$STAGE/disable" 2>/dev/null || true
rm -rf "$STAGE/webroot/emoji" "$STAGE/system/fonts/.luoshu-emoji-store" 2>/dev/null || true
rm -f "$STAGE/system/fonts/NotoColorEmoji.ttf" "$STAGE/system/fonts/NotoColorEmojiLegacy.ttf" \
      "$STAGE/config/active_emoji.conf" "$STAGE/config/emoji_task.conf" "$STAGE/config/emoji_reboot_required.conf" 2>/dev/null || true
chmod 0755 "$CUSTOMIZE" "$STAGE/post-fs-data.sh" "$STAGE/post-mount.sh" "$STAGE/service.sh" "$STAGE/uninstall.sh" 2>/dev/null || true
find "$STAGE/common" -maxdepth 1 -type f -exec chmod 0755 {} \; 2>/dev/null || true
