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
[ -f "$MODDIR/common/font_config_runtime.sh" ] && . "$MODDIR/common/font_config_runtime.sh"
[ -f "$MODDIR/common/font_config_partitions.sh" ] && . "$MODDIR/common/font_config_partitions.sh"
[ -f "$MODDIR/common/mount_compat.sh" ] && . "$MODDIR/common/mount_compat.sh"
[ -f "$MODDIR/common/font_provider_cache.sh" ] && . "$MODDIR/common/font_provider_cache.sh"

# Android toybox 的 chcon 不支持 GNU --reference；启动路径按目标文件实际标签复制。
_luoshu_provider_match_metadata() {
    _lpmm_source="$1"
    _lpmm_target="$2"
    _lpmm_uid=$(stat -c '%u' "$_lpmm_target" 2>/dev/null)
    _lpmm_gid=$(stat -c '%g' "$_lpmm_target" 2>/dev/null)
    _lpmm_mode=$(stat -c '%a' "$_lpmm_target" 2>/dev/null)
    [ -n "$_lpmm_uid" ] && [ -n "$_lpmm_gid" ] && chown "$_lpmm_uid:$_lpmm_gid" "$_lpmm_source" 2>/dev/null || true
    chmod "${_lpmm_mode:-644}" "$_lpmm_source" 2>/dev/null || true
    if command -v chcon >/dev/null 2>&1; then
        _lpmm_context=$(ls -Zd "$_lpmm_target" 2>/dev/null | awk '{print $1}')
        case "$_lpmm_context" in *:*:*:*) chcon "$_lpmm_context" "$_lpmm_source" 2>/dev/null || true ;; esac
    fi
}

type init_module >/dev/null 2>&1 && init_module
type ensure_public_storage >/dev/null 2>&1 && ensure_public_storage
mkdir -p "$MODDIR/config" "$MODDIR/logs" "$MODDIR/system/fonts" 2>/dev/null || true

# 每次启动静默校正原生 App 后端脚本权限。
chmod 0755 "$MODDIR" "$MODDIR/common" 2>/dev/null || true
chmod 0755 "$MODDIR/customize.sh" "$MODDIR/post-fs-data.sh" "$MODDIR/service.sh" "$MODDIR/uninstall.sh" "$MODDIR/action.sh" 2>/dev/null || true
find "$MODDIR/common" -maxdepth 1 -type f -exec chmod 0755 {} \; 2>/dev/null || true
chmod 0644 "$MODDIR/common/font_instance.py" "$MODDIR/common/composite_font.py" \
    "$MODDIR/common/font_axis_info.py" "$MODDIR/common/font_config_overlay.py" \
    "$MODDIR/common/font_name_normalize.py" "$MODDIR/common/font_metrics_normalize.py" \
    "$MODDIR/common/font_config_targets.py" 2>/dev/null || true

log_message "INFO" "===== post-fs-data $MODULE_VERSION 开始 ====="

# Emoji、symbols 与其他语言字体始终由 ROM 原始 fallback 保留。
rm -f "$MODDIR/system/fonts/NotoColorEmoji.ttf" "$MODDIR/system/fonts/NotoColorEmojiLegacy.ttf" 2>/dev/null || true
rm -f "$MODDIR/config/active_emoji.conf" "$MODDIR/config/emoji_task.conf" "$MODDIR/config/emoji_reboot_required.conf" 2>/dev/null || true

# 升级时清理实验版本遗留任务，避免原生 App 接管错误状态。
rm -f "$MODDIR/config"/v*_axes_task.conf "$MODDIR/config"/v*_axes_mix.conf "$MODDIR/config"/v*_axes_worker.pid 2>/dev/null || true
chmod 0755 "$MODDIR/common/python/bin/luoshu-python" 2>/dev/null || true

# 通过统一桥恢复中断的原子负载，并清理独立字重暂存任务。
if [ -f "$MODDIR/common/font_mix_controller.sh" ]; then
    MODDIR="$MODDIR" sh "$MODDIR/common/font_mix_controller.sh" recover >/dev/null 2>&1 || true
elif [ -f "$MODDIR/common/font_mix.sh" ]; then
    MODDIR="$MODDIR" sh "$MODDIR/common/font_mix.sh" recover >/dev/null 2>&1 || true
fi

ACTIVE_TEXT=$(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
[ -n "$ACTIVE_TEXT" ] || ACTIVE_TEXT="default"

# 架构升级负载会在 Android 完成启动后后台重建。第一次启动暂时沿用旧负载，
# 避免在 post-fs-data 阶段执行分钟级字体生成或提前把待迁移配置隔离掉。
if [ -f "$MODDIR/config/font-payload-rebuild-pending.conf" ]; then
    log_message "INFO" "检测到待后台重建的字体负载；本次启动跳过架构隔离"
elif type font_config_boot_guard >/dev/null 2>&1; then
    # 常规启动仍严格验证 XML、UI/Mono 九档和负载架构。
    font_config_boot_guard "$ACTIVE_TEXT" || true
fi

# Android 12+ 会在系统字体配置之后追加 /data/fonts/config/config.xml 中的命名字体族。
# Play 商店等应用请求 google-sans* 时会绕过 /system/fonts 的洛书文件，因此必须在
# FontManagerService 初始化共享字体表之前完成配置桥接。这里只覆盖 XML 视图，不改写
# /data/fonts/files 的签名字体、fs-verity、Emoji 或其他动态字体。
if type luoshu_provider_cache_boot >/dev/null 2>&1; then
    _provider_rc=0
    luoshu_provider_cache_boot "$ACTIVE_TEXT" || _provider_rc=$?
    case "$_provider_rc" in
        0) log_message "INFO" "开机前动态 Google Sans 字体桥已启用" ;;
        2) log_message "INFO" "设备没有动态 Google Sans family，无需桥接" ;;
        *) log_message "ERROR" "动态 Google Sans 字体桥失败（code=$_provider_rc），继续使用 ROM 原配置" ;;
    esac
fi

for _partition in system system_ext product vendor odm oem my_product my_engineering my_company my_preload my_region my_stock oplus_product oplus_engineering oplus_version oplus_region mi_ext cust; do
    [ -d "$MODDIR/$_partition" ] || continue
    set_perm_recursive "$MODDIR/$_partition" 0 0 0755 0644 2>/dev/null || true
done

# 字体索引由原生 App 按需刷新，启动早期不扫描或复制大字体。

# 完整重启后解除本次开机切换保护。
rm -f "$MODDIR/config/text_reboot_required.conf" "$MODDIR/config/font_weight_reboot_required.conf" \
      "$MODDIR/.font_switch.lock" 2>/dev/null || true

log_message "INFO" "当前文字=$ACTIVE_TEXT | 重启保护已复位"
log_message "INFO" "===== post-fs-data 完成 ====="
exit 0
