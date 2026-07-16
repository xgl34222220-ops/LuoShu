#!/system/bin/sh
# ============================================================
# 洛书 v14 - 后台服务
# 功能：静默校正运行权限、刷新字体状态并桥接 GMS / XWeb。
# ============================================================

MODDIR="${0%/*}"

(
    WAITED=0
    while [ "$(getprop sys.boot_completed 2>/dev/null)" != "1" ] && [ "$WAITED" -lt 90 ]; do
        sleep 3
        WAITED=$((WAITED + 3))
    done

    LOG_FILE="$MODDIR/logs/fontswitch.log"
    LOG_LEVEL="${LOG_LEVEL:-INFO}"
    mkdir -p "$MODDIR/logs" "$MODDIR/config" 2>/dev/null || true

    log_service() {
        LEVEL="$1"
        MSG="$2"
        TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)
        [ "$LEVEL" = "DEBUG" ] && [ "$LOG_LEVEL" != "DEBUG" ] && return 0
        echo "[$TIMESTAMP] [SERVICE] [$LEVEL] $MSG" >> "$LOG_FILE" 2>/dev/null || true
    }

    log_service "INFO" "服务脚本开始执行 (v14)"

    # 权限只在后台静默校正。WebUI 所有核心脚本同时使用 sh 调用，
    # 即使 Root 管理器解压时丢失可执行位，也不会再要求用户手动修复。
    chmod 0755 "$MODDIR" "$MODDIR/common" "$MODDIR/webroot" 2>/dev/null || true
    chmod 0755 "$MODDIR/customize.sh" "$MODDIR/post-fs-data.sh" "$MODDIR/service.sh" "$MODDIR/uninstall.sh" 2>/dev/null || true
    find "$MODDIR/common" -maxdepth 1 -type f -exec chmod 0755 {} \; 2>/dev/null || true
    chmod 0755 "$MODDIR/system/bin/洛书" "$MODDIR/system/bin/luoshud" 2>/dev/null || true

    # Root 管理器模块说明只显示当前字体，不再塞入更新日志。
    if [ -f "$MODDIR/common/module_status.sh" ]; then
        MODDIR="$MODDIR" sh "$MODDIR/common/module_status.sh" >/dev/null 2>&1 || true
    fi

    # 恢复用户保存的 Android 全局字重调节。
    if [ -f "$MODDIR/config/font_weight.conf" ] && command -v settings >/dev/null 2>&1; then
        FW_ADJ=$(sed -n 's/^adjustment=//p' "$MODDIR/config/font_weight.conf" 2>/dev/null | head -n1)
        case "$FW_ADJ" in ''|*[!0-9-]*) FW_ADJ=0 ;; esac
        if [ "$FW_ADJ" -ge -100 ] 2>/dev/null && [ "$FW_ADJ" -le 300 ] 2>/dev/null; then
            if settings --user current put secure font_weight_adjustment "$FW_ADJ" >/dev/null 2>&1 || settings put secure font_weight_adjustment "$FW_ADJ" >/dev/null 2>&1; then
                log_service "INFO" "已恢复字体粗细调整：$FW_ADJ"
            else
                log_service "INFO" "字体粗细调整恢复失败"
            fi
        fi
    fi

    if command -v cmd >/dev/null 2>&1; then
        cmd font system --update >/dev/null 2>&1 && log_service "INFO" "字体缓存刷新成功" || true
    fi

    if [ -f /system/bin/oplus-font ]; then
        oplus-font refresh >/dev/null 2>&1 && log_service "INFO" "ColorOS 字体刷新成功" || true
    fi

    if [ -f "$MODDIR/common/play_font_bridge" ]; then
        MODDIR="$MODDIR" sh "$MODDIR/common/play_font_bridge" boot
    fi

    if [ -f "$MODDIR/common/wechat_xweb_bridge" ]; then
        MODDIR="$MODDIR" sh "$MODDIR/common/wechat_xweb_bridge" &
    fi

    rm -f "$MODDIR/.first_boot" 2>/dev/null || true
    log_service "INFO" "服务脚本执行完成"
) &
