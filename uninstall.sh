#!/system/bin/sh
# 洛书 v2：安全卸载。恢复系统设置并解除动态字体配置桥。
set +e
MODDIR="${0%/*}"
MODULE_VERSION=$(sed -n 's/^version=//p' "$MODDIR/module.prop" 2>/dev/null | head -n1)
[ -n "$MODULE_VERSION" ] || MODULE_VERSION="unknown"

# 恢复安装洛书前记录的 Android 全局字体粗细设置。
if command -v settings >/dev/null 2>&1; then
    _fw_restore=0
    [ -f "$MODDIR/config/font_weight_original.conf" ] && \
        _fw_restore=$(sed -n 's/^adjustment=//p' "$MODDIR/config/font_weight_original.conf" 2>/dev/null | head -n1)
    case "$_fw_restore" in ''|*[!0-9-]*) _fw_restore=0 ;; esac
    settings --user current put secure font_weight_adjustment "$_fw_restore" >/dev/null 2>&1 || \
        settings put secure font_weight_adjustment "$_fw_restore" >/dev/null 2>&1 || true
fi

# 解除开机前 Google Sans 命名字体桥；完整重启后系统自然恢复原始字体表。
if [ -f "$MODDIR/common/font_provider_cache.sh" ]; then
    MODULE_DIR="$MODDIR"
    . "$MODDIR/common/font_provider_cache.sh"
    luoshu_provider_cache_restore >/dev/null 2>&1 || true
fi

rm -f "$MODDIR/.first_boot" "$MODDIR/.font_switch.lock" 2>/dev/null || true
mkdir -p "$MODDIR/logs" 2>/dev/null || true
echo "[$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)] 洛书 $MODULE_VERSION 已卸载" >> "$MODDIR/logs/fontswitch.log" 2>/dev/null || true
exit 0
