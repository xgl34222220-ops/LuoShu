#!/system/bin/sh
# LuoShu boot-loop guard (卡开机保护).
#
# The 22 frozen 1.1.1 boot/mount files cannot change, so this helper is entered
# from common/util_functions.sh, which every frozen boot router sources before
# it loads mount_compat.sh and calls luoshu_private_self_mount_ensure. The
# stage is taken from the router basename, as ensure_public_storage already does.
#
#   post-fs-data  count one started boot per boot_id (only while a non-default
#                 font is selected). After LUOSHU_BOOTLOOP_LIMIT consecutive
#                 boots that never reached boot-completed, enter safe mode.
#   post-mount    safe mode: stop before any LuoShu mount.
#   boot-completed / module_status (sys.boot_completed=1)
#                 the boot finished: clear the counter. Safe mode stays until
#                 the user re-enables it (action button or app_bridge
#                 boot_guard_reset), so a bad payload cannot loop again.
#
# Safe mode never deletes the payload or the user's selection; it only skips
# mounting and records the reason in config/self-mount.conf (read by the App
# and service.sh), config/boot-loop-guard.conf and logs/fontswitch.log.
set +e

LUOSHU_BOOTLOOP_LIMIT="${LUOSHU_BOOTLOOP_LIMIT:-2}"
LUOSHU_BOOTLOOP_REASON='boot-loop-safe-mode/卡开机保护已跳过挂载'

luoshu_bootloop_module() {
    printf '%s\n' "${MODULE_DIR:-${MODDIR:-/data/adb/modules/LuoShu}}"
}

luoshu_bootloop_boot_id() {
    if [ -n "${LUOSHU_BOOTLOOP_BOOT_ID:-}" ]; then
        printf '%s\n' "$LUOSHU_BOOTLOOP_BOOT_ID"
        return 0
    fi
    cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n'
}

luoshu_bootloop_state_file() {
    printf '%s/config/boot-loop-guard.conf\n' "$(luoshu_bootloop_module)"
}

luoshu_bootloop_safe_file() {
    printf '%s/config/boot-loop-safe-mode.conf\n' "$(luoshu_bootloop_module)"
}

luoshu_bootloop_get() {
    sed -n "s/^$1=//p" "$(luoshu_bootloop_state_file)" 2>/dev/null | head -n1 | tr -d '\r\n'
}

luoshu_bootloop_log() {
    _lbl_module=$(luoshu_bootloop_module)
    mkdir -p "$_lbl_module/logs" 2>/dev/null || true
    printf '[%s] [BOOT-GUARD] %s\n' \
        "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$*" \
        >> "$_lbl_module/logs/fontswitch.log" 2>/dev/null || true
}

