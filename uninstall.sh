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
# The Root manager deletes the module directory whatever this script returns
# (see the Google compatibility note below), so a task that could not be
# reaped must never abort the uninstall: stopping early would leave the
# self-mount state, the metamodule mirror and modules_update behind, and a
# leftover meta-overlayfs mirror can keep mounting fonts after removal.
# Record the failure and continue the best-effort cleanup.
if type luoshu_stop_module_tasks >/dev/null 2>&1; then
    if ! luoshu_stop_module_tasks "$MODDIR"; then
        echo '洛书：字体任务未全部回收；已记录并继续完整清理（私有视图、自挂载状态、元模块镜像）。' >&2
        if command -v log >/dev/null 2>&1; then
            log -t LuoShu 'uninstall: module tasks not fully reaped; continuing best-effort cleanup' >/dev/null 2>&1 || true
        fi
    fi
fi
for _bridge in google_font_provider_bridge.sh hyperos_theme_font_bridge.sh hyperos_webview_route.sh hyperos_theme_takeover.sh; do
    [ ! -f "$MODDIR/common/$_bridge" ] || MODDIR="$MODDIR" sh "$MODDIR/common/$_bridge" restore >/dev/null 2>&1 || true
done
[ -f "$MODDIR/common/private_payload.sh" ] && . "$MODDIR/common/private_payload.sh"
type luoshu_private_unmount_module_view >/dev/null 2>&1 && \
    ( luoshu_private_unmount_module_view "$MODDIR" >/dev/null 2>&1 ) || true
# 清理私有视图的挂载清单（只有清单文件，开机重挂时会重新生成）。
# 不删掉它，/data/adb/luoshu 永远 rmdir 不掉。
_lu_private_state="${LUOSHU_PRIVATE_STATE_ROOT:-/data/adb/luoshu/private-payload}"
_lu_private_state=${_lu_private_state%/}
if [ "${_lu_private_state##*/}" = private-payload ] && [ ! -L "$_lu_private_state" ]; then
    _lu_private_parent=${_lu_private_state%/*}
    [ "${_lu_private_parent##*/}" != luoshu ] || rm -rf "$_lu_private_state" 2>/dev/null || true
fi

# Google 字体兼容：恢复有记录的 FontsProvider 组件状态。
# 管理器在下次开机的 post-fs-data 早期执行本脚本，此时 pm/dumpsys 还不可用；
# 而且不论本脚本返回什么，管理器都会删除模块目录。所以这里绝不中止清理：
#   - 系统已开机完成（例如部分管理器当场执行卸载）时直接恢复；
#   - 仍有未恢复的记录时，把自包含的单次恢复脚本放到模块目录之外的
#     service.d，等开机完成后恢复并删除自己。恢复记录本身一直在
#     /data/adb/luoshu/google-font-fallback，不随模块删除。
_lu_google_store="${LUOSHU_GOOGLE_FALLBACK_STORE:-/data/adb/luoshu/google-font-fallback}"
_lu_google_legacy="${LUOSHU_GOOGLE_FALLBACK_LEGACY_STORE:-/data/adb/luoshu-google-font-fallback}"
_lu_google_pending() {
    for _lugp_dir in "$_lu_google_store" "$_lu_google_legacy"; do
        [ -d "$_lugp_dir" ] && [ ! -L "$_lugp_dir" ] || continue
        for _lugp_file in "$_lugp_dir"/user-*.json; do
            [ -e "$_lugp_file" ] || [ -L "$_lugp_file" ] && return 0
        done
    done
    return 1
}
if _lu_google_pending; then
    if [ "$(getprop sys.boot_completed 2>/dev/null)" = 1 ] && \
       [ -f "$MODDIR/common/google_font_fallback.sh" ]; then
        sh "$MODDIR/common/google_font_fallback.sh" restore-owned --json || true
    fi
fi
if _lu_google_pending; then
    _lu_restore_dir="${LUOSHU_SERVICE_D:-/data/adb/service.d}"
    _lu_restore_src="$MODDIR/common/google_font_deferred_restore.sh"
    _lu_restore_dst="$_lu_restore_dir/luoshu-uninstall-restore.sh"
    if [ -f "$_lu_restore_src" ] && mkdir -p "$_lu_restore_dir" 2>/dev/null && \
       [ -d "$_lu_restore_dir" ] && [ ! -L "$_lu_restore_dir" ] && \
       cp -f "$_lu_restore_src" "$_lu_restore_dst.tmp.$$" 2>/dev/null && \
       chmod 0755 "$_lu_restore_dst.tmp.$$" 2>/dev/null && \
       mv -f "$_lu_restore_dst.tmp.$$" "$_lu_restore_dst" 2>/dev/null; then
        chown 0:0 "$_lu_restore_dst" 2>/dev/null || true
        echo '洛书：Google 字体兼容将在开机完成后自动恢复。' >&2
    else
        rm -f "$_lu_restore_dst.tmp.$$" 2>/dev/null || true
        echo '洛书：Google 字体兼容未能安排开机后恢复；恢复记录已保留，重新安装洛书后可在 App 中恢复原设置。' >&2
    fi
fi
. "$MODDIR/.luoshu-runtime/compat/v227/uninstall.sh"
