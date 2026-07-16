#!/system/bin/sh
# LuoShu v13.4 Beta2 Hotfix2 - 安全卸载
set +e
MODDIR="${0%/*}"
MODULE_DIR="$MODDIR"
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/rom_adapters.sh" ] && . "$MODDIR/common/rom_adapters.sh"
type check_coloros >/dev/null 2>&1 && check_coloros

# 只删除洛书已知的 ColorOS 文字别名，不清空 /data/fonts 整个目录。
if [ "$IS_COLOROS" = "true" ] && [ -d /data/fonts ]; then
    for _name in $(get_all_coloros_names); do
        rm -f "/data/fonts/${_name}.ttf" 2>/dev/null || true
    done
fi

# 恢复安装洛书前的 Android 全局字体粗细设置。
if command -v settings >/dev/null 2>&1; then
    _fw_restore=0
    [ -f "$MODDIR/config/font_weight_original.conf" ] && \
        _fw_restore=$(sed -n 's/^adjustment=//p' "$MODDIR/config/font_weight_original.conf" 2>/dev/null | head -n1)
    case "$_fw_restore" in ''|*[!0-9-]*) _fw_restore=0 ;; esac
    settings --user current put secure font_weight_adjustment "$_fw_restore" >/dev/null 2>&1 || settings put secure font_weight_adjustment "$_fw_restore" >/dev/null 2>&1 || true
fi

# 清理 GMS 动态字体桥接状态。
if [ -f "$MODDIR/common/play_font_bridge" ]; then
    MODDIR="$MODDIR" sh "$MODDIR/common/play_font_bridge" restore >/dev/null 2>&1 || true
fi

rm -f "$MODDIR/.first_boot" "$MODDIR/.font_switch.lock" 2>/dev/null || true
mkdir -p "$MODDIR/logs" 2>/dev/null || true
echo "[$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)] 洛书 v13.4 Beta2 Hotfix2 已卸载" >> "$MODDIR/logs/fontswitch.log" 2>/dev/null || true
exit 0
