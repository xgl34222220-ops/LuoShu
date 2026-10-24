#!/bin/sh
# Regression for the casefold-F2FS OverlayFS loop-image fallback.
#  - normal overlay success never loads or calls the loop layer;
#  - an overlay failure without a casefold rejection keeps the bind fallback;
#  - casefold rejections already logged before the attempt are ignored; only
#    a rejection added by this overlay attempt enables the loop retry;
#  - a casefold rejection retries overlay with a read-only ext4 loop lower,
#    journaled before the captured stock lower so rollback releases it last;
#  - a failed retry releases the layer and still falls back to bind;
#  - Hybrid Mount / Mountify route probes are read-only and conservative.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-ovl-loop)
trap '[ -n "${KEEP_TMP:-}" ] || rm -rf "$TMP"' EXIT HUP INT TERM

fail() {
    echo "overlay loop layer test failed: $*" >&2
    exit 1
}

FAKE_MOUNT="$TMP/fake-mount.sh"
FAKE_UMOUNT="$TMP/fake-umount.sh"
FAKE_MKFS="$TMP/fake-mke2fs.sh"

# Mountinfo lines: "0 0 0:0 / <mountpoint> <opts> - <type> <source> rw".
cat > "$FAKE_MOUNT" <<'EOF_FAKE_MOUNT'
#!/bin/sh
set -eu
mi=${LUOSHU_SELF_MOUNTINFO:?}
log=${LUOSHU_TEST_MOUNT_LOG:?}
printf '%s\n' "$*" >> "$log"
record() { printf '0 0 0:0 / %s %s - %s %s rw\n' "$1" "$2" "$3" "$4" >> "$mi"; }
stash() {
    rm -rf "$1.test-stock"
    if [ -e "$1" ]; then mv "$1" "$1.test-stock"; else mkdir -p "$1.test-stock"; fi
}
case "$1" in
    --make-*) exit 0 ;;
    -o)
        case "$2" in
            bind)
                stash "$4"
                if [ -d "$3" ]; then mkdir -p "$4"; cp -a "$3/." "$4/"; else cp -a "$3" "$4"; fi
                record "$4" rw bind "$3"
                ;;
            remount,ro)
                awk -v t="$3" '$5==t {$6="ro"} {print}' "$mi" > "$mi.tmp" && mv "$mi.tmp" "$mi"
                ;;
            *) exit 2 ;;
        esac
        ;;
    -t)
        case "$2" in
            overlay)
                [ "$3" = KSU ] && [ "$4" = -o ] || exit 2
                layers=${5#lowerdir=}
                top=${layers%%:*}
                stock=${layers#*:}
                target=$6
                [ "${LUOSHU_TEST_FAIL_ALL_OVERLAY:-0}" != 1 ] || exit 1
                case "$top" in
                    "${LUOSHU_TEST_CASEFOLD_ROOT:-/nonexistent}"*)
                        printf '[  1.0] overlayfs: case-insensitive capable filesystem on %s not supported\n' \
                            "$top" >> "$LUOSHU_OVERLAY_DMESG_FILE"
                        exit 1
                        ;;
                esac
                [ "${LUOSHU_TEST_FAIL_LOOP_OVERLAY:-0}" != 1 ] || case "$top" in */work/overlay-*) exit 1 ;; esac
                stash "$target"
                mkdir -p "$target"
                cp -a "$stock/." "$target/"
                cp -a "$top/." "$target/"
                record "$target" ro overlay KSU
                ;;
            ext4)
                [ "$3" = -o ] || exit 2
                case "$4" in loop,*) ;; *) exit 2 ;; esac
                [ -d "$5.tree" ] || exit 1
                mkdir -p "$6"
                cp -a "$5.tree/." "$6/"
                record "$6" rw ext4 /dev/block/loop9
                ;;
            *) exit 2 ;;
        esac
        ;;
    *) exit 2 ;;
esac
EOF_FAKE_MOUNT

