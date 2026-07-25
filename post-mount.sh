#!/system/bin/sh
# LuoShu post-mount verification and last-resort self-mount fallback.
# External/root-manager mount owners always win; LuoShu must never stack a second
# OverlayFS over Mountify, Hybrid Mount, Magic Mount or meta-overlayfs.
set +e

MODDIR="${0%/*}"
MODULE_DIR="$MODDIR"
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/font_config_runtime.sh" ] && . "$MODDIR/common/font_config_runtime.sh"
[ -f "$MODDIR/common/font_config_partitions.sh" ] && . "$MODDIR/common/font_config_partitions.sh"
[ -f "$MODDIR/common/mount_compat.sh" ] && . "$MODDIR/common/mount_compat.sh"
[ -f "$MODDIR/common/mount_self_backend.sh" ] && . "$MODDIR/common/mount_self_backend.sh"

type luoshu_self_mount_ensure >/dev/null 2>&1 || exit 0

_lspm_engine=$(luoshu_detect_mount_engine 2>/dev/null | head -n1)
_lspm_root=$(luoshu_detect_root_manager 2>/dev/null | head -n1)
_lspm_external=''

case "$_lspm_engine" in
    meta-overlayfs|dual-dir-metamodule|mountify|magic-mount|magic-mount-rs|hybrid-mount)
        _lspm_external="$_lspm_engine"
        ;;
esac

# A selected metamodule may use a newer/unknown ID that LuoShu has not learned yet.
# Treat any enabled /data/adb/metamodule as the sole mount owner instead of risking
# a recursive or late double mount during Android's second-stage boot.
if [ -z "$_lspm_external" ] && [ -f /data/adb/metamodule/module.prop ] && \
   [ ! -e /data/adb/metamodule/disable ] && [ ! -e /data/adb/metamodule/remove ]; then
    _lspm_external=metamodule
fi

if [ -n "$_lspm_external" ]; then
    type _luoshu_self_state_write >/dev/null 2>&1 && \
        _luoshu_self_state_write delegated "external-$_lspm_external" '' ''
    type _luoshu_self_log >/dev/null 2>&1 && \
        _luoshu_self_log "检测到外部挂载所有者 $_lspm_external，禁止洛书二次挂载"
    exit 0
fi

# Magisk and APatch already own regular-module mounting. LuoShu self-mount is only
# permitted as a KernelSU last resort when no metamodule is active.
case "$_lspm_root" in
    KernelSU) ;;
    *)
        type _luoshu_self_state_write >/dev/null 2>&1 && \
            _luoshu_self_state_write delegated "root-manager-${_lspm_root:-unknown}" '' ''
        type _luoshu_self_log >/dev/null 2>&1 && \
            _luoshu_self_log "Root 管理器 ${_lspm_root:-unknown} 负责挂载，洛书不接管"
        exit 0
        ;;
esac

luoshu_self_mount_ensure >/dev/null 2>&1 || true
exit 0
