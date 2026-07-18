#!/system/bin/sh
# 洛书 - 启动早期初始化（版本以 module.prop 为准）
set +e

MODDIR="${0%/*}"
MODULE_VERSION=$(sed -n 's/^version=//p' "$MODDIR/module.prop" 2>/dev/null | head -n1)
[ -n "$MODULE_VERSION" ] || MODULE_VERSION="unknown"
MODULE_DIR="$MODDIR"
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/font_check.sh" ] && . "$MODDIR/common/font_check.sh"
[ -f "$MODDIR/common/rom_adapters.sh" ] && . "$MODDIR/common/rom_adapters.sh"

type init_module >/dev/null 2>&1 && init_module
type ensure_public_storage >/dev/null 2>&1 && ensure_public_storage
mkdir -p "$MODDIR/config" "$MODDIR/logs" "$MODDIR/system/fonts" "$MODDIR/webroot/fonts" 2>/dev/null || true

# 每次启动自动静默校正权限，WebUI 统一使用 sh 调用。
chmod 0755 "$MODDIR" "$MODDIR/common" "$MODDIR/webroot" 2>/dev/null || true
chmod 0755 "$MODDIR/customize.sh" "$MODDIR/post-fs-data.sh" "$MODDIR/service.sh" "$MODDIR/uninstall.sh" 2>/dev/null || true
find "$MODDIR/common" -maxdepth 1 -type f -exec chmod 0755 {} \; 2>/dev/null || true
chmod 0644 "$MODDIR/common/font_instance.py" "$MODDIR/common/composite_font.py" 2>/dev/null || true

log_message "INFO" "===== post-fs-data $MODULE_VERSION 开始 ====="

# 永远保留 ROM 自带 fonts.xml、fallback、Emoji、symbols 与其他语言字体。
rm -f "$MODDIR/system/etc/fonts.xml" "$MODDIR/system/etc/font_fallback.xml" 2>/dev/null || true
rm -f "$MODDIR/system/fonts/NotoColorEmoji.ttf" "$MODDIR/system/fonts/NotoColorEmojiLegacy.ttf" 2>/dev/null || true
rm -f "$MODDIR/config/active_emoji.conf" "$MODDIR/config/emoji_task.conf" "$MODDIR/config/emoji_reboot_required.conf" 2>/dev/null || true
rm -rf "$MODDIR/webroot/emoji" 2>/dev/null || true
set_perm_recursive "$MODDIR/system/fonts" 0 0 0755 0644 2>/dev/null || true
chmod 0755 "$MODDIR/common/python/bin/luoshu-python" 2>/dev/null || true
# 通过统一桥恢复中断的原子负载，并清理独立字重暂存任务。
if [ -f "$MODDIR/common/v14_mix.sh" ]; then
    MODDIR="$MODDIR" sh "$MODDIR/common/v14_mix.sh" recover >/dev/null 2>&1 || true
elif [ -f "$MODDIR/common/font_mix.sh" ]; then
    MODDIR="$MODDIR" sh "$MODDIR/common/font_mix.sh" recover >/dev/null 2>&1 || true
fi

ACTIVE_TEXT=$(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
[ -n "$ACTIVE_TEXT" ] || ACTIVE_TEXT="default"

# ColorOS 的 /data/fonts 只同步洛书管理的已知文字文件。
if [ "$IS_COLOROS" = "true" ] && [ -d /data/fonts ]; then
    _count=0
    for _name in $(get_all_coloros_names); do
        _dest="/data/fonts/${_name}.ttf"
        _src="$MODDIR/system/fonts/${_name}.ttf"
        if [ "$ACTIVE_TEXT" = "default" ]; then
            rm -f "$_dest" 2>/dev/null || true
        elif [ -f "$_src" ]; then
            link_or_copy_font "$_src" "$_dest" 2>/dev/null && { chmod 0644 "$_dest" 2>/dev/null || true; _count=$((_count + 1)); }
        fi
    done
    log_message "INFO" "ColorOS /data/fonts 安全同步：$_count 个文字目标"
fi

# 字体预览索引由 WebUI 按需刷新，启动早期不扫描或复制大字体。

# 完整重启后解除本次开机切换保护。
rm -f "$MODDIR/config/text_reboot_required.conf" "$MODDIR/config/font_weight_reboot_required.conf" \
      "$MODDIR/.font_switch.lock" 2>/dev/null || true

[ -f "$MODDIR/common/module_status.sh" ] && MODDIR="$MODDIR" sh "$MODDIR/common/module_status.sh" "$ACTIVE_TEXT" >/dev/null 2>&1 || true
log_message "INFO" "当前文字=$ACTIVE_TEXT | 重启保护已复位"
log_message "INFO" "===== post-fs-data 完成 ====="
exit 0