cat > "$FAKE_UMOUNT" <<'EOF_FAKE_UMOUNT'
#!/bin/sh
set -eu
mi=${LUOSHU_SELF_MOUNTINFO:?}
printf '%s\n' "$1" >> "${LUOSHU_TEST_UMOUNT_LOG:?}"
awk -v t="$1" '$5==t {found=1} END {exit !found}' "$mi" || exit 1
awk -v t="$1" '$5!=t {print}' "$mi" > "$mi.tmp" && mv "$mi.tmp" "$mi"
if [ -d "$1.test-stock" ]; then
    rm -rf "$1"
    mv "$1.test-stock" "$1"
fi
EOF_FAKE_UMOUNT

# Stand-in for Android e2fsprogs: records its argv and keeps a copy of the
# populated tree next to the image so the fake loop mount can expose it.
cat > "$FAKE_MKFS" <<'EOF_FAKE_MKFS'
#!/bin/sh
set -eu
printf '%s\n' "$*" >> "${LUOSHU_TEST_MKFS_LOG:?}"
src=''
img=''
while [ "$#" -gt 0 ]; do
    case "$1" in
        -d) src="$2"; shift 2 ;;
        -t|-b|-I|-m|-N|-O) shift 2 ;;
        -q) shift ;;
        *) img="$1"; shift ;;
    esac
done
case " $(cat "${LUOSHU_TEST_MKFS_LOG}") " in *'^casefold'*) ;; *) exit 1 ;; esac
[ -n "$src" ] && [ -f "$img" ] || exit 1
rm -rf "$img.tree"
mkdir -p "$img.tree/lost+found"
cp -a "$src/." "$img.tree/"
EOF_FAKE_MKFS
chmod 0755 "$FAKE_MOUNT" "$FAKE_UMOUNT" "$FAKE_MKFS"

setup_case() {
    CASE="$TMP/$1"
    MODULE="$CASE/module"
    VISIBLE="$CASE/visible"
    STATE="$CASE/state"
    mkdir -p "$MODULE/system/fonts" "$MODULE/config" "$MODULE/logs" \
        "$VISIBLE/system/fonts" "$STATE"
    ln -s "$ROOT/common" "$MODULE/common"
    printf 'new-font\n' > "$MODULE/system/fonts/Roboto-Regular.ttf"
    printf 'new-cjk\n' > "$MODULE/system/fonts/NotoSansCJK-Regular.ttc"
    printf 'stock-font\n' > "$VISIBLE/system/fonts/Roboto-Regular.ttf"
    printf 'stock-cjk\n' > "$VISIBLE/system/fonts/NotoSansCJK-Regular.ttc"
    printf 'stock-emoji\n' > "$VISIBLE/system/fonts/NotoColorEmoji.ttf"
    printf 'Demo\n' > "$MODULE/config/active_font.conf"
    : > "$CASE/mountinfo"
    : > "$CASE/dmesg"
    : > "$CASE/mount.log"
    : > "$CASE/umount.log"
    : > "$CASE/mkfs.log"
}

