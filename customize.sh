#!/system/bin/sh
# 洛书 v14.1 Test3 - Magisk / KernelSU / SukiSU Ultra / APatch 安装脚本
# 注意：APatch 会 source 本文件，因此成功路径不能使用 exit。
set +e

MODPATH="${MODPATH:-$3}"
[ -n "$MODPATH" ] || MODPATH="/data/adb/modules_update/LuoShu"
MODULE_DIR="$MODPATH"
WEBROOT_NAME=$(sed -n 's/^webroot=//p' "$MODPATH/module.prop" 2>/dev/null | head -n1 | tr -d '\r\n')
[ -n "$WEBROOT_NAME" ] || WEBROOT_NAME=webroot_v14103

for _lib in util_functions.sh font_check.sh rom_adapters.sh volume_key.sh mount_compat.sh; do
    [ -f "$MODPATH/common/$_lib" ] && . "$MODPATH/common/$_lib"
done
if ! type detect_font_family >/dev/null 2>&1; then detect_font_family(){ _n="${1%.*}"; printf '%s\n' "${_n%-*}"; }; fi
if ! type check_coloros >/dev/null 2>&1; then check_coloros(){ IS_COLOROS=false; }; fi
if ! type check_hyperos >/dev/null 2>&1; then check_hyperos(){ IS_HYPEROS=false; }; fi

installer_fail(){
    ui_print "! $1"
    if type abort >/dev/null 2>&1; then abort "$1"; else exit 1; fi
}

APATCH_ENV=false
case "${APATCH:-false}:${KERNELPATCH:-false}" in true:*|*:true) APATCH_ENV=true ;; esac
command -v apd >/dev/null 2>&1 && APATCH_ENV=true
if [ -d /data/adb/ap ] || [ -d /data/adb/apatch ]; then APATCH_ENV=true; fi

rm -f "$MODPATH/remove" "$MODPATH/disable" "$MODPATH/skip_mount" "$MODPATH/skip_mountify" "$MODPATH/magic" 2>/dev/null || true
[ -f "$MODPATH/module.prop" ] || installer_fail "安装包缺少 module.prop"

mkdir -p /sdcard/LuoShu/fonts /sdcard/LuoShu/import /sdcard/LuoShu/reports 2>/dev/null || true
mkdir -p "$MODPATH/system/fonts" "$MODPATH/system/bin" "$MODPATH/config" "$MODPATH/logs" "$MODPATH/$WEBROOT_NAME/fonts" 2>/dev/null || true
rm -rf "$MODPATH/webroot" "$MODPATH/webroot_v141" "$MODPATH/$WEBROOT_NAME/emoji" "$MODPATH/system/fonts/.luoshu-emoji-store" 2>/dev/null || true
rm -f "$MODPATH/system/fonts/NotoColorEmoji.ttf" "$MODPATH/system/fonts/NotoColorEmojiLegacy.ttf" \
      "$MODPATH/config/active_emoji.conf" "$MODPATH/config/emoji_task.conf" "$MODPATH/config/emoji_reboot_required.conf" 2>/dev/null || true

check_coloros
check_hyperos
ROOT_MANAGER="Root"
if [ "$APATCH_ENV" = true ]; then ROOT_MANAGER="APatch"
elif command -v ksud >/dev/null 2>&1 || [ -d /data/adb/ksu ]; then
    _ksu_info="$(ksud -V 2>/dev/null || ksud --version 2>/dev/null || true)"
    case "$_ksu_info $(getprop ro.build.version.incremental 2>/dev/null)" in *SukiSU*|*sukisu*|*SUKISU*) ROOT_MANAGER="SukiSU Ultra" ;; *) ROOT_MANAGER="KernelSU" ;; esac
elif command -v magisk >/dev/null 2>&1 || [ -d /data/adb/magisk ]; then ROOT_MANAGER="Magisk"
fi

ui_print ""
ui_print "╔══════════════════════════════════╗"
ui_print "║       洛 书  v14.1 Test3         ║"
ui_print "║       Android 全局字体管理       ║"
ui_print "╚══════════════════════════════════╝"
ui_print ""
ui_print "✓ Root 管理器：$ROOT_MANAGER"
if [ "$IS_COLOROS" = true ]; then ui_print "✓ 系统环境：ColorOS ${COLOROS_VERSION:-未知}"
elif [ "$IS_HYPEROS" = true ]; then ui_print "✓ 系统环境：HyperOS/MIUI ${HYPEROS_VERSION:-未知}"
else ui_print "✓ 系统环境：通用 Android"; fi
if [ -d /data/adb/modules/mountify ] && [ ! -f /data/adb/modules/mountify/disable ] && [ ! -f /data/adb/modules/mountify/remove ]; then ui_print "✓ Mountify：已启用"
else ui_print "• 元模块推荐：Mountify（可选）"; fi
[ "$APATCH_ENV" = true ] && ui_print "✓ APatch 安装模式：已启用持久化兼容处理"
ui_print "✓ 字体目录：/sdcard/LuoShu/fonts/"
ui_print ""

