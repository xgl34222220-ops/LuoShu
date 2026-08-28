#!/system/bin/sh
# LuoShu early-boot router.
# A foreground switch only prepares .luoshu-payload-next. Activate it here before
# any LuoShu font source is exposed or mounted, so the previous Android boot never
# observes its live payload being renamed or rewritten.
set +e
MODDIR="${0%/*}"
MODULE_DIR="$MODDIR"
NEXT_BOOT_HELPER="$MODDIR/common/next_boot_payload.sh"
[ -f "$NEXT_BOOT_HELPER" ] && . "$NEXT_BOOT_HELPER"
type luoshu_next_boot_activate >/dev/null 2>&1 && \
    luoshu_next_boot_activate >/dev/null 2>&1 || true

LEGACY_MODE="$MODDIR/config/font_runtime_legacy_v14_4.conf"
V4_POST_FS="$MODDIR/post-fs-data-v4.sh"
HYPEROS_LEGACY_COMPAT="$MODDIR/common/legacy_v14_4/hyperos_full_coverage.sh"

if [ ! -f "$LEGACY_MODE" ]; then
    if [ -f "$V4_POST_FS" ]; then
        exec sh "$V4_POST_FS"
    fi

    [ -f "$MODDIR/common/private_payload.sh" ] && . "$MODDIR/common/private_payload.sh"
    type luoshu_private_mount_module_view >/dev/null 2>&1 && \
        luoshu_private_mount_module_view "$MODDIR" >/dev/null 2>&1 || true
    [ -f "$MODDIR/common/mount_self_backend.sh" ] && . "$MODDIR/common/mount_self_backend.sh"
    _lpf_root=$(luoshu_detect_root_manager 2>/dev/null | head -n1)
    _lpf_stage=$(luoshu_self_mount_stage_for_manager "$_lpf_root" 2>/dev/null)
    case "$_lpf_stage" in
        post-mount)
            type luoshu_private_unmount_module_view >/dev/null 2>&1 && \
                luoshu_private_unmount_module_view "$MODDIR" >/dev/null 2>&1 || true
            ;;
        *)
            type luoshu_private_self_mount_ensure >/dev/null 2>&1 && \
                luoshu_private_self_mount_ensure >/dev/null 2>&1 || true
            ;;
    esac
    exit 0
fi

mkdir -p "$MODDIR/config" "$MODDIR/logs" 2>/dev/null || true
chmod 0755 "$MODDIR" "$MODDIR/common" 2>/dev/null || true
rm -rf "$MODDIR/config/font_switch.lock" "$MODDIR/config/mount.lock" 2>/dev/null || true

[ -f "$MODDIR/common/private_payload.sh" ] && . "$MODDIR/common/private_payload.sh"
type luoshu_private_mount_module_view >/dev/null 2>&1 && \
    luoshu_private_mount_module_view "$MODDIR" >/dev/null 2>&1 || true

# HyperOS 3 uses additional upright UI/typeface/clock slots across system_ext,
# product and mi_ext. Discover every safe physical slot that exists on this ROM
# before self-mount, rather than relying on a short static filename list.
[ -f "$HYPEROS_LEGACY_COMPAT" ] && . "$HYPEROS_LEGACY_COMPAT"
type luoshu_hyperos_full_payload_ensure >/dev/null 2>&1 && \
    luoshu_hyperos_full_payload_ensure >/dev/null 2>&1 || true

[ -f "$MODDIR/common/mount_self_backend.sh" ] && . "$MODDIR/common/mount_self_backend.sh"
_lpf_root=$(luoshu_detect_root_manager 2>/dev/null | head -n1)
_lpf_stage=$(luoshu_self_mount_stage_for_manager "$_lpf_root" 2>/dev/null)
case "$_lpf_stage" in
    post-mount)
        type luoshu_private_unmount_module_view >/dev/null 2>&1 && \
            luoshu_private_unmount_module_view "$MODDIR" >/dev/null 2>&1 || true
        ;;
    *)
        type luoshu_private_self_mount_ensure >/dev/null 2>&1 && \
            luoshu_private_self_mount_ensure >/dev/null 2>&1 || true
        ;;
esac

printf '[%s] physical compatibility early mount complete\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" \
    >> "$MODDIR/logs/post-fs-data.log" 2>/dev/null || true
exit 0