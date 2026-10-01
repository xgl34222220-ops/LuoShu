#!/system/bin/sh
# Disposable VM only. Production mounts, confined to a private child namespace.
set -eu
mod="$1"
[ "$(getprop ro.kernel.qemu)" = 1 ]
[ "$(getprop ro.build.version.sdk)" = 36 ]
[ "$(id -u)" = 0 ]
[ "$(readlink /proc/self/ns/mnt)" != "$LUOSHU_PARENT_MOUNT_NAMESPACE" ]
printf '%s\n' '{"namespacePhase":"isolation","state":"starting"}'
export MODDIR="$mod" MODULE_DIR="$mod" CONFIG_DIR="$mod/config"
export LUOSHU_SELF_MOUNT_STATE_ROOT="$mod/state/self"
export LUOSHU_PRIVATE_STATE_ROOT="$mod/state/private"
export LUOSHU_UNIVERSAL_MOUNT_STATE_ROOT="$mod/state/universal"
# This experiment verifies this private namespace, never init/global visibility.
export LUOSHU_SELF_PID1_ROOT=/proc/self/root
export LUOSHU_SELF_MOUNT_COMMAND="$mod/observe-mount.sh"
export PYTHONHOME="$mod/common/python"
export PYTHONPATH="$mod/common:$PYTHONHOME/lib/python3.14:$PYTHONHOME/lib/python3.14/site-packages"
export LD_LIBRARY_PATH="$PYTHONHOME/lib:$PYTHONHOME/lib/python3.14/lib-dynload"
py="$PYTHONHOME/bin/luoshu-python"
"$py" "$mod/module_namespace_verify.py" "$mod" isolate
verify() { "$py" "$mod/module_namespace_verify.py" "$mod" "$1"; }
hook() { sh "$mod/common/universal_mount_runtime.sh" hook post-fs-data; }
rollback() { sh "$mod/common/universal_mount_runtime.sh" rollback; }
trap 'rollback >/dev/null 2>&1 || true' EXIT
verify before
hook
verify mounted
cp "$mod/state/self/mounts.list" "$mod/first-mounts.list"
hook
cmp -s "$mod/first-mounts.list" "$mod/state/self/mounts.list"
verify idempotent
rollback
verify restored
# A stale, nonempty lower cannot be removed. Fonts must remain unavailable,
# while a later real etc overlay must be unwound by the failed transaction.
mkdir -p "$mod/state/self/lower/system-fonts"
printf owned-sentinel > "$mod/state/self/lower/system-fonts/sentinel"
: > "$mod/mount-calls.jsonl"
if hook; then echo 'missing required assets accepted' >&2; exit 30; fi
test "$(cat "$mod/state/self/lower/system-fonts/sentinel")" = owned-sentinel
verify partial-failure
rm "$mod/state/self/lower/system-fonts/sentinel"
rmdir "$mod/state/self/lower/system-fonts"
# Corruption is rejected before invoking any mount command.
verify hide-asset
: > "$mod/mount-calls.jsonl"
if hook; then echo 'missing sealed asset accepted' >&2; exit 31; fi
verify integrity-failure
verify restore-asset
verify finished
