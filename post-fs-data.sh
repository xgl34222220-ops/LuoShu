#!/system/bin/sh
# 洛书 v14 - 启动早期初始化
set +e

MODDIR="${0%/*}"
MODULE_DIR="$MODDIR"
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/font_check.sh" ] && . "$MODDIR/common/font_check.sh"
[ -f "$MODDIR/common/rom_adapters.sh" ] && . "$MODDIR/common/rom_adapters.sh"
[ -f "$MODDIR/common/font_manager.sh" ] && . "$MODDIR/common/font_manager.sh"

type init_module >/dev/null 2>&1 && init_module
type ensure_public_storage >/dev/null 2>&1 && ensure_public_storage
mkdir -p "$MODDIR/config" "$MODDIR/logs" "$MODDIR/system/fonts" "$MODDIR/webroot/fonts" "$MODDIR/webroot/emoji" 2>/dev/null || true

# 不再暴露“修复脚本权限”给用户：每次启动自动静默校正，WebUI 也统一使用 sh 调用。
chmod 0755 "$MODDIR" "$MODDIR/common" "$MODDIR/webroot" 2>/dev/null || true
chmod 0755 "$MODDIR/customize.sh" "$MODDIR/post-fs-data.sh" "$MODDIR/service.sh" "$MODDIR/uninstall.sh" 2>/dev/null || true
find "$MODDIR/common" -maxdepth 1 -type f -exec chmod 0755 {} \; 2>/dev/null || true

log_message "INFO" "===== post-fs-data v14 开始 ====="

# 永远保留 ROM 自带 fonts.xml、fallback、symbols 与其他语言字体。
rm -f "$MODDIR/system/etc/fonts.xml" "$MODDIR/system/etc/font_fallback.xml" 2>/dev/null || true
set_perm_recursive "$MODDIR/system/fonts" 0 0 0755 0644 2>/dev/null || true

ACTIVE_TEXT=$(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
[ -n "$ACTIVE_TEXT" ] || ACTIVE_TEXT="default"
ACTIVE_EMOJI=$(head -n1 "$MODDIR/config/active_emoji.conf" 2>/dev/null | tr -d '\r\n')
[ -n "$ACTIVE_EMOJI" ] || ACTIVE_EMOJI="default"

# ColorOS 的 /data/fonts 只同步洛书管理的已知文字文件。
if [ "$IS_COLOROS" = "true" ] && [ -d /data/fonts ]; then
    _count=0
    for _name in $(get_all_coloros_names); do
        _dest="/data/fonts/${_name}.ttf"
        _src="$MODDIR/system/fonts/${_name}.ttf"
        if [ "$ACTIVE_TEXT" = "default" ]; then
            rm -f "$_dest" 2>/dev/null || true
        elif [ -f "$_src" ]; then
            cp -f "$_src" "$_dest" 2>/dev/null && { chmod 0644 "$_dest" 2>/dev/null || true; _count=$((_count + 1)); }
        fi
    done
    log_message "INFO" "ColorOS /data/fonts 安全同步：$_count 个文字目标"
fi

type sync_preview_fonts >/dev/null 2>&1 && sync_preview_fonts 2>/dev/null || true
type sync_emoji_preview_fonts >/dev/null 2>&1 && sync_emoji_preview_fonts 2>/dev/null || true

# 完整重启后解除本次开机切换保护。
rm -f "$MODDIR/config/text_reboot_required.conf" "$MODDIR/config/emoji_reboot_required.conf" \
      "$MODDIR/config/font_weight_reboot_required.conf" "$MODDIR/.font_switch.lock" 2>/dev/null || true

[ -f "$MODDIR/common/module_status.sh" ] && MODDIR="$MODDIR" sh "$MODDIR/common/module_status.sh" "$ACTIVE_TEXT" >/dev/null 2>&1 || true
log_message "INFO" "当前文字=$ACTIVE_TEXT | Emoji=$ACTIVE_EMOJI | 重启保护已复位"
log_message "INFO" "===== post-fs-data 完成 ====="
exit 0
