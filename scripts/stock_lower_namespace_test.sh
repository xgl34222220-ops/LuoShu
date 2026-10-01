#!/bin/sh
# Actual Linux bind/overlay proof; Android evidence remains a separate gate.
set -eu
if [ "${1:-}" != --inside ]; then
    if ! command -v unshare >/dev/null 2>&1 || ! unshare -Urnm true 2>/dev/null; then
        [ "${LUOSHU_REQUIRE_MOUNT_NAMESPACE_TEST:-0}" != 1 ] || exit 1
        echo 'stock_lower_namespace_test: SKIP (namespace unavailable)'
        exit 0
    fi
    LUOSHU_LOWER_TEST_TOYBOX= unshare -Urnm sh "$0" --inside
    toybox="${LUOSHU_LOWER_TEST_TOYBOX:-$(command -v toybox || true)}"
    if [ -n "$toybox" ]; then
        LUOSHU_LOWER_TEST_TOYBOX="$toybox" unshare -Urnm sh "$0" --inside
    else
        echo 'stock_lower_namespace_test: Toybox companion unavailable (GNU kernel path tested)'
    fi
    exit 0
fi
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
r=$(mktemp -d)
mkdir -p "$r/source" "$r/target" "$r/state"
printf original > "$r/target/Original.ttf"
printf selected > "$r/source/Selected.ttf"
_luoshu_self_state_root() { printf '%s/state\n' "$r"; }
_real_mount() { if [ -n "${LUOSHU_LOWER_TEST_TOYBOX:-}" ]; then "$LUOSHU_LOWER_TEST_TOYBOX" mount "$@"; else mount "$@"; fi; }
_real_umount() { if [ -n "${LUOSHU_LOWER_TEST_TOYBOX:-}" ]; then "$LUOSHU_LOWER_TEST_TOYBOX" umount "$@"; else umount "$@"; fi; }
_luoshu_mount_cmd() { _real_mount "$@"; }
_luoshu_umount_cmd() { _real_umount "$@"; }
. "$ROOT/common/mount_self_atomic.sh"
. "${BACKEND_SCRIPT:-$ROOT/common/mount_self_backend.sh}"
set -eu
_lsme_mount_list="$r/mounts.list"
_luoshu_capture_lower_dir "$r/target" system-fonts
lower="$r/state/lower/system-fonts"
# Simulate a failed unmount while the real bind is still attached.
_luoshu_umount_cmd() { return 1; }
if _luoshu_prepare_lower_mountpoint "$lower"; then echo 'busy lower was reused' >&2; exit 1; fi
test "$(cat "$lower/Original.ttf")" = original
test "$(cat "$r/target/Original.ttf")" = original
_luoshu_umount_cmd() { _real_umount "$@"; }
_luoshu_overlay_mount_dir "$r/source" "$r/target" system-fonts
printf '%s\n' "$r/target" >> "$_lsme_mount_list"
test "$(cat "$r/target/Selected.ttf")" = selected
test "$(cat "$r/target/Original.ttf")" = original
awk -v p="$r/target" '$5==p && $6 ~ /(^|,)ro(,|$)/ {ok=1} END {exit !ok}' /proc/self/mountinfo
awk -v p="$lower" '$5==p {found=1;for(i=7;i<=NF&&$i!="-";i++)if($i ~ /^(shared|master):/)bad=1} END {exit !found||bad}' /proc/self/mountinfo
_luoshu_atomic_rollback "$_lsme_mount_list"
test ! -e "$r/target/Selected.ttf"
test "$(cat "$r/target/Original.ttf")" = original
if awk -v p="$r/" 'index($5,p)==1{found=1} END{exit !found}' /proc/self/mountinfo; then echo 'test mount leaked' >&2; exit 1; fi
rm -rf "$r"
echo "stock_lower_namespace_test: PASS (real lower, private propagation, read-only overlay, rollback; backend=${LUOSHU_LOWER_TEST_TOYBOX:-system-mount})"
