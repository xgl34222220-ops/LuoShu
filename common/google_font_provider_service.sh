#!/system/bin/sh
# Apply currently available provider/theme fonts once, then exit.
set +e

MODDIR="${MODDIR:-${MODULE_DIR:-/data/adb/modules/LuoShu}}"
# One bounded boot task, never an all-day observer. The wrapper supervises
# descendants even when a bridge double-forks or starts a separate session.
if [ "${LUOSHU_SCOPE_WORKER_PID:-}" != "$$" ]; then
    export MODDIR
    exec sh "$MODDIR/common/task_scope.sh" --timeout 180 -- sh "$0" "$@"
fi
BRIDGE="$MODDIR/common/google_font_provider_bridge.sh"
THEME_BRIDGE="$MODDIR/common/hyperos_theme_font_bridge.sh"
LOCK="$MODDIR/.google-font-provider.lock"
LOG="$MODDIR/logs/google-font-provider.log"

[ -f "$BRIDGE" ] || exit 0
[ -f "$MODDIR/common/font_switch_lock.sh" ] && . "$MODDIR/common/font_switch_lock.sh"
[ -f "$MODDIR/common/background_task.sh" ] && . "$MODDIR/common/background_task.sh"

_provider_child=
provider_signal_exit() {
    _provider_signal_code="$1"
    trap '' HUP INT TERM
    if [ -n "$_provider_child" ]; then
        if type luoshu_terminate_task_tree >/dev/null 2>&1; then
            luoshu_terminate_task_tree "$_provider_child"
        else
            kill -TERM "$_provider_child" 2>/dev/null || true
        fi
        wait "$_provider_child" 2>/dev/null || true
    fi
    exit "$_provider_signal_code"
}

provider_run() {
    MODDIR="$MODDIR" MODULE_DIR="$MODDIR" LUOSHU_GOOGLE_FONT_ALLOW_RESTART="$3" \
        sh "$1" "$2" >/dev/null 2>&1 &
    _provider_child=$!
    wait "$_provider_child"
    _provider_apply_rc=$?
    _provider_child=
    return "$_provider_apply_rc"
}

# A default selection restores owned mounts and ends this one-shot task.
_provider_default_clean=0
provider_selection_ready() {
    _active=$(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null | tr -d '\r\n')
    if [ -n "$_active" ] && [ "$_active" != default ]; then
        _provider_default_clean=0
        return 0
    fi
    if [ "$_provider_default_clean" != 1 ]; then
        provider_restore_theme || return 1
        _provider_default_clean=1
    fi
    # Re-selecting the same font after restore must repair even if metadata
    # matches the earlier snapshot. Default mode performs no font inspection.
    _fingerprint=
    _rc=2
    return 2
}

# Keep idle waits under the same cancellable child ownership as apply/restore.
# A foreground sleep used to defer TERM for the entire watch interval.
provider_pause() {
    sleep "$1" &
    _provider_child=$!
    wait "$_provider_child"
    _provider_child=
}

provider_wait_theme_ready() {
    # One bounded prerequisite wait in this task, NOT a resident observer.
    # No existing retry/watch preference can make this wait unbounded.
    [ -f "$THEME_BRIDGE" ] || return 0
    _theme_limit=${LUOSHU_THEME_SETTLE_SECONDS:-30}
    case "$_theme_limit" in ''|*[!0-9]*) _theme_limit=30 ;; esac
    [ "$_theme_limit" -le 60 ] 2>/dev/null || _theme_limit=60
    _theme_elapsed=0
    _theme_previous=
    while :; do
        [ -d "$MODDIR" ] && [ ! -f "$MODDIR/disable" ] && [ ! -f "$MODDIR/remove" ] || return 1
        _theme_probe=$(MODDIR="$MODDIR" sh "$THEME_BRIDGE" readiness 2>/dev/null) || _theme_probe=pending
        case "$_theme_probe" in
            inactive|'') return 0 ;;
            ready\|*)
                [ "$_theme_probe" != "$_theme_previous" ] || return 0
                _theme_previous=$_theme_probe
                ;;
            *) _theme_previous= ;;
        esac
        [ "$_theme_elapsed" -lt "$_theme_limit" ] || return 2
        provider_pause 1
        _theme_elapsed=$((_theme_elapsed + 1))
    done
}

provider_record_result() {
    [ -d "$MODDIR/config" ] || return 0
    _provider_result="$MODDIR/config/font-provider-one-shot.conf"
    {
        printf 'state=%s\nreason=%s\n' "$1" "$2"
        printf 'resident=false\n'
    } > "${_provider_result}.tmp.$$" && \
        mv -f "${_provider_result}.tmp.$$" "$_provider_result"
}

provider_apply() {
    provider_run "$BRIDGE" apply "$1"
    _provider_google_rc=$?
    _provider_theme_rc=2
    if [ -f "$THEME_BRIDGE" ]; then
        provider_run "$THEME_BRIDGE" apply 0
        _provider_theme_rc=$?
    fi
    # Either adapter can need repair even when the other has no targets.
    case "$_provider_google_rc:$_provider_theme_rc" in
        0:0|0:2|2:0) return 0 ;;
        2:2) return 2 ;;
        *) return 1 ;;
    esac
}

