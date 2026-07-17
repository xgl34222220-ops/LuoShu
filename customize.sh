#!/system/bin/sh
# LuoShu v14.1 - 安装脚本

MODPATH="${MODPATH:-$3}"
set +e

MODULE_DIR="$MODPATH"
if [ -f "$MODPATH/common/util_functions.sh" ]; then . "$MODPATH/common/util_functions.sh"; fi
if [ -f "$MODPATH/common/font_check.sh" ]; then . "$MODPATH/common/font_check.sh"; fi
if [ -f "$MODPATH/common/rom_adapters.sh" ]; then . "$MODPATH/common/rom_adapters.sh"; fi
if [ -f "$MODPATH/common/volume_key.sh" ]; then . "$MODPATH/common/volume_key.sh"; fi

# 最小降级保护
if ! type detect_font_family >/dev/null 2>&1; then
    detect_font_family() { _n="${1%.*}"; echo "${_n%-*}"; }
fi
if ! type check_coloros >/dev/null 2>&1; then check_coloros() { IS_COLOROS=false; }; fi
if ! type check_hyperos >/dev/null 2>&1; then check_hyperos() { IS_HYPEROS=false; }; fi
if ! type ensure_public_storage >/dev/null 2>&1; then
    LUOSHU_PUBLIC_DIR="/sdcard/LuoShu"; USER_FONTS_DIR="$LUOSHU_PUBLIC_DIR/fonts"; USER_EMOJI_DIR="$LUOSHU_PUBLIC_DIR/emoji"; USER_REPORT_DIR="$LUOSHU_PUBLIC_DIR/reports"
    ensure_public_storage() { mkdir -p "$USER_FONTS_DIR" "$USER_EMOJI_DIR" "$USER_REPORT_DIR" 2>/dev/null || true; }
fi

ensure_public_storage
check_coloros
check_hyperos

ui_print ""
ui_print "╔══════════════════════════════════╗"
ui_print "║          洛书 v14.1           ║"
ui_print "║      Android 全局字体管理       ║"
ui_print "╚══════════════════════════════════╝"
ui_print ""
if [ "$IS_COLOROS" = "true" ]; then
    ui_print "✓ 系统环境：ColorOS ${COLOROS_VERSION:-未知}"
elif [ "$IS_HYPEROS" = "true" ]; then
    ui_print "✓ 系统环境：HyperOS/MIUI ${HYPEROS_VERSION:-未知}"
else
    ui_print "✓ 系统环境：通用 Android"
fi

ROOT_MANAGER="Root"
if command -v apd >/dev/null 2>&1 || [ -d /data/adb/ap ] || [ -d /data/adb/apatch ]; then
    ROOT_MANAGER="APatch"
elif command -v ksud >/dev/null 2>&1 || [ -d /data/adb/ksu ]; then
    _ksu_info="$(ksud -V 2>/dev/null || ksud --version 2>/dev/null || true)"
    case "$_ksu_info $(getprop ro.build.version.incremental 2>/dev/null)" in
        *SukiSU*|*sukisu*|*SUKISU*) ROOT_MANAGER="SukiSU Ultra" ;;
        *) ROOT_MANAGER="KernelSU" ;;
    esac
elif command -v magisk >/dev/null 2>&1 || [ -d /data/adb/magisk ]; then
    ROOT_MANAGER="Magisk"
fi
ui_print "✓ Root 管理器：$ROOT_MANAGER"

MOUNTIFY_ACTIVE=false
if [ -d /data/adb/modules/mountify ] && [ ! -f /data/adb/modules/mountify/disable ] && [ ! -f /data/adb/modules/mountify/remove ]; then
    MOUNTIFY_ACTIVE=true
elif [ -d /data/adb/mountify ]; then
    MOUNTIFY_ACTIVE=true
fi
if [ "$MOUNTIFY_ACTIVE" = "true" ]; then
    ui_print "✓ Mountify：已检测并启用"
else
    ui_print "• 元模块推荐：Mountify（可选）"
fi
ui_print "✓ 字体目录：/sdcard/LuoShu/fonts/"
ui_print "✓ Emoji 目录：/sdcard/LuoShu/emoji/"
ui_print ""

mkdir -p "$MODPATH/system/fonts" "$MODPATH/system/bin" "$MODPATH/config" "$MODPATH/logs" "$MODPATH/webroot/fonts" "$MODPATH/webroot/emoji" 2>/dev/null || true

