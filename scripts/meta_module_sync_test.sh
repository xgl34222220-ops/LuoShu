#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "${0%/*}/.." && pwd)
SCRIPT="$ROOT/common/mount_compat.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MODDIR="$TMP/modules/LuoShu"
MODULE_DIR="$MODDIR"
LUOSHU_META_TEST_ROOT="$TMP/meta-content"
export MODDIR MODULE_DIR LUOSHU_META_TEST_ROOT
mkdir -p \
  "$MODDIR/common" \
  "$MODDIR/system/fonts" \
  "$MODDIR/my_product/fonts" \
  "$LUOSHU_META_TEST_ROOT"
cp "$SCRIPT" "$MODDIR/common/mount_compat.sh"
printf 'id=LuoShu\n' > "$MODDIR/module.prop"
printf 'font-one' > "$MODDIR/system/fonts/Test.ttf"
printf 'unsupported' > "$MODDIR/my_product/fonts/Oplus.ttf"
. "$MODDIR/common/mount_compat.sh"

# Official meta-overlayfs keeps a second persistent content tree. LuoShu mirrors
# supported partitions there and records unsupported OEM partitions without
# invalidating the otherwise usable payload.
LUOSHU_META_TEST_ENGINE=meta-overlayfs
export LUOSHU_META_TEST_ENGINE
luoshu_sync_mount_payload Demo
[ "$(cat "$LUOSHU_META_TEST_ROOT/LuoShu/system/fonts/Test.ttf")" = font-one ]
[ ! -e "$LUOSHU_META_TEST_ROOT/LuoShu/my_product" ]
[ -s "$MODDIR/config/mount-probes-expected.conf" ]
[ "$(sed -n 's/^unsupportedPartitions=//p' "$MODDIR/config/mount_compat.conf")" = my_product ]

printf 'font-two' > "$MODDIR/system/fonts/Test.ttf"
luoshu_sync_mount_payload Demo
[ "$(cat "$LUOSHU_META_TEST_ROOT/LuoShu/system/fonts/Test.ttf")" = font-two ]

# Mountify, Magic Mount RC/RS and Hybrid Mount all consume the canonical module
# tree directly. Compatibility must therefore remain passive and non-invasive.
for engine in mountify magic-mount magic-mount-rc magic-mount-rs hybrid-mount; do
    rm -rf "$LUOSHU_META_TEST_ROOT/LuoShu"
    touch "$MODDIR/skip_mount" "$MODDIR/mount_error"
    LUOSHU_META_TEST_ENGINE="$engine"
    export LUOSHU_META_TEST_ENGINE
    luoshu_sync_mount_payload Demo
    [ ! -e "$LUOSHU_META_TEST_ROOT/LuoShu" ]
    [ -e "$MODDIR/skip_mount" ]
    [ -e "$MODDIR/mount_error" ]
    [ ! -e "$MODDIR/config/mount-probes-expected.conf" ]
    luoshu_mount_verify_active Demo
    [ "$(sed -n 's/^state=//p' "$MODDIR/config/mount_compat.conf")" = verified ]
    rm -f "$MODDIR/skip_mount" "$MODDIR/mount_error"
done

# Only the true dual-directory engine treats skip_mount as a hard failure.
touch "$MODDIR/skip_mount"
LUOSHU_META_TEST_ENGINE=meta-overlayfs
export LUOSHU_META_TEST_ENGINE
if luoshu_sync_mount_payload Demo; then
    echo 'skip_mount was not rejected for meta-overlayfs' >&2
    exit 1
fi
rm -f "$MODDIR/skip_mount"

printf 'non-invasive metamodule adapter tests passed.\n'
