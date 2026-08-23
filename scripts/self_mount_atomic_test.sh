#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "${0%/*}" 2>/dev/null && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." 2>/dev/null && pwd)
ATOMIC_SCRIPT=${ATOMIC_SCRIPT:-$REPO_ROOT/common/mount_self_atomic.sh}
FINAL_SCRIPT=${FINAL_SCRIPT:-}
TEST_ROOT=$(mktemp -d)
trap 'rm -rf "$TEST_ROOT"' EXIT INT TERM

fail() {
    echo "self-mount atomic test failed: $*" >&2
    exit 1
}

setup_case() {
    CASE_ROOT="$TEST_ROOT/$1"
    MODULE_DIR="$CASE_ROOT/module"
    LUOSHU_MOUNT_MODDIR="$MODULE_DIR"
    LUOSHU_SELF_MOUNT_STATE_ROOT="$CASE_ROOT/state"
    LUOSHU_SELF_MOUNT_VISIBLE_ROOT="$CASE_ROOT/root"
    LUOSHU_SELF_PID1_ROOT=/
    export MODULE_DIR LUOSHU_MOUNT_MODDIR LUOSHU_SELF_MOUNT_STATE_ROOT \
        LUOSHU_SELF_MOUNT_VISIBLE_ROOT LUOSHU_SELF_PID1_ROOT
    mkdir -p "$MODULE_DIR/config" "$MODULE_DIR/logs" "$CASE_ROOT/root/system/fonts" \
        "$CASE_ROOT/root/system/etc" "$CASE_ROOT/state"
    printf 'custom\n' > "$MODULE_DIR/config/active_font.conf"
    : > "$CASE_ROOT/unmount.log"
    FAIL_OVERLAY=''
    FAIL_BIND=''
    LUOSHU_TEST_PRIVATE_PAYLOAD_ROOT=''
}

_luoshu_self_module() { printf '%s\n' "$MODULE_DIR"; }
_luoshu_self_state_root() { printf '%s\n' "$LUOSHU_SELF_MOUNT_STATE_ROOT"; }
_luoshu_self_log() { printf '%s\n' "$*" >> "$MODULE_DIR/logs/self-mount.log"; }
_luoshu_self_state_write() {
    {
        printf 'state=%s\n' "$1"
        printf 'backend=%s\n' "$2"
        printf 'mounted=%s\n' "$3"
        printf 'failed=%s\n' "$4"
    } > "$MODULE_DIR/config/self-mount.conf"
}
_luoshu_self_state_value() {
    sed -n "s/^${1}=//p" "$MODULE_DIR/config/self-mount.conf" 2>/dev/null | head -n1
}
luoshu_payload_partitions() { printf '%s\n' 'system product system_ext'; }
_lfrp_partitions() { luoshu_payload_partitions; }
_lfrp_payload_root() {
    printf '%s\n' "${LUOSHU_TEST_PRIVATE_PAYLOAD_ROOT:-$MODULE_DIR}"
}
_luoshu_partition_root() {
    case "$1" in
        system)
            test -d "$LUOSHU_SELF_MOUNT_VISIBLE_ROOT/system" || return 1
            printf '%s/system\n' "$LUOSHU_SELF_MOUNT_VISIBLE_ROOT"
            ;;
        product|system_ext)
            test -d "$LUOSHU_SELF_MOUNT_VISIBLE_ROOT/$1" || return 1
            printf '%s/%s\n' "$LUOSHU_SELF_MOUNT_VISIBLE_ROOT" "$1"
            ;;
        *) return 1 ;;
    esac
}
_luoshu_overlay_mount_dir() {
    test "${FAIL_OVERLAY:-}" != all && test "${FAIL_OVERLAY:-}" != "$3" || return 1
    cp -R "$1/." "$2/"
}
_luoshu_mount_cmd() {
    test "$1" = -o && test "$2" = bind || return 1
    test "${FAIL_BIND:-}" != "$4" || return 1
    cp -f "$3" "$4"
}
_luoshu_umount_cmd() {
    printf '%s\n' "$1" >> "$CASE_ROOT/unmount.log"
    return 0
}
luoshu_mount_record() {
    printf '%s|%s\n' "$1" "$2" > "$MODULE_DIR/config/mount-record.txt"
}

