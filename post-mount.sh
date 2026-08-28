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
type luoshu_private_mount_module_view >/dev/null 2>&1 && \
    luoshu_private_mount_module_view "$MODDIR" >/dev/null 2>&1 || true

[ -f "$HYPEROS_LEGACY_COMPAT" ] && . "$HYPEROS_LEGACY_COMPAT"
type luoshu_hyperos_full_payload_ensure >/dev/null 2>&1 && \
    luoshu_hyperos_full_payload_ensure >/dev/null 2>&1 || true

[ -f "$MODDIR/common/mount_self_backend.sh" ] && . "$MODDIR/common/mount_self_backend.sh"
type luoshu_private_self_mount_ensure >/dev/null 2>&1 || exit 0
luoshu_private_self_mount_ensure >/dev/null 2>&1 || true
exit 0