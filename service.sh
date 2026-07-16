#!/system/bin/sh
# LuoShu v13.6 Beta4 - late boot service
set +e

MODDIR="${0%/*}"
[ -f "$MODDIR/common/meta_overlay_compat" ] && . "$MODDIR/common/meta_overlay_compat"

(
    WAITED=0
    while [ "$(getprop sys.boot_completed 2>/dev/null)" != "1" ] && [ "$WAITED" -lt 90 ]; do
        sleep 3
        WAITED=$((WAITED + 3))
    done

    command mkdir -p "$MODDIR/logs" 2>/dev/null || true
    LOG_FILE="$MODDIR/logs/fontswitch.log"
    LOG_LEVEL="${LOG_LEVEL:-INFO}"

    log_service() {
        _level="$1"; _msg="$2"
        _time=$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)
        [ "$_level" = DEBUG ] && [ "$LOG_LEVEL" != DEBUG ] && return 0
        echo "[$_time] [SERVICE] [$_level] $_msg" >> "$LOG_FILE" 2>/dev/null || true
    }

    log_service INFO "服务脚本开始执行 (v13.6 Beta4)"

    if [ -f "$MODDIR/common/db_engine" ]; then
        DB_MODE=$(MODDIR="$MODDIR" sh "$MODDIR/common/db_engine" mode 2>/dev/null)
        if [ "$DB_MODE" = direct ]; then
            if MODDIR="$MODDIR" sh "$MODDIR/common/db_engine" verify >/dev/null 2>&1; then
                log_service INFO "DB 字体映射校验通过"
                type luoshu_clear_own_meta_errors >/dev/null 2>&1 && luoshu_clear_own_meta_errors 2>/dev/null || true
            else
                log_service INFO "DB 字体映射缺失，尝试补应用"
                if MODDIR="$MODDIR" sh "$MODDIR/common/db_engine" apply >/dev/null 2>&1; then
                    log_service INFO "DB 字体映射补应用成功"
                    type luoshu_clear_own_meta_errors >/dev/null 2>&1 && luoshu_clear_own_meta_errors 2>/dev/null || true
                else
                    log_service ERROR "DB 字体映射补应用失败"
                fi
            fi
            MODDIR="$MODDIR" sh "$MODDIR/common/db_engine" cleanup >/dev/null 2>&1 || true
        else
            log_service INFO "当前使用传统模块字体模式"
        fi
    fi

    if [ -x "$MODDIR/common/stability.sh" ]; then
        SNAPSHOT_RESULT=$(MODDIR="$MODDIR" sh "$MODDIR/common/stability.sh" boot_snapshot 2>/dev/null)
        log_service INFO "稳定快照：${SNAPSHOT_RESULT:-无返回}"
    else
        log_service INFO "稳定快照组件不可用"
    fi

    if [ -f "$MODDIR/config/font_weight.conf" ] && command -v settings >/dev/null 2>&1; then
        FW_ADJ=$(sed -n 's/^adjustment=//p' "$MODDIR/config/font_weight.conf" 2>/dev/null | head -n1)
        case "$FW_ADJ" in ''|*[!0-9-]*) FW_ADJ=0 ;; esac
        if [ "$FW_ADJ" -ge -100 ] 2>/dev/null && [ "$FW_ADJ" -le 300 ] 2>/dev/null; then
            if settings --user current put secure font_weight_adjustment "$FW_ADJ" >/dev/null 2>&1 || settings put secure font_weight_adjustment "$FW_ADJ" >/dev/null 2>&1; then
                log_service INFO "已恢复字体粗细调整：$FW_ADJ"
            else
                log_service INFO "字体粗细调整恢复失败"
            fi
        fi
    fi

    if command -v cmd >/dev/null 2>&1; then
        cmd font system --update >/dev/null 2>&1 && log_service INFO "字体缓存刷新成功" || log_service INFO "字体缓存刷新失败（可能不需要）"
    fi

    if [ -f /system/bin/oplus-font ]; then
        oplus-font refresh >/dev/null 2>&1 && log_service INFO "ColorOS 字体刷新成功" || log_service INFO "ColorOS 字体刷新未生效"
    fi

    if [ -f "$MODDIR/common/play_font_bridge" ]; then
        MODDIR="$MODDIR" sh "$MODDIR/common/play_font_bridge" boot
        MODDIR="$MODDIR" sh "$MODDIR/common/play_font_bridge" watch &
    fi
    if [ -f "$MODDIR/common/wechat_xweb_bridge" ]; then
        MODDIR="$MODDIR" sh "$MODDIR/common/wechat_xweb_bridge" &
    fi

    rm -f "$MODDIR/.first_boot" 2>/dev/null || true
    log_service INFO "服务脚本执行完成"
) &
