#!/system/bin/sh
# 洛书安全安装脚本。版本以 module.prop 为唯一来源。
set +e

MODPATH="${MODPATH:-$3}"
MODULE_VERSION=$(sed -n 's/^version=//p' "$MODPATH/module.prop" 2>/dev/null | head -n1)
[ -n "$MODULE_VERSION" ] || MODULE_VERSION="unknown"
MODULE_DIR="$MODPATH"
[ -f "$MODPATH/common/util_functions.sh" ] && . "$MODPATH/common/util_functions.sh"
[ -f "$MODPATH/common/rom_adapters.sh" ] && . "$MODPATH/common/rom_adapters.sh"
# customize.sh runs before the normal font runtime bridge is loaded. Set the v2.2
# schema first so a v2.1 payload is always scheduled for a device-template rebuild.
LUOSHU_PAYLOAD_SCHEMA_CURRENT=device-template-v1-baseline-v7-mono-v6
[ -f "$MODPATH/common/module_update_state.sh" ] && . "$MODPATH/common/module_update_state.sh"

if type ensure_public_storage >/dev/null 2>&1; then
    ensure_public_storage
else
    mkdir -p /sdcard/LuoShu/fonts /sdcard/LuoShu/import /sdcard/LuoShu/reports 2>/dev/null || true
fi
type check_coloros >/dev/null 2>&1 && check_coloros
type check_hyperos >/dev/null 2>&1 && check_hyperos

ui_print ""
ui_print "╔══════════════════════════════════╗"
ui_print "║  洛书 $MODULE_VERSION"
ui_print "║  Android 全局字体管理"
ui_print "╚══════════════════════════════════╝"
ui_print "• 用于管理和应用 Android 全局文字字体"
ui_print "• 支持单字体、多字重以及中英数字复合字体"
ui_print "• Emoji、图标、衬线与斜体保持系统原样"
if [ "${IS_COLOROS:-false}" = true ]; then
    ui_print "✓ 系统：ColorOS ${COLOROS_VERSION:-未知}"
elif [ "${IS_HYPEROS:-false}" = true ]; then
    ui_print "✓ 系统：HyperOS/MIUI ${HYPEROS_VERSION:-未知}"
else
    ui_print "✓ 系统：通用 Android"
fi

ROOT_MANAGER="Root"
if command -v apd >/dev/null 2>&1 || [ -d /data/adb/apatch ]; then
    ROOT_MANAGER="APatch"
elif command -v ksud >/dev/null 2>&1 || [ -d /data/adb/ksu ]; then
    ROOT_MANAGER="KernelSU / SukiSU Ultra"
elif command -v magisk >/dev/null 2>&1 || [ -d /data/adb/magisk ]; then
    ROOT_MANAGER="Magisk"
fi
ui_print "✓ Root：$ROOT_MANAGER"

MOUNTIFY_ACTIVE=false
if [ -d /data/adb/modules/mountify ] && [ ! -f /data/adb/modules/mountify/disable ] && [ ! -f /data/adb/modules/mountify/remove ]; then
    MOUNTIFY_ACTIVE=true
elif [ -d /data/adb/mountify ]; then
    MOUNTIFY_ACTIVE=true
fi
[ "$MOUNTIFY_ACTIVE" = true ] && ui_print "✓ Mountify：已启用" || ui_print "• 元模块推荐：Mountify（可选）"

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

# 更新安装只迁移活动配置和旧负载；任何耗时字体生成都移到完整开机后的后台服务。
if type luoshu_migrate_active_install >/dev/null 2>&1; then
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
    printf 'default\n' > "$MODPATH/config/active_font.conf"
fi

# 必须在新模块覆盖挂载系统字体之前读取原厂槽位。v2 扫描器会分别统计全部原厂
# 字体文件和可替换 UI 槽位，并读取 system、system_ext、product、my_product、vendor
# 各分区的 fonts*.xml。相同系统指纹复用；旧扫描器生成的清单会自动升级重扫。
FONT_INVENTORY_SCRIPT="$MODPATH/common/font_inventory_scan.py"
[ -f "$FONT_INVENTORY_SCRIPT" ] || FONT_INVENTORY_SCRIPT="$MODPATH/common/font_inventory.py"
FONT_INVENTORY_PYTHON="$MODPATH/common/python/bin/luoshu-python"
FONT_INVENTORY_OUTPUT="$MODPATH/config/device_font_inventory.json"
FONT_INVENTORY_LOG="$MODPATH/logs/font-inventory.log"
if [ ! -s "$FONT_INVENTORY_OUTPUT" ] && [ -s "$OLD_MOD/config/device_font_inventory.json" ]; then
    cp -f "$OLD_MOD/config/device_font_inventory.json" "$FONT_INVENTORY_OUTPUT" 2>/dev/null || true
