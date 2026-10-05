#!/system/bin/sh
# Finite current-boot activation with the unchanged stable 1.1.1 mount transaction.
set +e
MODDIR="${MODDIR:-${0%/*}/..}"
MODULE_DIR="$MODDIR"
. "$MODDIR/common/runtime_paths.sh" || exit 126
luoshu_runtime_paths_init "$MODDIR" || exit 126
if [ -z "${LUOSHU_TASK_SCOPE_PID:-}" ]; then
    exec sh "$MODDIR/common/task_scope.sh" request-run "font-live-$$-$(date +%s)" 120 -- sh "$0" "$@"
fi
NEXT="$MODDIR/.luoshu-payload-next"
NEXT_STATE="$LUOSHU_CONFIG_DIR/font-payload-next.conf"
LIVE_STATE="$LUOSHU_CONFIG_DIR/font-live.conf"
OLD_LIVE_STATE="$LUOSHU_CONFIG_DIR/font-live-previous.conf"
JOURNAL="$LUOSHU_CONFIG_DIR/font-live-transaction.conf"
LIVE_CACHE="$LUOSHU_CACHE_DIR/live-font-payload"
ACTIVE="$LUOSHU_CONFIG_DIR/active_font.conf"
BOOT=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n')
value() { sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'; }
result() { printf '{"liveApplied":%s,"activation":"%s","reason":"%s"}\n' "$1" "$2" "$3"; }
# Explicit cleanup runs after the original task's complete process proof.
# Hold the canonical selection lock in this outer shell across namespace entry.
_recover_lock_held=false
if [ "${1:-}" = recover ]; then
    . "$MODDIR/common/font_switch_lock.sh" || exit 126
    . "$MODDIR/common/font_next_transaction.sh" || exit 126
    _recover_lock="$MODDIR/.font_switch.lock"
    luoshu_font_lock_acquire "$_recover_lock" "$$" || { result false pending-reboot recovery-lock-unavailable; exit 1; }
    _recover_lock_held=true
    trap 'luoshu_font_lock_release "$_recover_lock" "$$" >/dev/null 2>&1 || true' EXIT
    trap 'exit 129' HUP
    trap 'exit 130' INT
    trap 'exit 143' TERM
    luoshu_next_transaction_recover "$MODDIR" || { result false pending-reboot next-transaction-cleanup-required; exit 1; }
    [ ! -e "$LUOSHU_BACKUP_DIR/next-transaction" ] && [ ! -L "$LUOSHU_BACKUP_DIR/next-transaction" ] || {
        result false pending-reboot next-transaction-cleanup-required; exit 1;
    }
    if [ ! -e "$JOURNAL" ] && [ ! -L "$JOURNAL" ]; then result false pending-reboot live-cleaned; exit 0; fi
fi
enter_live_namespace() {
    if [ "$_recover_lock_held" = true ]; then
        "$@"
        exit $?
    fi
    exec "$@"
}
if [ "${1:-}" != entered ]; then
    _mode="${1:-apply}"
    _self_ns=$(readlink /proc/self/ns/mnt 2>/dev/null)
    _init_ns=$(readlink /proc/1/ns/mnt 2>/dev/null)
    if [ -z "$_self_ns" ] || [ -z "$_init_ns" ]; then
        result false pending-reboot namespace-unavailable; exit 1
    fi
    if [ "$_self_ns" = "$_init_ns" ]; then
        enter_live_namespace sh "$0" entered "$_mode"
    elif command -v nsenter >/dev/null 2>&1; then
        enter_live_namespace nsenter -t 1 -m -- sh "$0" entered "$_mode"
    elif command -v toybox >/dev/null 2>&1; then
        enter_live_namespace toybox nsenter -t 1 -m -- sh "$0" entered "$_mode"
    elif command -v busybox >/dev/null 2>&1; then
        enter_live_namespace busybox nsenter -t 1 -m -- sh "$0" entered "$_mode"
    fi
    result false pending-reboot namespace-enter-failed; exit 1
fi
[ "$(readlink /proc/self/ns/mnt 2>/dev/null)" = "$(readlink /proc/1/ns/mnt 2>/dev/null)" ] && \
    [ -n "$BOOT" ] || { result false pending-reboot namespace-mismatch; exit 1; }
PYROOT="$MODDIR/common/python"
LIVE_LOCK="$LUOSHU_TASKS_DIR/font-live.lock"
_live_python() {
    if [ -n "${LUOSHU_LIVE_PAYLOAD_PYTHON:-}" ]; then
        "$LUOSHU_LIVE_PAYLOAD_PYTHON" "$MODDIR/common/font_live_payload.py" "$@"
    else
        PYTHONHOME="$PYROOT" PYTHONPATH="$PYROOT/lib/python3.14" \
        LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
            "$PYROOT/bin/luoshu-python" "$MODDIR/common/font_live_payload.py" "$@"
    fi
}
# Kernel ownership survives namespace entry and releases after SIGKILL; no
# PID lease can keep a dead switch locked for minutes.
if [ -z "${LUOSHU_LIVE_LOCK_FD:-}" ]; then
    _live_python --lock-exec "$LIVE_LOCK" sh "$0" entered "${2:-apply}"
    exit $?
fi
case "$LUOSHU_LIVE_LOCK_FD" in ''|*[!0-9]*) result false pending-reboot live-lock-invalid; exit 1 ;; esac
[ "$(readlink "/proc/self/fd/$LUOSHU_LIVE_LOCK_FD" 2>/dev/null)" = "$LIVE_LOCK" ] || \
    { result false pending-reboot live-lock-invalid; exit 1; }