# luoshu_bootloop_write COUNT START_BOOT COMPLETED_BOOT POSTFS_BOOT
luoshu_bootloop_write() {
    _lbw_file=$(luoshu_bootloop_state_file)
    mkdir -p "${_lbw_file%/*}" 2>/dev/null || return 1
    {
        printf 'count=%s\n' "$1"
        printf 'limit=%s\n' "$LUOSHU_BOOTLOOP_LIMIT"
        printf 'startBootId=%s\n' "$2"
        printf 'completedBootId=%s\n' "$3"
        printf 'postFsBootId=%s\n' "$4"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "${_lbw_file}.tmp.$$" 2>/dev/null && mv -f "${_lbw_file}.tmp.$$" "$_lbw_file" 2>/dev/null || {
        rm -f "${_lbw_file}.tmp.$$" 2>/dev/null || true
        return 1
    }
    chmod 0644 "$_lbw_file" 2>/dev/null || true
    return 0
}

luoshu_bootloop_safe_mode_active() {
    [ -f "$(luoshu_bootloop_safe_file)" ]
}

luoshu_bootloop_active_font() {
    _lbaf=$(head -n1 "$(luoshu_bootloop_module)/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    printf '%s\n' "${_lbaf:-default}"
}

# Record the skipped mount where the App, service.sh and module_status.sh
# already look, so no boot claims that the font is active.
luoshu_bootloop_record_skip() {
    _lbrs_module=$(luoshu_bootloop_module)
    mkdir -p "$_lbrs_module/config" 2>/dev/null || return 0
    {
        printf 'state=failed\n'
        printf 'backend=none\n'
        printf 'mounted=\n'
        printf 'failed=%s\n' "$LUOSHU_BOOTLOOP_REASON"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_lbrs_module/config/self-mount.conf.tmp.$$" 2>/dev/null && \
        mv -f "$_lbrs_module/config/self-mount.conf.tmp.$$" "$_lbrs_module/config/self-mount.conf" 2>/dev/null || \
        rm -f "$_lbrs_module/config/self-mount.conf.tmp.$$" 2>/dev/null || true
    # Same markers private_mount_policy.sh leaves after every self-mount: the
    # Root manager must not mount the module tree on its own either.
    : > "$_lbrs_module/skip_mount" 2>/dev/null || true
    : > "$_lbrs_module/skip_mountify" 2>/dev/null || true
}

luoshu_bootloop_enter_safe_mode() {
    _lbesm_count="$1"
    _lbesm_file=$(luoshu_bootloop_safe_file)
    mkdir -p "${_lbesm_file%/*}" 2>/dev/null || true
    {
        printf 'state=safe-mode\n'
        printf 'reason=%s\n' "$LUOSHU_BOOTLOOP_REASON"
        printf 'unfinishedBoots=%s\n' "$((_lbesm_count - 1))"
        printf 'activeFont=%s\n' "$(luoshu_bootloop_active_font)"
        printf 'bootId=%s\n' "$(luoshu_bootloop_boot_id)"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "${_lbesm_file}.tmp.$$" 2>/dev/null && mv -f "${_lbesm_file}.tmp.$$" "$_lbesm_file" 2>/dev/null || true
    chmod 0644 "$_lbesm_file" 2>/dev/null || true
    luoshu_bootloop_log "连续 $((_lbesm_count - 1)) 次启动未完成，进入卡开机保护：本次及之后启动跳过洛书挂载，字体文件与选择均保留。在 Root 管理器点击洛书“操作”按钮可重新启用。"
}

# post-fs-data. Returns 0 when mounting may continue, 1 in safe mode.
luoshu_bootloop_begin() {
    _lbb_boot=$(luoshu_bootloop_boot_id)
    _lbb_count=$(luoshu_bootloop_get count)
    case "$_lbb_count" in ''|*[!0-9]*) _lbb_count=0 ;; esac
    _lbb_start=$(luoshu_bootloop_get startBootId)
    _lbb_done=$(luoshu_bootloop_get completedBootId)

    if [ "${KSU_LATE_LOAD:-}" = 1 ]; then
        # KernelSU late-load runs after Android already booted: no boot to count.
        luoshu_bootloop_write "$_lbb_count" "$_lbb_start" "$_lbb_done" "$_lbb_boot" >/dev/null 2>&1 || true
    elif [ -z "$_lbb_boot" ]; then
        :
    elif [ "$(luoshu_bootloop_active_font)" = default ]; then
        # Nothing of LuoShu is mounted, so LuoShu cannot be the boot loop.
        luoshu_bootloop_write 0 "$_lbb_boot" "$_lbb_done" "$_lbb_boot" >/dev/null 2>&1 || true
    elif [ "$_lbb_start" != "$_lbb_boot" ]; then
        _lbb_count=$((_lbb_count + 1))
        luoshu_bootloop_write "$_lbb_count" "$_lbb_boot" "$_lbb_done" "$_lbb_boot" >/dev/null 2>&1 || true
        if [ "$_lbb_count" -gt "$LUOSHU_BOOTLOOP_LIMIT" ] && ! luoshu_bootloop_safe_mode_active; then
            luoshu_bootloop_enter_safe_mode "$_lbb_count"
        fi
    fi

    if luoshu_bootloop_safe_mode_active; then
        luoshu_bootloop_record_skip
        return 1
    fi
    return 0
}

# Android reached boot completed: clear the counter once per boot.
luoshu_bootloop_complete() {
    _lbc_boot=$(luoshu_bootloop_boot_id)
    [ -n "$_lbc_boot" ] || return 0
    [ "$(luoshu_bootloop_get completedBootId)" != "$_lbc_boot" ] || return 0
    _lbc_count=$(luoshu_bootloop_get count)
    luoshu_bootloop_write 0 "$(luoshu_bootloop_get startBootId)" "$_lbc_boot" \
        "$(luoshu_bootloop_get postFsBootId)" >/dev/null 2>&1 || return 0
    case "$_lbc_count" in ''|*[!0-9]*) _lbc_count=0 ;; esac
    # count=1 is the normal "this boot started" mark; more means earlier boots
    # never completed and are worth a log line.
    [ "$_lbc_count" -le 1 ] || \
        luoshu_bootloop_log "启动已完成，未完成启动计数已清零（此前 $_lbc_count）"
    return 0
}

# User re-enable: leave safe mode and start counting from zero.
luoshu_bootloop_reset() {
    _lbr_was=0
    luoshu_bootloop_safe_mode_active && _lbr_was=1
    rm -f "$(luoshu_bootloop_safe_file)" 2>/dev/null || true
    luoshu_bootloop_write 0 '' "$(luoshu_bootloop_boot_id)" "$(luoshu_bootloop_get postFsBootId)" >/dev/null 2>&1 || true
    [ "$_lbr_was" -eq 0 ] || luoshu_bootloop_log '用户已重新启用：退出卡开机保护，下次启动恢复洛书挂载'
    return 0
}

# KernelSU late-load: run the post-fs-data pipeline at most once per boot, and
# never when post-fs-data already ran during a normal boot.
luoshu_bootloop_late_load_claim() {
    _lbllc_boot=$(luoshu_bootloop_boot_id)
    [ -n "$_lbllc_boot" ] || return 0
    [ "$(luoshu_bootloop_get postFsBootId)" != "$_lbllc_boot" ]
}

# Entered by util_functions.sh. Exits the calling boot router in safe mode.
luoshu_bootloop_stage_hook() {
    _lbsh_module=$(luoshu_bootloop_module)
    [ -f "$_lbsh_module/module.prop" ] || return 0
    case "${0##*/}" in
        post-fs-data.sh)
            luoshu_bootloop_begin && return 0
            luoshu_bootloop_log '本次启动处于卡开机保护，post-fs-data 跳过挂载'
            # The v2.2.7 Magisk core sources a temporary copy; remove it here
            # because the core's own cleanup line is never reached.
            rm -f "$_lbsh_module/.post-fs-data-v227.$$.sh" 2>/dev/null || true
            exit 0
            ;;
        post-mount.sh)
            luoshu_bootloop_safe_mode_active || return 0
            luoshu_bootloop_record_skip
            luoshu_bootloop_log '本次启动处于卡开机保护，post-mount 跳过挂载'
            exit 0
            ;;
        boot-completed.sh)
            luoshu_bootloop_complete
            luoshu_bootloop_safe_mode_active || return 0
            luoshu_bootloop_record_skip
            exit 0
            ;;
    esac
    return 0
}
