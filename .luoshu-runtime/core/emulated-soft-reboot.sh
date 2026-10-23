#!/system/bin/sh
# LuoShu: prepare for a KernelSU emulated soft reboot.
#
# `ksud soft-reboot` keeps the kernel (and /proc/sys/kernel/random/boot_id)
# alive, runs every module's emulated-soft-reboot.sh with a short deadline,
# stops the Android framework and then replays post-fs-data, post-mount,
# service and boot-completed. LuoShu keys its self-mount journal on boot_id, so
# without help the replayed post-mount would treat its old layers as "already
# mounted this boot" and stack or skip work. This stage:
#
#   1. takes LuoShu's own mount journals for the current boot only;
#   2. releases each recorded target newest-first, and only when the topmost
#      mount at that path still belongs to LuoShu (never a foreign layer);
#   3. when everything was released, forgets this boot's self-mount decision
#      so the replayed post-mount starts a fresh transaction.
#
# Anything that cannot be released stays in the journal with boot-id intact,
# so post-mount falls back to its existing same-boot rollback path.
set +e

MODDIR="${MODDIR:-$(CDPATH= cd -- "${0%/*}/../.." 2>/dev/null && pwd)}"
MODULE_DIR="$MODDIR"

[ "${KSU:-}" = true ] || exit 0
[ -f "$MODDIR/module.prop" ] || exit 0

SR_SELF_STATE="${LUOSHU_SELF_MOUNT_STATE_ROOT:-/data/adb/luoshu/self-mount}"
SR_PRIVATE_STATE="${LUOSHU_PRIVATE_STATE_ROOT:-/data/adb/luoshu/private-payload}"
SR_MOUNTINFO="${LUOSHU_MOUNTINFO:-/proc/self/mountinfo}"
SR_RESULT="$MODDIR/config/ksu-soft-reboot.conf"
SR_LOG="$MODDIR/logs/soft-reboot.log"
SR_WORK="$SR_SELF_STATE/.soft-reboot.$$"

sr_log() {
    mkdir -p "${SR_LOG%/*}" 2>/dev/null || true
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" "$*" \
        >> "$SR_LOG" 2>/dev/null || true
}

sr_boot_id() {
    if [ -n "${LUOSHU_SOFT_REBOOT_BOOT_ID:-}" ]; then
        printf '%s\n' "$LUOSHU_SOFT_REBOOT_BOOT_ID"
        return 0
    fi
    tr -d '\r\n' < /proc/sys/kernel/random/boot_id 2>/dev/null
    printf '\n'
}

# Atomic key=value write of the stage result for the App and diagnostics.
sr_result() {
    mkdir -p "${SR_RESULT%/*}" 2>/dev/null || return 0
    {
        printf 'state=%s\n' "$1"
        printf 'reason=%s\n' "$2"
        printf 'released=%s\n' "$3"
        printf 'remaining=%s\n' "$4"
        printf 'bootId=%s\n' "$SR_BOOT"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$SR_RESULT.tmp.$$" 2>/dev/null && mv -f "$SR_RESULT.tmp.$$" "$SR_RESULT" 2>/dev/null || \
        rm -f "$SR_RESULT.tmp.$$" 2>/dev/null || true
}

# Print the mountinfo line of the topmost mount whose mount point is $1.
# Later lines in mountinfo are mounted later, so the last match is on top.
sr_top_mount() {
    awk -v want="$1" '
        { p = $5; gsub(/\\040/, " ", p); if (p == want) line = $0 }
        END { if (line != "") print line }
    ' "$SR_MOUNTINFO" 2>/dev/null
}

# A mount is LuoShu's when it sits inside LuoShu's private state directories,
# or when its source side (mountinfo root, source and super options, never the
# mount point itself) points into LuoShu-owned paths.
sr_owned() {
    _sro_target="$1"
    case "$_sro_target" in
        "${SR_SELF_STATE%/}"/*|"${SR_PRIVATE_STATE%/}"/*) return 0 ;;
    esac
    _sro_source=$(printf '%s\n' "$2" | awk '{
        out = $4
        for (i = 7; i <= NF; i++) if ($i == "-") { for (j = i + 1; j <= NF; j++) out = out " " $j; break }
        print out
    }')
    _sro_module_id="${MODDIR%/}"
    _sro_module_id="${_sro_module_id##*/}"
    case "$_sro_source" in
        *"/luoshu/self-mount"*|*"/luoshu/private-payload"*) return 0 ;;
        *"/modules/$_sro_module_id/"*|*"/modules_update/$_sro_module_id/"*) return 0 ;;
        *"${SR_SELF_STATE%/}"*|*"${SR_PRIVATE_STATE%/}"*|*"${MODDIR%/}/"*) return 0 ;;
    esac
    return 1
}

