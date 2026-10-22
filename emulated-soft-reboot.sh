#!/system/bin/sh
# KernelSU emulated-soft-reboot stage router (`ksud soft-reboot`).
# ksud runs this in PID 1's mount namespace before `stop`, with a 5 s wait
# budget, then re-runs post-fs-data / post-mount / service / boot-completed
# under the SAME kernel boot_id. Only LuoShu's own journaled mounts are
# released here; the regular post-mount transaction rebuilds them afterwards.
# Other root managers never call this stage and keep the current behaviour.
# Stage hook idea from 字域 Ziyu v1.4.8 (GPL-3.0-only), see THIRD_PARTY_NOTICES.md.
set +e
MODDIR="${0%/*}"
MODULE_DIR="$MODDIR"
export MODDIR MODULE_DIR
CORE="$MODDIR/.luoshu-runtime/core/emulated-soft-reboot.sh"
[ -f "$CORE" ] || exit 0
exec sh "$CORE"
