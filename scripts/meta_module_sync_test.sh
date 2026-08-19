#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "${0%/*}/.." && pwd)
. "$ROOT/scripts/assert.sh"
CASE='meta 模块同步'
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

# Official meta-overlayfs: runtime changes must be written to the persistent ext4 content tree.
MODDIR="$TMP/modules/LuoShu"
MODULE_DIR="$MODDIR"
LUOSHU_META_TEST_ENGINE=meta-overlayfs
LUOSHU_META_TEST_ROOT="$TMP/meta-content"
export MODDIR MODULE_DIR LUOSHU_META_TEST_ENGINE LUOSHU_META_TEST_ROOT
mkdir -p "$MODDIR/common" "$MODDIR/system/fonts" "$LUOSHU_META_TEST_ROOT"
cp "$ROOT/common/mount_compat.sh" "$MODDIR/common/mount_compat.sh"
cp "$ROOT/common/mount_compat_base.sh" "$MODDIR/common/mount_compat_base.sh"
cp "$ROOT/common/mount_self_fallback.sh" "$MODDIR/common/mount_self_fallback.sh"
cp "$ROOT/common/mount_compat_policy.sh" "$MODDIR/common/mount_compat_policy.sh"
printf 'id=LuoShu\n' > "$MODDIR/module.prop"
printf 'font-one' > "$MODDIR/system/fonts/Test.ttf"
. "$MODDIR/common/mount_compat.sh"

luoshu_sync_mount_payload Demo
[ "$(cat "$LUOSHU_META_TEST_ROOT/LuoShu/system/fonts/Test.ttf")" = font-one ]
[ -s "$MODDIR/system/etc/luoshu/mount-probe.conf" ]
[ "$(sed -n 's/^state=//p' "$MODDIR/config/mount_compat.conf")" = prepared ]

# A real dual-directory engine must reject undeclared OEM partitions instead of
# silently pretending that every payload partition was mirrored.
mkdir -p "$MODDIR/my_product/fonts"
printf 'unsupported-partition' > "$MODDIR/my_product/fonts/Oplus.ttf"
if luoshu_sync_mount_payload Demo; then
    echo 'undeclared dual-directory partition unexpectedly succeeded' >&2
    exit 1
fi
ok grep -q 'my_product' "$MODDIR/config/mount_compat.conf"
rm -rf "$MODDIR/my_product"

printf 'font-two' > "$MODDIR/system/fonts/Test.ttf"
luoshu_sync_mount_payload Demo
[ "$(cat "$LUOSHU_META_TEST_ROOT/LuoShu/system/fonts/Test.ttf")" = font-two ]

# Mountify and Hybrid Mount read the canonical module tree directly; no guessed mirror is created.
rm -rf "$LUOSHU_META_TEST_ROOT/LuoShu"
LUOSHU_META_TEST_ENGINE=mountify
export LUOSHU_META_TEST_ENGINE
luoshu_sync_mount_payload Demo
no test -e "$LUOSHU_META_TEST_ROOT/LuoShu"
ok grep -q '^detail=当前引擎直接读取标准模块目录' "$MODDIR/config/mount_compat.conf"
ok grep -q '^system|' "$MODDIR/config/mount-probes-expected.conf"
no grep -q '^my_product|' "$MODDIR/config/mount-probes-expected.conf"

LUOSHU_META_TEST_ENGINE=hybrid-mount
export LUOSHU_META_TEST_ENGINE
luoshu_sync_mount_payload Demo
no test -e "$LUOSHU_META_TEST_ROOT/LuoShu"

# Magic Mount reads the canonical module tree. An explicit font transaction only recovers
# LuoShu-local stale markers and never creates a guessed mirror or rewrites external config.
touch "$MODDIR/skip_mount" "$MODDIR/mount_error"
LUOSHU_META_TEST_ENGINE=magic-mount
export LUOSHU_META_TEST_ENGINE
luoshu_sync_mount_payload Demo
no test -e "$MODDIR/skip_mount"
no test -e "$MODDIR/mount_error"
no test -e "$LUOSHU_META_TEST_ROOT/LuoShu"
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
luoshu_sync_mount_payload Demo

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
