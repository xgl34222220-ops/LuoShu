#!/system/bin/sh
# Reliable final convergence stage for KernelSU/APatch. service.sh remains the
# Magisk-compatible fallback, but post-boot verification must not be one-shot.
set +e
MODDIR="${0%/*}"
MODULE_DIR="$MODDIR"

[ -f "$MODDIR/common/private_payload.sh" ] && . "$MODDIR/common/private_payload.sh"
type luoshu_private_mount_module_view >/dev/null 2>&1 && \
    luoshu_private_mount_module_view "$MODDIR" >/dev/null 2>&1 || true
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/font_config_runtime.sh" ] && . "$MODDIR/common/font_config_runtime.sh"
[ -f "$MODDIR/common/font_config_partitions.sh" ] && . "$MODDIR/common/font_config_partitions.sh"
[ -f "$MODDIR/common/mount_compat.sh" ] && . "$MODDIR/common/mount_compat.sh"
[ -f "$MODDIR/common/mount_self_backend.sh" ] && . "$MODDIR/common/mount_self_backend.sh"
[ -f "$MODDIR/common/font_boot_state.sh" ] && . "$MODDIR/common/font_boot_state.sh"

luoshu_font_rebuild_marker_reconcile >/dev/null 2>&1 || true
_lfbc_active=$(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
[ -n "$_lfbc_active" ] || _lfbc_active=default
if [ "$_lfbc_active" != default ]; then
    # The physical compatibility compositor has its own mount-confirmation
    # contract in service.sh and deliberately carries no v4 device-template
    # manifest. Running the v4 guard here falsely labels every successfully
    # activated composite as an expired payload and leaves the App showing both
    # "confirmed" and "next payload failed" at the same time.
    if [ ! -f "$MODDIR/config/font_runtime_legacy_v14_4.conf" ]; then
        type font_config_boot_guard >/dev/null 2>&1 && \
            font_config_boot_guard "$_lfbc_active" >/dev/null 2>&1 || true
    fi
    type luoshu_private_self_mount_ensure >/dev/null 2>&1 && \
        luoshu_private_self_mount_ensure >/dev/null 2>&1 || true
fi

_lfbc_attempt=1
while [ "$_lfbc_attempt" -le 5 ]; do
    luoshu_text_reboot_reconcile >/dev/null 2>&1 && exit 0
    [ "$_lfbc_attempt" -ge 5 ] || sleep 3
    _lfbc_attempt=$((_lfbc_attempt + 1))
done
exit 0
