#!/system/bin/sh
# LuoShu private payload mount. External metamodules are intentionally ignored.
set +e
MODDIR="${0%/*}"
MODULE_DIR="$MODDIR"
[ -f "$MODDIR/common/private_payload.sh" ] && . "$MODDIR/common/private_payload.sh"
luoshu_private_mount_module_view "$MODDIR" >/dev/null 2>&1 || true
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/font_config_runtime.sh" ] && . "$MODDIR/common/font_config_runtime.sh"
[ -f "$MODDIR/common/font_config_partitions.sh" ] && . "$MODDIR/common/font_config_partitions.sh"
[ -f "$MODDIR/common/mount_compat.sh" ] && . "$MODDIR/common/mount_compat.sh"
[ -f "$MODDIR/common/mount_self_backend.sh" ] && . "$MODDIR/common/mount_self_backend.sh"
type luoshu_private_self_mount_ensure >/dev/null 2>&1 || exit 0
luoshu_private_self_mount_ensure >/dev/null 2>&1 || true
exit 0
