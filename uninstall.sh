#!/system/bin/sh
# 洛书 v2.0.0：安全卸载。只恢复洛书明确记录的系统设置，不触碰 /data/fonts。
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

# 还原 GMS Fonts Provider 缓存劫持（切换字体时写入 /data/fonts/files 的副本），
# 否则卸载模块后 Play 商店等应用仍停留在用户字体。
if [ -f "$MODDIR/common/font_provider_cache.sh" ]; then
    MODULE_DIR="$MODDIR"
    . "$MODDIR/common/font_provider_cache.sh"
    luoshu_provider_cache_restore >/dev/null 2>&1 || true
fi

# v2 使用 systemless 字体与 XML 负载，不删除 Android/OEM 管理的动态字体数据库。
rm -f "$MODDIR/.first_boot" "$MODDIR/.font_switch.lock" 2>/dev/null || true
mkdir -p "$MODDIR/logs" 2>/dev/null || true
echo "[$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)] 洛书 $MODULE_VERSION 已卸载" >> "$MODDIR/logs/fontswitch.log" 2>/dev/null || true
exit 0
