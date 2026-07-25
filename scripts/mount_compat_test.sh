#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-mount)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MODULE="$TMP/modules/LuoShu"
META="$TMP/meta"
VISIBLE="$TMP/visible"
mkdir -p "$MODULE/common" "$MODULE/system/fonts" "$MODULE/product/fonts" "$MODULE/config" "$MODULE/logs" "$META" "$VISIBLE"
cp "$ROOT/common/mount_compat.sh" "$MODULE/common/mount_compat.sh"
printf 'id=LuoShu\nversion=v2.2.5\nversionCode=20205\n' > "$MODULE/module.prop"
printf 'font-a' > "$MODULE/system/fonts/Roboto-Regular.ttf"
printf 'product-a' > "$MODULE/product/fonts/Test.ttf"

# Dual-directory engines copy all used supported partitions and write one probe per partition.
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=meta-overlayfs LUOSHU_META_TEST_ROOT="$META" sh -c '
    . "$MODDIR/common/mount_compat.sh"
    luoshu_sync_mount_payload Demo
'
test -f "$META/LuoShu/system/fonts/Roboto-Regular.ttf"
test -f "$META/LuoShu/product/fonts/Test.ttf"
test -f "$META/LuoShu/system/etc/luoshu/mount-probe.conf"
test -f "$META/LuoShu/product/etc/luoshu/mount-probe.conf"
grep -q '^engine=meta-overlayfs$' "$MODULE/config/mount_compat.conf"
grep -q '^state=prepared$' "$MODULE/config/mount_compat.conf"
grep -q '^partitions=system,product$' "$MODULE/config/mount_compat.conf"

# Replacing a partition must remove stale files instead of merging trees.
rm -f "$MODULE/system/fonts/Roboto-Regular.ttf"
printf stale > "$META/LuoShu/system/fonts/Old.ttf"
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=meta-overlayfs LUOSHU_META_TEST_ROOT="$META" sh -c '
    . "$MODDIR/common/mount_compat.sh"
    luoshu_sync_mount_payload Demo
'
test ! -e "$META/LuoShu/system/fonts/Old.ttf"
test ! -e "$META/LuoShu/system/fonts/Roboto-Regular.ttf"
test -s "$META/LuoShu/system/etc/luoshu/mount-probe.conf"

# Verify every used partition, not merely /system.
mkdir -p "$VISIBLE/system/etc/luoshu" "$VISIBLE/product/etc/luoshu"
cp "$MODULE/system/etc/luoshu/mount-probe.conf" "$VISIBLE/system/etc/luoshu/mount-probe.conf"
cp "$MODULE/product/etc/luoshu/mount-probe.conf" "$VISIBLE/product/etc/luoshu/mount-probe.conf"
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=meta-overlayfs LUOSHU_META_TEST_ROOT="$META" LUOSHU_VISIBLE_PROBE_ROOT="$VISIBLE" sh -c '
    . "$MODDIR/common/mount_compat.sh"
    luoshu_mount_verify_active Demo
'
grep -q '^state=verified$' "$MODULE/config/mount_compat.conf"
grep -q '^verifiedPartitions=system,product$' "$MODULE/config/mount_compat.conf"
rm -f "$VISIBLE/product/etc/luoshu/mount-probe.conf"
if MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=meta-overlayfs LUOSHU_META_TEST_ROOT="$META" LUOSHU_VISIBLE_PROBE_ROOT="$VISIBLE" sh -c '
    . "$MODDIR/common/mount_compat.sh"
    luoshu_mount_verify_active Demo
'; then
    echo 'partition verification unexpectedly passed with product missing' >&2
    exit 1
fi
grep -q '^state=unverified$' "$MODULE/config/mount_compat.conf"
grep -q '^failedPartitions=product$' "$MODULE/config/mount_compat.conf"

# Unsupported vendor partitions are rejected explicitly rather than silently ignored.
mkdir -p "$MODULE/my_product/fonts"
printf vendor-font > "$MODULE/my_product/fonts/Oem.ttf"
if MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=meta-overlayfs LUOSHU_META_TEST_ROOT="$META" sh -c '
    . "$MODDIR/common/mount_compat.sh"
    luoshu_sync_mount_payload Demo
'; then
    echo 'unsupported meta-overlayfs partition unexpectedly succeeded' >&2
    exit 1
fi
grep -q 'my_product' "$MODULE/config/mount_compat.conf"
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=meta-overlayfs LUOSHU_META_TEST_ROOT="$META" LUOSHU_META_EXTRA_PARTITIONS=my_product sh -c '
    . "$MODDIR/common/mount_compat.sh"
    luoshu_sync_mount_payload Demo
'
test -f "$META/LuoShu/my_product/fonts/Oem.ttf"
rm -rf "$MODULE/my_product" "$META/LuoShu/my_product"

# Direct-source engines never create a guessed second module tree.
rm -rf "$META/LuoShu"
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=mountify LUOSHU_META_TEST_ROOT="$META" sh -c '
    . "$MODDIR/common/mount_compat.sh"
    luoshu_sync_mount_payload Demo
'
test ! -e "$META/LuoShu"
grep -q '^engine=mountify$' "$MODULE/config/mount_compat.conf"

# Hybrid Mount records the selected backend for diagnostics.
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=hybrid-mount LUOSHU_META_TEST_BACKEND=kasumi sh -c '
    . "$MODDIR/common/mount_compat.sh"
    luoshu_sync_mount_payload Demo
