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
cp "$ROOT/common/mount_compat_base.sh" "$MODDIR/common/mount_compat_base.sh"
cp "$ROOT/common/mount_self_fallback.sh" "$MODDIR/common/mount_self_fallback.sh"
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
grep -q '^system|' "$MODDIR/config/mount-probes-expected.conf"
! grep -q '^my_product|' "$MODDIR/config/mount-probes-expected.conf"

LUOSHU_META_TEST_ENGINE=hybrid-mount
export LUOSHU_META_TEST_ENGINE
luoshu_sync_mount_payload Demo
[ ! -e "$LUOSHU_META_TEST_ROOT/LuoShu" ]

# Magic Mount reads the canonical module tree. An explicit font transaction only recovers
# LuoShu-local stale markers and never creates a guessed mirror or rewrites external config.
touch "$MODDIR/skip_mount" "$MODDIR/mount_error"
LUOSHU_META_TEST_ENGINE=magic-mount
export LUOSHU_META_TEST_ENGINE
luoshu_sync_mount_payload Demo
[ ! -e "$MODDIR/skip_mount" ]
[ ! -e "$MODDIR/mount_error" ]
[ ! -e "$LUOSHU_META_TEST_ROOT/LuoShu" ]
[ "$(sed -n 's/^engine=//p' "$MODDIR/config/mount_compat.conf")" = magic-mount ]

# skip_mount remains an actual compatibility failure for a true dual-directory metamodule.
touch "$MODDIR/skip_mount"
LUOSHU_META_TEST_ENGINE=meta-overlayfs
export LUOSHU_META_TEST_ENGINE
if luoshu_sync_mount_payload Demo; then
    echo 'skip_mount was not rejected' >&2
    exit 1
fi
rm -f "$MODDIR/skip_mount"

# After reboot, every dual-directory partition probe must match the expected transaction probe.
VISIBLE_ROOT="$TMP/visible"
mkdir -p "$VISIBLE_ROOT/system/etc/luoshu"
cp "$MODDIR/system/etc/luoshu/mount-probe.conf" "$VISIBLE_ROOT/system/etc/luoshu/mount-probe.conf"
LUOSHU_VISIBLE_PROBE_ROOT="$VISIBLE_ROOT"
export LUOSHU_VISIBLE_PROBE_ROOT
luoshu_mount_verify_active Demo
[ "$(sed -n 's/^state=//p' "$MODDIR/config/mount_compat.conf")" = verified ]
printf 'nonce=wrong\n' > "$VISIBLE_ROOT/system/etc/luoshu/mount-probe.conf"
if luoshu_mount_verify_active Demo; then
    echo 'mismatched mount probe was accepted' >&2
    exit 1
fi

printf 'metamodule adapter tests passed.\n'