# run_case NAME [VAR=value ...] -- shell snippet executed after the real mount
# runtime (fallback + atomic + backend) is loaded with a visible-root sandbox.
run_case() {
    _rc_name="$1"
    shift
    _rc_env=''
    while [ "$#" -gt 0 ] && [ "$1" != -- ]; do
        _rc_env="$_rc_env $1"
        shift
    done
    shift
    setup_case "$_rc_name"
    # shellcheck disable=SC2086
    env \
        MODDIR="$MODULE" MODULE_DIR="$MODULE" LUOSHU_MOUNT_MODDIR="$MODULE" \
        LUOSHU_SELF_MOUNT_VISIBLE_ROOT="$VISIBLE" \
        LUOSHU_SELF_MOUNT_STATE_ROOT="$STATE" \
        LUOSHU_SELF_PID1_ROOT=/ \
        LUOSHU_SELF_VERIFY_DELAY=0 \
        LUOSHU_SELF_MOUNT_COMMAND="$FAKE_MOUNT" \
        LUOSHU_SELF_UMOUNT_COMMAND="$FAKE_UMOUNT" \
        LUOSHU_SELF_MOUNTINFO="$CASE/mountinfo" \
        LUOSHU_OVERLAY_DMESG_FILE="$CASE/dmesg" \
        LUOSHU_OVERLAY_SKIP_SELINUX=1 \
        LUOSHU_TEST_MOUNT_LOG="$CASE/mount.log" \
        LUOSHU_TEST_UMOUNT_LOG="$CASE/umount.log" \
        LUOSHU_TEST_MKFS_LOG="$CASE/mkfs.log" \
        LUOSHU_TEST_CASEFOLD_ROOT="${LUOSHU_TEST_CASEFOLD_ROOT_VALUE:-/nonexistent}" \
        CASE="$CASE" FAKE_MKFS="$FAKE_MKFS" \
        $_rc_env \
        sh -c '
            set +e
            . "$MODDIR/common/mount_self_fallback.sh"
            . "$MODDIR/common/mount_self_atomic.sh"
            . "$MODDIR/common/mount_self_backend.sh"
            luoshu_payload_partitions() { printf "system\n"; }
            set -e
            eval "$1"
        ' sh "$1" || fail "$_rc_name"
}

state_value() { sed -n "s/^$1=//p" "$MODULE/config/self-mount.conf" | head -n1; }

# 1. Normal overlay: the loop layer is neither loaded nor invoked.
run_case normal -- '
    luoshu_self_mount_ensure
    ! type luoshu_overlay_prepare_ext4_layer >/dev/null 2>&1
    ! type luoshu_overlay_release_ext4_layer >/dev/null 2>&1
'
[ "$(state_value state)" = mounted ] || fail 'normal: state'
[ "$(state_value backend)" = self-overlay ] || fail 'normal: backend'
[ "$(cat "$VISIBLE/system/fonts/Roboto-Regular.ttf")" = new-font ] || fail 'normal: payload'
[ "$(cat "$VISIBLE/system/fonts/NotoColorEmoji.ttf")" = stock-emoji ] || fail 'normal: stock'
[ ! -s "$CASE/mkfs.log" ] || fail 'normal: formatter called'
! grep -q 'ext4' "$CASE/mount.log" || fail 'normal: loop mount attempted'
! grep -q '/work/overlay-' "$STATE/mounts.list" || fail 'normal: layer journaled'

# 2. Overlay refused for another reason: bind fallback, no loop layer.
run_case plain-reject LUOSHU_TEST_FAIL_ALL_OVERLAY=1 LUOSHU_OVERLAY_FORMATTER="$FAKE_MKFS" -- '
    luoshu_self_mount_ensure
'
[ "$(state_value state)" = mounted ] || fail 'plain-reject: state'
[ "$(state_value backend)" = self-overlay-bind ] || fail 'plain-reject: backend'
[ ! -s "$CASE/mkfs.log" ] || fail 'plain-reject: formatter called'
[ -z "$(find "$STATE" -name 'overlay-*' -print -quit)" ] || fail 'plain-reject: layer left behind'

# 2b. Stale casefold rejections from earlier mounts (already in the kernel
# log) plus an unrelated overlay failure: still the plain bind fallback.
run_case stale-casefold LUOSHU_TEST_FAIL_ALL_OVERLAY=1 LUOSHU_OVERLAY_FORMATTER="$FAKE_MKFS" -- '
    printf "[  0.5] overlayfs: case-insensitive capable filesystem on fonts not supported\n" >> "$LUOSHU_OVERLAY_DMESG_FILE"
    printf "[  0.6] overlayfs: case-insensitive capable filesystem on media not supported\n" >> "$LUOSHU_OVERLAY_DMESG_FILE"
    luoshu_self_mount_ensure
    ! type luoshu_overlay_prepare_ext4_layer >/dev/null 2>&1
'
[ "$(state_value backend)" = self-overlay-bind ] || fail 'stale-casefold: backend'
[ ! -s "$CASE/mkfs.log" ] || fail 'stale-casefold: formatter called'
[ -z "$(find "$STATE" -name 'overlay-*' -print -quit)" ] || fail 'stale-casefold: layer left behind'

