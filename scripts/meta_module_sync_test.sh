#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "${0%/*}/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

# Official meta-overlayfs: runtime changes must be written to the persistent ext4 content tree.
MODDIR="$TMP/modules/LuoShu"
MODULE_DIR="$MODDIR"
LUOSHU_META_TEST_ENGINE=meta-overlayfs
LUOSHU_META_TEST_ROOT="$TMP/meta-content"
export MODDIR MODULE_DIR LUOSHU_META_TEST_ENGINE LUOSHU_META_TEST_ROOT
mkdir -p "$MODDIR/common" "$MODDIR/system/fonts" "$MODDIR/my_product/fonts" "$LUOSHU_META_TEST_ROOT"
cp "$ROOT/common/mount_compat.sh" "$MODDIR/common/mount_compat.sh"
printf 'id=LuoShu\n' > "$MODDIR/module.prop"
printf 'font-one' > "$MODDIR/system/fonts/Test.ttf"
printf 'unsupported-partition' > "$MODDIR/my_product/fonts/Oplus.ttf"
. "$MODDIR/common/mount_compat.sh"

luoshu_sync_mount_payload Demo
[ "$(cat "$LUOSHU_META_TEST_ROOT/LuoShu/system/fonts/Test.ttf")" = font-one ]
[ ! -e "$LUOSHU_META_TEST_ROOT/LuoShu/my_product" ]
[ -s "$MODDIR/system/etc/luoshu/mount-probe.conf" ]
[ "$(sed -n 's/^state=//p' "$MODDIR/config/mount_compat.conf")" = prepared ]

printf 'font-two' > "$MODDIR/system/fonts/Test.ttf"
luoshu_sync_mount_payload Demo
[ "$(cat "$LUOSHU_META_TEST_ROOT/LuoShu/system/fonts/Test.ttf")" = font-two ]

# Mountify and Hybrid Mount read the canonical module tree directly; no guessed mirror is created.
rm -rf "$LUOSHU_META_TEST_ROOT/LuoShu"
LUOSHU_META_TEST_ENGINE=mountify
export LUOSHU_META_TEST_ENGINE
luoshu_sync_mount_payload Demo
[ ! -e "$LUOSHU_META_TEST_ROOT/LuoShu" ]
[ "$(sed -n 's/^detail=//p' "$MODDIR/config/mount_compat.conf")" = '当前引擎直接读取标准模块目录，等待重启验证' ]

LUOSHU_META_TEST_ENGINE=hybrid-mount
export LUOSHU_META_TEST_ENGINE
luoshu_sync_mount_payload Demo
[ ! -e "$LUOSHU_META_TEST_ROOT/LuoShu" ]

# skip_mount is an actual compatibility failure for KernelSU metamodules.
touch "$MODDIR/skip_mount"
if luoshu_sync_mount_payload Demo; then
    echo 'skip_mount was not rejected' >&2
    exit 1
fi
rm -f "$MODDIR/skip_mount"

# After reboot, the visible system probe must match the expected transaction probe.
VISIBLE="$TMP/visible-probe.conf"
cp "$MODDIR/system/etc/luoshu/mount-probe.conf" "$VISIBLE"
LUOSHU_VISIBLE_PROBE="$VISIBLE"
export LUOSHU_VISIBLE_PROBE
luoshu_mount_verify_active Demo
[ "$(sed -n 's/^state=//p' "$MODDIR/config/mount_compat.conf")" = verified ]
printf 'nonce=wrong\n' > "$VISIBLE"
if luoshu_mount_verify_active Demo; then
    echo 'mismatched mount probe was accepted' >&2
    exit 1
fi

printf 'metamodule adapter tests passed.\n'
