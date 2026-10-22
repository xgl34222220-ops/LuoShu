#!/system/bin/sh
# LuoShu KernelSU emulated-soft-reboot implementation.
#
# ksud (`ksud soft-reboot`) switches to PID 1's mount namespace, runs every
# module's emulated-soft-reboot.sh (5 s wait budget), stops Android, then runs
# post-fs-data/post-mount/service/boot-completed again. The kernel boot_id does
# NOT change, so without this hook LuoShu's same-boot journal would still claim
# the old mounts while metamodules rebuild the layers underneath them.
#
# Contract:
#   * runs only when KernelSU invokes the stage (KSU=true); any other caller is
#     a no-op, so managers without soft reboot keep the current behaviour;
#   * unmounts only targets registered in LuoShu's own journals
#     (self-mount mounts.list, private module-view.mounts), newest first, and
#     only while mountinfo still shows a LuoShu-owned layer at that target, so a
#     foreign module's mount on the same path is never popped;
#   * on success clears the same-boot journal so the next post-mount runs a
#     fresh transaction; on failure keeps the unreleased entries so post-mount
#     falls back to its existing same-boot rollback.
#
# Adapted from 字域 Ziyu v1.4.8 emulated-soft-reboot.sh (作者 酷安@柔性体,
# shishui611-art/Ziyu, GPL-3.0-only). Provider/NoMount/mountify reload parts
# are intentionally not ported: LuoShu never touches other modules' mounts.
set +e
MODDIR="${MODDIR:-$(CDPATH= cd -- "${0%/*}/../.." 2>/dev/null && pwd)}"
MODULE_DIR="$MODDIR"

[ "${KSU:-}" = true ] || exit 0
[ -n "$MODDIR" ] && [ -d "$MODDIR" ] || exit 0
mkdir -p "$MODDIR/config" "$MODDIR/logs" 2>/dev/null || exit 1

LSR_STATE_ROOT="${LUOSHU_SELF_MOUNT_STATE_ROOT:-/data/adb/luoshu/self-mount}"
LSR_PRIVATE_ROOT="${LUOSHU_PRIVATE_STATE_ROOT:-/data/adb/luoshu/private-payload}"
LSR_SELF_LIST="$LSR_STATE_ROOT/mounts.list"
LSR_VIEW_LIST="$LSR_PRIVATE_ROOT/module-view.mounts"
LSR_STAGE="$MODDIR/config/ksu-soft-reboot.conf"
LSR_LOG="$MODDIR/logs/soft-reboot.log"
LSR_MOUNTINFO="${LUOSHU_SOFT_REBOOT_MOUNTINFO:-}"
if [ -z "$LSR_MOUNTINFO" ]; then
    if [ -r /proc/1/mountinfo ]; then LSR_MOUNTINFO=/proc/1/mountinfo
    else LSR_MOUNTINFO=/proc/self/mountinfo
    fi
fi

_lsr_log() {
    printf '[%s] [KSU-SOFT-REBOOT] %s\n' \
        "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$*" \
        >> "$LSR_LOG" 2>/dev/null || true
}

LSR_BOOT="${LUOSHU_TEST_BOOT_ID:-$(cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n')}"
if [ -z "$LSR_BOOT" ]; then
    _lsr_log 'boot_id unavailable; LuoShu mounts left untouched'
    exit 1
fi

_lsr_stage_write() {
    {
        printf 'boot_id=%s\n' "$LSR_BOOT"
        printf 'state=%s\n' "$1"
        printf 'reason=%s\n' "$2"
        printf 'released=%s\n' "${LSR_RELEASED:-0}"
        printf 'remaining=%s\n' "${LSR_REMAINING:-0}"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "${LSR_STAGE}.tmp.$$" 2>/dev/null && \
        mv -f "${LSR_STAGE}.tmp.$$" "$LSR_STAGE" 2>/dev/null || \
        rm -f "${LSR_STAGE}.tmp.$$" 2>/dev/null
}

_lsr_umount() {
    if [ -n "${LUOSHU_SELF_UMOUNT_COMMAND:-}" ]; then "$LUOSHU_SELF_UMOUNT_COMMAND" "$@"
    elif command -v umount >/dev/null 2>&1; then umount "$@"
    elif command -v toybox >/dev/null 2>&1; then toybox umount "$@"
    elif [ -x /data/adb/magisk/busybox ]; then /data/adb/magisk/busybox umount "$@"
    elif command -v busybox >/dev/null 2>&1; then busybox umount "$@"
    else return 127
    fi
}

# Markers that only LuoShu-owned layers carry in mountinfo: the module tree
# (overlay lowerdir, bind root, private view mountpoint) and the self-mount
# state tree (captured lower binds). Both absolute and /data-relative forms are
# checked because a bind's root field is relative to the /data filesystem.
_lsr_data="${LUOSHU_SOFT_REBOOT_DATA_ROOT:-/data}"
_lsr_mod_rel="${MODDIR#"$_lsr_data"}"
_lsr_state_rel="${LSR_STATE_ROOT#"$_lsr_data"}"
[ "$_lsr_mod_rel" != "$MODDIR" ] || _lsr_mod_rel=''
[ "$_lsr_state_rel" != "$LSR_STATE_ROOT" ] || _lsr_state_rel=''

_lsr_awk_owned() {
    # $1 = mountpoint to restrict to, or empty for any mountpoint.
    [ -r "$LSR_MOUNTINFO" ] || return 2
    awk -v target="$1" -v m1="${MODDIR%/}/" -v m2="${_lsr_mod_rel:+${_lsr_mod_rel%/}/}" \
        -v s1="${LSR_STATE_ROOT%/}/" -v s2="${_lsr_state_rel:+${_lsr_state_rel%/}/}" '
        target != "" && $5 != target { next }
        index($0, m1) || (m2 != "" && index($0, m2)) || index($0, s1) || (s2 != "" && index($0, s2)) {
            found = 1
        }
        END { exit found ? 0 : 1 }' "$LSR_MOUNTINFO" 2>/dev/null
}

_lsr_owned_at() { _lsr_awk_owned "$1"; }

# umount always pops the most recent mount at a path. Only do that when the
# most recent mount there is LuoShu's own; a foreign layer stacked above ours
# is never removed (the entry stays journaled instead).
_lsr_top_owned_at() {
    [ -r "$LSR_MOUNTINFO" ] || return 2
    awk -v target="$1" -v m1="${MODDIR%/}/" -v m2="${_lsr_mod_rel:+${_lsr_mod_rel%/}/}" \
        -v s1="${LSR_STATE_ROOT%/}/" -v s2="${_lsr_state_rel:+${_lsr_state_rel%/}/}" '
        $5 == target { top = $0 }
        END {
            if (top == "") exit 1
            if (index(top, m1) || (m2 != "" && index(top, m2)) || index(top, s1) || (s2 != "" && index(top, s2))) exit 0
            exit 1
        }' "$LSR_MOUNTINFO" 2>/dev/null
}

# Release one journal target. Plain umount first; Android is still running at
# this stage, so a busy target is detached lazily (the framework is stopped
# right after this hook). Repeats while a LuoShu layer is still stacked there.
_lsr_release_target() {
    _lsrt_target="$1"
    _lsrt_try=0
    while _lsr_owned_at "$_lsrt_target"; do
        _lsrt_try=$((_lsrt_try + 1))
        [ "$_lsrt_try" -le 4 ] || return 1
        if ! _lsr_top_owned_at "$_lsrt_target"; then
            _lsr_log "foreign mount stacked above LuoShu layer, left in place: $_lsrt_target"
            return 1
        fi
        if _lsr_umount "$_lsrt_target" >/dev/null 2>&1; then
            continue
        fi
        if _lsr_umount -l "$_lsrt_target" >/dev/null 2>&1; then
            _lsr_log "busy target detached lazily: $_lsrt_target"
            continue
        fi
        _lsr_owned_at "$_lsrt_target" && return 1
    done
    return 0
}

# Release a journal newest-first. $2=module restricts targets to MODDIR.
# Unreleased entries are written back in their original order.
_lsr_release_list() {
    _lsrl_list="$1"
    _lsrl_scope="$2"
    [ -s "$_lsrl_list" ] || return 0
    _lsrl_rev="${_lsrl_list}.rev.$$"
    _lsrl_keep="${_lsrl_list}.keep.$$"
    awk '{ item[NR]=$0 } END { for (i=NR; i>=1; i--) print item[i] }' "$_lsrl_list" > "$_lsrl_rev" 2>/dev/null || return 1
    : > "$_lsrl_keep" 2>/dev/null || { rm -f "$_lsrl_rev"; return 1; }
    while IFS= read -r _lsrl_target; do
        [ -n "$_lsrl_target" ] || continue
        if [ "$_lsrl_scope" = module ]; then
            case "$_lsrl_target" in "${MODDIR%/}"/*) ;; *) continue ;; esac
        fi
        if _lsr_release_target "$_lsrl_target"; then
            LSR_RELEASED=$((LSR_RELEASED + 1))
        else
            LSR_REMAINING=$((LSR_REMAINING + 1))
            _lsr_log "unable to release: $_lsrl_target"
            printf '%s\n' "$_lsrl_target" >> "$_lsrl_keep"
        fi
    done < "$_lsrl_rev"
    rm -f "$_lsrl_rev" 2>/dev/null
    if [ -s "$_lsrl_keep" ]; then
        awk '{ item[NR]=$0 } END { for (i=NR; i>=1; i--) print item[i] }' "$_lsrl_keep" > "${_lsrl_list}.tmp.$$" 2>/dev/null && \
            mv -f "${_lsrl_list}.tmp.$$" "$_lsrl_list" 2>/dev/null
        rm -f "$_lsrl_keep" 2>/dev/null
        return 1
    fi
    rm -f "$_lsrl_keep" 2>/dev/null
    return 0
}

LSR_RELEASED=0
LSR_REMAINING=0
LSR_FAIL=''

if [ ! -r "$LSR_MOUNTINFO" ]; then
    _lsr_stage_write failed mountinfo-unreadable
    _lsr_log 'mountinfo unreadable; LuoShu mounts left untouched'
    exit 1
fi

# Kernel mounts never outlive a real reboot: a journal from an older boot_id
# describes nothing live and must not be replayed against shared targets.
_lsr_journal_boot=$(cat "$LSR_STATE_ROOT/boot-id" 2>/dev/null | tr -d '\r\n')
if [ -s "$LSR_SELF_LIST" ] && [ "$_lsr_journal_boot" = "$LSR_BOOT" ]; then
    _lsr_release_list "$LSR_SELF_LIST" any || LSR_FAIL=self-mount-release-failed
elif [ -s "$LSR_SELF_LIST" ]; then
    _lsr_log 'self-mount journal belongs to another boot; not replayed'
fi
_lsr_release_list "$LSR_VIEW_LIST" module || LSR_FAIL="${LSR_FAIL:-module-view-release-failed}"

# Anything still carrying a LuoShu marker is not in our journals; report it
# without touching it.
if [ -z "$LSR_FAIL" ] && _lsr_awk_owned ''; then
    LSR_FAIL=untracked-luoshu-mount-remains
fi

if [ -n "$LSR_FAIL" ]; then
    _lsr_stage_write failed "$LSR_FAIL"
    _lsr_log "release incomplete: reason=$LSR_FAIL released=$LSR_RELEASED remaining=$LSR_REMAINING; post-mount keeps same-boot rollback"
    exit 1
fi

# Every LuoShu layer is gone: reset the same-boot decision so post-mount runs a
# fresh transaction (prepare_boot_state treats a missing boot-id as new boot).
: > "$LSR_SELF_LIST" 2>/dev/null || true
: > "$LSR_VIEW_LIST" 2>/dev/null || true
rm -f "$LSR_STATE_ROOT/boot-id" "$MODDIR/config/self-mount-required.conf" 2>/dev/null || true
{
    printf 'state=idle\n'
    printf 'backend=none\n'
    printf 'mounted=\n'
    printf 'failed=\n'
    printf 'reason=ksu-soft-reboot\n'
    printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
} > "$MODDIR/config/self-mount.conf.tmp.$$" 2>/dev/null && \
    mv -f "$MODDIR/config/self-mount.conf.tmp.$$" "$MODDIR/config/self-mount.conf" 2>/dev/null || \
    rm -f "$MODDIR/config/self-mount.conf.tmp.$$" 2>/dev/null
_lsr_stage_write ready none
_lsr_log "released=$LSR_RELEASED; fresh self-mount transaction requested for post-mount"
exit 0
