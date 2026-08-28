#!/system/bin/sh
# LuoShu post-mount router. Legacy-v14.4 mode only exposes the already-generated
# physical-file payload; normal mode preserves the current v4 post-mount behavior.
# External metamodules are intentionally ignored; LuoShu owns the self-mount path.
set +e
MODDIR="${0%/*}"
MODULE_DIR="$MODDIR"
LEGACY_MODE="$MODDIR/config/font_runtime_legacy_v14_4.conf"
V4_POST_MOUNT="$MODDIR/post-mount-v4.sh"
HYPEROS_LEGACY_COMPAT="$MODDIR/common/legacy_v14_4/hyperos_full_coverage.sh"

if [ ! -f "$LEGACY_MODE" ]; then
    [ -f "$V4_POST_MOUNT" ] && exec sh "$V4_POST_MOUNT"
    exit 0
fi

[ -f "$MODDIR/common/private_payload.sh" ] && . "$MODDIR/common/private_payload.sh"
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/font_config_runtime.sh" ] && . "$MODDIR/common/font_config_runtime.sh"
[ -f "$MODDIR/common/font_config_partitions.sh" ] && . "$MODDIR/common/font_config_partitions.sh"
# mount_compat.sh loads private_mount_policy + atomic/runtime mount functions.
# The previous legacy router sourced only mount_self_backend.sh, so the real
# luoshu_private_self_mount_ensure entry point did not exist and post-mount
# silently exited without mounting any font payload.
[ -f "$MODDIR/common/mount_compat.sh" ] && . "$MODDIR/common/mount_compat.sh"
[ -f "$MODDIR/common/mount_self_backend.sh" ] && . "$MODDIR/common/mount_self_backend.sh"

type luoshu_private_mount_module_view >/dev/null 2>&1 && \
    luoshu_private_mount_module_view "$MODDIR" >/dev/null 2>&1 || true

[ -f "$HYPEROS_LEGACY_COMPAT" ] && . "$HYPEROS_LEGACY_COMPAT"
type luoshu_hyperos_full_payload_ensure >/dev/null 2>&1 && \
    luoshu_hyperos_full_payload_ensure >/dev/null 2>&1 || true

if ! type luoshu_private_self_mount_ensure >/dev/null 2>&1; then
    mkdir -p "$MODDIR/config" "$MODDIR/logs" 2>/dev/null || true
    {
        printf 'state=failed\n'
        printf 'backend=none\n'
        printf 'failed=runtime-loader-missing\n'
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$MODDIR/config/self-mount.conf" 2>/dev/null || true
    printf '[%s] post-mount runtime loader missing; no font mount attempted\n' \
        "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" \
        >> "$MODDIR/logs/post-mount.log" 2>/dev/null || true
    exit 0
fi

if luoshu_private_self_mount_ensure >/dev/null 2>&1; then
    printf '[%s] physical compatibility post-mount completed\n' \
        "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" \
        >> "$MODDIR/logs/post-mount.log" 2>/dev/null || true
else
    printf '[%s] physical compatibility post-mount failed; see self-mount.conf/fontswitch.log\n' \
        "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" \
        >> "$MODDIR/logs/post-mount.log" 2>/dev/null || true
fi
exit 0