fi
chmod 0755 "$FONT_INVENTORY_PYTHON" 2>/dev/null || true
if [ -f "$FONT_INVENTORY_SCRIPT" ] && [ -x "$FONT_INVENTORY_PYTHON" ]; then
    ui_print "• 正在读取本机全部原厂字体与 UI 映射..."
    _inventory_pyroot="$MODPATH/common/python"
    _inventory_result=$(
        PYTHONHOME="$_inventory_pyroot" \
        PYTHONPATH="$_inventory_pyroot/lib/python3.14:$_inventory_pyroot/lib/python3.14/site-packages:$MODPATH/common" \
        LD_LIBRARY_PATH="$_inventory_pyroot/lib:$_inventory_pyroot/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
            "$FONT_INVENTORY_PYTHON" "$FONT_INVENTORY_SCRIPT" --scan \
                --output "$FONT_INVENTORY_OUTPUT" \
                --font-check "$MODPATH/common/font_check.sh" \
                --overlay-module "$OLD_MOD" 2>> "$FONT_INVENTORY_LOG"
    )
    _inventory_rc=$?
    printf '%s\n' "$_inventory_result" >> "$FONT_INVENTORY_LOG" 2>/dev/null || true
    if [ "$_inventory_rc" -eq 0 ]; then
        _inventory_files=$(printf '%s' "$_inventory_result" | sed -n 's/.*"stockFontFileCount"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' | tail -n1)
        _inventory_slots=$(printf '%s' "$_inventory_result" | sed -n 's/.*"slotCount"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' | tail -n1)
        _inventory_xml=$(printf '%s' "$_inventory_result" | sed -n 's/.*"xmlSlotCount"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' | tail -n1)
        _inventory_heuristic=$(printf '%s' "$_inventory_result" | sed -n 's/.*"heuristicSlotCount"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' | tail -n1)
        _inventory_rom=$(printf '%s' "$_inventory_result" | sed -n 's/.*"romKind"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | tail -n1)
        [ -n "$_inventory_files" ] || _inventory_files="未知"
        [ -n "$_inventory_slots" ] || _inventory_slots="未知"
        [ -n "$_inventory_xml" ] || _inventory_xml="未知"
        [ -n "$_inventory_heuristic" ] || _inventory_heuristic="未知"
        [ -n "$_inventory_rom" ] || _inventory_rom="generic"
        ui_print "✓ 原厂字体文件：$_inventory_files 个（ROM：$_inventory_rom）"
        ui_print "✓ 可替换 UI 槽位：$_inventory_slots 个（XML $_inventory_xml / OEM 探测 $_inventory_heuristic）"
    else
        ui_print "• 原厂字体清单扫描不可用，本机将自动使用旧静态适配清单"
    fi
else
    ui_print "• 字体清单扫描器不可用，本机将自动使用旧静态适配清单"
fi
# 安装安全 CLI，不暴露上一字体回滚、热刷新或重启 SystemUI 命令。
cp -f "$MODPATH/common/luoshu_cli.sh" "$MODPATH/system/bin/洛书" 2>/dev/null || true
chmod 0755 "$MODPATH"/*.sh "$MODPATH/common"/*.sh 2>/dev/null || true
chmod 0644 "$MODPATH/common"/*.py 2>/dev/null || true
chmod 0755 "$MODPATH/common/python/bin/luoshu-python" "$MODPATH/system/bin/洛书" 2>/dev/null || true
[ ! -f "$MODPATH/system/bin/luoshud" ] || chmod 0755 "$MODPATH/system/bin/luoshud" 2>/dev/null || true
find "$MODPATH/system/fonts" -type f -exec chmod 0644 {} \; 2>/dev/null || true
chmod 0755 "$MODPATH/system/fonts" "$MODPATH/system/bin" "$MODPATH/config" "$MODPATH/logs" 2>/dev/null || true
[ ! -f "$MODPATH/bundled/LuoShu-App.apk" ] || chmod 0644 "$MODPATH/bundled/LuoShu-App.apk" "$MODPATH/bundled/app.prop" 2>/dev/null || true
touch "$MODPATH/magic" 2>/dev/null || true

ui_print "✓ 模块文件已部署"
[ "$UPDATE_REENABLED" = true ] && ui_print "✓ 已解除旧版误设的 disable 标记"
if [ "$UPDATE_PRESERVED" = true ]; then
    _preserved_font=$(head -n1 "$MODPATH/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_preserved_font" ] || _preserved_font=default
    ui_print "✓ 已继承当前字体配置：$_preserved_font"
    if [ "${LUOSHU_UPDATE_REBUILD_REQUIRED:-false}" = true ]; then
        ui_print "• 旧版字体负载将在首次开机后后台重建"
        ui_print "• 本次刷写不再等待字体生成"
    else
        ui_print "✓ 更新后只需重启一次，无需重新应用字体"
    fi
else
    ui_print "✓ 当前保持系统默认字体"
fi

if [ -s "$MODPATH/bundled/LuoShu-App.apk" ] && [ -f "$MODPATH/common/app_installer.sh" ]; then
    _app_result=$(MODDIR="$MODPATH" APP_INSTALL_LOG="$MODPATH/logs/app-install.log" sh "$MODPATH/common/app_installer.sh" flash 2>/dev/null)
    _app_code=$?
    case "$_app_result" in
        installed) ui_print "✓ 洛书 App 已自动安装或更新" ;;
        already-current) ui_print "✓ 洛书 App 已是当前版本，无需重复安装" ;;
        *)
            ui_print "• 当前刷写环境无法完成 App 安装，将在首次开机后自动补装"
            ui_print "• 也可以重启后点击模块“操作”按钮手动重试"
            [ "$_app_code" -eq 0 ] || true
            ;;
    esac
else
    ui_print "✗ 模块内置 App 或安装器缺失，请重新下载洛书模块包"
fi
if [ "$UPDATE_PRESERVED" = true ] && [ "${LUOSHU_UPDATE_REBUILD_REQUIRED:-false}" = true ]; then
    ui_print "请先完整重启；后台重建完成后会通知再次重启。"
elif [ "$UPDATE_PRESERVED" = true ]; then
    ui_print "请完整重启一次，新版字体会直接生效。"
else
    ui_print "请完整重启后进入洛书 App 配置字体。"
fi
ui_print ""
[ -f "$MODPATH/common/module_status.sh" ] && MODDIR="$MODPATH" sh "$MODPATH/common/module_status.sh" "$(head -n1 "$MODPATH/config/active_font.conf" 2>/dev/null)" >/dev/null 2>&1 || true
exit 0
