#!/system/bin/sh
# KernelSU emulated soft reboot stage (`ksud soft-reboot`).
# ksud runs this from PID 1's mount namespace before `stop`, then replays the
# normal boot stages with the same kernel boot_id. Only KernelSU calls this
# stage; the router refuses to do anything for any other caller.
set +e
MODDIR="${0%/*}"
MODULE_DIR="$MODDIR"
export MODDIR MODULE_DIR

[ "${KSU:-}" = true ] || exit 0

CORE="$MODDIR/.luoshu-runtime/core/emulated-soft-reboot.sh"
[ -f "$CORE" ] || exit 0
exec sh "$CORE"
