#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-self-mount)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

MODULE="$TMP/modules/LuoShu"
VISIBLE="$TMP/visible"
STATE="$TMP/state"
FAKE_MOUNT="$TMP/fake-mount.sh"
mkdir -p \
    "$MODULE/system/fonts" \
    "$MODULE/system/etc/luoshu" \
    "$MODULE/config" \
    "$VISIBLE/system/fonts" \
    "$VISIBLE/system/etc"

printf 'new-font\n' > "$MODULE/system/fonts/Roboto-Regular.ttf"
printf 'stock-font\n' > "$VISIBLE/system/fonts/Roboto-Regular.ttf"
printf 'Demo\n' > "$MODULE/config/active_font.conf"
printf 'id=LuoShu\nfont=Demo\nengine=mountify\npartition=system\nnonce=test-system\n' \
    > "$MODULE/system/etc/luoshu/mount-probe.conf"
printf 'system|test-system|/system/etc/luoshu/mount-probe.conf\n' \
    > "$MODULE/config/mount-probes-expected.conf"

cat > "$FAKE_MOUNT" <<'EOF_FAKE_MOUNT'
#!/bin/sh
set -eu
case "$1" in
    -o)
        [ "$2" = bind ]
        src="$3"
        dst="$4"
        if [ -d "$src" ]; then
            mkdir -p "$dst"
        else
            cp -f "$src" "$dst"
        fi
        ;;
    -t)
        opts="$5"
        target="$6"
        upper=$(printf '%s' "$opts" | sed -n 's/.*upperdir=\([^,]*\).*/\1/p')
        [ -n "$upper" ]
        mkdir -p "$target"
        cp -a "$upper/." "$target/"
        ;;
    *) exit 2 ;;
esac
EOF_FAKE_MOUNT
chmod 0755 "$FAKE_MOUNT"

MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_MOUNT_MODDIR="$MODULE" \
LUOSHU_SELF_MOUNT_VISIBLE_ROOT="$VISIBLE" \
LUOSHU_SELF_MOUNT_STATE_ROOT="$STATE" \
LUOSHU_SELF_MOUNT_COMMAND="$FAKE_MOUNT" \
sh -c '
    luoshu_payload_partitions() { printf "system\n"; }
    luoshu_detect_mount_engine() { printf "mountify\n"; }
    luoshu_module_id() { printf "LuoShu\n"; }
    _luoshu_probe_path() { printf "/system/etc/luoshu/mount-probe.conf\n"; }
    _luoshu_now() { printf "1\n"; }
    luoshu_mount_record() { :; }
    . "$1/common/mount_self_fallback.sh"

    touch "$MODDIR/skip_mount" "$MODDIR/skip_mountify" "$MODDIR/mount_error"
    luoshu_self_mount_ensure
    [ ! -e "$MODDIR/skip_mount" ]
    [ ! -e "$MODDIR/skip_mountify" ]
    [ ! -e "$MODDIR/mount_error" ]
    [ "$(sed -n "s/^state=//p" "$MODDIR/config/self-mount.conf")" = mounted ]
    [ "$(sed -n "s/^backend=//p" "$MODDIR/config/self-mount.conf")" = self-overlay ]
    [ "$(cat "$LUOSHU_SELF_MOUNT_VISIBLE_ROOT/system/fonts/Roboto-Regular.ttf")" = new-font ]
    _luoshu_system_probe_visible
    grep -qx "$LUOSHU_SELF_MOUNT_VISIBLE_ROOT/system/fonts" "$LUOSHU_SELF_MOUNT_STATE_ROOT/mounts.list"
    grep -qx "$LUOSHU_SELF_MOUNT_VISIBLE_ROOT/system/etc" "$LUOSHU_SELF_MOUNT_STATE_ROOT/mounts.list"

    luoshu_self_mount_ensure
    [ "$(sed -n "s/^backend=//p" "$MODDIR/config/self-mount.conf")" = external-mount ]
' sh "$ROOT"

sh -n "$ROOT/common/mount_self_fallback.sh"
sh -n "$ROOT/post-mount.sh"
echo 'LuoShu post-mount self-mount regression checks passed.'