. "$MODDIR/common/mount_compat.sh" || { result false pending-reboot mount-runtime-missing; exit 1; }
type luoshu_private_self_mount_ensure >/dev/null 2>&1 || { result false pending-reboot mount-runtime-missing; exit 1; }
_lfrp_payload_root() { printf '%s\n' "$SOURCE"; }
MANIFEST="$MODDIR/config/self-mount-required.conf"
safe_source() {
    [ -d "$1" ] && [ ! -L "$1" ] || return 1
    case "$1" in "$MODDIR/.luoshu-payload") return 0 ;; esac
    _source_name=${1##*/}
    [ "$1" = "$LIVE_CACHE/$_source_name" ] || return 1
    _suffix=${_source_name#generation-}
    [ "${#_suffix}" -eq 64 ] || return 1
    case "$_suffix" in *[!0-9a-f]*) return 1 ;; esac
    [ -f "$1/.generation.json" ] && [ ! -L "$1/.generation.json" ]
}
live_visible() {
    if [ "$(value "$LIVE_STATE" font)" = default ]; then
        [ "$(value "$MODDIR/config/self-mount.conf" state)" = idle ] && \
            [ ! -s "$(_luoshu_self_state_root)/mounts.list" ]
    else
        _luoshu_atomic_verify_manifest "$MANIFEST"
    fi
}
restore_previous() {
    # ACTIVE may have been left at OLD_FONT by a killed rollback. The durable
    # next-state retains the user's latest reboot selection.
    _selected=$(value "$NEXT_STATE" font)
    [ -n "$_selected" ] || _selected=$(value "$JOURNAL" newFont)
    [ -n "$_selected" ] || return 1
    [ "$OLD_FONT" = default ] || safe_source "$OLD_SOURCE" || return 1
    SOURCE="$OLD_SOURCE"
    printf '%s\n' "$OLD_FONT" > "$ACTIVE" || return 1
    rm -f "$MANIFEST" 2>/dev/null || return 1
    luoshu_private_self_mount_ensure
    _restore_rc=$?
    printf '%s\n' "$_selected" > "$ACTIVE" || return 1
    [ "$_restore_rc" -eq 0 ] || { rm -f "$LIVE_STATE" 2>/dev/null || true; return 1; }
    if [ "$(value "$JOURNAL" oldLivePresent)" = true ]; then
        [ -f "$OLD_LIVE_STATE" ] && [ ! -L "$OLD_LIVE_STATE" ] || return 1
        _old_state_tmp="$LUOSHU_TASK_SCOPE_TMPDIR/font-live-restore-state"
        cp -p "$OLD_LIVE_STATE" "$_old_state_tmp" && mv -f "$_old_state_tmp" "$LIVE_STATE" || return 1
    else
        rm -f "$LIVE_STATE" || return 1
    fi
    rm -f "$JOURNAL" "$OLD_LIVE_STATE" || return 1
    return 0
}
signal_exit() {
    _signal_rc="$1"
    trap '' HUP INT TERM
    [ ! -s "$JOURNAL" ] || restore_previous
    exit "$_signal_rc"
}
recover_live() {
    [ ! -L "$JOURNAL" ] || return 1
    [ -e "$JOURNAL" ] || return 0
    [ -f "$JOURNAL" ] && [ -s "$JOURNAL" ] || return 1
    [ "$(value "$JOURNAL" schema)" = luoshu-live-transaction-v1 ] || return 1
    _journal_boot=$(value "$JOURNAL" bootId)
    [ -n "$_journal_boot" ] || return 1
    case "$(value "$JOURNAL" oldLivePresent)" in true|false) ;; *) return 1 ;; esac
    if [ "$_journal_boot" != "$BOOT" ]; then
        rm -f "$JOURNAL" "$OLD_LIVE_STATE"; return $?
    fi
    OLD_SOURCE=$(value "$JOURNAL" oldSource)
    OLD_FONT=$(value "$JOURNAL" oldFont)
    [ -n "$OLD_FONT" ] || return 1
    trap 'signal_exit 129' HUP
    trap 'signal_exit 130' INT
    trap 'signal_exit 143' TERM
    _journal_request=$(value "$JOURNAL" requestId)
    SOURCE=$(value "$JOURNAL" newSource)
    if safe_source "$SOURCE" && [ "$(value "$LIVE_STATE" source)" = "$SOURCE" ] && \
       [ "$(value "$LIVE_STATE" requestId)" = "$_journal_request" ] && \
       [ "$(value "$LIVE_STATE" bootId)" = "$BOOT" ] && live_visible; then
        rm -f "$JOURNAL" "$OLD_LIVE_STATE"; return $?
    fi
    restore_previous
}
recover_live || { result false pending-reboot previous-live-cleanup-required; exit 1; }
if [ "${2:-apply}" = recover ]; then result false pending-reboot live-cleaned; exit 0; fi
[ -d "$NEXT" ] && [ -s "$NEXT_STATE" ] || { result false pending-reboot next-payload-missing; exit 1; }
FONT=$(value "$NEXT_STATE" font)
REQUEST=$(value "$NEXT_STATE" requestId)
[ -n "$FONT" ] && [ -n "$REQUEST" ] || { result false pending-reboot next-font-missing; exit 1; }
OLD_SOURCE="$MODDIR/.luoshu-payload"
OLD_FONT=$(value "$NEXT_STATE" previousFont)
[ -n "$OLD_FONT" ] || OLD_FONT=default
if [ "$(value "$LIVE_STATE" bootId)" = "$BOOT" ] && [ "$(value "$LIVE_STATE" state)" = mounted ]; then
    _previous=$(value "$LIVE_STATE" source)
    if safe_source "$_previous"; then OLD_SOURCE="$_previous"; OLD_FONT=$(value "$LIVE_STATE" font); fi
