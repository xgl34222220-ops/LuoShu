#!/system/bin/sh
# LuoShu early-boot wrapper around the verified v2.2.7 initializer.
# Delegated core consumes font-payload-rebuild-pending.conf before the payload is hidden.
# Delegated recovery contract: font_mix_controller.sh recover
# Delegated dynamic view contract: device_font_dynamic_mount_apply
set +e
MODDIR="${0%/*}"
MODULE_DIR="$MODDIR"
_lpf_base="$MODDIR/.luoshu-runtime/post-fs-data-v227.sh"
_lpf_temp="$MODDIR/.post-fs-data-v227.$$.sh"
[ -f "$MODDIR/common/private_payload.sh" ] && . "$MODDIR/common/private_payload.sh"
luoshu_private_mount_module_view "$MODDIR" >/dev/null 2>&1 || true

# A hard failure detected after the previous boot is consumed before any font
# target is mounted.  This guarantees the next boot starts from the complete ROM
# font tree instead of attempting to hot-unmount fonts from running processes.
if [ -f "$MODDIR/common/font_activation_rollback.sh" ]; then
    . "$MODDIR/common/font_activation_rollback.sh"
    type luoshu_activation_rollback_pending >/dev/null 2>&1 && \
       luoshu_activation_rollback_pending && \
       luoshu_activation_rollback_apply >/dev/null 2>&1 || true
fi

sed '$d' "$_lpf_base" > "$_lpf_temp" 2>/dev/null || exit 0
. "$_lpf_temp"
_lpf_rc=$?
rm -f "$_lpf_temp" 2>/dev/null || true
[ "$_lpf_rc" -eq 0 ] || exit "$_lpf_rc"

[ -f "$MODDIR/common/mount_self_backend.sh" ] && . "$MODDIR/common/mount_self_backend.sh"
_lpf_root=$(luoshu_detect_root_manager 2>/dev/null | head -n1)
_lpf_stage=$(luoshu_self_mount_stage_for_manager "$_lpf_root" 2>/dev/null)
case "$_lpf_stage" in
    post-mount)
        # APatch and KernelSU-family managers provide post-mount after their
        # OverlayFS stage. Keep the payload hidden until that globally visible
        # stage instead of racing module mounts in blocking post-fs-data.
        luoshu_private_unmount_module_view "$MODDIR" >/dev/null 2>&1 || true
        ;;
    *)
        # Magisk has no module post-mount stage.
        type luoshu_private_self_mount_ensure >/dev/null 2>&1 && \
            luoshu_private_self_mount_ensure >/dev/null 2>&1 || true
        ;;
esac
exit 0
