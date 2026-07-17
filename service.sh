#!/system/bin/sh
# 洛书 v14.1 - 后台服务
set +e
MODDIR="${0%/*}"
(
    WAITED=0
    while [ "$(getprop sys.boot_completed 2>/dev/null)" != 1 ] && [ "$WAITED" -lt 120 ]; do sleep 3; WAITED=$((WAITED + 3)); done
    mkdir -p "$MODDIR/logs" "$MODDIR/config" /sdcard/LuoShu/fonts /sdcard/LuoShu/import /sdcard/LuoShu/reports 2>/dev/null || true
    LOG_FILE="$MODDIR/logs/fontswitch.log"
    if [ -f "$LOG_FILE" ]; then
        _size=$(wc -c < "$LOG_FILE" 2>/dev/null | tr -d '[:space:]'); case "$_size" in ''|*[!0-9]*) _size=0 ;; esac
        if [ "$_size" -gt 1048576 ]; then
            rm -f "$LOG_FILE.3"; [ ! -f "$LOG_FILE.2" ] || mv -f "$LOG_FILE.2" "$LOG_FILE.3"; [ ! -f "$LOG_FILE.1" ] || mv -f "$LOG_FILE.1" "$LOG_FILE.2"; mv -f "$LOG_FILE" "$LOG_FILE.1"
        fi
    fi
    log(){ printf '[%s] [SERVICE] %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" "$1" >> "$LOG_FILE" 2>/dev/null || true; }
    log 'v14.1 服务开始'

    WEBROOT_NAME=$(sed -n 's/^webroot=//p' "$MODDIR/module.prop" 2>/dev/null | head -n1 | tr -d '\r\n')
    [ -n "$WEBROOT_NAME" ] || WEBROOT_NAME=webroot
    ACTIVE_WEBROOT="$MODDIR/$WEBROOT_NAME"
    chmod 0755 "$MODDIR" "$MODDIR/common" "$ACTIVE_WEBROOT" 2>/dev/null || true
    chmod 0755 "$MODDIR/customize.sh" "$MODDIR/post-fs-data.sh" "$MODDIR/post-mount.sh" "$MODDIR/service.sh" "$MODDIR/uninstall.sh" 2>/dev/null || true
    find "$MODDIR/common" -maxdepth 1 -type f -exec chmod 0755 {} \; 2>/dev/null || true
    chmod 0755 "$MODDIR/system/bin/洛书" "$MODDIR/system/bin/luoshud" 2>/dev/null || true
    find "$ACTIVE_WEBROOT" -type f -exec chmod 0644 {} \; 2>/dev/null || true
    rm -f "$MODDIR/remove" "$MODDIR/disable" "$MODDIR/skip_mount" "$MODDIR/skip_mountify" "$MODDIR/magic" 2>/dev/null || true
    rm -f "$MODDIR/config/active_emoji.conf" "$MODDIR/config/emoji_task.conf" "$MODDIR/config/emoji_reboot_required.conf" 2>/dev/null || true
    rm -f "$MODDIR/system/fonts/NotoColorEmoji.ttf" "$MODDIR/system/fonts/NotoColorEmojiLegacy.ttf" 2>/dev/null || true
    rm -rf "$MODDIR/system/fonts/.luoshu-emoji-store" "$ACTIVE_WEBROOT/emoji" 2>/dev/null || true
    for _old_root in webroot webroot_v141; do [ "$_old_root" = "$WEBROOT_NAME" ] || rm -rf "$MODDIR/$_old_root" 2>/dev/null || true; done

    ACTIVE=$(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null | tr -d '\r\n'); [ -n "$ACTIVE" ] || ACTIVE=default
    [ -f "$MODDIR/common/module_status.sh" ] && MODDIR="$MODDIR" sh "$MODDIR/common/module_status.sh" "$ACTIVE" >/dev/null 2>&1 || true

    if [ -f "$MODDIR/config/font_weight.conf" ] && command -v settings >/dev/null 2>&1; then
        FW=$(sed -n 's/^adjustment=//p' "$MODDIR/config/font_weight.conf" 2>/dev/null | head -n1)
        case "$FW" in ''|*[!0-9-]*) FW=0 ;; esac
        [ "$FW" -ge -100 ] 2>/dev/null && [ "$FW" -le 300 ] 2>/dev/null && { settings --user current put secure font_weight_adjustment "$FW" >/dev/null 2>&1 || settings put secure font_weight_adjustment "$FW" >/dev/null 2>&1 || true; }
    fi
    command -v cmd >/dev/null 2>&1 && cmd font system --update >/dev/null 2>&1 || true
    [ ! -f /system/bin/oplus-font ] || oplus-font refresh >/dev/null 2>&1 || true

    if [ -f "$MODDIR/common/mount_compat.sh" ]; then
        MODULE_DIR="$MODDIR" . "$MODDIR/common/mount_compat.sh"
        luoshu_sync_mount_payload 2>/dev/null || true
    fi

    [ ! -f "$MODDIR/common/font_manager.sh" ] || MODDIR="$MODDIR" sh "$MODDIR/common/font_manager.sh" action list refresh >/dev/null 2>&1 || true
    [ ! -f "$MODDIR/common/preview_cache.sh" ] || MODDIR="$MODDIR" sh "$MODDIR/common/preview_cache.sh" prune >/dev/null 2>&1 || true
    [ ! -f "$MODDIR/common/play_font_bridge" ] || MODDIR="$MODDIR" sh "$MODDIR/common/play_font_bridge" boot >/dev/null 2>&1 || true
    [ ! -f "$MODDIR/common/wechat_xweb_bridge" ] || MODDIR="$MODDIR" sh "$MODDIR/common/wechat_xweb_bridge" >/dev/null 2>&1 &

    if [ -d /data/adb/ap ] || [ -d /data/adb/apatch ] || command -v apd >/dev/null 2>&1; then
        [ -f "$MODDIR/module.prop" ] && log 'APatch 持久化检查：模块目录存在' || log 'APatch 持久化检查失败：module.prop 不存在'
    fi
    log "服务完成，当前字体=$ACTIVE"
) &
