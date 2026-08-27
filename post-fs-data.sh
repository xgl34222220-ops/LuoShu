#!/system/bin/sh
# LuoShu early-boot router.
# Legacy-v14.4 mode mounts the already-generated physical-file payload directly and
# deliberately skips the v4 device-template / XML / payload rebuild initializer.
set +e
MODDIR="${0%/*}"
MODULE_DIR="$MODDIR"
LEGACY_MODE="$MODDIR/config/font_runtime_legacy_v14_4.conf"
V4_POST_FS="$MODDIR/post-fs-data-v4.sh"

if [ ! -f "$LEGACY_MODE" ]; then
    [ -f "$V4_POST_FS" ] && exec sh "$V4_POST_FS"
    exit 0
fi

mkdir -p "$MODDIR/config" "$MODDIR/logs" 2>/dev/null || true
chmod 0755 "$MODDIR" "$MODDIR/common" 2>/dev/null || true
rm -rf "$MODDIR/config/font_switch.lock" "$MODDIR/config/mount.lock" 2>/dev/null || true

# Expose the private payload only long enough for the existing self-mount backend.
[ -f "$MODDIR/common/private_payload.sh" ] && . "$MODDIR/common/private_payload.sh"
type luoshu_private_mount_module_view >/dev/null 2>&1 && \
    luoshu_private_mount_module_view "$MODDIR" >/dev/null 2>&1 || true

[ -f "$MODDIR/common/mount_self_backend.sh" ] && . "$MODDIR/common/mount_self_backend.sh"
_lpf_root=$(luoshu_detect_root_manager 2>/dev/null | head -n1)
_lpf_stage=$(luoshu_self_mount_stage_for_manager "$_lpf_root" 2>/dev/null)
case "$_lpf_stage" in
    post-mount)
        # APatch / KernelSU-family managers expose their global OverlayFS later.
        # Do not run the v4 initializer here; post-mount will expose the same payload.
        type luoshu_private_unmount_module_view >/dev/null 2>&1 && \
            luoshu_private_unmount_module_view "$MODDIR" >/dev/null 2>&1 || true
        ;;
    *)
        # Magisk: mount the legacy physical aliases now. No XML generation or validation.
        type luoshu_private_self_mount_ensure >/dev/null 2>&1 && \
            luoshu_private_self_mount_ensure >/dev/null 2>&1 || true
        ;;
esac

printf '[%s] legacy-v14.4 early mount complete\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" \
    >> "$MODDIR/logs/post-fs-data.log" 2>/dev/null || true
exit 0
