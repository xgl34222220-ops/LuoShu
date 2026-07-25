#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-mount)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MODULE="$TMP/modules/LuoShu"
META="$TMP/meta"
VISIBLE="$TMP/visible"
mkdir -p \
    "$MODULE/common" "$MODULE/system/fonts" "$MODULE/product/fonts" \
    "$MODULE/my_product/fonts" "$MODULE/config" "$MODULE/logs" \
    "$META" "$VISIBLE/system/fonts"
cp "$ROOT/common/mount_compat.sh" "$MODULE/common/mount_compat.sh"
cp "$ROOT/common/font_config_partitions.sh" "$MODULE/common/font_config_partitions.sh"
cp "$ROOT/common/mount_compat_hotfix.sh" "$MODULE/common/mount_compat_hotfix.sh"
printf 'id=LuoShu\nversion=v2.2.8\nversionCode=20208\n' > "$MODULE/module.prop"
printf 'font-a' > "$MODULE/system/fonts/Roboto-Regular.ttf"
printf 'product-a' > "$MODULE/product/fonts/Test.ttf"
printf 'vendor-a' > "$MODULE/my_product/fonts/Oem.ttf"

# Dual-directory engines still receive every used partition, including OEM ones.
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=meta-overlayfs LUOSHU_META_TEST_ROOT="$META" sh -c '
    . "$MODDIR/common/mount_compat.sh"
    luoshu_sync_mount_payload Demo
'
test -f "$META/LuoShu/system/fonts/Roboto-Regular.ttf"
test -f "$META/LuoShu/product/fonts/Test.ttf"
test -f "$META/LuoShu/my_product/fonts/Oem.ttf"
grep -q '^state=prepared$' "$MODULE/config/mount_compat.conf"

# Direct-source engines read the canonical module directory and never create guessed mirrors.
rm -rf "$META/LuoShu"
for ENGINE in mountify hybrid-mount magic-mount native-module-mount; do
    MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE="$ENGINE" LUOSHU_META_TEST_ROOT="$META" sh -c '
        . "$MODDIR/common/mount_compat.sh"
        luoshu_sync_mount_payload Demo
    '
    test ! -e "$META/LuoShu"
    grep -q "^engine=$ENGINE$" "$MODULE/config/mount_compat.conf"
done

# LuoShu must not rewrite Magic Mount RC configuration.
MAGIC_CONFIG="$TMP/magic-mount-config.toml"
printf 'mountsource = "KSU"\npartitions = ["vendor"]\n' > "$MAGIC_CONFIG"
cp "$MAGIC_CONFIG" "$MAGIC_CONFIG.before"
touch "$MODULE/skip_mount" "$MODULE/skip_mountify" "$MODULE/mount_error"
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=magic-mount LUOSHU_MAGIC_MOUNT_CONFIG="$MAGIC_CONFIG" sh -c '
    . "$MODDIR/common/mount_compat.sh"
    luoshu_sync_mount_payload Demo
'
cmp -s "$MAGIC_CONFIG" "$MAGIC_CONFIG.before"
test ! -e "$MODULE/skip_mount"
test ! -e "$MODULE/skip_mountify"
test ! -e "$MODULE/mount_error"

# Missing diagnostic probes are advisory and may not roll back a validated payload.
printf 'state=booting\nfont=Demo\n' > "$MODULE/config/font-payload-boot.conf"
MODDIR="$MODULE" MODULE_DIR="$MODULE" CONFIG_DIR="$MODULE/config" \
LUOSHU_META_TEST_ENGINE=magic-mount LUOSHU_VISIBLE_PROBE_ROOT="$VISIBLE" \
LUOSHU_VISIBLE_SYSTEM_ROOT="$VISIBLE/system" sh -c '
    . "$MODDIR/common/mount_compat.sh"
    font_config_mark_boot_success
'
grep -q '^state=confirmed$' "$MODULE/config/font-payload-boot.conf"
grep -q '^state=unverified$' "$MODULE/config/mount_compat.conf"

# A real visible font verifies the mount even if a synthetic probe is absent.
cp "$MODULE/system/fonts/Roboto-Regular.ttf" "$VISIBLE/system/fonts/Roboto-Regular.ttf"
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=mountify \
LUOSHU_VISIBLE_PROBE_ROOT="$VISIBLE" LUOSHU_VISIBLE_SYSTEM_ROOT="$VISIBLE/system" sh -c '
    . "$MODDIR/common/mount_compat.sh"
    luoshu_mount_verify_active Demo
'
grep -q '^state=verified$' "$MODULE/config/mount_compat.conf"

# Multiple enabled engines remain a warning instead of changing the direct-source contract.
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=mountify \
LUOSHU_META_TEST_CANDIDATES='mountify magic-mount' sh -c '
    . "$MODDIR/common/mount_compat.sh"
    luoshu_sync_mount_payload Demo
    luoshu_mount_status_json > "$MODDIR/config/mount_status.json"
'
grep -q '^warning=检测到多个已启用挂载模块：mountify、magic-mount$' "$MODULE/config/mount_compat.conf"
grep -q '"backend":"mountify"' "$MODULE/config/mount_status.json"

# The compatibility override must always be loaded after the original implementation.
grep -q 'common/mount_compat_hotfix.sh' "$ROOT/common/font_config_partitions.sh"
sh -n "$ROOT/common/mount_compat.sh"
sh -n "$ROOT/common/mount_compat_hotfix.sh"
sh -n "$ROOT/common/font_config_partitions.sh"
sh -n "$ROOT/common/font_mix.sh"
sh -n "$ROOT/post-fs-data.sh"
sh -n "$ROOT/service.sh"

echo 'LuoShu metamodule compatibility checks passed.'
