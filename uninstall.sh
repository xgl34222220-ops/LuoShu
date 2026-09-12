#!/system/bin/sh
# Remove the private module view before the verified v2.2.7 cleanup runs.
# Delegated dynamic cleanup contract: device-font-dynamic-mount.conf
# Delegated Flyme restore contract: luoshu_flyme_pending_apply
set +e
MODDIR="${0%/*}"
MODULE_DIR="$MODDIR"
# Stop the watcher and its active child before undoing mounts; otherwise an
# in-flight FontTools/bind child can recreate a view after restore completes.
[ ! -f "$MODDIR/common/font_switch_lock.sh" ] || . "$MODDIR/common/font_switch_lock.sh"
[ ! -f "$MODDIR/common/background_task.sh" ] || . "$MODDIR/common/background_task.sh"
if type luoshu_font_lock_active >/dev/null 2>&1 && type luoshu_terminate_task_tree >/dev/null 2>&1; then
    for _provider_lock in "$MODDIR/.google-font-provider.lock" "$MODDIR/.google-font-provider-bridge.lock"; do
        if luoshu_font_lock_active "$_provider_lock"; then
            _provider_pid=$(luoshu_font_lock_pid "$_provider_lock")
            case "$_provider_pid" in ''|*[!0-9]*|0|1) continue ;; esac
            if grep -aq -e 'google_font_provider_service.sh' -e 'google_font_provider_bridge.sh' -e 'hyperos_theme_font_bridge.sh' \
                "/proc/$_provider_pid/cmdline" 2>/dev/null; then
                luoshu_terminate_task_tree "$_provider_pid"
            fi
        fi
    done
fi
for _bridge in google_font_provider_bridge.sh hyperos_theme_font_bridge.sh; do
    [ ! -f "$MODDIR/common/$_bridge" ] || MODDIR="$MODDIR" sh "$MODDIR/common/$_bridge" restore >/dev/null 2>&1 || true
done
[ -f "$MODDIR/common/private_payload.sh" ] && . "$MODDIR/common/private_payload.sh"
type luoshu_private_unmount_module_view >/dev/null 2>&1 && \
    luoshu_private_unmount_module_view "$MODDIR" >/dev/null 2>&1 || true
. "$MODDIR/.luoshu-runtime/uninstall-v227.sh"