sr_umount() {
    if [ -n "${LUOSHU_SOFT_REBOOT_UMOUNT:-}" ]; then
        "$LUOSHU_SOFT_REBOOT_UMOUNT" "$@"
        return $?
    fi
    if command -v umount >/dev/null 2>&1; then
        umount "$@"
    elif [ -x /system/bin/umount ]; then
        /system/bin/umount "$@"
    else
        busybox umount "$@"
    fi
}

# Release one recorded target. 0 = gone now, 1 = still present (kept).
sr_release() {
    _srr_target="$1"
    _srr_top=$(sr_top_mount "$_srr_target")
    [ -n "$_srr_top" ] || return 0
    if ! sr_owned "$_srr_target" "$_srr_top"; then
        sr_log "保留 $_srr_target：最上层挂载不属于洛书"
        return 1
    fi
    sr_umount "$_srr_target" >/dev/null 2>&1 || \
        sr_umount -l "$_srr_target" >/dev/null 2>&1 || {
        sr_log "无法卸载 $_srr_target"
        return 1
    }
    sr_log "已卸载 $_srr_target"
    return 0
}

# sr_drain LIST SCOPE -> rewrites LIST with only the entries still mounted.
# SCOPE limits accepted targets to a path prefix ('' = no limit).
sr_drain() {
    _srd_list="$1"
    _srd_scope="$2"
    [ -s "$_srd_list" ] || return 0
    _srd_keep="$SR_WORK/keep"
    : > "$_srd_keep" 2>/dev/null || return 1
    awk 'NF { line[++n] = $0 } END { for (i = n; i >= 1; i--) print line[i] }' "$_srd_list" \
        > "$SR_WORK/order" 2>/dev/null || return 1
    while IFS= read -r _srd_target; do
        [ -n "$_srd_target" ] || continue
        case "$_srd_target" in /*) ;; *) continue ;; esac
        if [ -n "$_srd_scope" ]; then
            case "$_srd_target" in "${_srd_scope%/}"/*) ;; *) continue ;; esac
        fi
        if sr_release "$_srd_target"; then
            SR_RELEASED=$((SR_RELEASED + 1))
        else
            SR_REMAINING=$((SR_REMAINING + 1))
            printf '%s\n' "$_srd_target" >> "$_srd_keep"
        fi
    done < "$SR_WORK/order"
    # Keep the surviving entries in their original (oldest-first) order.
    awk 'NF { line[++n] = $0 } END { for (i = n; i >= 1; i--) print line[i] }' "$_srd_keep" \
        > "$_srd_list.tmp.$$" 2>/dev/null && mv -f "$_srd_list.tmp.$$" "$_srd_list" 2>/dev/null
}

SR_BOOT=$(sr_boot_id)
SR_RELEASED=0
SR_REMAINING=0

SR_SAVED=$(tr -d '\r\n' < "$SR_SELF_STATE/boot-id" 2>/dev/null)
if [ -z "$SR_BOOT" ] || [ "$SR_SAVED" != "$SR_BOOT" ]; then
    # No journal from this boot: nothing of ours to release, and an older
    # journal must never be replayed against targets another module may own.
    sr_log "KernelSU 软重启：无本次启动的自挂载记录，无需处理"
    sr_result ready no-current-journal 0 0
    exit 0
fi

mkdir -p "$SR_WORK" 2>/dev/null || {
    sr_result failed state-unwritable 0 0
    exit 0
}
sr_log "KernelSU 软重启：开始释放洛书自挂载"
sr_drain "$SR_SELF_STATE/mounts.list" ''
sr_drain "$SR_PRIVATE_STATE/module-view.mounts" "$MODDIR"
rm -rf "$SR_WORK" 2>/dev/null || true

if [ "$SR_REMAINING" -gt 0 ]; then
    sr_log "仍有 $SR_REMAINING 个挂载未释放，保留本次启动状态交由 post-mount 回滚"
    sr_result failed targets-busy "$SR_RELEASED" "$SR_REMAINING"
    exit 0
fi

# Everything is released: forget this boot's self-mount decision.
: > "$SR_SELF_STATE/mounts.list" 2>/dev/null || true
rm -rf "$SR_SELF_STATE/lower" "$SR_SELF_STATE/work" 2>/dev/null || true
rm -f "$SR_SELF_STATE/boot-id" "$MODDIR/config/self-mount-required.conf" 2>/dev/null || true
mkdir -p "$MODDIR/config" 2>/dev/null || true
{
    printf 'state=idle\n'
    printf 'backend=none\n'
    printf 'mounted=\n'
    printf 'failed=\n'
    printf 'reason=ksu-soft-reboot\n'
    printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
} > "$MODDIR/config/self-mount.conf.tmp.$$" 2>/dev/null && \
    mv -f "$MODDIR/config/self-mount.conf.tmp.$$" "$MODDIR/config/self-mount.conf" 2>/dev/null || \
    rm -f "$MODDIR/config/self-mount.conf.tmp.$$" 2>/dev/null || true
sr_log "已释放 $SR_RELEASED 个挂载，post-mount 将重新执行自挂载"
sr_result ready released "$SR_RELEASED" 0
exit 0
