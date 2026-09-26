#!/system/bin/sh
# 洛书安全安装脚本。版本以 module.prop 为唯一来源。
set +e

MODPATH="${MODPATH:-$3}"
MODULE_VERSION=$(sed -n 's/^version=//p' "$MODPATH/module.prop" 2>/dev/null | head -n1)
[ -n "$MODULE_VERSION" ] || MODULE_VERSION="unknown"
MODULE_DIR="$MODPATH"
[ -f "$MODPATH/common/util_functions.sh" ] && . "$MODPATH/common/util_functions.sh"
# customize.sh runs before the normal font runtime bridge is loaded. Keep this in
# lockstep with device_font_payload_bridge.sh so upgrades are classified once.
LUOSHU_PAYLOAD_SCHEMA_CURRENT=device-template-v2-baseline-v9-rolegraph-v2
[ -f "$MODPATH/common/module_update_state.sh" ] && . "$MODPATH/common/module_update_state.sh"

if type ensure_public_storage >/dev/null 2>&1; then
    ensure_public_storage
else
    mkdir -p /sdcard/LuoShu/fonts /sdcard/LuoShu/import /sdcard/LuoShu/reports 2>/dev/null || true
fi
_install_android=$(getprop ro.build.version.release 2>/dev/null)
_install_rom="Android ${_install_android:-未知} · 自动识别本机字体"

ROOT_MANAGER="Root"
if command -v apd >/dev/null 2>&1 || [ -d /data/adb/apatch ]; then
    ROOT_MANAGER="APatch"
elif command -v ksud >/dev/null 2>&1 || [ -d /data/adb/ksu ]; then
    ROOT_MANAGER="KernelSU / SukiSU Ultra"
elif command -v magisk >/dev/null 2>&1 || [ -d /data/adb/magisk ]; then
    ROOT_MANAGER="Magisk"
fi
ui_print "系统：$_install_rom · $ROOT_MANAGER"
ui_print "按实际字体文件判断替换能力；Emoji、图标与纯符号保留"

OLD_MOD="${LUOSHU_OLD_MOD:-/data/adb/modules/LuoShu}"
mkdir -p "$MODPATH/system/fonts" "$MODPATH/system/bin" "$MODPATH/config" "$MODPATH/logs" 2>/dev/null || true

# Flashing LuoShu is an explicit enable action. Root managers install updates into MODPATH while
# the currently active module remains in OLD_MOD until reboot, so both trees must be recovered.
# v2.0.0 could create disable itself and then discard the failure counter during a later update,
# which means the marker can no longer be distinguished from a manual one. The explicit flash is
# the authority to re-enable this module; never carry that stale marker into or through an update.
UPDATE_REENABLED=false
for _enable_dir in "$MODPATH" "$OLD_MOD"; do
    [ -d "$_enable_dir" ] || continue
    if [ -e "$_enable_dir/disable" ]; then
        rm -f "$_enable_dir/disable" 2>/dev/null || true
        [ -e "$_enable_dir/disable" ] || UPDATE_REENABLED=true
    fi
    rm -f "$_enable_dir/config/font-boot-failures" \
          "$_enable_dir/config/font-payload-quarantine.conf" 2>/dev/null || true
done
rm -f "$MODPATH/remove" 2>/dev/null || true
UPDATE_PRESERVED=false
RUNTIME_RECOVERY_RESET=false

# 更新安装只迁移活动配置和旧负载。后台服务不得改写字体；架构升级由
# 用户下一次明确应用在同一个前台事务中一次提交。
if type luoshu_runtime_recovery_required >/dev/null 2>&1 && \
   luoshu_runtime_recovery_required "$OLD_MOD" "$MODPATH"; then
    # v3.3.4+ uses the recovered v3.0 runtime.  Never carry a generated v3.1-v3.3
    # payload across that boundary: keep user choices, boot once on stock, and
    # let the user explicitly build a clean payload with the recovered engine.
    RUNTIME_RECOVERY_RESET=true
elif type luoshu_migrate_active_install >/dev/null 2>&1; then
    if luoshu_migrate_active_install "$OLD_MOD" "$MODPATH"; then
        UPDATE_PRESERVED=true
    fi
fi

