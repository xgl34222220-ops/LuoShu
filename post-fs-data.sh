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

# Bind mount 的 mountinfo 根路径会省略 /data 前缀，不能用绝对源路径字符串判断。
# 同时确认目标是独立挂载点且内容与洛书生成文件一致，避免误卸载其他模块的挂载。
_luoshu_provider_mount_is_ours() {
    _lpmi_target="$1"
    _lpmi_source="$2"
    [ -r /proc/self/mountinfo ] && [ -f "$_lpmi_source" ] || return 1
    awk -v target="$_lpmi_target" '$5 == target { found=1 } END { exit !found }' \
        /proc/self/mountinfo 2>/dev/null || return 1
    cmp -s "$_lpmi_source" "$_lpmi_target" 2>/dev/null
}

# post-fs-data 专用启动实现：用 XML 节点校验，而不是搜索整个文件文本。
# /data/fonts/config/config.xml 仍会保留 GoogleSans 文件目录，只有同名 family 必须移除。
luoshu_provider_cache_boot() {
    _lpcb_active="${1:-default}"
    _lpcb_cfg="$(_luoshu_provider_config)"

    if [ "$_lpcb_active" = default ] || [ -z "$_lpcb_active" ]; then
        luoshu_provider_cache_restore
        return 0
    fi

    _luoshu_provider_restore_legacy_files
    _luoshu_provider_dynamic_google_present || return 2
    [ -s "$LUOSHU_PROVIDER_CONFIG_XML" ] && [ -s "$LUOSHU_PROVIDER_SYSTEM_XML" ] || return 2
    _luoshu_provider_select_fonts || {
        luoshu_provider_log "未找到可供 Google Sans family 使用的洛书系统字体"
        return 1
    }

    mkdir -p "$LUOSHU_PROVIDER_OVERLAY_DIR" "$_lpcb_cfg" 2>/dev/null || return 1
    _luoshu_provider_unmount_all

    _luoshu_provider_generate_overlays \
        "$LUOSHU_PROVIDER_CONFIG_XML" "$LUOSHU_PROVIDER_CONFIG_OVERLAY" \
        "$LUOSHU_PROVIDER_SYSTEM_XML" "$LUOSHU_PROVIDER_SYSTEM_OVERLAY" \
        "$LUOSHU_PROVIDER_REPORT"
    _lpcb_rc=$?
    if [ "$_lpcb_rc" -ne 0 ]; then
        rm -f "$LUOSHU_PROVIDER_CONFIG_OVERLAY" "$LUOSHU_PROVIDER_SYSTEM_OVERLAY" \
            "$LUOSHU_PROVIDER_REPORT" 2>/dev/null || true
        luoshu_provider_log "动态字体命名字体桥生成失败：code=$_lpcb_rc"
        return 1
    fi

    _luoshu_provider_python - \
        "$LUOSHU_PROVIDER_CONFIG_OVERLAY" "$LUOSHU_PROVIDER_SYSTEM_OVERLAY" <<'PY_LUOSHU_PROVIDER_VALIDATE' >/dev/null 2>&1
import re
import sys
import xml.etree.ElementTree as ET

blocked = re.compile(r"(google[-_\s]*sans|product[-_\s]*sans)", re.I)

def local_name(tag):
    return tag.rsplit("}", 1)[-1]

provider = ET.parse(sys.argv[1]).getroot()
for node in provider.iter():
    if local_name(node.tag) == "family" and blocked.search(node.attrib.get("name", "")):
        raise SystemExit(2)

system = ET.parse(sys.argv[2]).getroot()
seen = set()
for node in system.iter():
    if local_name(node.tag) == "family":
        seen.add(node.attrib.get("name", "").strip().lower())
required = {"google-sans", "google-sans-text", "google-sans-medium", "google-sans-bold"}
if not required.issubset(seen):
    raise SystemExit(3)
PY_LUOSHU_PROVIDER_VALIDATE
    _lpcb_rc=$?
    if [ "$_lpcb_rc" -ne 0 ]; then
        rm -f "$LUOSHU_PROVIDER_CONFIG_OVERLAY" "$LUOSHU_PROVIDER_SYSTEM_OVERLAY" \
            "$LUOSHU_PROVIDER_REPORT" 2>/dev/null || true
        luoshu_provider_log "动态字体 XML 节点校验失败：code=$_lpcb_rc"
        return 1
    fi

    _luoshu_provider_match_metadata "$LUOSHU_PROVIDER_SYSTEM_OVERLAY" "$LUOSHU_PROVIDER_SYSTEM_XML"
    _luoshu_provider_match_metadata "$LUOSHU_PROVIDER_CONFIG_OVERLAY" "$LUOSHU_PROVIDER_CONFIG_XML"

    if ! _luoshu_provider_bind_one "$LUOSHU_PROVIDER_SYSTEM_OVERLAY" "$LUOSHU_PROVIDER_SYSTEM_XML"; then
        rm -f "$LUOSHU_PROVIDER_CONFIG_OVERLAY" "$LUOSHU_PROVIDER_SYSTEM_OVERLAY" \
            "$LUOSHU_PROVIDER_REPORT" 2>/dev/null || true
        luoshu_provider_log "无法挂载系统 Google Sans 命名字体配置"
        return 1
    fi
    if ! _luoshu_provider_bind_one "$LUOSHU_PROVIDER_CONFIG_OVERLAY" "$LUOSHU_PROVIDER_CONFIG_XML"; then
        _luoshu_provider_unmount_one "$LUOSHU_PROVIDER_SYSTEM_XML" "$LUOSHU_PROVIDER_SYSTEM_OVERLAY" || true
        rm -f "$LUOSHU_PROVIDER_CONFIG_OVERLAY" "$LUOSHU_PROVIDER_SYSTEM_OVERLAY" \
            "$LUOSHU_PROVIDER_REPORT" 2>/dev/null || true
        luoshu_provider_log "无法挂载动态字体配置隔离层"
        return 1
    fi

    _lpcb_removed=$(sed -n 's/^removed=//p' "$LUOSHU_PROVIDER_REPORT" 2>/dev/null | head -n1)
    {
        printf 'mode=mounted\n'
        printf 'font=%s\n' "$_lpcb_active"
        printf 'removed=%s\n' "${_lpcb_removed:-0}"
        printf 'regular=%s\n' "$LUOSHU_PROVIDER_REGULAR"
        printf 'medium=%s\n' "$LUOSHU_PROVIDER_MEDIUM"
        printf 'bold=%s\n' "$LUOSHU_PROVIDER_BOLD"
        printf 'time=%s\n' "$(date +%s)"
    } > "$LUOSHU_PROVIDER_STATE" 2>/dev/null || true
    chmod 0644 "$LUOSHU_PROVIDER_STATE" "$LUOSHU_PROVIDER_REPORT" 2>/dev/null || true
    luoshu_provider_log "动态 Google Sans 命名字体桥已启用：移除 ${_lpcb_removed:-0} 个动态 family"
    return 0
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

# Android 12+ 的 FontManagerService 会在系统 XML 之后追加 /data/fonts 中的命名字体族，
# Play 商店因此可能继续使用下载版 Google Sans。必须在 FontManagerService 初始化前：
# 1. 保留所有签名字体文件、Emoji 与其他动态字体；
# 2. 只隐藏 Google/Product Sans 的动态 family；
# 3. 向当前 system fonts.xml 注入同名 family，指向洛书现有字体槽。
if type luoshu_provider_cache_boot >/dev/null 2>&1; then
    _provider_rc=0
    luoshu_provider_cache_boot "$ACTIVE_TEXT" || _provider_rc=$?
    case "$_provider_rc" in
        0) log_message "INFO" "Android 动态 Google Sans 命名字体桥已准备完成" ;;
        2) log_message "INFO" "设备没有动态 Google Sans 字体，无需额外处理" ;;
        *) log_message "ERROR" "Android 动态字体命名覆盖准备失败（code=$_provider_rc），继续使用原配置" ;;
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
