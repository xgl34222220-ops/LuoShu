#!/system/bin/sh
# LuoShu private payload mount. External metamodules are intentionally ignored.
# Fail open for boot safety, but always leave an explicit current-boot hook result.
set +e
MODDIR="${0%/*}"
MODULE_DIR="$MODDIR"

_post_mount_boot_id() {
    if [ -n "${LUOSHU_BOOT_ID:-}" ]; then
        printf '%s\n' "$LUOSHU_BOOT_ID"
        return 0
    fi
    _pm_boot=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n')
    if [ -z "$_pm_boot" ] && command -v getprop >/dev/null 2>&1; then
        _pm_boot=$(getprop ro.runtime.firstboot 2>/dev/null | tr -d '\r\n')
    fi
    [ -n "$_pm_boot" ] || _pm_boot=unknown
    printf '%s\n' "$_pm_boot"
}

_post_mount_state() {
    _pm_state="$1"
    _pm_reason="$2"
    _pm_code="$3"
    mkdir -p "$MODDIR/config" "$MODDIR/logs" 2>/dev/null || true
    {
        printf 'state=%s\n' "$_pm_state"
        printf 'reason=%s\n' "$_pm_reason"
        printf 'code=%s\n' "$_pm_code"
        printf 'bootId=%s\n' "$(_post_mount_boot_id)"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$MODDIR/config/post-mount-hook.conf.tmp.$$" 2>/dev/null && \
        mv -f "$MODDIR/config/post-mount-hook.conf.tmp.$$" \
            "$MODDIR/config/post-mount-hook.conf" 2>/dev/null || true
    printf '[%s] [POST-MOUNT] state=%s reason=%s code=%s\n' \
        "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" \
        "$_pm_state" "$_pm_reason" "$_pm_code" \
        >> "$MODDIR/logs/self-mount.log" 2>/dev/null || true
}

[ -f "$MODDIR/common/private_payload.sh" ] && . "$MODDIR/common/private_payload.sh"
if ! type luoshu_private_mount_module_view >/dev/null 2>&1 || \
   ! luoshu_private_mount_module_view "$MODDIR" >/dev/null 2>&1; then
    _post_mount_state failed module-view-failed 1
    exit 0
fi
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/font_config_runtime.sh" ] && . "$MODDIR/common/font_config_runtime.sh"
[ -f "$MODDIR/common/font_config_partitions.sh" ] && . "$MODDIR/common/font_config_partitions.sh"
[ -f "$MODDIR/common/mount_compat.sh" ] && . "$MODDIR/common/mount_compat.sh"
[ -f "$MODDIR/common/mount_self_backend.sh" ] && . "$MODDIR/common/mount_self_backend.sh"
if ! type luoshu_private_self_mount_ensure >/dev/null 2>&1; then
    _post_mount_state failed mount-entry-missing 127
    exit 0
fi
luoshu_private_self_mount_ensure >/dev/null 2>&1
_pm_rc=$?
if [ "$_pm_rc" -eq 0 ]; then
    _post_mount_state completed self-mount-complete 0
else
    _post_mount_state failed self-mount-failed "$_pm_rc"
fi
exit 0
