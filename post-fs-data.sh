#!/system/bin/sh
# 洛书 v14.1 - 启动早期最小初始化
# APatch 的 post-fs-data 是阻塞阶段且模块尚未挂载，因此这里不访问 /sdcard、不扫描字体。
set +e
MODDIR="${0%/*}"
mkdir -p "$MODDIR/config" "$MODDIR/logs" "$MODDIR/system/fonts" 2>/dev/null || true
chmod 0755 "$MODDIR" "$MODDIR/common" "$MODDIR/webroot" 2>/dev/null || true
find "$MODDIR/common" -maxdepth 1 -type f -exec chmod 0755 {} \; 2>/dev/null || true
find "$MODDIR/system/fonts" -type f -exec chmod 0644 {} \; 2>/dev/null || true
rm -f "$MODDIR/remove" "$MODDIR/disable" "$MODDIR/skip_mount" "$MODDIR/skip_mountify" "$MODDIR/magic" 2>/dev/null || true
rm -f "$MODDIR/config/active_emoji.conf" "$MODDIR/config/emoji_task.conf" "$MODDIR/config/emoji_reboot_required.conf" 2>/dev/null || true
rm -f "$MODDIR/system/fonts/NotoColorEmoji.ttf" "$MODDIR/system/fonts/NotoColorEmojiLegacy.ttf" 2>/dev/null || true
rm -rf "$MODDIR/system/fonts/.luoshu-emoji-store" 2>/dev/null || true
WEBROOT_NAME=$(sed -n 's/^webroot=//p' "$MODDIR/module.prop" 2>/dev/null | head -n1 | tr -d '\r\n')
for _old_root in webroot webroot_v141; do [ "$_old_root" = "$WEBROOT_NAME" ] || rm -rf "$MODDIR/$_old_root" 2>/dev/null || true; done
rm -f "$MODDIR/config/text_reboot_required.conf" "$MODDIR/config/font_weight_reboot_required.conf" "$MODDIR/.font_switch.lock" 2>/dev/null || true
[ -f "$MODDIR/common/font_transaction.sh" ] && . "$MODDIR/common/font_transaction.sh" && luoshu_txn_cleanup_stale
printf '[%s] post-fs-data v14.1 minimal init\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" >> "$MODDIR/logs/fontswitch.log" 2>/dev/null || true
exit 0