OLD_MOD="/data/adb/modules/LuoShu"
OLD_ACTIVE=$(head -n1 "$OLD_MOD/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
SELECTED_FONT="default"

if [ "$OLD_ACTIVE" = mix ] && [ -s "$OLD_MOD/config/font_mix.conf" ] && [ -d "$OLD_MOD/system/fonts" ]; then
    rm -rf "$MODPATH/system/fonts" 2>/dev/null || true
    mkdir -p "$MODPATH/system" 2>/dev/null || true
    cp -a "$OLD_MOD/system/fonts" "$MODPATH/system/fonts" 2>/dev/null || cp -R "$OLD_MOD/system/fonts" "$MODPATH/system/fonts" 2>/dev/null || true
    cp -f "$OLD_MOD/config/font_mix.conf" "$MODPATH/config/font_mix.conf" 2>/dev/null || true
    printf 'mix\n' > "$MODPATH/config/active_font.conf"
    SELECTED_FONT="mix"
    ui_print "✓ 升级保留当前字体组合"
else
    find_font_for_family(){
        _want="$1"
        for _f in /sdcard/LuoShu/fonts/*.ttf /sdcard/LuoShu/fonts/*.otf /sdcard/LuoShu/fonts/*.ttc \
                  /sdcard/LuoShu/fonts/*.TTF /sdcard/LuoShu/fonts/*.OTF /sdcard/LuoShu/fonts/*.TTC; do
            [ -f "$_f" ] || continue
            [ "$(detect_font_family "$(basename "$_f")")" = "$_want" ] && { printf '%s\n' "$_f"; return 0; }
        done
        return 1
    }
    SELECTED_FILE=""
    if [ -n "$OLD_ACTIVE" ] && [ "$OLD_ACTIVE" != default ]; then SELECTED_FILE=$(find_font_for_family "$OLD_ACTIVE"); [ -f "$SELECTED_FILE" ] && SELECTED_FONT="$OLD_ACTIVE"; fi
    if [ ! -f "$SELECTED_FILE" ]; then
        for _f in /sdcard/LuoShu/fonts/*.ttf /sdcard/LuoShu/fonts/*.otf /sdcard/LuoShu/fonts/*.ttc \
                  /sdcard/LuoShu/fonts/*.TTF /sdcard/LuoShu/fonts/*.OTF /sdcard/LuoShu/fonts/*.TTC; do
            [ -f "$_f" ] || continue
            SELECTED_FILE="$_f"; SELECTED_FONT=$(detect_font_family "$(basename "$_f")"); break
        done
    fi
    rm -rf "$MODPATH/system/fonts/.luoshu-font-store" 2>/dev/null || true
    find "$MODPATH/system/fonts" -mindepth 1 -maxdepth 1 -type f -delete 2>/dev/null || true
    if [ -f "$SELECTED_FILE" ]; then
        if type font_validate >/dev/null 2>&1 && ! font_validate "$SELECTED_FILE" text; then installer_fail "$FONT_CHECK_ERROR"; fi
        apply_font_by_rom "$SELECTED_FILE" "$MODPATH/system/fonts" full "$SELECTED_FONT" || installer_fail "ROM 字体映射失败"
        ui_print "✓ 已准备文字字体：$SELECTED_FONT"
    else
        SELECTED_FONT="default"
        ui_print "• 未发现字体文件，安装后从 WebUI 选择"
    fi
    printf '%s\n' "$SELECTED_FONT" > "$MODPATH/config/active_font.conf"
fi

if [ "$IS_COLOROS" = true ]; then
    mkdir -p "$MODPATH/system_ext/fonts" "$MODPATH/product/fonts" 2>/dev/null || true
    for _src in "$MODPATH/system/fonts"/*; do
        [ -f "$_src" ] || continue; _file=$(basename "$_src")
        [ -e "/system_ext/fonts/$_file" ] && link_or_copy_font "$_src" "$MODPATH/system_ext/fonts/$_file" 2>/dev/null || true
        [ -e "/product/fonts/$_file" ] && link_or_copy_font "$_src" "$MODPATH/product/fonts/$_file" 2>/dev/null || true
    done
fi

for _conf in font_weight.conf font_weight_original.conf recent_fonts.conf; do [ -f "$OLD_MOD/config/$_conf" ] && cp -f "$OLD_MOD/config/$_conf" "$MODPATH/config/$_conf" 2>/dev/null || true; done
rm -f "$MODPATH/config/text_reboot_required.conf" "$MODPATH/config/switch_task.conf" "$MODPATH/config/mix_task.conf" "$MODPATH/.font_switch.lock" 2>/dev/null || true
rm -f "$MODPATH/system/etc/fonts.xml" "$MODPATH/system/etc/font_fallback.xml" 2>/dev/null || true

cp -f "$MODPATH/common/luoshu_cli.sh" "$MODPATH/system/bin/洛书" 2>/dev/null || true
chmod 0755 "$MODPATH/customize.sh" "$MODPATH/post-fs-data.sh" "$MODPATH/post-mount.sh" "$MODPATH/service.sh" "$MODPATH/uninstall.sh" 2>/dev/null || true
find "$MODPATH/common" -maxdepth 1 -type f -exec chmod 0755 {} \; 2>/dev/null || true
chmod 0755 "$MODPATH/system/bin/洛书" "$MODPATH/system/bin/luoshud" 2>/dev/null || true
find "$MODPATH/system/fonts" -type f -exec chmod 0644 {} \; 2>/dev/null || true
find "$MODPATH/$WEBROOT_NAME" -type f -exec chmod 0644 {} \; 2>/dev/null || true
chmod 0644 "$MODPATH/module.prop" "$MODPATH/config/active_font.conf" 2>/dev/null || true

MOD_REAL=$(CDPATH= cd -- "$MODPATH" 2>/dev/null && pwd)
OLD_REAL=$(CDPATH= cd -- "$OLD_MOD" 2>/dev/null && pwd)
if [ -d "$OLD_MOD" ] && [ -n "$MOD_REAL" ] && [ -n "$OLD_REAL" ] && [ "$MOD_REAL" != "$OLD_REAL" ]; then
    if [ -d "$MODPATH/$WEBROOT_NAME" ]; then
        _tmp="$OLD_MOD/.${WEBROOT_NAME}.$$"
        rm -rf "$_tmp" 2>/dev/null || true
        cp -a "$MODPATH/$WEBROOT_NAME" "$_tmp" 2>/dev/null || cp -R "$MODPATH/$WEBROOT_NAME" "$_tmp" 2>/dev/null || true
        if [ -d "$_tmp" ]; then
            rm -rf "$OLD_MOD/$WEBROOT_NAME" 2>/dev/null || true
            mv -f "$_tmp" "$OLD_MOD/$WEBROOT_NAME" 2>/dev/null || true
        fi
    fi
    cp -f "$MODPATH/module.prop" "$OLD_MOD/module.prop" 2>/dev/null || true
    rm -rf "$OLD_MOD/webroot" "$OLD_MOD/webroot_v141" "$OLD_MOD/$WEBROOT_NAME/emoji" 2>/dev/null || true
    chmod 0644 "$OLD_MOD/module.prop" 2>/dev/null || true
    find "$OLD_MOD/$WEBROOT_NAME" -type f -exec chmod 0644 {} \; 2>/dev/null || true
    ui_print "✓ 已切换到全新 WebUI 目录，旧缓存已清理"
fi

[ "$APATCH_ENV" = true ] && printf 'apatch-compatible=1\ninstalled=%s\n' "$(date +%s)" > "$MODPATH/config/install_environment.conf" 2>/dev/null || true
[ -f "$MODPATH/common/preview_cache.sh" ] && MODDIR="$MODPATH" sh "$MODPATH/common/preview_cache.sh" prune >/dev/null 2>&1 || true
[ -f "$MODPATH/common/module_status.sh" ] && MODDIR="$MODPATH" sh "$MODPATH/common/module_status.sh" "$SELECTED_FONT" >/dev/null 2>&1 || true
ui_print ""
ui_print "╭──────────────────────────────╮"
ui_print "│          安装完成            │"
ui_print "╰──────────────────────────────╯"
ui_print "✓ v14.1 Test3 已完成字体配置与缓存优化"
ui_print "⚠ 请关闭 Root 管理器中的『默认卸载模块』"
ui_print "请完整重启手机。"
ui_print ""
true
