#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# shellcheck disable=SC1090
. "$ROOT/common/mount_fast_sync.sh"

SRC="$TMP/source/system"
DST="$TMP/content/system"
mkdir -p "$SRC/fonts" "$SRC/etc"
dd if=/dev/zero of="$SRC/fonts/.anchor.font" bs=1M count=8 status=none
for name in MiSansVF.ttf Roboto-Regular.ttf GoogleSansText-Regular.ttf 100.ttf 400.ttf 700.ttf; do
    ln "$SRC/fonts/.anchor.font" "$SRC/fonts/$name"
done
printf '<familyset/>\n' > "$SRC/etc/fonts.xml"

luoshu_copy_tree_bounded "$SRC" "$DST"
test -s "$DST/fonts/MiSansVF.ttf"
test -s "$DST/etc/fonts.xml"

inode="$(stat -c '%d:%i' "$DST/fonts/.anchor.font")"
for name in MiSansVF.ttf Roboto-Regular.ttf GoogleSansText-Regular.ttf 100.ttf 400.ttf 700.ttf; do
    test "$(stat -c '%d:%i' "$DST/fonts/$name")" = "$inode"
done

# Source and mirror should also share the inode on the normal /data-style same-filesystem path.
test "$(stat -c '%d:%i' "$SRC/fonts/.anchor.font")" = "$inode"

echo 'mount_fast_sync_test: PASS'