. "$ATOMIC_SCRIPT"
[ -z "$FINAL_SCRIPT" ] || . "$FINAL_SCRIPT"
# mount_self_backend.sh owns the production OverlayFS helper. Replace it with
# the deterministic fixture after loading the selected final implementation.
_luoshu_overlay_mount_dir() {
    test "${FAIL_OVERLAY:-}" != all && test "${FAIL_OVERLAY:-}" != "$3" || return 1
    cp -R "$1/." "$2/"
}
CURRENT_BOOT_ID=test-boot
_luoshu_atomic_boot_id() { printf '%s\n' "$CURRENT_BOOT_ID"; }

setup_case success
mkdir -p "$MODULE_DIR/system/fonts" "$MODULE_DIR/system/etc"
printf 'new-font\n' > "$MODULE_DIR/system/fonts/Roboto.ttf"
printf 'new-xml\n' > "$MODULE_DIR/system/etc/fonts.xml"
printf 'stock-font\n' > "$CASE_ROOT/root/system/fonts/Roboto.ttf"
printf 'stock-xml\n' > "$CASE_ROOT/root/system/etc/fonts.xml"
luoshu_self_mount_ensure || fail 'complete overlay transaction returned failure'
grep -q '^state=mounted$' "$MODULE_DIR/config/self-mount.conf" || fail 'success was not recorded as mounted'
test "$(wc -l < "$MODULE_DIR/config/self-mount-required.conf" | tr -d ' ')" -eq 2 || fail 'required manifest is incomplete'
luoshu_mount_verify_active custom || fail 'strict verifier rejected a complete transaction'
grep -q '^verified|' "$MODULE_DIR/config/mount-record.txt" || fail 'verified record missing'
printf 'state=degraded\nbackend=legacy\nmounted=system/fonts\nfailed=system/etc\n' > "$MODULE_DIR/config/self-mount.conf"
if luoshu_mount_verify_active custom; then
    fail 'legacy degraded state was accepted'
fi

setup_case stale-journal
printf 'default\n' > "$MODULE_DIR/config/active_font.conf"
printf 'old-boot\n' > "$CASE_ROOT/state/boot-id"
printf '%s\n' "$CASE_ROOT/root/system/fonts" > "$CASE_ROOT/state/mounts.list"
luoshu_self_mount_ensure || fail 'default-font stale-journal cleanup failed'
test ! -s "$CASE_ROOT/unmount.log" || fail 'stale boot journal unmounted a potentially foreign target'

setup_case same-boot-journal
printf 'default\n' > "$MODULE_DIR/config/active_font.conf"
printf '%s\n' "$CURRENT_BOOT_ID" > "$CASE_ROOT/state/boot-id"
printf '%s\n' "$CASE_ROOT/root/system/fonts" > "$CASE_ROOT/state/mounts.list"
luoshu_self_mount_ensure || fail 'same-boot journal cleanup failed'
test -s "$CASE_ROOT/unmount.log" || fail 'same-boot LuoShu mount was not rolled back'

setup_case rollback
mkdir -p "$MODULE_DIR/system/fonts" "$MODULE_DIR/system/etc" "$MODULE_DIR/product/etc" \
    "$CASE_ROOT/root/product/etc"
printf 'new-font\n' > "$MODULE_DIR/system/fonts/Roboto.ttf"
printf 'new-xml\n' > "$MODULE_DIR/system/etc/fonts.xml"
printf 'product-xml\n' > "$MODULE_DIR/product/etc/fonts.xml"
printf 'stock-font\n' > "$CASE_ROOT/root/system/fonts/Roboto.ttf"
printf 'stock-xml\n' > "$CASE_ROOT/root/system/etc/fonts.xml"
printf 'stock-product\n' > "$CASE_ROOT/root/product/etc/fonts.xml"
FAIL_OVERLAY=product-etc
FAIL_BIND="$CASE_ROOT/root/product/etc/fonts.xml"
if luoshu_self_mount_ensure; then
    fail 'partial product/etc failure was accepted'
