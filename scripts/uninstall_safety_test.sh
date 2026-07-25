#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-uninstall)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MODULE="$TMP/module"
DATA="$TMP/flyme-data"
PROVIDER="$TMP/provider"
BIN="$TMP/bin"
TARGET="$TMP/data-fonts-config.xml"
MOUNTINFO="$TMP/mountinfo"
mkdir -p "$MODULE/common" "$MODULE/.luoshu-runtime" \
    "$MODULE/config/flyme-data-original" "$MODULE/system/etc" \
    "$DATA" "$PROVIDER" "$BIN"
cp "$ROOT/uninstall.sh" "$MODULE/uninstall.sh"
cp "$ROOT/.luoshu-runtime/uninstall-v227.sh" "$MODULE/.luoshu-runtime/uninstall-v227.sh"
cp "$ROOT/common/private_payload.sh" "$MODULE/common/private_payload.sh"
cp "$ROOT/common/origin_flyme_global.sh" "$MODULE/common/origin_flyme_global.sh"
cp "$ROOT/common/font_provider_cache.sh" "$MODULE/common/font_provider_cache.sh"
printf 'id=LuoShu\nversion=v2.3-test\n' > "$MODULE/module.prop"

# Simulate LuoShu's private dynamic view mounted on the original config path.
printf '<fontConfig sanitized="true"/>\n' > "$MODULE/system/etc/.luoshu-data-fonts-config.xml"
cp "$MODULE/system/etc/.luoshu-data-fonts-config.xml" "$TARGET"
HASH=$(sha256sum "$TARGET" | awk '{print $1}')
cat > "$MODULE/config/device-font-dynamic-mount.conf" <<EOF_STATE
state=prepared
source=system/etc/.luoshu-data-fonts-config.xml
target=$TARGET
targetSha256=original
sourceSha256=$HASH
EOF_STATE
printf '101 1 0:42 / %s rw,relatime - tmpfs tmpfs rw\n' "$TARGET" > "$MOUNTINFO"
cat > "$BIN/umount" <<'EOF_UMOUNT'
#!/bin/sh
printf '%s\n' "$1" >> "$LUOSHU_UMOUNT_LOG"
exit 0
EOF_UMOUNT
chmod 0755 "$BIN/umount"

# Simulate a retired provider overwrite that still has LuoShu's explicit backup.
printf 'old-provider\n' > "$PROVIDER/GoogleSans-Regular.ttf.luoshu-bak"
printf 'modified-provider\n' > "$PROVIDER/GoogleSans-Regular.ttf"

# Simulate Flyme persistent font currently replaced by LuoShu and its captured original.
dd if=/dev/zero of="$MODULE/config/flyme-data-original/flymeFont.ttf" bs=2048 count=1 2>/dev/null
printf 'original=present\n' > "$MODULE/config/flyme-data-original/state.conf"
dd if=/dev/zero of="$DATA/flymeFont.ttf" bs=3072 count=1 2>/dev/null
ORIGINAL_HASH=$(sha256sum "$MODULE/config/flyme-data-original/flymeFont.ttf" | awk '{print $1}')

PATH="$BIN:$PATH" \
LUOSHU_UMOUNT_LOG="$TMP/umount.log" \
LUOSHU_MOUNTINFO="$MOUNTINFO" \
LUOSHU_PROVIDER_DIR="$PROVIDER" \
LUOSHU_TEST_ROM=flyme \
LUOSHU_FLYME_DATA_FONT_ROOT="$DATA" \
LUOSHU_MODULES_DIR="$TMP/modules" \
LUOSHU_MODULES_UPDATE_DIR="$TMP/modules-update" \
LUOSHU_METAMODULE_MNT="$TMP/metamodule" \
LUOSHU_SELF_MOUNT_STATE="$TMP/luoshu/self-mount" \
    sh "$MODULE/uninstall.sh"

grep -qx "$TARGET" "$TMP/umount.log"
test "$(cat "$PROVIDER/GoogleSans-Regular.ttf")" = old-provider
test ! -e "$PROVIDER/GoogleSans-Regular.ttf.luoshu-bak"
test "$(sha256sum "$DATA/flymeFont.ttf" | awk '{print $1}')" = "$ORIGINAL_HASH"
test ! -e "$MODULE/config/flyme-data-original"
test ! -e "$MODULE/config/flyme-data-pending.conf"

CORE="$ROOT/.luoshu-runtime/uninstall-v227.sh"
sh -n "$ROOT/uninstall.sh"
sh -n "$CORE"
grep -q 'private_payload.sh' "$ROOT/uninstall.sh"
grep -q 'uninstall-v227.sh' "$ROOT/uninstall.sh"
grep -q 'device-font-dynamic-mount.conf' "$CORE"
grep -q '_luoshu_flyme_prepare_data_restore' "$CORE"
grep -q 'luoshu_flyme_pending_apply' "$CORE"
grep -q '_luoshu_cleanup_self_mount' "$CORE"

echo 'LuoShu uninstall restores recorded state through the v2.3 private self-mount wrapper.'