fi
_COPY_TMP="$LUOSHU_TASK_SCOPE_TMPDIR/live-generation-$$"
SOURCE=$(_live_python "$NEXT" "$LIVE_CACHE" "$BOOT" "$_COPY_TMP")
safe_source "$SOURCE" || { result false pending-reboot live-copy-failed; exit 1; }
if [ "$OLD_SOURCE" != "$SOURCE" ] || ! live_visible; then
    _journal_tmp="$LUOSHU_TASK_SCOPE_TMPDIR/live-transaction-state"
    [ ! -L "$LIVE_STATE" ] && [ ! -L "$OLD_LIVE_STATE" ] || { result false pending-reboot live-state-unsafe; exit 1; }
    _old_live_present=false
    if [ -f "$LIVE_STATE" ]; then
        cp -p "$LIVE_STATE" "$OLD_LIVE_STATE" || { result false pending-reboot live-state-backup-failed; exit 1; }
        _old_live_present=true
    elif [ -e "$LIVE_STATE" ]; then
        result false pending-reboot live-state-unsafe; exit 1
    fi
    {
        printf 'schema=luoshu-live-transaction-v1\nbootId=%s\nrequestId=%s\noldLivePresent=%s\n' "$BOOT" "$REQUEST" "$_old_live_present"
        printf 'oldSource=%s\noldFont=%s\nnewSource=%s\nnewFont=%s\n' "$OLD_SOURCE" "$OLD_FONT" "$SOURCE" "$FONT"
    } > "$_journal_tmp" && mv -f "$_journal_tmp" "$JOURNAL" || { result false pending-reboot live-journal-unwritable; exit 1; }
    trap 'signal_exit 129' HUP
    trap 'signal_exit 130' INT
    trap 'signal_exit 143' TERM
    if ! rm -f "$MANIFEST" || ! luoshu_private_self_mount_ensure; then
        restore_previous
        _restored=$?
        [ "$_restored" -ne 0 ] || result false pending-reboot live-mount-failed-previous-restored
        [ "$_restored" -eq 0 ] || result false pending-reboot live-mount-and-restore-failed
        exit 1
    fi
fi
_state_tmp="$LUOSHU_TASK_SCOPE_TMPDIR/font-live-state"
{
    printf 'state=mounted\nfont=%s\nrequestId=%s\n' "$FONT" "$REQUEST"
    printf 'source=%s\nbootId=%s\n' "$SOURCE" "$BOOT"
} > "$_state_tmp" && mv -f "$_state_tmp" "$LIVE_STATE" || {
    [ ! -s "$JOURNAL" ] || restore_previous
    result false pending-reboot live-state-unwritable; exit 1
}
chmod 0644 "$LIVE_STATE" 2>/dev/null || true
rm -f "$JOURNAL" "$OLD_LIVE_STATE" || { result false pending-reboot live-journal-cleanup-required; exit 1; }
result true live-mounted ''
exit 0