fi
grep -q '^state=failed$' "$MODULE_DIR/config/self-mount.conf" || fail 'rollback failure state missing'
grep -q 'product/etc-bind-incomplete' "$MODULE_DIR/config/self-mount.conf" || fail 'failed component not recorded'
test ! -e "$MODULE_DIR/config/self-mount-required.conf" || fail 'failed manifest was committed'
test -s "$CASE_ROOT/unmount.log" || fail 'partial mounts were not rolled back'
if grep -q '^state=degraded$' "$MODULE_DIR/config/self-mount.conf"; then
    fail 'degraded state survived atomic policy'
fi

setup_case missing-root
mkdir -p "$MODULE_DIR/system/fonts" "$MODULE_DIR/product/etc"
printf 'new-font\n' > "$MODULE_DIR/system/fonts/Roboto.ttf"
printf 'stock-font\n' > "$CASE_ROOT/root/system/fonts/Roboto.ttf"
printf 'product-xml\n' > "$MODULE_DIR/product/etc/fonts.xml"
luoshu_self_mount_ensure || fail 'missing optional payload partition root rolled back system/fonts'
grep -q '^state=mounted$' "$MODULE_DIR/config/self-mount.conf" || fail 'optional missing partition was not skipped'
grep -q '^failed=$' "$MODULE_DIR/config/self-mount.conf" || fail 'optional missing partition was recorded as failure'
test "$(wc -l < "$MODULE_DIR/config/self-mount-required.conf" | tr -d ' ')" -eq 1 || fail 'missing optional root entered required manifest'

setup_case missing-optional-target
mkdir -p "$MODULE_DIR/system/fonts" "$MODULE_DIR/system_ext/fonts" "$CASE_ROOT/root/system_ext"
printf 'new-font\n' > "$MODULE_DIR/system/fonts/Roboto.ttf"
printf 'extension-font\n' > "$MODULE_DIR/system_ext/fonts/Extension.ttf"
printf 'stock-font\n' > "$CASE_ROOT/root/system/fonts/Roboto.ttf"
luoshu_self_mount_ensure || fail 'missing optional system_ext/fonts target rolled back system/fonts'
grep -q '^state=mounted$' "$MODULE_DIR/config/self-mount.conf" || fail 'optional missing target was not skipped'
grep -q '^failed=$' "$MODULE_DIR/config/self-mount.conf" || fail 'optional missing target was recorded as failure'
test "$(wc -l < "$MODULE_DIR/config/self-mount-required.conf" | tr -d ' ')" -eq 1 || fail 'missing optional target entered required manifest'

if [ -n "$FINAL_SCRIPT" ]; then
    setup_case kernelsu-private-payload-missing-optional-target
    LUOSHU_TEST_PRIVATE_PAYLOAD_ROOT="$MODULE_DIR/.luoshu-payload"
    mkdir -p "$LUOSHU_TEST_PRIVATE_PAYLOAD_ROOT/system/fonts" "$LUOSHU_TEST_PRIVATE_PAYLOAD_ROOT/system_ext/fonts" "$CASE_ROOT/root/system_ext"
    printf 'new-font\n' > "$LUOSHU_TEST_PRIVATE_PAYLOAD_ROOT/system/fonts/Roboto.ttf"
    printf 'extension-font\n' > "$LUOSHU_TEST_PRIVATE_PAYLOAD_ROOT/system_ext/fonts/Extension.ttf"
    printf 'stock-font\n' > "$CASE_ROOT/root/system/fonts/Roboto.ttf"
    luoshu_self_mount_ensure || fail 'KernelSU private payload rolled back on missing optional system_ext/fonts'
    grep -q '^state=mounted$' "$MODULE_DIR/config/self-mount.conf" || fail 'KernelSU private payload was not committed'
    grep -q '^failed=$' "$MODULE_DIR/config/self-mount.conf" || fail 'KernelSU private optional target was recorded as failure'
    test "$(wc -l < "$MODULE_DIR/config/self-mount-required.conf" | tr -d ' ')" -eq 1 || fail 'KernelSU private optional target entered required manifest'
fi

