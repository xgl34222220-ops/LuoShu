#!/system/bin/sh
# 洛书安全安装脚本。版本以 module.prop 为唯一来源。
set +e

MODPATH="${MODPATH:-$3}"
MODULE_VERSION=$(sed -n 's/^version=//p' "$MODPATH/module.prop" 2>/dev/null | head -n1)
[ -n "$MODULE_VERSION" ] || MODULE_VERSION="unknown"
MODULE_DIR="$MODPATH"
[ -f "$MODPATH/common/util_functions.sh" ] && . "$MODPATH/common/util_functions.sh"
[ -f "$MODPATH/common/rom_adapters.sh" ] && . "$MODPATH/common/rom_adapters.sh"
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
ui_print "• Emoji、图标和等宽字体默认保持系统原样"
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

mkdir -p "$MODPATH/system/fonts" "$MODPATH/system/bin" "$MODPATH/config" "$MODPATH/logs" 2>/dev/null || true
OLD_MOD="/data/adb/modules/LuoShu"
UPDATE_PRESERVED=false

# 更新安装继承当前活动字体与各分区负载；只清理任务、缓存、PID 和旧待重启标记。
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
                  app_install_pending app_install_state.conf app_install_manual; do
        rm -f "$MODPATH/config/$_state" 2>/dev/null || true
    done
    rm -f "$MODPATH/system/etc/fonts.xml" "$MODPATH/system/etc/font_fallback.xml" \
          "$MODPATH/system/fonts/NotoColorEmoji.ttf" "$MODPATH/system/fonts/NotoColorEmojiLegacy.ttf" 2>/dev/null || true
    printf 'default\n' > "$MODPATH/config/active_font.conf"
fi

# 安装安全 CLI，不暴露上一字体回滚、热刷新或重启 SystemUI 命令。
cp -f "$MODPATH/common/luoshu_cli.sh" "$MODPATH/system/bin/洛书" 2>/dev/null || true
chmod 0755 "$MODPATH"/*.sh "$MODPATH/common"/*.sh "$MODPATH/common/play_font_bridge" "$MODPATH/common/wechat_xweb_bridge" 2>/dev/null || true
chmod 0644 "$MODPATH/common"/*.py 2>/dev/null || true
chmod 0755 "$MODPATH/common/python/bin/luoshu-python" "$MODPATH/system/bin/洛书" 2>/dev/null || true
[ ! -f "$MODPATH/system/bin/luoshud" ] || chmod 0755 "$MODPATH/system/bin/luoshud" 2>/dev/null || true
find "$MODPATH/system/fonts" -type f -exec chmod 0644 {} \; 2>/dev/null || true
chmod 0755 "$MODPATH/system/fonts" "$MODPATH/system/bin" "$MODPATH/config" "$MODPATH/logs" 2>/dev/null || true
[ ! -f "$MODPATH/bundled/LuoShu-App.apk" ] || chmod 0644 "$MODPATH/bundled/LuoShu-App.apk" "$MODPATH/bundled/app.prop" 2>/dev/null || true
touch "$MODPATH/magic" 2>/dev/null || true

ui_print "✓ 模块文件已部署"
if [ "$UPDATE_PRESERVED" = true ]; then
    _preserved_font=$(head -n1 "$MODPATH/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    [ -n "$_preserved_font" ] || _preserved_font=default
    ui_print "✓ 已继承当前字体：$_preserved_font"
    ui_print "✓ 更新后只需重启一次，无需重新应用字体"
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
if [ "$UPDATE_PRESERVED" = true ]; then
    ui_print "请完整重启一次，新版本会继续使用当前字体。"
else
    ui_print "请完整重启后进入洛书 App 配置字体。"
fi
ui_print ""
[ -f "$MODPATH/common/module_status.sh" ] && MODDIR="$MODPATH" sh "$MODPATH/common/module_status.sh" "$(head -n1 "$MODPATH/config/active_font.conf" 2>/dev/null)" >/dev/null 2>&1 || true
exit 0