# 2c. Counter semantics: unreadable log reads 0; retry needs a strict increase.
run_case counter LUOSHU_OVERLAY_FORMATTER="$FAKE_MKFS" -- '
    [ "$(LUOSHU_OVERLAY_DMESG_FILE=/nonexistent _luoshu_overlay_casefold_rejections)" = 0 ]
    printf "overlayfs: case-insensitive capable filesystem on x not supported\n" >> "$LUOSHU_OVERLAY_DMESG_FILE"
    [ "$(_luoshu_overlay_casefold_rejections)" = 1 ]
    ! luoshu_overlay_loop_retry "$MODDIR/system/fonts" "$LUOSHU_SELF_MOUNT_VISIBLE_ROOT/system/fonts" k "$CASE/l" 1
    ! luoshu_overlay_loop_retry "$MODDIR/system/fonts" "$LUOSHU_SELF_MOUNT_VISIBLE_ROOT/system/fonts" k "$CASE/l" ""
    ! type luoshu_overlay_prepare_ext4_layer >/dev/null 2>&1
'
[ ! -s "$CASE/mkfs.log" ] || fail 'counter: formatter called'

# 3. Casefold rejection: overlay retried on a read-only ext4 loop lower.
LUOSHU_TEST_CASEFOLD_ROOT_VALUE="$TMP/casefold/module" \
run_case casefold LUOSHU_OVERLAY_FORMATTER="$FAKE_MKFS" -- '
    luoshu_self_mount_ensure
    list="$LUOSHU_SELF_MOUNT_STATE_ROOT/mounts.list"
    layer="$LUOSHU_SELF_MOUNT_STATE_ROOT/work/overlay-system-fonts"
    lower="$LUOSHU_SELF_MOUNT_STATE_ROOT/lower/system-fonts"
    target="$LUOSHU_SELF_MOUNT_VISIBLE_ROOT/system/fonts"
    [ "$(sed -n 1p "$list")" = "$layer" ]
    [ "$(sed -n 2p "$list")" = "$lower" ]
    [ "$(sed -n 3p "$list")" = "$target" ]
    awk -v t="$layer" '\''$5==t && $6=="ro" {ok=1} END {exit !ok}'\'' "$LUOSHU_SELF_MOUNTINFO"
    [ ! -e "$layer/lost+found" ]
    grep -q "lowerdir=$layer:$lower" "$LUOSHU_TEST_MOUNT_LOG"
    grep -q -- "-O ^has_journal,^casefold" "$LUOSHU_TEST_MKFS_LOG"
    _luoshu_atomic_verify_manifest "$MODDIR/config/self-mount-required.conf"
    # Reverse-order rollback releases overlay, captured lower, then the layer.
    _luoshu_atomic_rollback "$list"
    [ "$(sed -n 1p "$LUOSHU_TEST_UMOUNT_LOG")" = "$target" ]
    [ "$(sed -n 2p "$LUOSHU_TEST_UMOUNT_LOG")" = "$lower" ]
    [ "$(sed -n 3p "$LUOSHU_TEST_UMOUNT_LOG")" = "$layer" ]
    [ ! -e "$LUOSHU_SELF_MOUNT_STATE_ROOT/work" ]
    [ "$(cat "$target/Roboto-Regular.ttf")" = stock-font ]
'
# setup_case places the module under $TMP/casefold/module, matching the root.
[ "$(state_value state)" = mounted ] || fail 'casefold: state'
[ "$(state_value backend)" = self-overlay ] || fail 'casefold: backend'
grep -q 'ext4 loop 兼容层挂载' "$MODULE/logs/self-mount.log" || fail 'casefold: log'

