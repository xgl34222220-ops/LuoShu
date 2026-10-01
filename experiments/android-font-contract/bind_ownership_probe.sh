#!/system/bin/sh
# Real Android bind lifecycle, contained in a private disposable namespace.
set -eu
mod="$1"
[ "$(getprop ro.kernel.qemu)" = 1 ]
[ "$(getprop ro.build.version.sdk)" = 36 ]
[ "$(id -u)" = 0 ]
[ "$(readlink /proc/self/ns/mnt)" != "$LUOSHU_PARENT_MOUNT_NAMESPACE" ]
export PYTHONHOME="$mod/common/python"
export PYTHONPATH="$mod/common:$PYTHONHOME/lib/python3.14:$PYTHONHOME/lib/python3.14/site-packages"
export LD_LIBRARY_PATH="$PYTHONHOME/lib:$PYTHONHOME/lib/python3.14/lib-dynload"
export TMPDIR="$mod/bind-namespace"
mkdir "$TMPDIR"
"$PYTHONHOME/bin/luoshu-python" "$mod/module_namespace_verify.py" "$TMPDIR" isolate
sh "$mod/scripts/bind_ownership_namespace_test.sh" --inside
