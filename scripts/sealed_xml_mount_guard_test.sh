#!/bin/sh
# Real backend/control flow; mounts and chcon are mocked, only temp copies change.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
r=$(mktemp -d)
trap 'rm -rf "$r"' EXIT HUP INT TERM
mkdir -p "$r/source" "$r/stock" "$r/state/lower/system-etc"
printf selected > "$r/source/fonts.xml"
printf original > "$r/stock/fonts.xml"
cp "$r/stock/fonts.xml" "$r/state/lower/system-etc/fonts.xml"
. "$ROOT/common/mount_self_backend.sh"
set -eu
_luoshu_self_state_root() { printf '%s/state\n' "$r"; }
_luoshu_prepare_lower_mountpoint() { return 0; }
_luoshu_bind_private_lower() { return 0; }
_luoshu_umount_cmd() { return 0; }
_luoshu_selinux_active() { return 0; }
getenforce() { echo Enforcing; }
getprop() { echo 0; }
id() { echo 0; }
_luoshu_file_context() {
    case "$1" in
        "$r/stock"|"$r/state/lower/system-etc") echo u:object_r:system_file:s0 ;;
        "$r/stock/fonts.xml"|"$r/state/lower/system-etc/fonts.xml") echo u:object_r:font_config:s0 ;;
        *) awk -F'|' -v p="$1" '$1==p{v=$2}END{if(v=="")exit 1;print v}' "$r/labels" ;;
    esac
}
_luoshu_set_file_context() {
    [ "${DENY_LABEL:-0}" = 0 ] || return 1
    [ "${IGNORE_LABEL:-0}" = 0 ] || return 0
    printf '%s|%s\n' "$2" "$1" >> "$r/labels"
}
_luoshu_overlay_memory_layer() (
    source="$1";point="$2";stock="$4";mode="$5"
    mkdir -p "$point"
    cp "$source/fonts.xml" "$point/fonts.xml"
    printf 'f|fonts.xml\n' > "$r/inventory"
    _luoshu_restore_memory_labels "$point" "$stock" "$r/inventory" "$mode"
)
_luoshu_overlay_try() {
    case "$1" in "$r/state/memory-layers/system-etc") printf published > "$r/published"; return 0 ;; *) return 1 ;; esac
}
_lsme_mount_list="$r/state/mounts.list"
LUOSHU_REQUIRED_PAYLOAD_FILES=1
: > "$r/labels"
# A flag without the scoped verifier cannot authorize production labels.
if _luoshu_config_copy_labels_allowed "$r/source" system-etc "$r/stock"; then exit 1; fi
LUOSHU_XML_COPY_LABEL_TEST_APPROVED=true
if _luoshu_config_copy_labels_allowed "$r/source" system-etc "$r/stock"; then exit 1; fi
unset LUOSHU_XML_COPY_LABEL_TEST_APPROVED
_luoshu_universal_xml_copy_check() {
    [ "${DENY_PROOF:-0}" = 0 ] || return 1
    [ -z "${3:-}" ] || _luoshu_config_contexts_match "$3" "$2"
}
# Production callback succeeds with qemu=0 and no experimental flag.
_luoshu_overlay_mount_dir "$r/source" "$r/stock" system-etc
test -s "$r/published"
test "$(cat "$r/stock/fonts.xml")" = original
test "$(cat "$r/state/lower/system-etc/fonts.xml")" = original
if grep -F "$r/stock" "$r/labels"; then exit 1; fi
if grep -F "$r/state/lower" "$r/labels"; then exit 1; fi
for failure in denied ignored proof; do
    rm -f "$r/published"; : > "$r/labels"
    DENY_LABEL=0; IGNORE_LABEL=0; DENY_PROOF=0
    case "$failure" in denied) DENY_LABEL=1 ;; ignored) IGNORE_LABEL=1 ;; proof) DENY_PROOF=1 ;; esac
    rc=0
    _luoshu_overlay_mount_dir "$r/source" "$r/stock" system-etc || rc=$?
    test "$rc" = 3
    test ! -e "$r/published"
done
DENY_LABEL=0; IGNORE_LABEL=0; DENY_PROOF=0
# Capture failure is fatal too, before any direct or copy publication.
_luoshu_bind_private_lower() { return 1; }
rc=0; _luoshu_overlay_mount_dir "$r/source" "$r/stock" system-etc || rc=$?
test "$rc" = 3

# Both callers must distinguish fatal proof failure from ordinary fallback.
for engine in atomic private; do
    (
        MODDIR="$r/module-$engine"; MODULE_DIR="$MODDIR"
        mkdir -p "$MODDIR/config" "$MODDIR/system/fonts" "$MODDIR/system/etc" "$r/visible/system/fonts" "$r/visible/system/etc"
        printf mix > "$MODDIR/config/active_font.conf"
        printf font > "$MODDIR/system/fonts/demo.ttf"
        printf xml > "$MODDIR/system/etc/fonts.xml"
        . "$ROOT/common/mount_self_atomic.sh"
        _luoshu_self_module() { printf '%s\n' "$MODDIR"; }
        _luoshu_self_state_root() { printf '%s/state\n' "$MODDIR"; }
        _luoshu_atomic_prepare_boot_state() { return 1; }
        _luoshu_partition_root() { printf '%s/visible/system\n' "$r"; }
        luoshu_payload_partitions() { echo system; }
        _lfrp_partitions() { echo system; }
        _lfrp_payload_root() { printf '%s\n' "$MODDIR"; }
        _luoshu_self_state_write() { printf '%s\n' "$*" > "$MODDIR/result"; }
        _luoshu_self_log() { :; }
        _luoshu_overlay_mount_dir() { case "$3" in system-etc) return 3 ;; *) return 0 ;; esac; }
        _luoshu_capture_lower_dir() { printf bypass > "$MODDIR/bind-bypass"; }
        _luoshu_atomic_finish_plan() { printf bypass > "$MODDIR/bind-bypass"; }
        _luoshu_atomic_rollback() { printf rollback > "$MODDIR/rolled-back"; }
        if [ "$engine" = private ]; then . "$ROOT/common/font_runtime_mount.sh"; fi
        if luoshu_self_mount_ensure; then exit 1; fi
        test -s "$MODDIR/rolled-back"
        test ! -e "$MODDIR/bind-bypass"
        grep -q sealed-xml-proof-failed "$MODDIR/result"
    )
done
printf 'sealed_xml_mount_guard_test: PASS (mock mounts/labels, production scope, denial, fatal rollback)\n'
