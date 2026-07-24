#!/system/bin/sh
# 洛书安全卸载：恢复模块明确记录的设置与持久字体，不修改 FontManagerService 数据文件。
set +e
MODDIR="${0%/*}"
MODULE_DIR="$MODDIR"
MODULE_VERSION=$(sed -n 's/^version=//p' "$MODDIR/module.prop" 2>/dev/null | head -n1)
[ -n "$MODULE_VERSION" ] || MODULE_VERSION="unknown"

_luoshu_uninstall_hash() {
    _luh_file="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$_luh_file" 2>/dev/null | awk '{print $1}'
    elif command -v busybox >/dev/null 2>&1; then
        busybox sha256sum "$_luh_file" 2>/dev/null | awk '{print $1}'
    else
        cksum "$_luh_file" 2>/dev/null | awk '{print $1 ":" $2}'
    fi
}

# 恢复安装洛书前记录的 Android 全局字体粗细设置。
if command -v settings >/dev/null 2>&1; then
    _fw_restore=0
    [ -f "$MODDIR/config/font_weight_original.conf" ] && \
        _fw_restore=$(sed -n 's/^adjustment=//p' "$MODDIR/config/font_weight_original.conf" 2>/dev/null | head -n1)
    case "$_fw_restore" in ''|*[!0-9-]*) _fw_restore=0 ;; esac
    settings --user current put secure font_weight_adjustment "$_fw_restore" >/dev/null 2>&1 || \
        settings put secure font_weight_adjustment "$_fw_restore" >/dev/null 2>&1 || true
fi

# 只撤销洛书记录的 /data/fonts/config/config.xml bind。目标内容、源内容和记录哈希
# 必须完全一致，避免误卸载其他模块或系统自己的挂载；这里不写入动态字体数据库。
_dynamic_state="$MODDIR/config/device-font-dynamic-mount.conf"
if [ -s "$_dynamic_state" ]; then
    _dynamic_source_rel=$(sed -n 's/^source=//p' "$_dynamic_state" 2>/dev/null | head -n1)
    _dynamic_target=$(sed -n 's/^target=//p' "$_dynamic_state" 2>/dev/null | head -n1)
    _dynamic_source_hash=$(sed -n 's/^sourceSha256=//p' "$_dynamic_state" 2>/dev/null | head -n1)
    case "$_dynamic_source_rel" in system/etc/.luoshu-data-fonts-config.xml) ;; *) _dynamic_source_rel='' ;; esac
    _dynamic_source="$MODDIR/$_dynamic_source_rel"
    _mountinfo="${LUOSHU_MOUNTINFO:-/proc/self/mountinfo}"
    if [ -n "$_dynamic_source_rel" ] && [ -s "$_dynamic_source" ] && [ -s "$_dynamic_target" ] && \
       [ "$(_luoshu_uninstall_hash "$_dynamic_source")" = "$_dynamic_source_hash" ] && \
       [ "$(_luoshu_uninstall_hash "$_dynamic_target")" = "$_dynamic_source_hash" ] && \
       awk -v path="$_dynamic_target" '$5 == path { found=1 } END { exit !found }' "$_mountinfo" 2>/dev/null; then
        umount "$_dynamic_target" 2>/dev/null || true
    fi
fi

# 恢复旧实验版本遗留的 provider 备份。v2.2 本身从不覆盖 /data/fonts/files。
if [ -f "$MODDIR/common/font_provider_cache.sh" ]; then
    . "$MODDIR/common/font_provider_cache.sh"
    luoshu_provider_cache_restore >/dev/null 2>&1 || true
fi

# Flyme 还存在 /data/customizecenter/font/flymeFont.ttf 持久槽；模块目录删除前
# 必须使用已保存的原厂副本完成原子恢复。其他 ROM 只使用 systemless 文件，无需写入。
if [ -f "$MODDIR/common/origin_flyme_global.sh" ]; then
    . "$MODDIR/common/origin_flyme_global.sh"
    if type _luoshu_detect_flyme >/dev/null 2>&1 && _luoshu_detect_flyme; then
        type _luoshu_flyme_prepare_data_restore >/dev/null 2>&1 && \
            _luoshu_flyme_prepare_data_restore >/dev/null 2>&1 || true
        type luoshu_flyme_pending_apply >/dev/null 2>&1 && \
            luoshu_flyme_pending_apply >/dev/null 2>&1 || true
    fi
fi

rm -f "$MODDIR/.first_boot" "$MODDIR/.font_switch.lock" 2>/dev/null || true
mkdir -p "$MODDIR/logs" 2>/dev/null || true
echo "[$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)] 洛书 $MODULE_VERSION 已卸载" >> "$MODDIR/logs/fontswitch.log" 2>/dev/null || true
exit 0
