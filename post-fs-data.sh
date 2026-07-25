#!/system/bin/sh
# LuoShu early-boot wrapper around the verified v2.2.7 initializer.
# Delegated core consumes font-payload-rebuild-pending.conf before the payload is hidden.
set +e
MODDIR="${0%/*}"
MODULE_DIR="$MODDIR"
_lpf_base="$MODDIR/.luoshu-runtime/post-fs-data-v227.sh"
_lpf_temp="$MODDIR/.post-fs-data-v227.$$.sh"
[ -f "$MODDIR/common/private_payload.sh" ] && . "$MODDIR/common/private_payload.sh"
luoshu_private_mount_module_view "$MODDIR" >/dev/null 2>&1 || true

sed '$d' "$_lpf_base" > "$_lpf_temp" 2>/dev/null || exit 0
. "$_lpf_temp"
_lpf_rc=$?
rm -f "$_lpf_temp" 2>/dev/null || true
[ "$_lpf_rc" -eq 0 ] || exit "$_lpf_rc"

[ -f "$MODDIR/common/mount_self_backend.sh" ] && . "$MODDIR/common/mount_self_backend.sh"
_lpf_root=$(luoshu_detect_root_manager 2>/dev/null | head -n1)
case "$_lpf_root" in
    KernelSU)
        # KernelSU runs metamodules next. They must only see empty partition shells.
        luoshu_private_unmount_module_view "$MODDIR" >/dev/null 2>&1 || true
        ;;
    *)
        # Magisk/APatch have no KernelSU post-mount stage.
        type luoshu_private_self_mount_ensure >/dev/null 2>&1 && \
            luoshu_private_self_mount_ensure >/dev/null 2>&1 || true
        ;;
esac
exit 0
