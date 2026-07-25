#!/system/bin/sh
# Remove the private module view before the verified v2.2.7 cleanup runs.
set +e
MODDIR="${0%/*}"
MODULE_DIR="$MODDIR"
[ -f "$MODDIR/common/private_payload.sh" ] && . "$MODDIR/common/private_payload.sh"
type luoshu_private_unmount_module_view >/dev/null 2>&1 && \
    luoshu_private_unmount_module_view "$MODDIR" >/dev/null 2>&1 || true
. "$MODDIR/.luoshu-runtime/uninstall-v227.sh"
