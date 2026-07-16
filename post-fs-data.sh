#!/system/bin/sh
# LuoShu v13.6 Beta3 - early boot initialization
set +e

MODDIR="${0%/*}"
MODULE_DIR="$MODDIR"
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/font_check.sh" ] && . "$MODDIR/common/font_check.sh"
[ -f "$MODDIR/common/rom_adapters.sh" ] && . "$MODDIR/common/rom_adapters.sh"
[ -f "$MODDIR/common/font_manager.sh" ] && . "$MODDIR/common/font_manager.sh"
[ -f "$MODDIR/common/meta_overlay_compat" ] && . "$MODDIR/common/meta_overlay_compat"

type init_module >/dev/null 2>&1 && init_module
type ensure_public_storage >/dev/null 2>&1 && ensure_public_storage
command mkdir -p "$MODDIR/config" "$MODDIR/logs" "$MODDIR/webroot/fonts" "$MODDIR/webroot/emoji" 2>/dev/null || true

log_message "INFO" "===== post-fs-data v13.6 Beta3 开始 ====="

# Keep original ROM XML/fallback/symbol resources untouched.
rm -f "$MODDIR/system/etc/fonts.xml" "$MODDIR/system/etc/font_fallback.xml" 2>/dev/null || true
[ ! -d "$MODDIR/system/fonts" ] || set_perm_recursive "$MODDIR/system/fonts" 0 0 0755 0644 2>/dev/null || true

ACTIVE_TEXT=$(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
[ -n "$ACTIVE_TEXT" ] || ACTIVE_TEXT=default
ACTIVE_EMOJI=$(head -n1 "$MODDIR/config/active_emoji.conf" 2>/dev/null | tr -d '\r\n')
[ -n "$ACTIVE_EMOJI" ] || ACTIVE_EMOJI=default
DB_MODE=module
[ -f "$MODDIR/common/db_engine" ] && DB_MODE=$(MODDIR="$MODDIR" sh "$MODDIR/common/db_engine" mode 2>/dev/null)
[ -n "$DB_MODE" ] || DB_MODE=module

if [ "$DB_MODE" = direct ]; then
    if MODDIR="$MODDIR" sh "$MODDIR/common/db_engine" apply; then
        log_message "INFO" "DB 字体映射已应用"
        type luoshu_clear_own_meta_errors >/dev/null 2>&1 && luoshu_clear_own_meta_errors 2>/dev/null || true
    else
        log_message "ERROR" "DB 字体映射部分失败，详见 direct_map.log"
    fi
else
    # ColorOS writable font cache is synchronized only in traditional module mode.
    if [ "$IS_COLOROS" = true ] && [ -d /data/fonts ]; then
        _count=0
        for _name in $(get_all_coloros_names); do
            _dest="/data/fonts/${_name}.ttf"
            _src="$MODDIR/system/fonts/${_name}.ttf"
            if [ "$ACTIVE_TEXT" = default ]; then
                rm -f "$_dest" 2>/dev/null || true
            elif [ -f "$_src" ]; then
                cp -f "$_src" "$_dest" 2>/dev/null && { chmod 0644 "$_dest" 2>/dev/null || true; _count=$((_count + 1)); }
            fi
        done
        log_message "INFO" "ColorOS /data/fonts 同步：$_count 个目标"
    fi
fi

# Emoji and other small partition payloads may still need the external engine's content directory.
type luoshu_sync_meta_payload >/dev/null 2>&1 && luoshu_sync_meta_payload 2>/dev/null || true

# Preview files are WebUI-only.
type sync_preview_fonts >/dev/null 2>&1 && sync_preview_fonts 2>/dev/null || true
type sync_emoji_preview_fonts >/dev/null 2>&1 && sync_emoji_preview_fonts 2>/dev/null || true

rm -f "$MODDIR/config/text_reboot_required.conf" "$MODDIR/config/emoji_reboot_required.conf" \
      "$MODDIR/config/font_weight_reboot_required.conf" "$MODDIR/.font_switch.lock" 2>/dev/null || true

log_message "INFO" "当前文字=$ACTIVE_TEXT | Emoji=$ACTIVE_EMOJI | mode=$DB_MODE"
log_message "INFO" "===== post-fs-data 完成 ====="
exit 0