# 4. Casefold rejection, loop retry also refused: layer released, bind kept.
LUOSHU_TEST_CASEFOLD_ROOT_VALUE="$TMP/casefold-retry/module" \
run_case casefold-retry LUOSHU_OVERLAY_FORMATTER="$FAKE_MKFS" LUOSHU_TEST_FAIL_LOOP_OVERLAY=1 -- '
    luoshu_self_mount_ensure
    ! grep -q "/work/overlay-" "$LUOSHU_SELF_MOUNT_STATE_ROOT/mounts.list"
    ! awk '\''$5 ~ /\/work\/overlay-/ {f=1} END {exit !f}'\'' "$LUOSHU_SELF_MOUNTINFO"
    [ ! -e "$LUOSHU_SELF_MOUNT_STATE_ROOT/work/overlay-system-fonts.img" ]
'
[ "$(state_value state)" = mounted ] || fail 'casefold-retry: state'
[ "$(state_value backend)" = self-overlay-bind ] || fail 'casefold-retry: backend'
[ -s "$CASE/mkfs.log" ] || fail 'casefold-retry: layer never attempted'

# 4b. SELinux labels: the layer mirrors payload labels (unlabelled entries
# take the stock target's label) and a label that does not stick is refused.
SEBIN="$TMP/sebin"
mkdir -p "$SEBIN" "$TMP/selinuxfs"
: > "$TMP/selinuxfs/enforce"
cat > "$SEBIN/ls" <<'EOF_FAKE_LS'
#!/bin/sh
if [ "$1" = -Zd ]; then
    ctx=$(awk -v p="$2" -F'|' '$1 == p { c = $2 } END { print c }' "$LUOSHU_TEST_CTX_DB" 2>/dev/null)
    case "$ctx:$2" in
        :*/module/system/fonts/Roboto-Regular.ttf) ctx=u:object_r:luoshu_font_file:s0 ;;
        :*/visible/system/fonts) ctx=u:object_r:system_file:s0 ;;
        :*/module/*) ctx='?' ;;
        :*) ctx='?' ;;
    esac
    printf '%s %s\n' "$ctx" "$2"
    exit 0
fi
exec /bin/ls "$@"
EOF_FAKE_LS
cat > "$SEBIN/chcon" <<'EOF_FAKE_CHCON'
#!/bin/sh
[ "$1" = -h ] && shift
case "$2" in *"${LUOSHU_TEST_CHCON_IGNORE:-/nonexistent}") exit 0 ;; esac
printf '%s|%s\n' "$2" "$1" >> "$LUOSHU_TEST_CTX_DB"
EOF_FAKE_CHCON
chmod 0755 "$SEBIN/ls" "$SEBIN/chcon"

LUOSHU_TEST_CASEFOLD_ROOT_VALUE="$TMP/casefold-selinux/module" \
run_case casefold-selinux PATH="$SEBIN:$PATH" LUOSHU_OVERLAY_SKIP_SELINUX=0 \
    LUOSHU_OVERLAY_SELINUXFS="$TMP/selinuxfs" LUOSHU_TEST_CTX_DB="$TMP/ctx-ok.db" \
    LUOSHU_OVERLAY_FORMATTER="$FAKE_MKFS" -- '
    luoshu_self_mount_ensure
    layer="$LUOSHU_SELF_MOUNT_STATE_ROOT/work/overlay-system-fonts"
    grep -qx "$layer|u:object_r:system_file:s0" "$LUOSHU_TEST_CTX_DB"
    grep -qx "$layer/Roboto-Regular.ttf|u:object_r:luoshu_font_file:s0" "$LUOSHU_TEST_CTX_DB"
    grep -qx "$layer/NotoSansCJK-Regular.ttc|u:object_r:system_file:s0" "$LUOSHU_TEST_CTX_DB"
'
[ "$(state_value backend)" = self-overlay ] || fail 'casefold-selinux: backend'

LUOSHU_TEST_CASEFOLD_ROOT_VALUE="$TMP/casefold-badlabel/module" \
run_case casefold-badlabel PATH="$SEBIN:$PATH" LUOSHU_OVERLAY_SKIP_SELINUX=0 \
    LUOSHU_OVERLAY_SELINUXFS="$TMP/selinuxfs" LUOSHU_TEST_CTX_DB="$TMP/ctx-bad.db" \
    LUOSHU_TEST_CHCON_IGNORE=/NotoSansCJK-Regular.ttc \
    LUOSHU_OVERLAY_FORMATTER="$FAKE_MKFS" -- '
    luoshu_self_mount_ensure
    ! grep -q "/work/overlay-" "$LUOSHU_SELF_MOUNT_STATE_ROOT/mounts.list"
    ! awk '\''$5 ~ /\/work\/overlay-/ {f=1} END {exit !f}'\'' "$LUOSHU_SELF_MOUNTINFO"
'
[ "$(state_value backend)" = self-overlay-bind ] || fail 'casefold-badlabel: backend'
grep -q 'SELinux 标签\|标签校验失败' "$MODULE/logs/self-mount.log" || fail 'casefold-badlabel: log'

# 5. Casefold rejection without a usable formatter: plain bind fallback.
LUOSHU_TEST_CASEFOLD_ROOT_VALUE="$TMP/no-formatter/module" \
run_case no-formatter LUOSHU_OVERLAY_FORMATTER="$TMP/missing-mke2fs" -- '
    luoshu_self_mount_ensure
'
[ "$(state_value backend)" = self-overlay-bind ] || fail 'no-formatter: backend'
[ -z "$(find "$STATE" -name 'overlay-*.img' -print -quit)" ] || fail 'no-formatter: image left behind'

# 6. Kill switch keeps the previous behaviour exactly.
LUOSHU_TEST_CASEFOLD_ROOT_VALUE="$TMP/disabled/module" \
run_case disabled LUOSHU_OVERLAY_LOOP_DISABLE=1 LUOSHU_OVERLAY_FORMATTER="$FAKE_MKFS" -- '
    luoshu_self_mount_ensure
'
[ "$(state_value backend)" = self-overlay-bind ] || fail 'disabled: backend'
[ ! -s "$CASE/mkfs.log" ] || fail 'disabled: formatter called'

# 7. Read-only Hybrid Mount / Mountify route probes.
PROBE="$TMP/probe"
mkdir -p "$PROBE/adb/hybrid-mount" "$PROBE/adb/mountify" "$PROBE/module"
printf 'id=LuoShu\n' > "$PROBE/module/module.prop"
probe() {
    LUOSHU_META_DETECT_ROOT="$PROBE/adb" LUOSHU_MOUNT_MODDIR="$PROBE/module" \
    MODDIR="$PROBE/module" MODULE_DIR="$ROOT" \
        sh -c '. "$1/common/mount_compat_base.sh" >/dev/null 2>&1; "$2"' sh "$ROOT" "$1" | cut -d'|' -f1
}
snapshot() { find "$PROBE" -type f -exec cksum {} + | sort; }

[ "$(probe luoshu_hybrid_route_probe)" = hybrid-config-missing ] || fail 'hybrid missing'
printf 'default_mode = "overlay"\n' > "$PROBE/adb/hybrid-mount/config.toml"
[ "$(probe luoshu_hybrid_route_probe)" = hybrid-route-not-pure-vfs ] || fail 'hybrid global overlay'
printf 'default_mode = "overlay"\n[rules.LuoShu]\ndefault_mode = "vfs" # pure\n' > "$PROBE/adb/hybrid-mount/config.toml"
[ "$(probe luoshu_hybrid_route_probe)" = hybrid-pure-vfs ] || fail 'hybrid module vfs'
printf '[rules.LuoShu.paths]\n"/system/fonts" = "magic"\n' >> "$PROBE/adb/hybrid-mount/config.toml"
[ "$(probe luoshu_hybrid_route_probe)" = hybrid-route-not-pure-vfs ] || fail 'hybrid unsafe path'
printf 'default_mode = "vfs"\nrules.LuoShu = { default_mode = "magic" }\n' > "$PROBE/adb/hybrid-mount/config.toml"
[ "$(probe luoshu_hybrid_route_probe)" = hybrid-config-unverified ] || fail 'hybrid dotted rule'
printf 'default_mode = "vfs"\n' > "$PROBE/adb/hybrid-mount/config.toml"
printf 'blacklist = ["Other", "LuoShu"]\n' > "$PROBE/adb/hybrid-mount/module_blacklist.toml"
[ "$(probe luoshu_hybrid_route_probe)" = hybrid-module-excluded ] || fail 'hybrid blacklist'
printf 'blacklist = "LuoShu"\n' > "$PROBE/adb/hybrid-mount/module_blacklist.toml"
[ "$(probe luoshu_hybrid_route_probe)" = hybrid-config-unverified ] || fail 'hybrid blacklist grammar'
rm -f "$PROBE/adb/hybrid-mount/module_blacklist.toml"
[ "$(probe luoshu_hybrid_route_probe)" = hybrid-pure-vfs ] || fail 'hybrid global vfs'

[ "$(probe luoshu_mountify_route_probe)" = mountify-config-missing ] || fail 'mountify missing'
printf '# mountify\n' > "$PROBE/adb/mountify/config.sh"
[ "$(probe luoshu_mountify_route_probe)" = mountify-all-modules ] || fail 'mountify default'
printf 'mountify_mounts=0\n' > "$PROBE/adb/mountify/config.sh"
[ "$(probe luoshu_mountify_route_probe)" = mountify-mounts-disabled ] || fail 'mountify 0'
printf 'mountify_mounts="1"\n' > "$PROBE/adb/mountify/config.sh"
[ "$(probe luoshu_mountify_route_probe)" = mountify-whitelist-excluded ] || fail 'mountify 1 excluded'
printf 'Other\nLuoShu\n' > "$PROBE/adb/mountify/modules.txt"
[ "$(probe luoshu_mountify_route_probe)" = mountify-whitelist-selected ] || fail 'mountify 1 selected'
: > "$PROBE/module/skip_mountify"
[ "$(probe luoshu_mountify_route_probe)" = mountify-module-skipped ] || fail 'mountify skip marker'
rm -f "$PROBE/module/skip_mountify"
printf 'mountify_mounts=$MODE\n' > "$PROBE/adb/mountify/config.sh"
[ "$(probe luoshu_mountify_route_probe)" = mountify-config-unverified ] || fail 'mountify unverified'

# Probes never modify the provider configuration they read.
before=$(snapshot)
probe luoshu_hybrid_route_probe >/dev/null
probe luoshu_mountify_route_probe >/dev/null
[ "$before" = "$(snapshot)" ] || fail 'probe modified provider files'

# Diagnostics JSON carries both route reasons.
STATUS=$(LUOSHU_META_DETECT_ROOT="$PROBE/adb" LUOSHU_MOUNT_MODDIR="$PROBE/module" \
    MODDIR="$PROBE/module" MODULE_DIR="$ROOT" \
    sh -c '. "$1/common/mount_compat_base.sh" >/dev/null 2>&1; luoshu_mount_status_json' sh "$ROOT")
printf '%s' "$STATUS" | grep -q '"hybridRoute":"hybrid-pure-vfs"' || fail 'status hybridRoute'
printf '%s' "$STATUS" | grep -q '"mountifyRoute":"mountify-config-unverified"' || fail 'status mountifyRoute'
printf '%s' "$STATUS" | python3 -c 'import json,sys; json.load(sys.stdin)' || fail 'status json invalid'

# Static guards: the loop layer is only reachable from the overlay failure path.
sh -n "$ROOT/common/mount_overlay_layer.sh"
sh -n "$ROOT/common/mount_self_backend.sh"
sh -n "$ROOT/common/mount_compat_base.sh"
[ "$(grep -l 'mount_overlay_layer.sh' "$ROOT"/common/*.sh "$ROOT"/*.sh "$ROOT"/.luoshu-runtime/core/*.sh 2>/dev/null \
    | grep -v '/mount_overlay_layer.sh$' | sed 's#.*/##')" = mount_self_backend.sh ] || fail 'unexpected loader'
grep -qx 'common/mount_overlay_layer.sh' "$ROOT/scripts/module_payload_manifest.txt" || fail 'payload manifest'
echo 'LuoShu overlay loop layer regression checks passed.'
