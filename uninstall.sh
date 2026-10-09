#!/system/bin/sh
# Remove the private module view before the verified v2.2.7 cleanup runs.
# Delegated dynamic cleanup contract: device-font-dynamic-mount.conf
# Delegated Flyme restore contract: luoshu_flyme_pending_apply
set +e
MODDIR="${0%/*}"
MODULE_DIR="$MODDIR"
[ ! -f "$MODDIR/common/font_settings_policy.sh" ] || . "$MODDIR/common/font_settings_policy.sh"
# Stop verified tasks before undoing mounts so an in-flight FontTools/bind
# child cannot recreate a view after restore completes.
[ ! -f "$MODDIR/common/font_switch_lock.sh" ] || . "$MODDIR/common/font_switch_lock.sh"
[ ! -f "$MODDIR/common/background_task.sh" ] || . "$MODDIR/common/background_task.sh"
if type luoshu_stop_module_tasks >/dev/null 2>&1; then
    if ! luoshu_stop_module_tasks "$MODDIR"; then
        echo '洛书：字体任务未全部回收，清理证据已保留，未继续拆除挂载。' >&2
        exit 1
    fi
fi
for _bridge in google_font_provider_bridge.sh hyperos_theme_font_bridge.sh hyperos_webview_route.sh; do
    [ ! -f "$MODDIR/common/$_bridge" ] || MODDIR="$MODDIR" sh "$MODDIR/common/$_bridge" restore >/dev/null 2>&1 || true
done
[ -f "$MODDIR/common/private_payload.sh" ] && . "$MODDIR/common/private_payload.sh"
type luoshu_private_unmount_module_view >/dev/null 2>&1 && \
    ( luoshu_private_unmount_module_view "$MODDIR" >/dev/null 2>&1 ) || true
# Restore recorded component overrides before removing the runtime.
if [ -f "$MODDIR/common/google_font_fallback.sh" ]; then
    if ! sh "$MODDIR/common/google_font_fallback.sh" restore-owned --json; then
        echo '洛书：Google 字体兼容恢复未全部完成，恢复记录与模块运行环境已保留，未继续卸载。' >&2
        exit 1
    fi
fi
. "$MODDIR/.luoshu-runtime/compat/v227/uninstall.sh"