provider_fingerprint() {
    _provider_google_fp=$(MODDIR="$MODDIR" sh "$BRIDGE" fingerprint 2>/dev/null) || return 1
    _provider_theme_fp=
    if [ -f "$THEME_BRIDGE" ]; then
        _provider_theme_fp=$(MODDIR="$MODDIR" sh "$THEME_BRIDGE" fingerprint 2>/dev/null) || return 1
    fi
    printf 'google|%s\ntheme|%s\n' "$_provider_google_fp" "$_provider_theme_fp"
}

provider_restore_theme() {
    # Restore both adapters. Keep this function name for older lifecycle callers.
    _provider_cleanup_rc=0
    provider_restore_bridge "$BRIDGE" || _provider_cleanup_rc=1
    [ ! -f "$THEME_BRIDGE" ] || provider_restore_bridge "$THEME_BRIDGE" || _provider_cleanup_rc=1
    return "$_provider_cleanup_rc"
}

provider_restore_bridge() {
    _provider_restore_bridge="$1"
    _provider_restore_attempt=1
    while [ "$_provider_restore_attempt" -le 3 ]; do
        provider_run "$_provider_restore_bridge" restore 0 && return 0
        # Removal can finish while a child is unwinding. Do not recreate a
        # removed module just to record an already obsolete cleanup failure.
        [ -d "$MODDIR" ] && [ -f "$_provider_restore_bridge" ] || return 0
        mkdir -p "${LOG%/*}" 2>/dev/null || true
        printf '[%s] font restore failed (attempt %s/3); namespace journal retained\n' \
            "$(date '+%F %T' 2>/dev/null)" "$_provider_restore_attempt" >> "$LOG" 2>/dev/null || true
        [ "$_provider_restore_attempt" -lt 3 ] || return 1
        # Keep the bounded retry pause cancellable through the same child-tree
        # handler as apply/restore; disabling must never leave a waiting worker.
        sleep 3 &
        _provider_child=$!
        wait "$_provider_child"
        _provider_child=
        _provider_restore_attempt=$((_provider_restore_attempt + 1))
    done
    return 1
}

# A bare mkdir lock survives an interrupted boot and used to disable all later
# attempts. Reuse the module's PID/start-time/boot-identity lock implementation.
# Acquire before waiting for boot too: repeated service entries must not leave
# several sleeping boot waiters around for ten minutes.
type luoshu_font_lock_acquire >/dev/null 2>&1 || exit 1
luoshu_font_lock_acquire "$LOCK" "$$" || exit 0
trap 'luoshu_font_lock_release "$LOCK" "$$" >/dev/null 2>&1 || true' EXIT
trap 'provider_signal_exit 129' HUP
trap 'provider_signal_exit 130' INT
trap 'provider_signal_exit 143' TERM

_waited=0
while [ "$(getprop sys.boot_completed 2>/dev/null)" != 1 ] && [ "$_waited" -lt 600 ]; do
    [ -d "$MODDIR" ] && [ ! -f "$MODDIR/disable" ] && [ ! -f "$MODDIR/remove" ] || { provider_restore_theme; exit $?; }
    provider_pause 3
    _waited=$((_waited + 3))
done
[ "$(getprop sys.boot_completed 2>/dev/null)" = 1 ] || exit 0

# Existing static mounts do not require an observer. Finish the bounded boot
# prerequisite wait before applying once; never schedule work after exit.
[ -d "$MODDIR" ] && [ ! -f "$MODDIR/disable" ] && [ ! -f "$MODDIR/remove" ] || { provider_restore_theme; exit $?; }
provider_selection_ready
case "$?" in 1) exit 1 ;; 2) exit 0 ;; esac
provider_wait_theme_ready
_theme_ready_rc=$?
if [ "$_theme_ready_rc" = 1 ]; then
    provider_restore_theme
    exit $?
fi
provider_apply 0
_rc=$?
case "$_rc" in
    0|2) ;;
    *)
        mkdir -p "${LOG%/*}" 2>/dev/null || true
        printf '[%s] one-shot font apply failed; no automatic rebuild loop\n' "$(date '+%F %T' 2>/dev/null)" >> "$LOG"
        provider_record_result failed apply-failed
        exit 1
        ;;
esac
if [ -s "$MODDIR/config/google-font-refresh-pending.conf" ]; then
    provider_run "$BRIDGE" refresh 0 || { provider_record_result failed refresh-failed; exit 1; }
fi
if [ "$_theme_ready_rc" = 2 ]; then
    provider_record_result partial theme-route-not-ready
    mkdir -p "${LOG%/*}" 2>/dev/null || true
    printf '[WARN] HyperOS 主题字体路由未就绪：本次英数补齐未确认，任务已退出，无常驻重试\n' >> "$LOG"
    printf '[WARN] HyperOS 主题字体路由未就绪：本次英数补齐未确认，任务已退出，无常驻重试\n' >> "$MODDIR/logs/fontswitch.log"
elif [ "$_rc" = 2 ]; then
    provider_record_result not-applicable no-existing-font-targets
else
    provider_record_result complete one-shot-apply-finished
fi
exit 0