scan_fonts_lines() {
    for _f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
              "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_f" ] || continue
        _fam=$(detect_font_family "$(basename "$_f")")
        case "$_fam" in SysFont*|SysSans*|'') continue ;; esac
        printf '%s\n' "$_fam"
    done | awk '!seen[$0]++'
}

FONT_LIST_TMP="$MODPATH/config/.install_fonts.$$"
scan_fonts_lines > "$FONT_LIST_TMP" 2>/dev/null || : > "$FONT_LIST_TMP"
FONT_COUNT=$(grep -c . "$FONT_LIST_TMP" 2>/dev/null)
[ -n "$FONT_COUNT" ] || FONT_COUNT=0
case "$FONT_COUNT" in ''|*[!0-9]*) FONT_COUNT=0 ;; esac

OLD_MOD="/data/adb/modules/LuoShu"
# 停止旧版可能仍在运行的复合任务，避免升级期间继续占用内存。
if [ -f "$OLD_MOD/config/mix_worker.pid" ]; then
    _old_worker=$(cat "$OLD_MOD/config/mix_worker.pid" 2>/dev/null | tr -cd '0-9')
    [ -z "$_old_worker" ] || kill "$_old_worker" 2>/dev/null || true
fi
if command -v pkill >/dev/null 2>&1; then
    pkill -f "$OLD_MOD/common/composite_font.py" 2>/dev/null || true
fi
rm -f "$OLD_MOD/.font_switch.lock" "$OLD_MOD/config/mix_worker.pid" "$OLD_MOD/config/composite_progress.json" 2>/dev/null || true

# 正式版刷写阶段只安装引擎，不扫描大字体、不生成复合字体、不继承旧文字负载。
# 这样刷写速度稳定，任何字体组合都由开机后的 WebUI 主动、事务式完成。
SELECTED_FONT="default"
rm -rf "$MODPATH/system/fonts" "$MODPATH/system_ext/fonts" "$MODPATH/product/fonts" 2>/dev/null || true
mkdir -p "$MODPATH/system/fonts" 2>/dev/null || true
ui_print "✓ 已安装完整复合字体引擎"
ui_print "• 检测到字体库：${FONT_COUNT} 款（刷写阶段不处理）"
ui_print "• 首次启动保持系统默认字体"
ui_print "• 重启后从 WebUI 选择中文、英文和数字字体"

rm -f "$MODPATH/system/etc/fonts.xml" "$MODPATH/system/etc/font_fallback.xml" 2>/dev/null || true
printf '%s\n' "$SELECTED_FONT" > "$MODPATH/config/active_font.conf"
printf '%s\n' "default" > "$MODPATH/config/active_emoji.conf"
cp -f "$FONT_LIST_TMP" "$MODPATH/config/font_list.conf" 2>/dev/null || : > "$MODPATH/config/font_list.conf"
rm -f "$FONT_LIST_TMP" 2>/dev/null || true

if [ -f "$OLD_MOD/config/active_emoji.conf" ]; then
    cp -f "$OLD_MOD/config/active_emoji.conf" "$MODPATH/config/active_emoji.conf" 2>/dev/null || true
fi
for _fw_conf in font_weight.conf font_weight_original.conf; do
    [ -f "$OLD_MOD/config/$_fw_conf" ] && cp -f "$OLD_MOD/config/$_fw_conf" "$MODPATH/config/$_fw_conf" 2>/dev/null || true
done

