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
    verify before
    sh "$mod/common/universal_mount_runtime.sh" hook post-fs-data
    verify mounted
    ;;
 rollback)
    sh "$mod/common/universal_mount_runtime.sh" rollback
    verify restored
    verify finished
    ;;
 *) exit 2 ;;
esac
