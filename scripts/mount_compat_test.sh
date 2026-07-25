#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SCRIPT="$ROOT/common/mount_compat.sh"
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-mount)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MODULE="$TMP/modules/LuoShu"
META="$TMP/meta"
VISIBLE="$TMP/visible"
mkdir -p \
  "$MODULE/common" \
  "$MODULE/system/fonts" \
  "$MODULE/product/fonts" \
  "$MODULE/my_product/fonts" \
  "$MODULE/config" \
  "$MODULE/logs" \
  "$META" \
  "$VISIBLE"
cp "$SCRIPT" "$MODULE/common/mount_compat.sh"
printf 'id=LuoShu\nversion=v2.2.7\nversionCode=20207\n' > "$MODULE/module.prop"
printf 'font-a' > "$MODULE/system/fonts/A.ttf"
printf 'product-a' > "$MODULE/product/fonts/B.ttf"
printf 'oem-a' > "$MODULE/my_product/fonts/C.ttf"

# A real dual-directory metamodule is the only engine that receives a mirror.
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=meta-overlayfs LUOSHU_META_TEST_ROOT="$META" sh -c '
  . "$MODDIR/common/mount_compat.sh"
  luoshu_sync_mount_payload Demo
'
test -f "$META/LuoShu/system/fonts/A.ttf"
test -f "$META/LuoShu/product/fonts/B.ttf"
test ! -e "$META/LuoShu/my_product"
grep -q '^state=prepared$' "$MODULE/config/mount_compat.conf"
grep -q '^unsupportedPartitions=my_product$' "$MODULE/config/mount_compat.conf"
test -s "$MODULE/config/mount-probes-expected.conf"

# Only the dual-directory engine uses synthetic probes because its persistent
# content tree differs from the canonical module directory.
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
grep -q '^failedPartitions=product$' "$MODULE/config/mount_compat.conf"

# Direct-source engines are passive: no mirror, no config edit, no marker cleanup,
# no whitelist rejection and no synthetic probe requirement.
for engine in mountify magic-mount magic-mount-rc magic-mount-rs hybrid-mount native-module-mount; do
  rm -rf "$META/LuoShu"
  rm -f "$MODULE/config/mount-probes-expected.conf" "$MODULE/config/mount-probe-expected.conf"
  touch "$MODULE/skip_mount" "$MODULE/mount_error"
  MAGIC_CONFIG="$TMP/${engine}.toml"
  printf 'partitions = ["vendor"]\ncustom = true\n' > "$MAGIC_CONFIG"
  cp "$MAGIC_CONFIG" "$MAGIC_CONFIG.before"
  MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE="$engine" LUOSHU_META_TEST_ROOT="$META" LUOSHU_MAGIC_MOUNT_CONFIG="$MAGIC_CONFIG" sh -c '
    . "$MODDIR/common/mount_compat.sh"
    luoshu_sync_mount_payload Demo
    luoshu_mount_verify_active Demo
  '
  test ! -e "$META/LuoShu"
  test -e "$MODULE/skip_mount"
  test -e "$MODULE/mount_error"
  cmp -s "$MAGIC_CONFIG.before" "$MAGIC_CONFIG"
  test ! -e "$MODULE/config/mount-probes-expected.conf"
  grep -q '^state=verified$' "$MODULE/config/mount_compat.conf"
  grep -q '不再用合成探针误判' "$MODULE/config/mount_compat.conf"
  rm -f "$MODULE/skip_mount" "$MODULE/mount_error"
done

# Direct engines must not care about a disable marker either; the compatibility
# layer is not allowed to change user/root-manager state.
touch "$MODULE/disable"
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=mountify sh -c '
  . "$MODDIR/common/mount_compat.sh"
  luoshu_sync_mount_payload Demo
'
test -e "$MODULE/disable"
rm -f "$MODULE/disable"

# A true dual-directory engine still rejects an actual mount exclusion marker.
touch "$MODULE/skip_mount"
if MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=meta-overlayfs LUOSHU_META_TEST_ROOT="$META" sh -c '
  . "$MODDIR/common/mount_compat.sh"
  luoshu_sync_mount_payload Demo
'; then
  echo 'meta-overlayfs unexpectedly accepted skip_mount' >&2
  exit 1
fi
rm -f "$MODULE/skip_mount"

# Conflicts are diagnostic only and must not block a direct engine transaction.
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_META_TEST_ENGINE=mountify LUOSHU_META_TEST_CANDIDATES='mountify magic-mount' sh -c '
  . "$MODDIR/common/mount_compat.sh"
  luoshu_sync_mount_payload Demo
  luoshu_mount_status_json > "$MODDIR/config/mount_status.json"
'
grep -q '^warning=检测到多个已启用挂载模块：mountify、magic-mount$' "$MODULE/config/mount_compat.conf"
grep -q '"warning":"检测到多个已启用挂载模块：mountify、magic-mount"' "$MODULE/config/mount_status.json"

# A copy timeout has one bounded attempt only and preserves the old destination tree.
SLOWBIN="$TMP/slowbin"
mkdir -p "$SLOWBIN" "$TMP/source/system" "$TMP/dest/system"
printf 'new' > "$TMP/source/system/new.ttf"
printf 'old' > "$TMP/dest/system/old.ttf"
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

# The dangerous regression must not return.
! grep -q 'Mountify 白名单未包含' "$SCRIPT"
! grep -q 'Magic Mount 增加分区' "$SCRIPT"
! grep -q 'mv -f.*magic_mount/config' "$SCRIPT"
grep -q 'direct-source bypass' "$SCRIPT"
test ! -e "$ROOT/common/mount_compat_hotfix.sh"
! grep -q 'mount_compat_hotfix.sh' "$ROOT/common/font_config_partitions.sh"

# Font transactions remain the only runtime sync caller; early boot never mirrors blindly.
grep -q 'common/mount_compat.sh' "$ROOT/common/font_mix.sh"
grep -q 'luoshu_sync_mount_payload' "$ROOT/common/font_mix.sh"
! grep -q 'luoshu_sync_mount_payload' "$ROOT/post-fs-data.sh"
! grep -q 'luoshu_sync_mount_payload' "$ROOT/service.sh"

# The installer still recovers the active and staging module trees, while release
# payloads never ship markers that exclude LuoShu from mount planning.
grep -q 'for _enable_dir in "$MODPATH" "$OLD_MOD"' "$ROOT/customize.sh"
grep -q 'rm -f "$_enable_dir/disable"' "$ROOT/customize.sh"
STAGE="$TMP/stage"
mkdir -p "$STAGE"
cp -R "$ROOT/." "$STAGE/"
rm -rf "$STAGE/.git" "$STAGE/dist" "$STAGE/common/python" 2>/dev/null || true
! find "$STAGE" -type f \( -name skip_mount -o -name skip_mountify \) | grep -q .

sh -n "$SCRIPT"
sh -n "$ROOT/common/font_mix.sh"
sh -n "$ROOT/common/app_bridge.sh"
sh -n "$ROOT/post-fs-data.sh"
sh -n "$ROOT/service.sh"
printf 'LuoShu non-invasive metamodule checks passed.\n'