ACTIVE_EMOJI=$(head -n1 "$MODPATH/config/active_emoji.conf" 2>/dev/null | tr -d '\r\n')
if [ -n "$ACTIVE_EMOJI" ] && [ "$ACTIVE_EMOJI" != "default" ]; then
    EMOJI_SRC=""
    for _ef in "$USER_EMOJI_DIR"/*.ttf "$USER_EMOJI_DIR"/*.otf "$USER_EMOJI_DIR"/*.ttc \
               "$USER_EMOJI_DIR"/*.TTF "$USER_EMOJI_DIR"/*.OTF "$USER_EMOJI_DIR"/*.TTC; do
        [ -f "$_ef" ] || continue
        [ "${_ef##*/}" = "$ACTIVE_EMOJI.ttf" ] || [ "${_ef##*/}" = "$ACTIVE_EMOJI.otf" ] || [ "${_ef##*/}" = "$ACTIVE_EMOJI.ttc" ] || \
        [ "${_ef##*/}" = "$ACTIVE_EMOJI.TTF" ] || [ "${_ef##*/}" = "$ACTIVE_EMOJI.OTF" ] || [ "${_ef##*/}" = "$ACTIVE_EMOJI.TTC" ] || continue
        EMOJI_SRC="$_ef"; break
    done
    [ -f "$EMOJI_SRC" ] || [ ! -f "$OLD_MOD/system/fonts/NotoColorEmoji.ttf" ] || EMOJI_SRC="$OLD_MOD/system/fonts/NotoColorEmoji.ttf"
    if [ -f "$EMOJI_SRC" ] && { ! type font_validate >/dev/null 2>&1 || font_validate "$EMOJI_SRC" emoji; }; then
        cp -f "$EMOJI_SRC" "$MODPATH/system/fonts/NotoColorEmoji.ttf" 2>/dev/null || true
        [ -e /system/fonts/NotoColorEmojiLegacy.ttf ] && cp -f "$EMOJI_SRC" "$MODPATH/system/fonts/NotoColorEmojiLegacy.ttf" 2>/dev/null || true
        chmod 0644 "$MODPATH/system/fonts"/NotoColorEmoji*.ttf 2>/dev/null || true
        ui_print "升级保留 Emoji：$ACTIVE_EMOJI"
    else
        printf '%s\n' "default" > "$MODPATH/config/active_emoji.conf"
        ui_print "提示：旧 Emoji 源文件不可用，已保留系统默认 Emoji"
    fi
fi

cp -f "$MODPATH/common/font_manager.sh" "$MODPATH/system/bin/洛书" 2>/dev/null || true
chmod 755 "$MODPATH/customize.sh" "$MODPATH/post-fs-data.sh" "$MODPATH/service.sh" "$MODPATH/uninstall.sh" 2>/dev/null || true
chmod 755 "$MODPATH/common/font_manager.sh" "$MODPATH/common/font_check.sh" "$MODPATH/common/font_import.sh" "$MODPATH/common/font_report.sh" \
          "$MODPATH/common/util_functions.sh" "$MODPATH/common/rom_adapters.sh" "$MODPATH/common/volume_key.sh" \
          "$MODPATH/common/play_font_bridge" "$MODPATH/common/wechat_xweb_bridge" 2>/dev/null || true
chmod 755 "$MODPATH/common/module_status.sh" "$MODPATH/common/v14_switch.sh" "$MODPATH/common/font_mix.sh" "$MODPATH/common/v14_mix.sh" "$MODPATH/common/luoshu_composite.sh" 2>/dev/null || true
chmod 755 "$MODPATH/common/python/bin/luoshu-python" 2>/dev/null || true
chmod 755 "$MODPATH/system/bin/洛书" 2>/dev/null || true
[ ! -f "$MODPATH/system/bin/luoshud" ] || chmod 755 "$MODPATH/system/bin/luoshud" 2>/dev/null || true
find "$MODPATH/system/fonts" -type f -exec chmod 0644 {} \; 2>/dev/null || true
find "$MODPATH/webroot" -type f -exec chmod 0644 {} \; 2>/dev/null || true
chmod 0755 "$MODPATH/system/fonts" "$MODPATH/system/bin" "$MODPATH/config" "$MODPATH/logs" "$MODPATH/webroot" 2>/dev/null || true

touch "$MODPATH/magic" 2>/dev/null || true

ui_print ""
ui_print "╭──────────────────────────────╮"
ui_print "│          安装完成            │"
ui_print "╰──────────────────────────────╯"
ui_print "✓ 复合字体引擎已安装；当前保持系统默认字体"
if [ "$MOUNTIFY_ACTIVE" = "true" ]; then
    ui_print "✓ Mountify 适配已启用"
else
    ui_print "• 如需元模块，推荐使用 Mountify"
fi
ui_print "请完整重启手机以应用字体。"
ui_print ""
[ -f "$MODPATH/common/module_status.sh" ] && MODDIR="$MODPATH" sh "$MODPATH/common/module_status.sh" "$SELECTED_FONT" >/dev/null 2>&1 || true
exit 0
