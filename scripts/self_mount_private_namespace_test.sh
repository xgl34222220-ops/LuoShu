#!/bin/sh
# Prove fallback syntax and kernel isolation without requiring an Android device.
set -eu
if [ "${1:-}" != --inside ]; then
    if ! command -v unshare >/dev/null 2>&1 || ! unshare -Urnm true 2>/dev/null; then
        [ "${LUOSHU_REQUIRE_MOUNT_NAMESPACE_TEST:-0}" != 1 ] || exit 1
        echo 'self_mount_private_namespace_test: SKIP (namespace unavailable)'
        exit 0
    fi
    exec unshare -Urnm sh "$0" --inside
fi
ROOT=$(CDPATH= cd -- "${0%/*}/.." && pwd)
r=$(mktemp -d)
trap 'umount "$r/visible/system/fonts" 2>/dev/null || true; umount "$r/state/lower/system-fonts" 2>/dev/null || true; umount "$r/point" 2>/dev/null || true; rm -rf "$r"' EXIT INT TERM
mkdir -p "$r/source" "$r/point" "$r/state"
printf stock > "$r/source/Stock.ttf"
_luoshu_self_log() { printf '%s\n' "$*" >> "$r/log"; }
_luoshu_umount_cmd() { umount "$@"; }
. "$ROOT/common/mount_self_atomic.sh"
. "$ROOT/common/mount_self_backend.sh"
set -eu
_lsme_mount_list="$r/state/mounts.list"
_luoshu_mount_cmd() {
    # Model a mount implementation rejecting the legacy spelling, but perform
    # the bind and supported private spelling with actual kernel mounts.
    if [ "$1" = -o ] && [ "$2" = private ]; then
        printf 'Invalid argument\n' >&2; return 32
    fi
    mount "$@"
}
_luoshu_bind_private_lower "$r/source" "$r/point"
_luoshu_mount_is_private "$r/point"
grep -q 'stage=private-option .*result=failed' "$r/log"
grep -q 'stage=private-long-option .*result=mounted' "$r/log"
test "$(cat "$r/point/Stock.ttf")" = stock
# A lying command returning zero may not leave a shared lower accepted.
mount --make-shared "$r/point"
if _luoshu_mount_is_private "$r/point"; then echo 'shared mount accepted' >&2; exit 1; fi
_luoshu_mount_cmd() { return 0; }
if _luoshu_make_private "$r/point"; then echo 'no-op private command accepted' >&2; exit 1; fi
# The equivalent long spelling must actually remove propagation peers.
_luoshu_mount_cmd() {
    if [ "$1" = -o ] && [ "$2" = private ]; then return 32; fi
    mount "$@"
}
_luoshu_make_private "$r/point"
_luoshu_mount_is_private "$r/point"
umount "$r/point"
# If both spellings are denied, cleanup the captured lower and report failure.
_luoshu_mount_cmd() {
    if [ "$1" = --make-private ] || { [ "$1" = -o ] && [ "$2" = private ]; }; then return 1; fi
    mount "$@"
}
if _luoshu_bind_private_lower "$r/source" "$r/point"; then echo 'unproven lower accepted' >&2; exit 1; fi
! awk -v p="$r/point" '$5==p{found=1}END{exit !found}' /proc/self/mountinfo
test "$(cat "$r/source/Stock.ttf")" = stock
# A preserved payload may intentionally have different bytes for two ROM names
# that are symlink aliases. A working directory overlay must keep both roles;
# falling back to a bind would collapse them into one terminal and must fail.
mkdir -p "$r/payload/system/fonts" "$r/visible/system/fonts"
printf canonical-selected > "$r/payload/system/fonts/CanonicalCJK.ttf"
printf alias-selected > "$r/payload/system/fonts/AliasCJK.ttf"
printf stock > "$r/visible/system/fonts/CanonicalCJK.ttf"
ln -s CanonicalCJK.ttf "$r/visible/system/fonts/AliasCJK.ttf"
_luoshu_self_state_root() { printf '%s\n' "$r/state"; }
_luoshu_mount_cmd() {
    if [ "$1" = -o ] && [ "$2" = private ]; then return 32; fi
    mount "$@"
}
: > "$_lsme_mount_list"
_luoshu_overlay_mount_dir "$r/payload/system/fonts" "$r/visible/system/fonts" system-fonts
_lsme_state_root="$r/state"
_lsme_failed=''
printf '%s|%s|overlay\n' "$r/payload/system/fonts" "$r/visible/system/fonts" > "$r/plan"
_luoshu_atomic_finish_plan "$r/plan" "$r/payload" system
cmp "$r/payload/system/fonts/CanonicalCJK.ttf" "$r/visible/system/fonts/CanonicalCJK.ttf"
cmp "$r/payload/system/fonts/AliasCJK.ttf" "$r/visible/system/fonts/AliasCJK.ttf"
test ! -L "$r/visible/system/fonts/AliasCJK.ttf"
_luoshu_atomic_rollback "$_lsme_mount_list"
test -L "$r/visible/system/fonts/AliasCJK.ttf"
test "$(cat "$r/visible/system/fonts/CanonicalCJK.ttf")" = stock
echo 'self_mount_private_namespace_test: PASS (fallback, propagation proof, denial cleanup, preserved alias roles)'