'
grep -q '^engine=hybrid-mount$' "$MODULE/config/mount_compat.conf"
grep -q '^backend=kasumi$' "$MODULE/config/mount_compat.conf"

# Magic Mount retries clear recoverable markers and update partitions under a config lock.
touch "$MODULE/skip_mount" "$MODULE/mount_error"
MAGIC_CONFIG="$TMP/magic-mount-config.toml"
printf 'mountsource = "KSU"\numount = false\npartitions = [\n  "vendor", # keep existing\n]\n' > "$MAGIC_CONFIG"
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=magic-mount LUOSHU_MAGIC_MOUNT_CONFIG="$MAGIC_CONFIG" sh -c '
    . "$MODDIR/common/mount_compat.sh"
    luoshu_sync_mount_payload Demo
'
test ! -e "$MODULE/skip_mount"
test ! -e "$MODULE/mount_error"
grep -q '"vendor"' "$MAGIC_CONFIG"
grep -q '"product"' "$MAGIC_CONFIG"
test "$(grep -c '^[[:space:]]*partitions[[:space:]]*=' "$MAGIC_CONFIG")" -eq 1
test -s "$MAGIC_CONFIG.luoshu.bak"
test ! -e "$MAGIC_CONFIG.luoshu.lock"

# Explicit font transactions recover an old LuoShu disable marker, but never remove remove.
touch "$MODULE/disable"
printf '2\n' > "$MODULE/config/font-boot-failures"
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=magic-mount LUOSHU_MAGIC_MOUNT_CONFIG="$MAGIC_CONFIG" sh -c '
    . "$MODDIR/common/mount_compat.sh"
    luoshu_sync_mount_payload FontA
'
test ! -e "$MODULE/disable"
test ! -e "$MODULE/config/font-boot-failures"
touch "$MODULE/remove"
if MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=magic-mount LUOSHU_MAGIC_MOUNT_CONFIG="$MAGIC_CONFIG" sh -c '
    . "$MODDIR/common/mount_compat.sh"
    luoshu_sync_mount_payload FontA
'; then
    echo 'remove marker was unexpectedly cleared' >&2
    exit 1
fi
test -e "$MODULE/remove"
rm -f "$MODULE/remove"

# A copy timeout has one bounded attempt only and preserves the old destination tree.
SLOWBIN="$TMP/slowbin"
mkdir -p "$SLOWBIN" "$TMP/source/system" "$TMP/dest/system"
printf new > "$TMP/source/system/new.ttf"
printf old > "$TMP/dest/system/old.ttf"
cat > "$SLOWBIN/cp" <<'EOS'
#!/bin/sh
sleep 10
exit 1
EOS
chmod 0755 "$SLOWBIN/cp"
if PATH="$SLOWBIN:$PATH" MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_MOUNT_TIMEOUT=2 LUOSHU_META_TEST_ENGINE=native-module-mount sh -c '
    . "$MODDIR/common/mount_compat.sh"
    luoshu_mount_budget_begin
    luoshu_copy_partition_atomic "$1" "$2"
' sh "$TMP/source/system" "$TMP/dest/system"; then
    echo 'slow copy unexpectedly succeeded' >&2
    exit 1
fi
test -f "$TMP/dest/system/old.ttf"
test ! -e "$TMP/dest/system/new.ttf"

# Conflicting enabled mount modules are surfaced in diagnostics instead of being silently guessed.
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=mountify LUOSHU_META_TEST_CANDIDATES="mountify magic-mount" sh -c '
    . "$MODDIR/common/mount_compat.sh"
    luoshu_sync_mount_payload Demo
    luoshu_mount_status_json > "$MODDIR/config/mount_status.json"
'
grep -q '^warning=检测到多个已启用挂载模块：mountify、magic-mount$' "$MODULE/config/mount_compat.conf"
grep -q '"backend":"mountify"' "$MODULE/config/mount_status.json"
grep -q '"warning":"检测到多个已启用挂载模块：mountify、magic-mount"' "$MODULE/config/mount_status.json"

# The flash installer must recover both the staging tree and the currently active module tree.
grep -q 'for _enable_dir in "$MODPATH" "$OLD_MOD"' "$ROOT/customize.sh"
grep -q 'rm -f "$_enable_dir/disable"' "$ROOT/customize.sh"

# Runtime syncing remains transaction-only. Never mirror blindly from early boot scripts.
grep -q 'common/mount_compat.sh' "$ROOT/common/font_mix.sh"
grep -q 'luoshu_sync_mount_payload' "$ROOT/common/font_mix.sh"
! grep -q 'luoshu_sync_mount_payload' "$ROOT/post-fs-data.sh"
! grep -q 'luoshu_sync_mount_payload' "$ROOT/service.sh"
! grep -q 'prepare_mount_compat.sh' "$ROOT/scripts/build.sh"

# Release packages must not contain markers that exclude LuoShu from mount planning.
STAGE="$TMP/stage"
mkdir -p "$STAGE"
cp -R "$ROOT/." "$STAGE/"
rm -rf "$STAGE/.git" "$STAGE/dist" "$STAGE/common/python" 2>/dev/null || true
! find "$STAGE" -type f \( -name skip_mount -o -name skip_mountify \) | grep -q .
sh -n "$ROOT/common/mount_compat.sh"
sh -n "$ROOT/common/font_mix.sh"
sh -n "$ROOT/common/app_bridge.sh"
sh -n "$ROOT/post-fs-data.sh"
sh -n "$ROOT/service.sh"

echo 'LuoShu metamodule compatibility checks passed.'
