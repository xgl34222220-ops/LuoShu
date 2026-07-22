#!/system/bin/sh
# ============================================================
# 洛书 - 后台服务（版本以 module.prop 为准）
# 功能：启动完成后校正权限、补装内置 App、重建旧字体负载、预热索引并恢复字重。
# ============================================================

MODDIR="${0%/*}"
MODULE_VERSION=$(sed -n 's/^version=//p' "$MODDIR/module.prop" 2>/dev/null | head -n1)
[ -n "$MODULE_VERSION" ] || MODULE_VERSION="unknown"
MODULE_DIR="$MODDIR"
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/font_config_runtime.sh" ] && . "$MODDIR/common/font_config_runtime.sh"
[ -f "$MODDIR/common/font_config_partitions.sh" ] && . "$MODDIR/common/font_config_partitions.sh"
[ -f "$MODDIR/common/mount_compat.sh" ] && . "$MODDIR/common/mount_compat.sh"
[ -f "$MODDIR/common/module_update_state.sh" ] && . "$MODDIR/common/module_update_state.sh"

(
    WAITED=0
    while [ "$(getprop sys.boot_completed 2>/dev/null)" != "1" ] && [ "$WAITED" -lt 600 ]; do
        sleep 3
        WAITED=$((WAITED + 3))
    done

    # A timeout is not proof that Android completed boot; never confirm in that case.
    [ "$(getprop sys.boot_completed 2>/dev/null)" = "1" ] || exit 0

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

    notify_service() {
        _title="$1"
        _message="$2"
        _tag="$3"
        command -v cmd >/dev/null 2>&1 || return 0
        cmd notification post -S bigtext -t "$_title" "$_tag" "$_message" >/dev/null 2>&1 || \
            cmd notification post -t "$_title" "$_tag" "$_message" >/dev/null 2>&1 || true
    }

    log_service "INFO" "服务脚本开始执行 ($MODULE_VERSION)"
    type font_config_mark_boot_success >/dev/null 2>&1 && font_config_mark_boot_success
    if [ -f "$LOG_FILE" ]; then
        _log_size=$(wc -c < "$LOG_FILE" 2>/dev/null | tr -d '[:space:]')
        case "$_log_size" in ''|*[!0-9]*) _log_size=0 ;; esac
        if [ "$_log_size" -gt 1048576 ]; then
            _trim="$LOG_FILE.trim.$$"
            tail -n 1200 "$LOG_FILE" > "$_trim" 2>/dev/null && mv -f "$_trim" "$LOG_FILE" 2>/dev/null || true
        fi
    fi

    # 原生 App 后端统一通过 sh 调用，仍校正权限以兼容不同 Root 管理器的解压行为。
    chmod 0755 "$MODDIR" "$MODDIR/common" 2>/dev/null || true
    chmod 0755 "$MODDIR/customize.sh" "$MODDIR/post-fs-data.sh" "$MODDIR/service.sh" "$MODDIR/uninstall.sh" "$MODDIR/action.sh" 2>/dev/null || true
    find "$MODDIR/common" -maxdepth 1 -type f -exec chmod 0755 {} \; 2>/dev/null || true
    chmod 0644 "$MODDIR/common/font_instance.py" "$MODDIR/common/composite_font.py" "$MODDIR/common/font_metrics_normalize.py" 2>/dev/null || true
    chmod 0755 "$MODDIR/common/python/bin/luoshu-python" 2>/dev/null || true
    chmod 0755 "$MODDIR/system/bin/洛书" "$MODDIR/system/bin/luoshud" 2>/dev/null || true

    # 刷写阶段无法调用 pm 时，只在首次完整开机后自动重试一次。
    # 成功覆盖安装会保留 App 数据、字体索引和外观设置。
    if [ -s "$MODDIR/bundled/LuoShu-App.apk" ] && [ -f "$MODDIR/common/app_installer.sh" ]; then
        if [ -f "$MODDIR/config/app_install_pending" ] || [ ! -f "$MODDIR/config/app_install_state.conf" ]; then
            _app_result=$(MODDIR="$MODDIR" APP_INSTALL_LOG="$MODDIR/logs/app-install.log" sh "$MODDIR/common/app_installer.sh" first-boot 2>/dev/null)
            _app_code=$?
            case "$_app_result" in
                installed)
                    rm -f "$MODDIR/config/app_install_manual" 2>/dev/null || true
                    log_service "INFO" "已在首次开机自动安装或更新洛书 App"
                    ;;
                already-current)
                    rm -f "$MODDIR/config/app_install_manual" 2>/dev/null || true
                    log_service "INFO" "洛书 App 已是模块内置版本"
                    ;;
                *)
                    # 首次开机只自动尝试一次，避免签名冲突时每次开机重复失败。
                    rm -f "$MODDIR/config/app_install_pending" 2>/dev/null || true
                    touch "$MODDIR/config/app_install_manual" 2>/dev/null || true
                    log_service "INFO" "App 自动更新未完成（code=$_app_code），请使用模块操作按钮重试；详情见 app-install.log"
                    ;;
            esac
        fi
    fi

    # 架构升级时不再卡住刷写界面。Android 完成启动后再使用完整运行环境后台重建，
    # 成功后通知用户重启一次加载新负载；失败则立即撤销覆盖并恢复系统默认字体。
    if [ -f "$MODDIR/config/font-payload-rebuild-pending.conf" ]; then
        _pending_font=$(sed -n 's/^font=//p' "$MODDIR/config/font-payload-rebuild-pending.conf" 2>/dev/null | head -n1 | tr -d '\r\n')
        [ -n "$_pending_font" ] || _pending_font=$(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
        [ -n "$_pending_font" ] || _pending_font=default
        LUOSHU_UPDATE_ACTIVE="$_pending_font"
        export LUOSHU_UPDATE_ACTIVE
        log_service "INFO" "开始后台重建旧字体负载：$_pending_font"
        notify_service "洛书" "正在后台升级当前字体，无需停留在刷写页面。" luoshu-font-rebuild
        if type luoshu_rebuild_preserved_payload >/dev/null 2>&1 && luoshu_rebuild_preserved_payload "$MODDIR"; then
            log_service "INFO" "旧字体负载已按新架构重建：$_pending_font"
            notify_service "洛书" "字体升级完成，请完整重启一次使新版字体生效。" luoshu-font-rebuild
        else
            log_service "ERROR" "旧字体负载后台重建失败，正在恢复系统默认字体"
            if type luoshu_payload_quarantine >/dev/null 2>&1; then
                luoshu_payload_quarantine
            else
                printf 'default\n' > "$MODDIR/config/active_font.conf" 2>/dev/null || true
                rm -f "$MODDIR/config/font-payload-rebuild-pending.conf" "$MODDIR/config/font-payload-schema.conf" 2>/dev/null || true
            fi
            notify_service "洛书" "字体升级失败，已安全恢复系统默认字体；请打开洛书重新应用。" luoshu-font-rebuild
        fi
    fi

    # Root 管理器模块说明只显示当前字体，不再塞入更新日志。
    if [ -f "$MODDIR/common/module_status.sh" ]; then
        MODDIR="$MODDIR" sh "$MODDIR/common/module_status.sh" >/dev/null 2>&1 || true
    fi

    # 字体列表在后台预热。轻量指纹未变化时跳过轮廓解析；变化后重建原生索引。
    if [ -f "$MODDIR/common/font_library_cache.sh" ] && [ -f "$MODDIR/common/font_manager.sh" ]; then
        _font_fp=$(MODDIR="$MODDIR" sh "$MODDIR/common/font_library_cache.sh" value 2>/dev/null)
        _font_fp_old=$(cat "$MODDIR/config/native_font_index.key" 2>/dev/null)
        case "$_font_fp_old" in native-v1\|*) _font_fp_old="${_font_fp_old##*|}" ;; esac
        if [ -n "$_font_fp" ] && { [ "$_font_fp" != "$_font_fp_old" ] || [ ! -s "$MODDIR/config/native_font_index.json" ]; }; then
            if MODDIR="$MODDIR" sh "$MODDIR/common/font_manager.sh" action list refresh >/dev/null 2>&1; then
                log_service "INFO" "原生字体索引后台预热完成"
            else
                log_service "INFO" "字体索引后台预热失败，App 将继续使用已有本地索引"
            fi
        fi
    fi

    # 恢复用户保存的 Android 全局字重调节；组合槽字重已固化到字体轮廓。
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

    # 新字体只由原生 App 或后台迁移任务提交，完整重启后由系统自然加载。
    rm -f "$MODDIR/.first_boot" 2>/dev/null || true
    log_service "INFO" "服务脚本执行完成"
) &
