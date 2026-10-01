#!/bin/sh
set -eu
if [ "${1:-}" != --inside ]; then
    if ! unshare -Urnm true 2>/dev/null; then
        [ "${LUOSHU_REQUIRE_MOUNT_NAMESPACE_TEST:-0}" != 1 ] || exit 1
        echo 'overlay_memory_layer_test: SKIP (namespace unavailable)'; exit 0
    fi
    unshare -Urnm sh "$0" --inside
    exit 0
fi
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
r=$(mktemp -d)
mkdir -p "$r/source" "$r/target" "$r/state"
mount -t tmpfs stock-rom "$r/target"
original_mount=$(awk -v p="$r/target" '$5==p{id=$1}END{print id}' /proc/self/mountinfo)
printf selected > "$r/source/new.ttf"
printf original > "$r/target/old.ttf"
_luoshu_self_state_root() { printf '%s/state\n' "$r"; }
_luoshu_mount_cmd() {
    # Reproduce a casefold-capable source refusal. Every other mount is real.
    case " $* " in *"lowerdir=$r/source:"*) return 1 ;; esac
    mount "$@"
}
_luoshu_umount_cmd() { umount "$@"; }
. "$ROOT/common/mount_self_atomic.sh"
. "$ROOT/common/mount_self_backend.sh"
set -eu
_lsme_mount_list="$r/state/mounts.list"
LUOSHU_REQUIRED_PAYLOAD_FILES=1
_luoshu_overlay_mount_dir "$r/source" "$r/target" system-fonts
printf '%s\n' "$r/target" >> "$_lsme_mount_list"
test "$(cat "$r/target/new.ttf")" = selected
test "$(cat "$r/target/old.ttf")" = original
memory="$r/state/memory-layers/system-fonts"
awk -v p="$memory" '$5==p&&$6~/^ro(,|$)/{ok=1}END{exit !ok}' /proc/self/mountinfo
# A busy failed unmount preserves all bytes and journal; never recursive rm.
_luoshu_umount_cmd() { return 1; }
if _luoshu_atomic_rollback "$_lsme_mount_list"; then exit 1; fi
test "$(cat "$memory/new.ttf")" = selected
test "$(cat "$r/target/old.ttf")" = original
test -s "$_lsme_mount_list"
_luoshu_umount_cmd() { umount "$@"; }
# A foreign new top layer must never be mistaken for our lower overlay.
mount -t tmpfs foreign-layer "$r/target"
foreign_mount=$(awk -v p="$r/target" '$5==p{id=$1}END{print id}' /proc/self/mountinfo)
if _luoshu_atomic_rollback "$_lsme_mount_list"; then exit 1; fi
test "$(awk -v p="$r/target" '$5==p{id=$1}END{print id}' /proc/self/mountinfo)" = "$foreign_mount"
umount "$r/target"
_luoshu_atomic_rollback "$_lsme_mount_list"
_luoshu_atomic_rollback "$_lsme_mount_list"
test "$(awk -v p="$r/target" '$5==p{id=$1}END{print id}' /proc/self/mountinfo)" = "$original_mount"
test ! -e "$r/target/new.ttf"
test "$(cat "$r/target/old.ttf")" = original
test ! -e "$r/state/memory-layer-kb"
# A corrupted copy must fail before readonly publication and remain cleanable.
cp() { command cp "$@"; printf corrupted > "$memory/new.ttf"; }
if _luoshu_overlay_memory_layer "$r/source" "$memory" "$r/state"; then exit 1; fi
unset -f cp
_luoshu_atomic_rollback "$_lsme_mount_list"
test ! -e "$memory"
# Kill the helper after a real successful overlay but before journal append.
# Its persisted intent must recover only that exact owned overlay.
_luoshu_mount_cmd() {
    mount "$@" || return $?
    if [ "${1:-}" = -t ] && [ "${2:-}" = overlay ]; then
        sh -c 'kill -KILL "$PPID"'
    fi
}
LUOSHU_REQUIRED_PAYLOAD_FILES=0
if _luoshu_overlay_mount_dir "$r/source" "$r/target" system-fonts; then exit 1; fi
test "$(cat "$r/target/new.ttf")" = selected
test -f "$r/state/overlay-intents/system-fonts"
_luoshu_atomic_rollback "$_lsme_mount_list"
test ! -e "$r/target/new.ttf"
test "$(cat "$r/target/old.ttf")" = original
test ! -f "$r/state/overlay-intents/system-fonts"
_luoshu_mount_cmd() { mount "$@"; }
LUOSHU_REQUIRED_PAYLOAD_FILES=1
# A declared budget already consumed must refuse before any new memory mount.
printf 262144 > "$r/state/memory-layer-kb"
if _luoshu_overlay_memory_layer "$r/source" "$memory" "$r/state"; then exit 1; fi
test ! -e "$memory"
rm "$r/state/memory-layer-kb"
ln -s /etc/passwd "$r/source/unsafe"
if _luoshu_overlay_memory_layer "$r/source" "$memory" "$r/state"; then exit 1; fi
rm "$r/source/unsafe"
mkfifo "$r/source/special"
if _luoshu_overlay_memory_layer "$r/source" "$memory" "$r/state"; then exit 1; fi
rm "$r/source/special"
find() { return 1; }
if _luoshu_overlay_memory_layer "$r/source" "$memory" "$r/state"; then exit 1; fi
unset -f find
LUOSHU_REQUIRED_PAYLOAD_FILES=0
if _luoshu_overlay_memory_layer "$r/source" "$memory" "$r/state"; then exit 1; fi
test "$(awk -v p="$r/target" '$5==p{id=$1}END{print id}' /proc/self/mountinfo)" = "$original_mount"
umount "$r/target"
if awk -v p="$r/" 'index($5,p)==1{ok=1}END{exit !ok}' /proc/self/mountinfo; then exit 1; fi
rm -rf "$r"
echo 'overlay_memory_layer_test: PASS (real tmpfs+overlay, readonly, failed-unmount retention, rollback, budget and symlink guards)'
