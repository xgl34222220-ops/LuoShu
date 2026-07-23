#!/system/bin/sh
# 洛书安全安装脚本。版本以 module.prop 为唯一来源。
set +e

MODPATH="${MODPATH:-$3}"
MODULE_VERSION=$(sed -n 's/^version=//p' "$MODPATH/module.prop" 2>/dev/null | head -n1)
[ -n "$MODULE_VERSION" ] || MODULE_VERSION="unknown"
MODULE_DIR="$MODPATH"
[ -f "$MODPATH/common/util_functions.sh" ] && . "$MODPATH/common/util_functions.sh"
[ -f "$MODPATH/common/rom_adapters.sh" ] && . "$MODPATH/common/rom_adapters.sh"
# customize.sh runs before the normal font runtime bridge is loaded. Set the new
# schema here so an active v2.1 payload is never mistaken for a current v2.2 payload.
LUOSHU_PAYLOAD_SCHEMA_CURRENT="${LUOSHU_PAYLOAD_SCHEMA_CURRENT:-device-template-v1-baseline-v7-mono-v6}"
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
