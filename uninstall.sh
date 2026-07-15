#!/system/bin/sh
# ============================================================
# 洛书 - 卸载脚本 (uninstall.sh)
# 作者：惜故里丶
# 版本：v12.8
# 功能：模块卸载时撤销临时字体挂载
# ============================================================

MODDIR="${0%/*}"

# ---------- 清理 ColorOS 字体 ----------
# ColorOS 使用 /data/fonts/ 存放自定义字体
if [ -d /data/fonts ]; then
    rm -f /data/fonts/*.ttf /data/fonts/*.otf 2>/dev/null
    rm -f /data/fonts/*.TTF /data/fonts/*.OTF 2>/dev/null
fi

# ---------- 撤销 GMS 动态字体 bind mount ----------
if [ -f "$MODDIR/common/play_font_bridge.sh" ]; then
    MODDIR="$MODDIR" sh "$MODDIR/common/play_font_bridge.sh" restore >/dev/null 2>&1 || true
fi

# Android 16 的字体配置与动态字体由 FontManagerService 管理；卸载模块时不再
# 删除 /data/system/font_config.xml、/data/fonts/files 或系统 overlay，避免破坏
# 系统/GMS 自己维护的数据。重启后所有 systemless 挂载会自然消失。

# ---------- 清理标记文件 ----------
rm -f "$MODDIR/.first_boot" 2>/dev/null

# ---------- 日志 ----------
if [ -d "$MODDIR/logs" ] 2>/dev/null; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)] 洛书模块已卸载" >> "$MODDIR/logs/fontswitch.log" 2>/dev/null || true
fi
