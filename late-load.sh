#!/system/bin/sh
# KernelSU late-load stage (`ksud late-load`, https://kernelsu.org/guide/module.html#late-load-mode).
# In late-load mode KernelSU does not run post-fs-data.sh; it runs late-load.sh
# before its OverlayFS stage, then post-mount.sh, service.sh and boot-completed.sh
# as usual. Run the unchanged post-fs-data pipeline (next-boot payload
# activation, private view hidden until post-mount) exactly once per boot.
set +e
MODDIR="${0%/*}"
MODULE_DIR="$MODDIR"
export MODDIR MODULE_DIR

# Normal boots already ran post-fs-data.sh; this file must never repeat it.
[ "${KSU_LATE_LOAD:-}" = 1 ] || exit 0

GUARD="$MODDIR/common/boot_loop_guard.sh"
if [ -f "$GUARD" ]; then
    . "$GUARD"
    if ! luoshu_bootloop_late_load_claim; then
        # post-fs-data already ran during this boot (or a repeated late-load):
        # the payload may be mounted, so it must not be activated again.
        luoshu_bootloop_log 'late-load：本次启动已执行过早期流程，跳过重复执行'
        exit 0
    fi
    luoshu_bootloop_log 'KernelSU late-load：执行与 post-fs-data 相同的早期流程'
fi

[ -f "$MODDIR/post-fs-data.sh" ] || exit 0
exec sh "$MODDIR/post-fs-data.sh"
