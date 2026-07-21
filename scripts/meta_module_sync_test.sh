#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "${0%/*}/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MODDIR="$TMP/modules/LuoShu"
MODULE_DIR="$MODDIR"
LUOSHU_META_TEST_ROOT="$TMP/meta"
export MODDIR MODULE_DIR LUOSHU_META_TEST_ROOT
mkdir -p "$MODDIR/common" "$MODDIR/system/fonts" "$LUOSHU_META_TEST_ROOT"
cp "$ROOT/common/mount_compat.sh" "$MODDIR/common/mount_compat.sh"
printf 'id=LuoShu\n' > "$MODDIR/module.prop"
printf 'first-payload' > "$MODDIR/system/fonts/Test.ttf"
. "$MODDIR/common/mount_compat.sh"

luoshu_sync_mount_payload
DEST="$LUOSHU_META_TEST_ROOT/LuoShu/system/fonts/Test.ttf"
[ "$(cat "$DEST")" = first-payload ]
[ -s "$LUOSHU_META_TEST_ROOT/LuoShu/system/.luoshu-part-fingerprint" ]

luoshu_sync_mount_payload
[ "$(sed -n 's/^skipped=//p' "$MODDIR/config/mount_compat.conf")" -ge 1 ]

printf 'second-payload' > "$MODDIR/system/fonts/Test.ttf"
luoshu_sync_mount_payload
[ "$(cat "$DEST")" = second-payload ]
[ "$(sed -n 's/^failed=//p' "$MODDIR/config/mount_compat.conf")" = 0 ]

echo 'meta-module sync tests passed'
