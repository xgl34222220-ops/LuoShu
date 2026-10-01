#!/system/bin/sh
# Disposable API36 VM only. No namespace entry, policy/init change, or boot hook.
set -eu
mod="$1"; action="$2"
[ "$(getprop ro.kernel.qemu)" = 1 ]
[ "$(getprop ro.build.version.sdk)" = 36 ]
[ "$(id -u)" = 0 ]
[ "$(getenforce)" = Enforcing ]
[ "$(readlink /proc/self/ns/mnt)" = "$(readlink /proc/1/ns/mnt)" ]
export MODDIR="$mod" MODULE_DIR="$mod" CONFIG_DIR="$mod/config"
export LUOSHU_SELF_MOUNT_STATE_ROOT="$mod/state/self"
export LUOSHU_PRIVATE_STATE_ROOT="$mod/state/private"
export LUOSHU_UNIVERSAL_MOUNT_STATE_ROOT="$mod/state/universal"
export LUOSHU_SELF_PID1_ROOT=/proc/1/root
export LUOSHU_SELF_MOUNT_COMMAND="$mod/observe-mount.sh"
export PYTHONHOME="$mod/common/python"
export PYTHONPATH="$mod/common:$PYTHONHOME/lib/python3.14:$PYTHONHOME/lib/python3.14/site-packages"
export LD_LIBRARY_PATH="$PYTHONHOME/lib:$PYTHONHOME/lib/python3.14/lib-dynload"
py="$PYTHONHOME/bin/luoshu-python"
verify() { "$py" "$mod/module_namespace_verify.py" "$mod" "$1"; }
case "$action" in
 apply)
    if [ "${LUOSHU_STAGED_HOOK_TEST_APPROVED:-false}" = true ]; then
        export LUOSHU_UNIVERSAL_TEST_MANAGER=KernelSU
        expected_id=$(sed -n 's/^deploymentId=//p' "$mod/config/universal-font-next.conf")
        expected_digest=$(sed -n 's/^payloadDigest=//p' "$mod/config/universal-font-next.conf")
        [ -n "$expected_id" ] && [ -n "$expected_digest" ]
        sh "$mod/post-fs-data.sh"
        [ ! -e "$mod/config/universal-font-next.conf" ]
        grep -qx 'state=active' "$mod/config/universal-font-runtime.conf"
        [ "$(sed -n 's/^deploymentId=//p' "$mod/config/universal-font-runtime.conf")" = "$expected_id" ]
        [ "$(sed -n 's/^payloadDigest=//p' "$mod/config/universal-font-runtime.conf")" = "$expected_digest" ]
        # An early hook for the simulated manager must not publish any font.
        verify before
        sh "$mod/post-mount.sh"
        verify mounted
        printf 'STAGED_HOOKS next-to-live and deferred post-mount verified\n'
    else
        verify before
        sh "$mod/common/universal_mount_runtime.sh" hook post-fs-data
        verify mounted
    fi
    ;;
 rollback)
    sh "$mod/common/universal_mount_runtime.sh" rollback
    verify restored
    verify finished
    ;;
 *) exit 2 ;;
esac
