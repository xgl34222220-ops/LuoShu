#!/bin/sh
set -eu
if [ "${1:-}" != --inside ]; then
    if ! unshare -Urnm true 2>/dev/null; then
        [ "${LUOSHU_REQUIRE_MOUNT_NAMESPACE_TEST:-0}" != 1 ] || exit 1
        echo 'bind_ownership_namespace_test: SKIP (namespace unavailable)';exit 0
    fi
    unshare -Urnm sh "$0" --inside
    exit 0
fi
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
r=$(mktemp -d)
mkdir -p "$r/source" "$r/target" "$r/state"
printf underlying > "$r/target/font.ttf"
printf original > "$r/original.ttf"
printf selected > "$r/source/font.ttf"
printf foreign > "$r/foreign.ttf"
mount --bind "$r/original.ttf" "$r/target/font.ttf"
_luoshu_self_state_root() { echo "$r/state"; }
_luoshu_mount_cmd() { mount "$@"; }
_luoshu_umount_cmd() { umount "$@"; }
_luoshu_self_log() { :; }
. "$ROOT/common/mount_self_atomic.sh"
. "$ROOT/common/mount_self_backend.sh"
set -eu
_lsme_mount_list="$r/state/mounts.list"
: > "$_lsme_mount_list"
baseline=$(_luoshu_visible_mount_id "$r/target/font.ttf")
_luoshu_atomic_bind_tree "$r/source" "$r/target"
test "$(cat "$r/target/font.ttf")" = selected
mount --bind "$r/foreign.ttf" "$r/target/font.ttf"
foreign=$(_luoshu_visible_mount_id "$r/target/font.ttf")
if _luoshu_atomic_rollback "$_lsme_mount_list"; then exit 1; fi
test "$(_luoshu_visible_mount_id "$r/target/font.ttf")" = "$foreign"
umount "$r/target/font.ttf"
_luoshu_atomic_rollback "$_lsme_mount_list"
_luoshu_atomic_rollback "$_lsme_mount_list"
test "$(_luoshu_visible_mount_id "$r/target/font.ttf")" = "$baseline"
test "$(cat "$r/target/font.ttf")" = original
# Kernel bind completed, but caller never got to append the journal.
_luoshu_mount_cmd() { mount "$@" || return $?; sh -c 'kill -KILL "$PPID"'; }
if _luoshu_atomic_bind_tree "$r/source" "$r/target"; then exit 1; fi
test "$(cat "$r/target/font.ttf")" = selected
_luoshu_atomic_rollback "$_lsme_mount_list"
test "$(_luoshu_visible_mount_id "$r/target/font.ttf")" = "$baseline"
# A legacy bare-path journal cannot authorize unmounting the original.
printf '%s\n' "$r/target/font.ttf" > "$_lsme_mount_list"
if _luoshu_atomic_rollback "$_lsme_mount_list"; then exit 1; fi
if _luoshu_atomic_rollback "$_lsme_mount_list"; then exit 1; fi
test "$(_luoshu_visible_mount_id "$r/target/font.ttf")" = "$baseline"
: > "$_lsme_mount_list"
umount "$r/target/font.ttf"
test "$(cat "$r/target/font.ttf")" = underlying
# A logical symlink must record and restore the kernel's canonical target.
_luoshu_mount_cmd() { mount "$@"; }
mkdir -p "$r/logical" "$r/alias-source"
ln -s ../target/font.ttf "$r/logical/Alias.ttf"
printf alias-selected > "$r/alias-source/Alias.ttf"
mount --bind "$r/original.ttf" "$r/target/font.ttf"
baseline=$(_luoshu_visible_mount_id "$r/target/font.ttf")
_luoshu_atomic_bind_tree "$r/alias-source" "$r/logical"
test "$(cat "$r/logical/Alias.ttf")" = alias-selected
_luoshu_atomic_rollback "$_lsme_mount_list"
_luoshu_atomic_rollback "$_lsme_mount_list"
test "$(_luoshu_visible_mount_id "$r/logical/Alias.ttf")" = "$baseline"
test "$(cat "$r/logical/Alias.ttf")" = original
umount "$r/target/font.ttf"
# Directory alias + overlay + child bind must unwind child before parent.
mkdir -p "$r/overlay-source" "$r/child-source"
printf overlay-selected > "$r/overlay-source/font.ttf"
printf child-selected > "$r/child-source/font.ttf"
ln -s target "$r/target-alias"
baseline=$(_luoshu_visible_mount_id "$r/target")
LUOSHU_REQUIRED_PAYLOAD_FILES=1
_luoshu_overlay_mount_dir "$r/overlay-source" "$r/target-alias" alias-fixture
_luoshu_atomic_bind_tree "$r/child-source" "$r/target-alias"
test "$(cat "$r/target-alias/font.ttf")" = child-selected
_luoshu_atomic_rollback "$_lsme_mount_list"
_luoshu_atomic_rollback "$_lsme_mount_list"
test ! -s "$_lsme_mount_list"
test "$(_luoshu_visible_mount_id "$r/target-alias")" = "$baseline"
test "$(cat "$r/target/font.ttf")" = underlying
rm -rf "$r"
echo 'bind_ownership_namespace_test: PASS (original bind, foreign top, cancellation, repeated rollback, legacy rejection, symlink target, overlay-child dependency)'
