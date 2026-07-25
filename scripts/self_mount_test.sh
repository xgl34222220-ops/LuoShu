#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-self-mount)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MODULE="$TMP/modules/LuoShu"
VISIBLE="$TMP/visible"
STATE="$TMP/state"
PRIVATE_STATE="$TMP/private-state"
FAKE_MOUNT="$TMP/fake-mount.sh"
FAKE_UMOUNT="$TMP/fake-umount.sh"
MOUNTINFO="$TMP/mounts"
mkdir -p \
    "$MODULE/system/fonts" \
    "$MODULE/system/etc/luoshu" \
    "$MODULE/config" \
    "$VISIBLE/system/fonts" \
    "$VISIBLE/system/etc"
ln -s "$ROOT/common" "$MODULE/common"

printf 'new-font\n' > "$MODULE/system/fonts/Roboto-Regular.ttf"
printf 'stock-font\n' > "$VISIBLE/system/fonts/Roboto-Regular.ttf"
printf 'stock-emoji\n' > "$VISIBLE/system/fonts/NotoColorEmoji.ttf"
printf 'Demo\n' > "$MODULE/config/active_font.conf"
printf 'id=LuoShu\nfont=Demo\nengine=self-mount\npartition=system\nnonce=test-system\n' \
    > "$MODULE/system/etc/luoshu/mount-probe.conf"
printf 'system|test-system|/system/etc/luoshu/mount-probe.conf\n' \
    > "$MODULE/config/mount-probes-expected.conf"
: > "$MOUNTINFO"

cat > "$FAKE_MOUNT" <<'EOF_FAKE_MOUNT'
#!/bin/sh
set -eu
mountinfo=${LUOSHU_TEST_MOUNTINFO:?}
case "$1" in
    -o)
        [ "$2" = bind ]
        src="$3"
        dst="$4"
        backup="${dst}.luoshu-test-stock"
        rm -rf "$backup"
        if [ -d "$dst" ]; then mv "$dst" "$backup"; else mkdir -p "$backup"; fi
        mkdir -p "$dst"
        cp -a "$src/." "$dst/"
        printf 'bind %s %s %s\n' "$src" "$dst" "$backup" >> "$mountinfo"
        ;;
    -t)
        [ "$2" = overlay ]
        [ "$3" = KSU ]
        [ "$4" = -o ]
        opts="$5"
        target="$6"
        layers=$(printf '%s' "$opts" | sed -n 's/^lowerdir=//p')
        source=${layers%%:*}
        stock=${layers#*:}
        backup="${target}.luoshu-test-stock"
        rm -rf "$backup"
        mv "$target" "$backup"
        mkdir -p "$target"
        cp -a "$stock/." "$target/"
        cp -a "$source/." "$target/"
        printf 'overlay %s %s %s\n' "$source" "$target" "$backup" >> "$mountinfo"
        ;;
    *) exit 2 ;;
esac
EOF_FAKE_MOUNT

cat > "$FAKE_UMOUNT" <<'EOF_FAKE_UMOUNT'
#!/bin/sh
set -eu
target="$1"
backup="${target}.luoshu-test-stock"
rm -rf "$target"
if [ -d "$backup" ]; then mv "$backup" "$target"; else mkdir -p "$target"; fi
EOF_FAKE_UMOUNT
chmod 0755 "$FAKE_MOUNT" "$FAKE_UMOUNT"

# Installation moves standard partition payloads into a private tree and leaves
# an empty shell that Mountify/Hybrid/Magic Mount cannot consume.
MODDIR="$MODULE" MODULE_DIR="$MODULE" \
LUOSHU_PRIVATE_STATE_ROOT="$PRIVATE_STATE" \
LUOSHU_PRIVATE_MOUNTINFO="$MOUNTINFO" \
LUOSHU_PRIVATE_MOUNT_COMMAND="$FAKE_MOUNT" \
LUOSHU_PRIVATE_UMOUNT_COMMAND="$FAKE_UMOUNT" \
LUOSHU_TEST_MOUNTINFO="$MOUNTINFO" \
sh -c '
    . "$1/common/private_payload.sh"
    luoshu_private_install_migrate "$MODDIR"
    [ -f "$MODDIR/.luoshu-payload/system/fonts/Roboto-Regular.ttf" ]
    [ -f "$MODDIR/.luoshu-payload/system/etc/luoshu/mount-probe.conf" ]
    [ -d "$MODDIR/system" ]
    [ -z "$(find "$MODDIR/system" -mindepth 1 -print -quit)" ]
    [ -e "$MODDIR/skip_mount" ]
    [ -e "$MODDIR/skip_mountify" ]
    [ -e "$MODDIR/config/self-mount-owned" ]

    luoshu_private_mount_module_view "$MODDIR"
    [ "$(cat "$MODDIR/system/fonts/Roboto-Regular.ttf")" = new-font ]
    luoshu_private_unmount_module_view "$MODDIR"
    [ -z "$(find "$MODDIR/system" -mindepth 1 -print -quit)" ]
