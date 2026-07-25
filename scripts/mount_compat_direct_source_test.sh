#!/bin/sh
set -eux

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-direct-mount)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MODULE="$TMP/modules/LuoShu"
VISIBLE="$TMP/visible"
FAKE_MOUNTIFY="$TMP/mountify"
FAKE_MAGIC="$TMP/magic_mount"
mkdir -p \
    "$MODULE/common" \
    "$MODULE/system/fonts" \
    "$MODULE/product/fonts" \
    "$MODULE/config" \
    "$MODULE/logs" \
    "$VISIBLE/system/etc/luoshu" \
    "$FAKE_MOUNTIFY" \
    "$FAKE_MAGIC" \
    "$TMP/modules/meta-mm"
cp "$ROOT/common/mount_compat.sh" "$MODULE/common/mount_compat.sh"
cp "$ROOT/common/font_config_partitions.sh" "$MODULE/common/font_config_partitions.sh"
cp "$ROOT/common/mount_compat_direct_source.sh" "$MODULE/common/mount_compat_direct_source.sh"
printf 'id=LuoShu\nversion=v2-test\nversionCode=1\n' > "$MODULE/module.prop"
printf 'system-font\n' > "$MODULE/system/fonts/Roboto-Regular.ttf"
printf 'product-font\n' > "$MODULE/product/fonts/ProductSans-Regular.ttf"

# Standalone Mountify state is valid evidence even when no exact module.prop package id exists.
MODDIR="$MODULE" MODULE_DIR="$MODULE" \
LUOSHU_META_TEST_MOUNTIFY_ROOT="$FAKE_MOUNTIFY" \
LUOSHU_META_TEST_MODULES_ROOT="$TMP/modules" sh -c '
    . "$MODDIR/common/mount_compat.sh"
    _luoshu_mountify_present
'

# Magic Mount RC must keep the legacy meta-mm helper path that v2.2.5 accidentally dropped.
printf 'partitions = ["system"]\n' > "$FAKE_MAGIC/config.toml"
printf '#!/system/bin/sh\n' > "$TMP/modules/meta-mm/meta-mm"
MODDIR="$MODULE" MODULE_DIR="$MODULE" \
LUOSHU_META_TEST_MAGIC_ROOT="$FAKE_MAGIC" \
LUOSHU_META_TEST_MODULES_ROOT="$TMP/modules" sh -c '
    . "$MODDIR/common/mount_compat.sh"
    _luoshu_magic_mount_present
'

# Direct-source engines write only the stable /system probe instead of making every OEM alias a
# destructive rollback gate.
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=mountify sh -c '
    . "$MODDIR/common/mount_compat.sh"
    luoshu_write_mount_probes Demo
'
grep -q '^system|' "$MODULE/config/mount-probes-expected.conf"
! grep -q '^product|' "$MODULE/config/mount-probes-expected.conf"

# An old v2.2.5/v2.2.6 manifest may still contain product/OEM probes. Mountify must validate the
# system probe and ignore stale non-system rows rather than rolling back a working font.
cp "$MODULE/system/etc/luoshu/mount-probe.conf" "$VISIBLE/system/etc/luoshu/mount-probe.conf"
NONCE=$(sed -n 's/^nonce=//p' "$MODULE/system/etc/luoshu/mount-probe.conf" | head -n1)
printf 'system|%s|/system/etc/luoshu/mount-probe.conf\nproduct|stale-product|/product/etc/luoshu/mount-probe.conf\n' \
    "$NONCE" > "$MODULE/config/mount-probes-expected.conf"
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=mountify \
LUOSHU_VISIBLE_PROBE_ROOT="$VISIBLE" sh -c '
    . "$MODDIR/common/mount_compat.sh"
    luoshu_mount_verify_active Demo
'
grep -q '^state=verified$' "$MODULE/config/mount_compat.conf"
grep -q '^verifiedPartitions=system$' "$MODULE/config/mount_compat.conf"

# Missing direct-source probes stay visible in diagnostics, but no longer disable or roll back an
# otherwise working module. Device font-load verification remains the real payload gate.
rm -f "$VISIBLE/system/etc/luoshu/mount-probe.conf"
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=magic-mount \
LUOSHU_VISIBLE_PROBE_ROOT="$VISIBLE" sh -c '
    . "$MODDIR/common/mount_compat.sh"
    luoshu_mount_verify_active Demo
'
grep -q '^state=verified$' "$MODULE/config/mount_compat.conf"
grep -q '^detail=兼容模式：magic-mount 未暴露系统探针' "$MODULE/config/mount_compat.conf"

# Real dual-directory meta-overlayfs keeps strict per-partition verification.
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=meta-overlayfs sh -c '
    . "$MODDIR/common/mount_compat.sh"
    luoshu_write_mount_probes Demo
'
cp "$MODULE/system/etc/luoshu/mount-probe.conf" "$VISIBLE/system/etc/luoshu/mount-probe.conf"
rm -rf "$VISIBLE/product"
if MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=meta-overlayfs \
LUOSHU_VISIBLE_PROBE_ROOT="$VISIBLE" sh -c '
    . "$MODDIR/common/mount_compat.sh"
    luoshu_mount_verify_active Demo
'; then
    echo 'strict meta-overlayfs verification unexpectedly accepted a missing product probe' >&2
    exit 1
fi
grep -q '^state=unverified$' "$MODULE/config/mount_compat.conf"
grep -q '^failedPartitions=product$' "$MODULE/config/mount_compat.conf"

sh -n "$ROOT/common/mount_compat_direct_source.sh"
echo 'LuoShu direct-source metamodule regression checks passed.'
