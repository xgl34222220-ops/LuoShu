#!/system/bin/sh
# Compatibility layer retained for release payload stability.
#
# mount_self_atomic.sh is the single self-mount implementation. It resolves
# _lfrp_payload_root at call time, after font_runtime_policy.sh has exposed the
# canonical private tree. Do not redefine luoshu_self_mount_ensure here: a stale
# copy in this final-loaded file previously overrode the corrected atomic policy
# and made a missing optional system_ext/fonts target fatal on KernelSU.
set +e

type _lfrp_payload_root >/dev/null 2>&1 || return 0 2>/dev/null || exit 0
type _luoshu_atomic_manifest >/dev/null 2>&1 || return 0 2>/dev/null || exit 0
