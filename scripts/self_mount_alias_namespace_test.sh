#!/bin/sh
# Real Linux mounts inside a disposable user/mount namespace; no Android claims.
set -eu
if [ "${1:-}" != --inside ]; then
    if ! command -v unshare >/dev/null 2>&1 || ! unshare -Urnm true 2>/dev/null; then
        [ "${LUOSHU_REQUIRE_MOUNT_NAMESPACE_TEST:-0}" != 1 ] || exit 1
        echo 'self_mount_alias_namespace_test: SKIP (user mount namespace unavailable)'
        exit 0
    fi
    exec unshare -Urnm sh "$0" --inside
fi
[ "$(readlink /proc/self/ns/mnt)" != "$(readlink /proc/1/ns/mnt)" ] || exit 1
ROOT=$(CDPATH= cd -- "${0%/*}/.." && pwd)
TMP=$(mktemp -d)
trap 'umount "$TMP/visible/system/fonts" 2>/dev/null || true; umount "$TMP/visible/system/fonts/Canonical.ttf" 2>/dev/null || true; rm -rf "$TMP"' EXIT
mkdir -p "$TMP/payload/system/fonts" "$TMP/payload/product/fonts" "$TMP/visible/system/fonts" "$TMP/visible/product/fonts" "$TMP/state"
printf canonical-output > "$TMP/payload/system/fonts/Canonical.ttf"
printf different-output > "$TMP/payload/product/fonts/Alias.ttf"
printf stock-output > "$TMP/visible/system/fonts/Canonical.ttf"
ln -s ../../system/fonts/Canonical.ttf "$TMP/visible/product/fonts/Alias.ttf"
_luoshu_self_state_root() { printf '%s\n' "$TMP/state"; }
_luoshu_self_log() { printf '%s\n' "$*" >> "$TMP/log"; }
_luoshu_mount_cmd() { mount "$@"; }
_luoshu_umount_cmd() { umount "$@"; }
. "$ROOT/common/mount_self_atomic.sh"
. "$ROOT/common/mount_self_backend.sh"
set -e
_lsme_state_root="$TMP/state"
_lsme_mount_list="$TMP/state/mounts.list"
: > "$_lsme_mount_list"
_lsme_failed=''
printf '%s|%s|bind\n' "$TMP/payload/system/fonts" "$TMP/visible/system/fonts" "$TMP/payload/product/fonts" "$TMP/visible/product/fonts" > "$TMP/plan"
if _luoshu_atomic_finish_plan "$TMP/plan" "$TMP/payload" any; then
    echo 'conflicting physical aliases were accepted' >&2; exit 1
fi
test ! -s "$_lsme_mount_list"
test "$(cat "$TMP/visible/system/fonts/Canonical.ttf")" = stock-output
# Identical bytes can share one physical bind across components.
cp "$TMP/payload/system/fonts/Canonical.ttf" "$TMP/payload/product/fonts/Alias.ttf"
_lsme_failed=''
_luoshu_atomic_finish_plan "$TMP/plan" "$TMP/payload" any
test "$(wc -l < "$_lsme_mount_list" | tr -d ' ')" = 1
cmp "$TMP/payload/product/fonts/Alias.ttf" "$TMP/visible/product/fonts/Alias.ttf"
_luoshu_atomic_rollback "$_lsme_mount_list"
# An actual overlay supplies independent regular files over a ROM alias. The
# same logical names with distinct content must remain supported in this mode.
printf different-output > "$TMP/payload/system/fonts/Alias.ttf"
ln -s Canonical.ttf "$TMP/visible/system/fonts/Alias.ttf"
# Match production: a read-only union of payload plus original directories.
# This also avoids requiring the workspace filesystem to support an upperdir.
_luoshu_overlay_mount_dir "$TMP/payload/system/fonts" "$TMP/visible/system/fonts" system-fonts
[ ! -L "$TMP/visible/system/fonts/Alias.ttf" ]
printf '%s|%s|overlay\n' "$TMP/payload/system/fonts" "$TMP/visible/system/fonts" > "$TMP/overlay-plan"
_lsme_failed=''
_luoshu_atomic_finish_plan "$TMP/overlay-plan" "$TMP/payload" any
cmp "$TMP/payload/system/fonts/Alias.ttf" "$TMP/visible/system/fonts/Alias.ttf"
# A later bind through another partition must not invalidate the earlier
# overlay's canonical bytes. Detect this before binding and rollback the overlay.
printf product-conflict > "$TMP/payload/product/fonts/Alias.ttf"
printf '%s|%s|overlay\n' "$TMP/payload/system/fonts" "$TMP/visible/system/fonts" > "$TMP/mixed-plan"
printf '%s|%s|bind\n' "$TMP/payload/product/fonts" "$TMP/visible/product/fonts" >> "$TMP/mixed-plan"
_lsme_failed=''
if _luoshu_atomic_finish_plan "$TMP/mixed-plan" "$TMP/payload" any; then
    echo 'cross-partition bind invalidated an overlay contract' >&2; exit 1
fi
_luoshu_atomic_rollback "$_lsme_mount_list"
test "$(cat "$TMP/visible/system/fonts/Canonical.ttf")" = stock-output
printf 'self_mount_alias_namespace_test: PASS (real bind and overlay)\n'
