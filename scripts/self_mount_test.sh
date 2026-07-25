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
printf 'stock-emoji\n' > "$VISIBLE/system/fonts/NotoColorEmoji.ttf"
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
            rm -rf "$dst"
            mkdir -p "$dst"
            cp -a "$src/." "$dst/"
        else
            cp -f "$src" "$dst"
        fi
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
        [ -d "$source" ]
        [ -d "$stock" ]
        rm -rf "$target"
        mkdir -p "$target"
        cp -a "$stock/." "$target/"
        cp -a "$source/." "$target/"
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
    . "$1/common/mount_self_backend.sh"

    touch "$MODDIR/skip_mount" "$MODDIR/skip_mountify" "$MODDIR/mount_error"
    luoshu_self_mount_ensure
    [ ! -e "$MODDIR/skip_mount" ]
    [ ! -e "$MODDIR/skip_mountify" ]
    [ ! -e "$MODDIR/mount_error" ]
    [ "$(sed -n "s/^state=//p" "$MODDIR/config/self-mount.conf")" = mounted ]
    [ "$(sed -n "s/^backend=//p" "$MODDIR/config/self-mount.conf")" = self-overlay ]
    [ "$(cat "$LUOSHU_SELF_MOUNT_VISIBLE_ROOT/system/fonts/Roboto-Regular.ttf")" = new-font ]
    [ "$(cat "$LUOSHU_SELF_MOUNT_VISIBLE_ROOT/system/fonts/NotoColorEmoji.ttf")" = stock-emoji ]
    _luoshu_system_probe_visible
    grep -qx "$LUOSHU_SELF_MOUNT_STATE_ROOT/lower/system-fonts" "$LUOSHU_SELF_MOUNT_STATE_ROOT/mounts.list"
    grep -qx "$LUOSHU_SELF_MOUNT_VISIBLE_ROOT/system/fonts" "$LUOSHU_SELF_MOUNT_STATE_ROOT/mounts.list"
    grep -qx "$LUOSHU_SELF_MOUNT_STATE_ROOT/lower/system-etc" "$LUOSHU_SELF_MOUNT_STATE_ROOT/mounts.list"
    grep -qx "$LUOSHU_SELF_MOUNT_VISIBLE_ROOT/system/etc" "$LUOSHU_SELF_MOUNT_STATE_ROOT/mounts.list"

    luoshu_self_mount_ensure
    [ "$(sed -n "s/^backend=//p" "$MODDIR/config/self-mount.conf")" = external-mount ]
' sh "$ROOT"

# The boot entry point must never call the self-mount backend when any external
# metamodule owns mounting. This protects Mountify/Hybrid/Magic Mount from a
# recursive OverlayFS stack during Android second-stage boot.
POST_MODULE="$TMP/post-module"
POST_CALLED="$TMP/post-mount-called"
POST_FAKE_MOUNT="$TMP/post-fake-mount.sh"
mkdir -p "$POST_MODULE/config" "$POST_MODULE/logs"
ln -s "$ROOT/common" "$POST_MODULE/common"
cp -f "$ROOT/post-mount.sh" "$POST_MODULE/post-mount.sh"
printf 'Demo\n' > "$POST_MODULE/config/active_font.conf"
cat > "$POST_FAKE_MOUNT" <<EOF_POST_FAKE
#!/bin/sh
printf 'called\n' > "$POST_CALLED"
exit 1
EOF_POST_FAKE
chmod 0755 "$POST_FAKE_MOUNT"

for engine in mountify hybrid-mount magic-mount meta-overlayfs; do
    rm -f "$POST_CALLED" "$POST_MODULE/config/self-mount.conf"
    KSU=1 LUOSHU_META_TEST_ENGINE="$engine" \
    LUOSHU_SELF_MOUNT_COMMAND="$POST_FAKE_MOUNT" \
    LUOSHU_SELF_MOUNT_STATE_ROOT="$TMP/post-state" \
        sh "$POST_MODULE/post-mount.sh"
    [ ! -e "$POST_CALLED" ]
    [ "$(sed -n 's/^state=//p' "$POST_MODULE/config/self-mount.conf")" = delegated ]
    [ "$(sed -n 's/^backend=//p' "$POST_MODULE/config/self-mount.conf")" = "external-$engine" ]
done

# Hybrid Mount v4 uses default_mode and allows a LuoShu-specific rule to override
# the global mode. Validate the non-invasive parser used only for diagnostics.
HYBRID_CFG="$TMP/hybrid-config.toml"
cat > "$HYBRID_CFG" <<'EOF_HYBRID_CFG'
default_mode = "overlay"

[rules.LuoShu]
default_mode = "magic"
EOF_HYBRID_CFG
HYBRID_MODE=$(sh -c '. "$1/common/mount_compat_policy.sh"; _luoshu_hybrid_mode_from_file "$2"' sh "$ROOT" "$HYBRID_CFG")
[ "$HYBRID_MODE" = magic ]

sh -n "$ROOT/common/mount_self_fallback.sh"
sh -n "$ROOT/common/mount_self_backend.sh"
sh -n "$ROOT/common/mount_compat_policy.sh"
sh -n "$ROOT/post-mount.sh"
echo 'LuoShu post-mount self-mount regression checks passed.'
