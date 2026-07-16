#!/system/bin/sh
# LuoShu v13.4 Beta2 Hotfix6 - 安装脚本

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
ui_print "║       洛 书  v13.4 Beta2 Hotfix6        ║"
ui_print "║   文字与 Emoji 独立管理          ║"
ui_print "╚══════════════════════════════════╝"
ui_print ""
if [ "$IS_COLOROS" = "true" ]; then
    ui_print "检测到：ColorOS ${COLOROS_VERSION:-未知}"
elif [ "$IS_HYPEROS" = "true" ]; then
    ui_print "检测到：HyperOS/MIUI ${HYPEROS_VERSION:-未知}"
else
    ui_print "检测到：通用 AOSP 方案"
fi
ui_print "字体目录：/sdcard/LuoShu/fonts/"
ui_print "Emoji目录：/sdcard/LuoShu/emoji/"
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

find_family_file() {
    _want="$1"
    for _f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
              "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_f" ] || continue
        [ "$(detect_font_family "$(basename "$_f")")" = "$_want" ] && { echo "$_f"; return 0; }
    done
    return 1
}

FONT_LIST_TMP="$MODPATH/config/.install_fonts.$$"
scan_fonts_lines > "$FONT_LIST_TMP" 2>/dev/null || : > "$FONT_LIST_TMP"
FONT_COUNT=$(grep -c . "$FONT_LIST_TMP" 2>/dev/null)
[ -n "$FONT_COUNT" ] || FONT_COUNT=0
case "$FONT_COUNT" in ''|*[!0-9]*) FONT_COUNT=0 ;; esac
SELECTED_FONT="default"
SELECTED_FILE=""
OLD_MOD="/data/adb/modules/LuoShu"
OLD_ACTIVE_TEXT=$(head -n1 "$OLD_MOD/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
if [ -n "$OLD_ACTIVE_TEXT" ] && [ "$OLD_ACTIVE_TEXT" != "default" ]; then
    _old_file=$(find_family_file "$OLD_ACTIVE_TEXT")
    if [ -f "$_old_file" ]; then
        SELECTED_FONT="$OLD_ACTIVE_TEXT"
        SELECTED_FILE="$_old_file"
        ui_print "升级保留当前文字字体：$SELECTED_FONT"
    fi
fi

if [ "$FONT_COUNT" -gt 0 ]; then
    if [ -n "$SELECTED_FILE" ]; then
        :
    elif [ "$FONT_COUNT" -gt 1 ] && type volume_key_menu >/dev/null 2>&1; then
        _opts=""; _first=true
        while IFS= read -r _fam; do
            [ -n "$_fam" ] || continue
            if [ "$_first" = true ]; then _opts="$_fam"; _first=false; else _opts="$_opts|$_fam"; fi
        done < "$FONT_LIST_TMP"
        ui_print "发现 $FONT_COUNT 款字体，可用音量键选择（超时默认第一款）"
        volume_key_menu "$_opts" 5
        _idx=0
        while IFS= read -r _fam; do
            [ -n "$_fam" ] || continue
            if [ "$_idx" -eq "${VK_SELECTED:-0}" ]; then SELECTED_FONT="$_fam"; break; fi
            _idx=$((_idx + 1))
        done < "$FONT_LIST_TMP"
    else
        IFS= read -r SELECTED_FONT < "$FONT_LIST_TMP"
    fi
    [ -n "$SELECTED_FILE" ] || SELECTED_FILE=$(find_family_file "$SELECTED_FONT")
    if [ ! -f "$SELECTED_FILE" ]; then
        ui_print "错误：无法读取选中的字体文件"
        exit 1
    fi
    if type font_validate >/dev/null 2>&1 && ! font_validate "$SELECTED_FILE" text; then
        ui_print "错误：$FONT_CHECK_ERROR"
        ui_print "请放入真实的 TTF/OTF/TTC 文件，不能只改扩展名。"
        exit 1
    fi
    [ -n "$FONT_CHECK_WARNING" ] && ui_print "提示：$FONT_CHECK_WARNING"
    ui_print "应用文字字体：$SELECTED_FONT（$FONT_CHECK_FORMAT）"
    apply_font_by_rom "$SELECTED_FILE" "$MODPATH/system/fonts" full "$SELECTED_FONT" || {
        ui_print "错误：ROM 字体映射失败"
        exit 1
    }
    if [ "$IS_COLOROS" = "true" ]; then
        mkdir -p "$MODPATH/system_ext/fonts" "$MODPATH/product/fonts" 2>/dev/null || true
        for _n in $(get_all_coloros_names); do
            _src="$MODPATH/system/fonts/${_n}.ttf"
            [ -f "$_src" ] || continue
            [ -e "/system_ext/fonts/${_n}.ttf" ] && link_or_copy_font "$_src" "$MODPATH/system_ext/fonts/${_n}.ttf" 2>/dev/null || true
            [ -e "/product/fonts/${_n}.ttf" ] && link_or_copy_font "$_src" "$MODPATH/product/fonts/${_n}.ttf" 2>/dev/null || true
        done
    fi
else
    ui_print "未发现字体文件：模块将以系统默认字体安装。"
    ui_print "安装后把字体放入公开目录，再从 WebUI 选择即可。"
fi

# 保留系统 fonts.xml / fallback / symbols / emoji；只覆盖 ROM 已知文字目标。
rm -f "$MODPATH/system/etc/fonts.xml" "$MODPATH/system/etc/font_fallback.xml" 2>/dev/null || true
printf '%s\n' "$SELECTED_FONT" > "$MODPATH/config/active_font.conf"
printf '%s\n' "default" > "$MODPATH/config/active_emoji.conf"
cp -f "$FONT_LIST_TMP" "$MODPATH/config/font_list.conf" 2>/dev/null || : > "$MODPATH/config/font_list.conf"
rm -f "$FONT_LIST_TMP" 2>/dev/null || true

# 旧版本升级时尽量保留当前 Emoji 配置。
if [ -f "$OLD_MOD/config/active_emoji.conf" ]; then
    cp -f "$OLD_MOD/config/active_emoji.conf" "$MODPATH/config/active_emoji.conf" 2>/dev/null || true
fi

# 保留可变字体粗细偏好和首次调整前的系统原值，避免升级后无法恢复。
for _fw_conf in font_weight.conf font_weight_original.conf; do
    [ -f "$OLD_MOD/config/$_fw_conf" ] && cp -f "$OLD_MOD/config/$_fw_conf" "$MODPATH/config/$_fw_conf" 2>/dev/null || true
done

# 升级时恢复独立 Emoji 映射；找不到公开源文件时复用旧模块中的安全副本。
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

# 命令行入口
cp -f "$MODPATH/common/font_manager.sh" "$MODPATH/system/bin/洛书" 2>/dev/null || true

# 权限
chmod 755 "$MODPATH/customize.sh" "$MODPATH/post-fs-data.sh" "$MODPATH/service.sh" "$MODPATH/uninstall.sh" 2>/dev/null || true
chmod 755 "$MODPATH/common/font_manager.sh" "$MODPATH/common/font_check.sh" "$MODPATH/common/font_import.sh" "$MODPATH/common/font_report.sh" \
          "$MODPATH/common/util_functions.sh" "$MODPATH/common/rom_adapters.sh" "$MODPATH/common/volume_key.sh" \
          "$MODPATH/common/play_font_bridge" "$MODPATH/common/wechat_xweb_bridge" 2>/dev/null || true
chmod 755 "$MODPATH/system/bin/洛书" 2>/dev/null || true
[ ! -f "$MODPATH/system/bin/luoshud" ] || chmod 755 "$MODPATH/system/bin/luoshud" 2>/dev/null || true
find "$MODPATH/system/fonts" -type f -exec chmod 0644 {} \; 2>/dev/null || true
find "$MODPATH/webroot" -type f -exec chmod 0644 {} \; 2>/dev/null || true
chmod 0755 "$MODPATH/system/fonts" "$MODPATH/system/bin" "$MODPATH/config" "$MODPATH/logs" "$MODPATH/webroot" 2>/dev/null || true

# Hybrid Mount Nano 识别此 marker；Full/Lite 用户应在 WebUI 选择 Magic。
touch "$MODPATH/magic" 2>/dev/null || true

ui_print ""
ui_print "安装完成。"
ui_print "请重启手机；切换字体后同样需要完整重启。"
ui_print "Hybrid Mount：推荐 Magic，不能选 Ignore。"
[ -x "$MODPATH/system/bin/luoshud" ] && ui_print "ARM64 原生扫描器：已保留（诊断回退）"
ui_print ""
exit 0
