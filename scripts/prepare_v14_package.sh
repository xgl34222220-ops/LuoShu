#!/bin/sh
set -eu
STAGE="$1"; CUSTOMIZE="$STAGE/customize.sh"; PROP="$STAGE/module.prop"; MANAGER="$STAGE/common/font_manager.sh"
for file in "$CUSTOMIZE" "$PROP" "$MANAGER" "$STAGE/common/module_status.sh" "$STAGE/common/v14_switch.sh" "$STAGE/common/font_switch_v141.sh" "$STAGE/common/font_transaction.sh" "$STAGE/common/font_mix.sh" "$STAGE/common/v14_mix.sh" "$STAGE/common/device_capabilities.sh" "$STAGE/common/preview_cache.sh" "$STAGE/common/luoshu_cli.sh"; do test -f "$file"; done

grep -q '^version=v14.1 Test3$' "$PROP"
grep -q '^versionCode=14103$' "$PROP"
grep -q '^webroot=webroot_v14103$' "$PROP"
grep -q 'preview_prepare' "$MANAGER"
grep -q 'resolve_slot_file' "$STAGE/common/font_mix.sh"
grep -q 'role_anchor' "$STAGE/common/font_mix.sh"

rm -f "$STAGE/magic" "$STAGE/skip_mount" "$STAGE/skip_mountify" "$STAGE/remove" "$STAGE/disable" 2>/dev/null || true
rm -rf "$STAGE/webroot/emoji" "$STAGE/system/fonts/.luoshu-emoji-store" 2>/dev/null || true
rm -f "$STAGE/system/fonts/NotoColorEmoji.ttf" "$STAGE/system/fonts/NotoColorEmojiLegacy.ttf" \
      "$STAGE/config/active_emoji.conf" "$STAGE/config/emoji_task.conf" "$STAGE/config/emoji_reboot_required.conf" 2>/dev/null || true
chmod 0755 "$CUSTOMIZE" "$STAGE/post-fs-data.sh" "$STAGE/post-mount.sh" "$STAGE/service.sh" "$STAGE/uninstall.sh" 2>/dev/null || true
find "$STAGE/common" -maxdepth 1 -type f -exec chmod 0755 {} \; 2>/dev/null || true
