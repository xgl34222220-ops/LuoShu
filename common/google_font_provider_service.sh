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
PROVIDER_REPORT="$MODDIR/config/font-provider-one-shot.conf"
PROVIDER_PROBE="$MODDIR/config/.font-provider-probe.$$"

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
trap 'rm -f "$PROVIDER_PROBE"; luoshu_font_lock_release "$LOCK" "$$" >/dev/null 2>&1 || true' EXIT
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

# Wait only for initial framework routing to settle, not for later downloads.
# A completed boot property does not guarantee theme_webview has been created.
# This bound is part of the same 180-second supervised boot task, never a daemon.
provider_theme_ready() {
    _provider_theme_probe=not-applicable
    [ -f "$THEME_BRIDGE" ] || return 0
    _provider_settle=${LUOSHU_THEME_SETTLE_SECONDS:-20}
    case "$_provider_settle" in ''|*[!0-9]*) _provider_settle=20 ;; esac
    [ "$_provider_settle" -le 30 ] 2>/dev/null || _provider_settle=30
    _provider_elapsed=0
    _provider_previous=
    while :; do
        [ -d "$MODDIR" ] && [ ! -f "$MODDIR/disable" ] && [ ! -f "$MODDIR/remove" ] || return 2
        # Capture in the worker, so TERM owns both the probe and its output file.
        MODDIR="$MODDIR" sh "$THEME_BRIDGE" readiness > "$PROVIDER_PROBE" 2>/dev/null &
        _provider_child=$!
        wait "$_provider_child"
        _provider_probe_rc=$?
        _provider_child=
        _provider_theme_probe=$(head -n1 "$PROVIDER_PROBE" 2>/dev/null)
        rm -f "$PROVIDER_PROBE"
        case "$_provider_theme_probe" in
            not-applicable) return 0 ;;
            ready\|*)
                [ "$_provider_theme_probe" = "$_provider_previous" ] && return 0
                ;;
            *) _provider_theme_probe=pending ;;
        esac
        [ "$_provider_elapsed" -lt "$_provider_settle" ] || return 1
        _provider_previous=$_provider_theme_probe
        provider_pause 1
        _provider_elapsed=$((_provider_elapsed + 1))
    done
}

provider_report() {
    [ -d "$MODDIR/config" ] || return 0
    {
        printf 'state=%s\nreason=%s\n' "$1" "$2"
        printf 'googleResult=%s\nthemeResult=%s\n' "${_provider_google_rc:-2}" "${_provider_theme_rc:-2}"
        printf 'themeWaitSeconds=%s\nresident=false\n' "${_provider_elapsed:-0}"
    } > "${PROVIDER_REPORT}.tmp.$$" && mv -f "${PROVIDER_REPORT}.tmp.$$" "$PROVIDER_REPORT"
    chmod 0600 "$PROVIDER_REPORT" 2>/dev/null || true
    if [ "$1" = partial ]; then
        printf '[WARN] HyperOS 主题字体路由未确认：任务已退出，无常驻重试（%s）\n' "$2" >> "$MODDIR/logs/fontswitch.log" 2>/dev/null || true
    fi
    printf '[%s] one-shot state=%s reason=%s; no resident observer\n' \
        "$(date '+%F %T' 2>/dev/null)" "$1" "$2" >> "$LOG" 2>/dev/null || true
}

[ -d "$MODDIR" ] && [ ! -f "$MODDIR/disable" ] && [ ! -f "$MODDIR/remove" ] || { provider_restore_theme; exit $?; }
provider_selection_ready
case "$?" in 1) exit 1 ;; 2) provider_report not-applicable default-selection; exit 0 ;; esac
provider_theme_ready
_provider_ready_rc=$?
[ "$_provider_ready_rc" != 2 ] || { provider_restore_theme; exit $?; }
provider_selection_ready
case "$?" in 1) exit 1 ;; 2) provider_report not-applicable default-selection; exit 0 ;; esac
provider_apply 0
_rc=$?
case "$_rc" in
    0|2) ;;
    *) provider_report error apply-failed; exit 1 ;;
esac
if [ -s "$MODDIR/config/google-font-refresh-pending.conf" ]; then
    provider_run "$BRIDGE" refresh 0 || { provider_report error refresh-failed; exit 1; }
fi
if [ "$_provider_ready_rc" != 0 ]; then
    provider_report partial theme-route-not-ready
elif [ "$_provider_theme_probe" != not-applicable ] && [ "$_provider_theme_rc" != 0 ]; then
    provider_report partial theme-not-applied
elif [ "$_rc" = 2 ]; then
    provider_report not-applicable no-existing-targets
else
    provider_report applied existing-targets-only
fi
exit 0
