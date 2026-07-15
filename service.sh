#!/system/bin/sh
# ============================================================
# 洛书 - 服务脚本 (service.sh)
# 作者：惜故里丶
# 版本：v12.8
# 功能：系统启动后刷新字体缓存并桥接 GMS 动态字体
# ============================================================

MODDIR="${0%/*}"

# 在后台子进程中执行，避免阻塞启动
(
    # 等待系统完全启动，最多约 90 秒
    WAITED=0
    while [ "$(getprop sys.boot_completed 2>/dev/null)" != "1" ] && [ "$WAITED" -lt 90 ]; do
        sleep 3
        WAITED=$((WAITED + 3))
    done

    LOG_FILE="$MODDIR/logs/fontswitch.log"
    LOG_LEVEL="${LOG_LEVEL:-INFO}"

    log_service() {
        LEVEL="$1"
        MSG="$2"
        TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "unknown")
        # DEBUG 级别仅在 LOG_LEVEL=DEBUG 时记录
        if [ "$LEVEL" = "DEBUG" ] && [ "$LOG_LEVEL" != "DEBUG" ]; then
            return 0
        fi
        if [ -d "$MODDIR/logs" ]; then
            echo "[$TIMESTAMP] [SERVICE] [$LEVEL] $MSG" >> "$LOG_FILE" 2>/dev/null || true
        fi
    }

    log_service "INFO" "服务脚本开始执行 (v12.8)"

    # 刷新字体缓存
    if command -v cmd >/dev/null 2>&1; then
        cmd font system --update >/dev/null 2>&1 && \
            log_service "INFO" "字体缓存刷新成功" || \
            log_service "INFO" "字体缓存刷新失败（可能不需要）"
    fi

    # ColorOS 特定刷新
    if [ -f /system/bin/oplus-font ]; then
        oplus-font refresh >/dev/null 2>&1 && \
            log_service "INFO" "ColorOS 字体刷新成功" || \
            log_service "INFO" "ColorOS 字体刷新未生效"
    fi

    # Android 16 的 GMS 字体既可能注册到 /data/fonts/files，也可能只保存在
    # GMS 私有 opentype 目录。桥接两种真机路径；Flex/Code 保留原版。
    if [ -f "$MODDIR/common/play_font_bridge.sh" ]; then
        MODDIR="$MODDIR" sh "$MODDIR/common/play_font_bridge.sh" boot
    fi

    # 微信公众号由 XWeb/独立 Chromium 进程渲染，不一定沿用微信主进程
    # 的字体视图。单独桥接相关 zygote、XWeb 和微信子进程。
    if [ -f "$MODDIR/common/wechat_xweb_bridge.sh" ]; then
        MODDIR="$MODDIR" sh "$MODDIR/common/wechat_xweb_bridge.sh" &
    fi

    # 删除首次启动标记
    rm -f "$MODDIR/.first_boot" 2>/dev/null

    log_service "INFO" "服务脚本执行完成"
) &