' sh "$ROOT"

# After all metamodules finish, LuoShu restores its private module view and mounts
# the payload itself. Skip markers remain, and ROM Emoji survives.
MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_MOUNT_MODDIR="$MODULE" \
LUOSHU_SELF_MOUNT_VISIBLE_ROOT="$VISIBLE" \
LUOSHU_SELF_MOUNT_STATE_ROOT="$STATE" \
LUOSHU_SELF_MOUNT_COMMAND="$FAKE_MOUNT" \
LUOSHU_SELF_UMOUNT_COMMAND="$FAKE_UMOUNT" \
LUOSHU_PRIVATE_STATE_ROOT="$PRIVATE_STATE" \
LUOSHU_PRIVATE_MOUNTINFO="$MOUNTINFO" \
LUOSHU_PRIVATE_MOUNT_COMMAND="$FAKE_MOUNT" \
LUOSHU_PRIVATE_UMOUNT_COMMAND="$FAKE_UMOUNT" \
LUOSHU_TEST_MOUNTINFO="$MOUNTINFO" \
sh -c '
    luoshu_payload_partitions() { printf "system\n"; }
    luoshu_module_id() { printf "LuoShu\n"; }
    _luoshu_probe_path() { printf "/system/etc/luoshu/mount-probe.conf\n"; }
    _luoshu_now() { printf "1\n"; }
    luoshu_mount_record() { :; }
    . "$1/common/private_payload.sh"
    luoshu_private_mount_module_view "$MODDIR"
    . "$MODDIR/common/mount_compat.sh"
    . "$MODDIR/common/mount_self_backend.sh"

    touch "$MODDIR/mount_error"
    luoshu_private_self_mount_ensure
    [ -e "$MODDIR/skip_mount" ]
    [ -e "$MODDIR/skip_mountify" ]
    [ ! -e "$MODDIR/mount_error" ]
    [ "$(sed -n "s/^state=//p" "$MODDIR/config/self-mount.conf")" = mounted ]
    [ "$(sed -n "s/^backend=//p" "$MODDIR/config/self-mount.conf")" = self-overlay ]
    [ "$(cat "$LUOSHU_SELF_MOUNT_VISIBLE_ROOT/system/fonts/Roboto-Regular.ttf")" = new-font ]
    [ "$(cat "$LUOSHU_SELF_MOUNT_VISIBLE_ROOT/system/fonts/NotoColorEmoji.ttf")" = stock-emoji ]
    _luoshu_system_probe_visible

    luoshu_private_self_mount_ensure
    [ "$(sed -n "s/^backend=//p" "$MODDIR/config/self-mount.conf")" = self-existing ]
' sh "$ROOT"

# Production policy never detects or configures a metamodule. Engine injection is
# retained only for legacy regression fixtures.
MODE=$(MODDIR="$ROOT" MODULE_DIR="$ROOT" sh -c '. "$1/common/mount_compat.sh"; luoshu_detect_mount_engine' sh "$ROOT")
[ "$MODE" = self-mount ]
INJECTED=$(MODDIR="$ROOT" MODULE_DIR="$ROOT" LUOSHU_META_TEST_ENGINE=hybrid-mount sh -c '. "$1/common/mount_compat.sh"; luoshu_detect_mount_engine' sh "$ROOT")
[ "$INJECTED" = hybrid-mount ]
grep -q 'External metamodules are intentionally ignored' "$ROOT/post-mount.sh"
! grep -Eq '_luoshu_(mountify|magic_mount|hybrid_mount)_present|/data/adb/metamodule' "$ROOT/post-mount.sh"

sh -n "$ROOT/common/private_payload.sh"
sh -n "$ROOT/common/mount_self_fallback.sh"
sh -n "$ROOT/common/mount_self_backend.sh"
sh -n "$ROOT/common/mount_compat_policy.sh"
sh -n "$ROOT/common/private_mount_policy.sh"
sh -n "$ROOT/common/mount_compat.sh"
sh -n "$ROOT/post-fs-data.sh"
sh -n "$ROOT/post-mount.sh"
echo 'LuoShu private self-mount regression checks passed.'