if [ "$UPDATE_PRESERVED" != true ]; then
    # 全新安装或旧负载无效时，仅迁移可安全复用的用户偏好。
    for _config in font_weight.conf font_weight_original.conf axes_mix.conf font_mix.conf; do
        [ -f "$OLD_MOD/config/$_config" ] && cp -f "$OLD_MOD/config/$_config" "$MODPATH/config/$_config" 2>/dev/null || true
    done
    for _state in previous_font.conf switch_task.conf mix_task.conf axes_task.conf text_reboot_required.conf \
                  font_weight_reboot_required.conf active_emoji.conf emoji_task.conf emoji_reboot_required.conf \
                  webui_font_list.json webui_font_list.key native_font_index.json native_font_index.key \
                  app_install_pending app_install_state.conf app_install_manual font-payload-schema.conf \
                  font-payload-rebuild-pending.conf font-payload-boot.conf font-payload-manifest.conf; do
        rm -f "$MODPATH/config/$_state" 2>/dev/null || true
    done
    rm -f "$MODPATH/system/etc/fonts.xml" "$MODPATH/system/etc/font_fallback.xml" \
          "$MODPATH/system/fonts/NotoColorEmoji.ttf" "$MODPATH/system/fonts/NotoColorEmojiLegacy.ttf" 2>/dev/null || true
    _old_selected=$(head -n1 "$OLD_MOD/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    if [ -n "$_old_selected" ] && [ "$_old_selected" != default ]; then
        # Migration state must never prevent the module from installing. Preserve
        # the user's last selection as recovery metadata, boot stock if the exact
        # old payload cannot be trusted, and still run the universal stock scan.
        printf '%s\n' "$_old_selected" > "$MODPATH/config/previous_font.conf" 2>/dev/null || true
        : > "$MODPATH/config/stock_inventory_scan_pending" 2>/dev/null || true
        ui_print "• 旧字体负载 $_old_selected 无法完整迁移；继续安装并重新扫描本机字体槽位"
    fi
    printf 'default\n' > "$MODPATH/config/active_font.conf"
fi

# 必须在新模块覆盖挂载系统字体之前读取原厂槽位。v2 扫描器会分别统计全部原厂
# 字体文件和可替换 UI 槽位，并读取 system、system_ext、product、my_product、vendor
# 各分区的 fonts*.xml。刷写时重新验证可信原厂视图，日常操作再复用有效清单。
luoshu_install_stage 2 '检测原厂字体与 UI 槽位'
_inventory_started=$(date +%s 2>/dev/null)
LUOSHU_INSTALL_SCAN_SUMMARY='待首次启动补扫'
FONT_INVENTORY_SCRIPT="$MODPATH/common/stock_inventory_scan.py"
[ -f "$FONT_INVENTORY_SCRIPT" ] || FONT_INVENTORY_SCRIPT="$MODPATH/common/font_inventory_scan.py"
[ -f "$FONT_INVENTORY_SCRIPT" ] || FONT_INVENTORY_SCRIPT="$MODPATH/common/font_inventory.py"
FONT_INVENTORY_PYTHON="$MODPATH/common/python/bin/luoshu-python"
FONT_INVENTORY_OUTPUT="$MODPATH/config/device_font_inventory.json"
FONT_INVENTORY_CANDIDATES="$MODPATH/config/device_font_candidates.json"
FONT_INVENTORY_LOG="$MODPATH/logs/font-inventory.log"
if [ ! -s "$FONT_INVENTORY_OUTPUT" ] && [ -s "$OLD_MOD/config/device_font_inventory.json" ]; then
    cp -f "$OLD_MOD/config/device_font_inventory.json" "$FONT_INVENTORY_OUTPUT" 2>/dev/null || true
fi
chmod 0755 "$FONT_INVENTORY_PYTHON" 2>/dev/null || true
if [ -f "$FONT_INVENTORY_SCRIPT" ] && [ -x "$FONT_INVENTORY_PYTHON" ]; then
    ui_print "正在扫描全部系统字体文件和字体配置，包含各分区与嵌套目录。"
    _inventory_pyroot="$MODPATH/common/python"
    _inventory_result=$(
        LUOSHU_FRESH_STOCK_SCAN=1 \
        PYTHONHOME="$_inventory_pyroot" \
        PYTHONPATH="$_inventory_pyroot/lib/python3.14:$_inventory_pyroot/lib/python3.14/site-packages:$MODPATH/common" \
        LD_LIBRARY_PATH="$_inventory_pyroot/lib:$_inventory_pyroot/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
            "$FONT_INVENTORY_PYTHON" "$FONT_INVENTORY_SCRIPT" --scan --force \
                --output "$FONT_INVENTORY_OUTPUT" \
                --font-check "$MODPATH/common/font_check.sh" \
                --overlay-module "$OLD_MOD" 2>> "$FONT_INVENTORY_LOG"
    )
    _inventory_rc=$?
    printf '%s\n' "$_inventory_result" >> "$FONT_INVENTORY_LOG" 2>/dev/null || true
    if [ "$_inventory_rc" -eq 0 ]; then
        rm -f "$MODPATH/config/stock_inventory_scan_pending" 2>/dev/null || true
        _inventory_files=$(printf '%s' "$_inventory_result" | sed -n 's/.*"stockFontFileCount"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' | tail -n1)
        _inventory_slots=$(printf '%s' "$_inventory_result" | sed -n 's/.*"slotCount"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' | tail -n1)
        _inventory_xml=$(printf '%s' "$_inventory_result" | sed -n 's/.*"xmlSlotCount"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' | tail -n1)
        _inventory_heuristic=$(printf '%s' "$_inventory_result" | sed -n 's/.*"heuristicSlotCount"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' | tail -n1)
        _inventory_generic=$(printf '%s' "$_inventory_result" | sed -n 's/.*"genericSlotCount"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' | tail -n1)
        _inventory_physical=$(printf '%s' "$_inventory_result" | sed -n 's/.*"physicalSlotCount"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' | tail -n1)
        _inventory_dynamic=$(printf '%s' "$_inventory_result" | sed -n 's/.*"dynamicPartitionCount"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' | tail -n1)
        _inventory_nested_roots=$(printf '%s' "$_inventory_result" | sed -n 's/.*"nestedFontRootCount"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' | tail -n1)
        [ -n "$_inventory_files" ] || _inventory_files="未知"
        [ -n "$_inventory_slots" ] || _inventory_slots="未知"
        [ -n "$_inventory_xml" ] || _inventory_xml="未知"
        [ -n "$_inventory_heuristic" ] || _inventory_heuristic="0"
        [ -n "$_inventory_generic" ] || _inventory_generic="0"
        [ -n "$_inventory_physical" ] || _inventory_physical="0"
        [ -n "$_inventory_dynamic" ] || _inventory_dynamic="0"
        [ -n "$_inventory_nested_roots" ] || _inventory_nested_roots="0"
        _inventory_elapsed=$(luoshu_install_elapsed "$_inventory_started")
        LUOSHU_INSTALL_SCAN_SUMMARY="$_inventory_files 个原厂字体 / $_inventory_slots 个已识别文字槽位"
        ui_print "✓ 原厂字体 $_inventory_files 个 · 文字槽位 $_inventory_slots 个${_inventory_elapsed:+ · $_inventory_elapsed 秒}"
        ui_print "  应用字体时逐个替换其中可用的中文、英文与数字，其余字形保留。"
        ui_print "  XML $_inventory_xml / 通用 $_inventory_generic / OEM $_inventory_heuristic / 补充 $_inventory_physical"
        if [ "$_inventory_dynamic" -gt 0 ] 2>/dev/null || [ "$_inventory_nested_roots" -gt 0 ] 2>/dev/null; then
            ui_print "  额外 OEM 分区 $_inventory_dynamic 个 · 嵌套字体目录 $_inventory_nested_roots 个"
        fi
    else
        # The install must remain successful even when the current flash namespace
        # cannot expose a verified stock lower/mirror. Keep a retry marker so the
        # pre-mount boot hook scans before LuoShu mounts its own payload.
        : > "$MODPATH/config/stock_inventory_scan_pending" 2>/dev/null || true
        _inventory_candidates=$(sed -n 's/.*"candidateCount"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' "$FONT_INVENTORY_CANDIDATES" 2>/dev/null | head -n1)
        _inventory_font_paths=$(sed -n 's/.*"fontFileCount"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' "$FONT_INVENTORY_CANDIDATES" 2>/dev/null | head -n1)
        [ -n "$_inventory_candidates" ] || _inventory_candidates="0"
        [ -n "$_inventory_font_paths" ] || _inventory_font_paths="0"
        ui_print "! 原厂字体视图尚未通过验证"
        ui_print "  已找到 $_inventory_font_paths 个路径 / $_inventory_candidates 个候选"
        _inventory_error=$(tail -n 3 "$FONT_INVENTORY_LOG" 2>/dev/null | sed -n 's/.*"message"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | tail -n1)
        [ -z "$_inventory_error" ] || ui_print "  原因：$_inventory_error"
        ui_print "  将在下次启动、挂载字体前重试；当前安装继续。"
        ui_print "  详情：logs/font-inventory.log"
    fi
else
    : > "$MODPATH/config/stock_inventory_scan_pending" 2>/dev/null || true
    ui_print "! 扫描组件暂不可用；已安排下次启动、挂载前重试。"
fi
luoshu_install_stage 3 '配置模块与洛书 App'
# 安装安全 CLI，不暴露上一字体回滚、热刷新或重启 SystemUI 命令。
cp -f "$MODPATH/common/luoshu_cli.sh" "$MODPATH/system/bin/洛书" 2>/dev/null || true
chmod 0755 "$MODPATH"/*.sh "$MODPATH/common"/*.sh 2>/dev/null || true
chmod 0644 "$MODPATH/common"/*.py 2>/dev/null || true
chmod 0755 "$MODPATH/common/python/bin/luoshu-python" "$MODPATH/common/python/bin/luoshu-brotli" "$MODPATH/system/bin/洛书" 2>/dev/null || true
[ ! -f "$MODPATH/system/bin/luoshud" ] || chmod 0755 "$MODPATH/system/bin/luoshud" 2>/dev/null || true
find "$MODPATH/system/fonts" -type f -exec chmod 0644 {} \; 2>/dev/null || true
chmod 0755 "$MODPATH/system/fonts" "$MODPATH/system/bin" "$MODPATH/config" "$MODPATH/logs" 2>/dev/null || true
[ ! -f "$MODPATH/bundled/LuoShu-App.apk" ] || chmod 0644 "$MODPATH/bundled/LuoShu-App.apk" "$MODPATH/bundled/app.prop" 2>/dev/null || true
touch "$MODPATH/magic" 2>/dev/null || true

ui_print "✓ 模块文件已准备"
[ "$UPDATE_REENABLED" = true ] && ui_print "✓ 已重新启用模块"
if [ "$UPDATE_PRESERVED" = true ]; then
    _preserved_font=$(head -n1 "$MODPATH/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_preserved_font" ] || _preserved_font=default
    ui_print "✓ 已继承当前字体：$_preserved_font"
elif [ "$RUNTIME_RECOVERY_RESET" = true ]; then
    ui_print "• 已清理不兼容的旧引擎负载，保留选择与组合偏好"
fi

LUOSHU_INSTALL_APP_SUMMARY='需要重新下载完整模块包'
if [ -s "$MODPATH/bundled/LuoShu-App.apk" ] && [ -f "$MODPATH/common/app_installer.sh" ]; then
    ui_print '正在检查 App 版本与安装状态...'
    _app_result=$(MODDIR="$MODPATH" APP_INSTALL_LOG="$MODPATH/logs/app-install.log" sh "$MODPATH/common/app_installer.sh" flash 2>/dev/null)
    _app_code=$?
    case "$_app_result:$_app_code" in
        installed:0)
            LUOSHU_INSTALL_APP_SUMMARY='已安装或更新'
            ui_print "✓ 洛书 App 已安装或更新"
            ;;
        already-current:0)
            LUOSHU_INSTALL_APP_SUMMARY='已是当前版本'
            ui_print "✓ 洛书 App 已是当前版本"
            ;;
        permanent-failure:*)
            LUOSHU_INSTALL_APP_SUMMARY='安装受阻，请查看安装日志'
            ui_print '! App 安装包或签名不兼容，自动重试无法解决'
            ui_print '  模块保留；详情见 logs/app-install.log。'
            ;;
        invalid-package:*|invalid-apk:*|not-bundled:*)
            LUOSHU_INSTALL_APP_SUMMARY='校验失败，请重新下载完整模块包'
            ui_print '! 内置 App 校验失败，已拒绝安装'
            ui_print '  请重新下载完整模块包；详情见 logs/app-install.log。'
            ;;
        deferred:*|failed:*)
            LUOSHU_INSTALL_APP_SUMMARY='待首次启动自动补装'
            ui_print '• App 安装暂未完成，将在首次启动后重试'
            ui_print '  也可重启后点击模块“操作”按钮重试。'
            ;;
        *)
            LUOSHU_INSTALL_APP_SUMMARY='安装状态未知，请查看安装日志'
            ui_print "! App 安装器未返回有效状态（退出码 $_app_code）"
            ui_print '  重启后可点击模块“操作”按钮重试。'
            ;;
    esac
else
    ui_print "! 内置 App 或安装器缺失，请重新下载完整模块包"
fi
[ -f "$MODPATH/common/module_status.sh" ] && MODDIR="$MODPATH" sh "$MODPATH/common/module_status.sh" "$(head -n1 "$MODPATH/config/active_font.conf" 2>/dev/null)" >/dev/null 2>&1 || true
exit 0