setup_case bind-compatible-alias
mkdir -p "$MODULE_DIR/system/fonts"
printf 'font-a\n' > "$MODULE_DIR/system/fonts/A.ttf"
printf 'font-b\n' > "$MODULE_DIR/system/fonts/B.ttf"
printf 'stock-a\n' > "$CASE_ROOT/root/system/fonts/A.ttf"
FAIL_OVERLAY=system-fonts
luoshu_self_mount_ensure || fail 'bind fallback rejected a device-compatible existing target'
grep -q '^state=mounted$' "$MODULE_DIR/config/self-mount.conf" || fail 'bind fallback success was not recorded'
grep -q '^backend=self-overlay-bind$' "$MODULE_DIR/config/self-mount.conf" || fail 'bind fallback backend missing'
test "$(cat "$CASE_ROOT/root/system/fonts/A.ttf")" = 'font-a' || fail 'existing bind target was not replaced'
test ! -e "$CASE_ROOT/root/system/fonts/B.ttf" || fail 'bind fallback created an additive ROM alias'
luoshu_mount_verify_active custom || fail 'strict verifier rejected compatible bind fallback'

setup_case bind-symlink-alias
mkdir -p "$MODULE_DIR/system/fonts"
printf 'font-alias\n' > "$MODULE_DIR/system/fonts/Alias.ttf"
printf 'font-canonical\n' > "$MODULE_DIR/system/fonts/Canonical.ttf"
printf 'stock-canonical\n' > "$CASE_ROOT/root/system/fonts/Canonical.ttf"
ln -s Canonical.ttf "$CASE_ROOT/root/system/fonts/Alias.ttf"
FAIL_OVERLAY=system-fonts
luoshu_self_mount_ensure || fail 'bind fallback rejected aliases sharing one real ROM target'
grep -q '^state=mounted$' "$MODULE_DIR/config/self-mount.conf" || fail 'symlink bind fallback was not committed'
test "$(cat "$CASE_ROOT/root/system/fonts/Canonical.ttf")" = 'font-canonical' || fail 'canonical bind target was overwritten by its alias'
test "$(cat "$CASE_ROOT/root/system/fonts/Alias.ttf")" = 'font-canonical' || fail 'ROM alias does not expose the canonical bound font'
luoshu_mount_verify_active custom || fail 'strict verifier rejected a deduplicated symlink bind'

setup_case bind-additive-etc
mkdir -p "$MODULE_DIR/system/fonts" "$MODULE_DIR/system/etc/luoshu"
printf 'font-a\n' > "$MODULE_DIR/system/fonts/A.ttf"
printf 'dynamic-config\n' > "$MODULE_DIR/system/etc/.luoshu-data-fonts-config.xml"
printf 'probe\n' > "$MODULE_DIR/system/etc/luoshu/mount-probe.conf"
printf 'stock-a\n' > "$CASE_ROOT/root/system/fonts/A.ttf"
FAIL_OVERLAY=all
luoshu_self_mount_ensure || fail 'additive-only system/etc rejected an otherwise complete font bind'
grep -q '^state=mounted$' "$MODULE_DIR/config/self-mount.conf" || fail 'additive-only etc skip was not committed'
test "$(wc -l < "$MODULE_DIR/config/self-mount-required.conf" | tr -d ' ')" -eq 1 || fail 'skipped additive component entered the required manifest'
test "$(cat "$CASE_ROOT/root/system/fonts/A.ttf")" = 'font-a' || fail 'font bind was lost while skipping additive etc'
test ! -e "$CASE_ROOT/root/system/etc/.luoshu-data-fonts-config.xml" || fail 'bind fallback created a missing dynamic config target'
luoshu_mount_verify_active custom || fail 'strict verifier rejected the font-only compatible bind'

setup_case bind-no-compatible-target
mkdir -p "$MODULE_DIR/system/fonts"
printf 'font-a\n' > "$MODULE_DIR/system/fonts/A.ttf"
printf 'font-b\n' > "$MODULE_DIR/system/fonts/B.ttf"
FAIL_OVERLAY=system-fonts
if luoshu_self_mount_ensure; then
    fail 'bind fallback with no device-compatible target was accepted'
fi
grep -q 'system/fonts-bind-empty' "$MODULE_DIR/config/self-mount.conf" || fail 'empty bind reason absent'

echo "self-mount transaction tests passed: ${FINAL_SCRIPT:-atomic}"

if [ -z "$FINAL_SCRIPT" ]; then
    FINAL_SCRIPT="$REPO_ROOT/common/mount_self_backend.sh" sh "$0"
    FINAL_SCRIPT="$REPO_ROOT/common/font_runtime_mount.sh" sh "$0"
fi
