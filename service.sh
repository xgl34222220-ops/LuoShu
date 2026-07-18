#!/system/bin/sh
# ============================================================
# 洛书 v14.2 Alpha2 - 后台服务
# 功能：启动完成后静默校正权限、恢复字重设置并维护日志。
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

    log_service "INFO" "服务脚本开始执行 (v14.2 Alpha2)"
    if [ -f "$LOG_FILE" ]; then
        _log_size=$(wc -c < "$LOG_FILE" 2>/dev/null | tr -d '[:space:]')
        case "$_log_size" in ''|*[!0-9]*) _log_size=0 ;; esac
        if [ "$_log_size" -gt 1048576 ]; then
            _trim="$LOG_FILE.trim.$$"
            tail -n 1200 "$LOG_FILE" > "$_trim" 2>/dev/null && mv -f "$_trim" "$LOG_FILE" 2>/dev/null || true
        fi
    fi

    # 权限只在后台静默校正。WebUI 所有核心脚本同时使用 sh 调用，
    # 即使 Root 管理器解压时丢失可执行位，也不会再要求用户手动修复。
    chmod 0755 "$MODDIR" "$MODDIR/common" "$MODDIR/webroot" 2>/dev/null || true
    chmod 0755 "$MODDIR/customize.sh" "$MODDIR/post-fs-data.sh" "$MODDIR/service.sh" "$MODDIR/uninstall.sh" 2>/dev/null || true
    find "$MODDIR/common" -maxdepth 1 -type f -exec chmod 0755 {} \; 2>/dev/null || true
    chmod 0644 "$MODDIR/common/font_instance.py" "$MODDIR/common/composite_font.py" 2>/dev/null || true
    chmod 0755 "$MODDIR/common/python/bin/luoshu-python" 2>/dev/null || true
    chmod 0755 "$MODDIR/system/bin/洛书" "$MODDIR/system/bin/luoshud" 2>/dev/null || true

    # Root 管理器模块说明只显示当前字体，不再塞入更新日志。
    if [ -f "$MODDIR/common/module_status.sh" ]; then
        MODDIR="$MODDIR" sh "$MODDIR/common/module_status.sh" >/dev/null 2>&1 || true
    fi

    # 恢复用户保存的 Android 全局字重调节。这与组合槽的独立字重互不覆盖：
    # 组合字重已经固化到字体轮廓，这里只恢复系统级整体微调。
    if [ -f "$MODDIR/config/font_weight.conf" ] && command -v settings >/dev/null 2>&1; then
        FW_ADJ=$(sed -n 's/^adjustment=//p' "$MODDIR/config/font_weight.conf" 2>/dev/null | head -n1)
        case "$FW_ADJ" in ''|*[!0-9-]*) FW_ADJ=0 ;; esac
        if [ "$FW_ADJ" -ge -100 ] 2>/dev/null && [ "$FW_ADJ" -le 300 ] 2>/dev/null; then
            if settings --user current put secure font_weight_adjustment "$FW_ADJ" >/dev/null 2>&1 || settings put secure font_weight_adjustment "$FW_ADJ" >/dev/null 2>&1; then
                log_service "INFO" "已恢复系统字体粗细调整：$FW_ADJ"
            else
                log_service "INFO" "字体粗细调整恢复失败"
            fi
        fi
    fi

    # v14.2 Alpha2 不在开机完成后刷新字体服务或重复桥接。
    # 新复合字体只在 WebUI 主动生成，完整重启后由系统自然加载。

    rm -f "$MODDIR/.first_boot" 2>/dev/null || true
    log_service "INFO" "服务脚本执行完成"
) &
