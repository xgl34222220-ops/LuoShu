#!/system/bin/sh
# LuoShu post-mount verification and self-mount fallback.
set +e

MODDIR="${0%/*}"
MODULE_DIR="$MODDIR"
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/font_config_runtime.sh" ] && . "$MODDIR/common/font_config_runtime.sh"
[ -f "$MODDIR/common/font_config_partitions.sh" ] && . "$MODDIR/common/font_config_partitions.sh"
[ -f "$MODDIR/common/mount_compat.sh" ] && . "$MODDIR/common/mount_compat.sh"
[ -f "$MODDIR/common/mount_self_fallback.sh" ] && . "$MODDIR/common/mount_self_fallback.sh"

type luoshu_self_mount_ensure >/dev/null 2>&1 || exit 0
luoshu_self_mount_ensure
exit $?
