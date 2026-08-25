#!/system/bin/sh
set +e
# ============================================================
# 洛书 - 工具函数库入口
# 作者：惜故里丶
# 功能：加载通用工具核心，并覆盖字体切换身份锁实现。
# ============================================================

_luof_core=''
for _luof_candidate in \
    "${MODULE_DIR:-}/common/util_functions_core.sh" \
    "${MODDIR:-}/common/util_functions_core.sh" \
    "${MODPATH:-}/common/util_functions_core.sh" \
    "${0%/*}/util_functions_core.sh" \
    "${0%/*}/common/util_functions_core.sh" \
    "${0%/*}/../common/util_functions_core.sh" \
    "${PWD:-.}/common/util_functions_core.sh"; do
    [ "$_luof_candidate" != "/common/util_functions_core.sh" ] || continue
    if [ -f "$_luof_candidate" ]; then
        _luof_core="$_luof_candidate"
        break
    fi
done
if [ -z "$_luof_core" ]; then
    echo 'LuoShu: util_functions_core.sh not found' >&2
    return 1 2>/dev/null || exit 1
fi
. "$_luof_core"
unset _luof_candidate _luof_core

# Return the Linux process start time (field 22 of /proc/<pid>/stat).
# Strip the leading "pid (comm)" section first because comm may contain spaces.
luoshu_process_starttime() {
    _lps_pid="$1"
    case "$_lps_pid" in ''|*[!0-9]*) return 1 ;; esac
    _lps_stat_path="/proc/$_lps_pid/stat"
    # Some Root shells and PID namespaces expose the shell's externally addressable PID through
    # $$ while /proc is keyed by the inner namespace PID. /proc/self is still authoritative for
    # the lock owner itself, so capture its birth identity instead of silently writing a PID-only
    # lock that cannot detect reuse.
    if [ "$_lps_pid" = "$$" ] && [ ! -r "$_lps_stat_path" ]; then
        # This helper is normally evaluated through command substitution, which creates a short
        # subshell. Its parent is the actual $$ lock owner; /proc/self would identify the temporary
        # substitution process and change on every read.
        if [ -n "${PPID:-}" ] && [ -r "/proc/$PPID/stat" ]; then
            _lps_stat_path="/proc/$PPID/stat"
        else
            _lps_stat_path=/proc/self/stat
        fi
    fi
    [ -r "$_lps_stat_path" ] || return 1
    # Open the proc file in the shell. `cat /proc/self/stat` reports cat's identity, not ours.
    IFS= read -r _lps_stat < "$_lps_stat_path" 2>/dev/null || return 1
    _lps_tail="${_lps_stat##*) }"
    [ "$_lps_tail" != "$_lps_stat" ] || return 1
    set -- $_lps_tail
    [ "$#" -ge 20 ] || return 1
    shift 19
    case "$1" in ''|*[!0-9]*) return 1 ;; esac
    printf '%s\n' "$1"
}

luoshu_current_boot_id() {
    _lcbi_value="$(cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n')"
    [ -n "$_lcbi_value" ] || return 1
    printf '%s\n' "$_lcbi_value"
}

luoshu_font_lock_pid() {
    _lflp_path="${1:-$MODULE_DIR/.font_switch.lock}"
    if [ -d "$_lflp_path" ]; then
        sed -n '1p' "$_lflp_path/pid" 2>/dev/null
    elif [ -f "$_lflp_path" ]; then
        sed -n '1p' "$_lflp_path" 2>/dev/null
    fi
}

luoshu_font_lock_starttime() {
    _lfls_path="${1:-$MODULE_DIR/.font_switch.lock}"
    if [ -d "$_lfls_path" ]; then
        sed -n 's/^starttime=//p' "$_lfls_path/pid" 2>/dev/null | sed -n '1p'
    elif [ -f "$_lfls_path" ]; then
        sed -n 's/^starttime=//p' "$_lfls_path" 2>/dev/null | sed -n '1p'
    fi
}

luoshu_font_lock_boot_id() {
    _lflb_path="${1:-$MODULE_DIR/.font_switch.lock}"
    if [ -d "$_lflb_path" ]; then
        sed -n 's/^boot_id=//p' "$_lflb_path/pid" 2>/dev/null | sed -n '1p'
    elif [ -f "$_lflb_path" ]; then
        sed -n 's/^boot_id=//p' "$_lflb_path" 2>/dev/null | sed -n '1p'
    fi
}

luoshu_font_lock_token() {
    _lflt_path="${1:-$MODULE_DIR/.font_switch.lock}"
    if [ -d "$_lflt_path" ]; then
        sed -n 's/^token=//p' "$_lflt_path/pid" 2>/dev/null | sed -n '1p'
    elif [ -f "$_lflt_path" ]; then
        sed -n 's/^token=//p' "$_lflt_path" 2>/dev/null | sed -n '1p'
    fi
}

luoshu_font_lock_created() {
    _lflc_path="${1:-$MODULE_DIR/.font_switch.lock}"
    if [ -d "$_lflc_path" ]; then
        sed -n 's/^created=//p' "$_lflc_path/pid" 2>/dev/null | sed -n '1p'
    elif [ -f "$_lflc_path" ]; then
        sed -n 's/^created=//p' "$_lflc_path" 2>/dev/null | sed -n '1p'
    fi
}

# Root managers and PID namespaces do not always expose an otherwise-live owner
# through kill(2) or /proc. A newly issued token is therefore a short lease as
# well as an ownership nonce. Normal EXIT/signal cleanup releases it immediately;
# the bounded lease only prevents a concurrent request from deleting a live lock.
luoshu_font_lock_recent_token() {
    _lfrt_path="$1"
    _lfrt_token="$(luoshu_font_lock_token "$_lfrt_path")"
    [ -n "$_lfrt_token" ] || return 1
    _lfrt_created="$(luoshu_font_lock_created "$_lfrt_path")"
    _lfrt_now="$(date +%s 2>/dev/null)"
    case "$_lfrt_created:$_lfrt_now" in *[!0-9:]*) return 1 ;; esac
    _lfrt_age=$((_lfrt_now - _lfrt_created))
    _lfrt_lease="${LUOSHU_FONT_LOCK_LEASE_SECONDS:-480}"
    case "$_lfrt_lease" in ''|*[!0-9]*) _lfrt_lease=480 ;; esac
    [ "$_lfrt_age" -ge 0 ] && [ "$_lfrt_age" -le "$_lfrt_lease" ]
}

# A process-local ownership registry closes two PID-namespace races:
# 1. several subshells may report the same $$ even though only one owns the atomic mkdir;
# 2. /proc/<reported-pid> may be hidden, so re-reading starttime during EXIT cannot prove
#    ownership. The random mktemp suffix is persisted in the lock and retained only by the
#    winning shell. Multiple nested LuoShu locks are supported as newline-delimited records.
luoshu_font_lock_owned_record() {
    _lfor_path="$1"
    _lfor_pid="$2"
    printf '%s\n' "${LUOSHU_FONT_LOCK_OWNERS:-}" | awk -F '|' -v p="$_lfor_path" -v i="$_lfor_pid" '
        $1 == p && $2 == i { print; exit }
    '
}

luoshu_font_lock_forget_owned() {
    _lffo_path="$1"
    _lffo_pid="$2"
    LUOSHU_FONT_LOCK_OWNERS="$(printf '%s\n' "${LUOSHU_FONT_LOCK_OWNERS:-}" | awk -F '|' -v p="$_lffo_path" -v i="$_lffo_pid" '
        !($1 == p && $2 == i) && NF { print }
    ')"
}

luoshu_font_lock_active() {
    _lfla_path="${1:-$MODULE_DIR/.font_switch.lock}"
    _lfla_pid="$(luoshu_font_lock_pid "$_lfla_path")"
    case "$_lfla_pid" in ''|*[!0-9]*) return 1 ;; esac

    # A boot mismatch is definitive even when a recycled PID is currently alive.
    _lfla_saved_boot="$(luoshu_font_lock_boot_id "$_lfla_path")"
    if [ -n "$_lfla_saved_boot" ]; then
        _lfla_live_boot="$(luoshu_current_boot_id)" || \
            { luoshu_font_lock_recent_token "$_lfla_path" && return 0; return 1; }
        [ "$_lfla_saved_boot" = "$_lfla_live_boot" ] || return 1
    fi

    _lfla_saved_start="$(luoshu_font_lock_starttime "$_lfla_path")"
    if [ -n "$_lfla_saved_start" ]; then
        case "$_lfla_saved_start" in *[!0-9]*) return 1 ;; esac
        if _lfla_live_start="$(luoshu_process_starttime "$_lfla_pid")"; then
            if [ "$_lfla_saved_start" != "$_lfla_live_start" ]; then
                # A fresh token wins over an ambiguous namespace-visible PID. A
                # genuine reused-PID fixture has no token (legacy) or an expired
                # lease, while a current concurrent switch must not be reaped.
                luoshu_font_lock_recent_token "$_lfla_path" && return 0
                return 1
            fi
            return 0
        fi
        # The lock explicitly supplied a birth identity, so a process that cannot
        # prove that identity is not allowed to keep a legacy lock alive merely
        # because kill -0 happens to resolve in another PID namespace. Only a
        # fresh v4 token lease can bridge that visibility gap.
        luoshu_font_lock_recent_token "$_lfla_path" && return 0
        return 1
    fi
    kill -0 "$_lfla_pid" 2>/dev/null && return 0
    luoshu_font_lock_recent_token "$_lfla_path"
}

luoshu_font_lock_reap_stale() {
    _lfls_path="${1:-$MODULE_DIR/.font_switch.lock}"
    [ -e "$_lfls_path" ] || return 0
    luoshu_font_lock_active "$_lfls_path" && return 1

    # mkdir is the atomic ownership primitive. There is necessarily a tiny window
    # between mkdir and the metadata rename. Do not rely on one scheduler-sensitive
    # sleep to distinguish that window from an abandoned directory: the first
    # observer leaves a marker and refuses to reap. A later observer may wait the
    # configured grace and remove the directory only if it is still ownerless.
    if [ -d "$_lfls_path" ] && [ ! -s "$_lfls_path/pid" ]; then
        _lfls_observed="$_lfls_path/.init-observed"
        if [ ! -e "$_lfls_observed" ]; then
            : > "$_lfls_observed" 2>/dev/null || true
            return 1
        fi
        _lfls_grace="${LUOSHU_FONT_LOCK_INIT_GRACE_SECONDS:-1}"
        case "$_lfls_grace" in ''|*[!0-9.]*|*.*.*) _lfls_grace=1 ;; esac
        sleep "$_lfls_grace" 2>/dev/null || sleep 1
        [ -e "$_lfls_path" ] || return 0
        luoshu_font_lock_active "$_lfls_path" && return 1
    fi

    if [ -d "$_lfls_path" ]; then
        rm -f "$_lfls_path/pid" "$_lfls_path/.init-observed" 2>/dev/null || true
        rmdir "$_lfls_path" 2>/dev/null
    else
        rm -f "$_lfls_path" 2>/dev/null
    fi
}

luoshu_font_lock_acquire() {
    _lfla_path="${1:-$MODULE_DIR/.font_switch.lock}"
    _lfla_owner="${2:-$$}"
    case "$_lfla_owner" in ''|*[!0-9]*) return 1 ;; esac

    _lfla_start="$(luoshu_process_starttime "$_lfla_owner" 2>/dev/null)"
    _lfla_boot="$(luoshu_current_boot_id 2>/dev/null)"
    _lfla_created="$(date +%s 2>/dev/null)"
    case "$_lfla_created" in ''|*[!0-9]*) _lfla_created=0 ;; esac
    _lfla_attempt=0
    # Two attempts can be consumed deliberately while an ownerless directory
    # passes through the two-phase initialization guard. Keep extra bounded
    # retries for slow Root/PID namespaces without ever allowing two owners.
    while [ "$_lfla_attempt" -lt 6 ]; do
        _lfla_tmp="$(mktemp "${_lfla_path}.owner.XXXXXX" 2>/dev/null)" || return 1
        _lfla_token="${_lfla_tmp##*.owner.}"
        {
            printf '%s\n' "$_lfla_owner"
            [ -n "$_lfla_start" ] && printf 'starttime=%s\n' "$_lfla_start"
            [ -n "$_lfla_boot" ] && printf 'boot_id=%s\n' "$_lfla_boot"
            printf 'token=%s\n' "$_lfla_token"
            printf 'created=%s\n' "$_lfla_created"
        } > "$_lfla_tmp" 2>/dev/null || {
            rm -f "$_lfla_tmp" 2>/dev/null || true
            return 1
        }
        chmod 0600 "$_lfla_tmp" 2>/dev/null || true

        if mkdir "$_lfla_path" 2>/dev/null; then
            if mv -f "$_lfla_tmp" "$_lfla_path/pid" 2>/dev/null; then
                LUOSHU_FONT_LOCK_OWNERS="${LUOSHU_FONT_LOCK_OWNERS:+$LUOSHU_FONT_LOCK_OWNERS
}${_lfla_path}|${_lfla_owner}|${_lfla_start}|${_lfla_boot}|${_lfla_token}|${_lfla_created}"
                return 0
            fi
            rm -f "$_lfla_tmp" "$_lfla_path/pid" 2>/dev/null || true
            rmdir "$_lfla_path" 2>/dev/null || true
            return 1
        fi
        rm -f "$_lfla_tmp" 2>/dev/null || true

        [ -e "$_lfla_path" ] || {
            _lfla_attempt=$((_lfla_attempt + 1))
            continue
        }
        luoshu_font_lock_active "$_lfla_path" && return 2
        luoshu_font_lock_reap_stale "$_lfla_path" >/dev/null 2>&1 || true
        _lfla_attempt=$((_lfla_attempt + 1))
        sleep 0.02 2>/dev/null || true
    done
    return 2
}

luoshu_font_lock_release() {
    _lflr_path="${1:-$MODULE_DIR/.font_switch.lock}"
    _lflr_owner="${2:-$$}"
    [ -e "$_lflr_path" ] || return 0
    _lflr_pid="$(luoshu_font_lock_pid "$_lflr_path")"
    [ "$_lflr_pid" = "$_lflr_owner" ] || return 1

    _lflr_saved_start="$(luoshu_font_lock_starttime "$_lflr_path")"
    _lflr_saved_boot="$(luoshu_font_lock_boot_id "$_lflr_path")"
    _lflr_saved_token="$(luoshu_font_lock_token "$_lflr_path")"
    _lflr_owned="$(luoshu_font_lock_owned_record "$_lflr_path" "$_lflr_owner")"
    if [ -n "$_lflr_saved_token" ] && [ -n "$_lflr_owned" ]; then
        _lflr_owned_start="$(printf '%s\n' "$_lflr_owned" | awk -F '|' '{print $3; exit}')"
        _lflr_owned_boot="$(printf '%s\n' "$_lflr_owned" | awk -F '|' '{print $4; exit}')"
        _lflr_owned_token="$(printf '%s\n' "$_lflr_owned" | awk -F '|' '{print $5; exit}')"
        [ "$_lflr_saved_token" = "$_lflr_owned_token" ] || return 1
        [ "$_lflr_saved_start" = "$_lflr_owned_start" ] || return 1
        [ "$_lflr_saved_boot" = "$_lflr_owned_boot" ] || return 1
    else
        # Legacy pid/starttime locks and locks inherited from an older shell have no
        # process-local token; retain the strict live-identity check for compatibility.
        if [ -n "$_lflr_saved_start" ]; then
            _lflr_live_start="$(luoshu_process_starttime "$_lflr_owner")" || return 1
            [ "$_lflr_saved_start" = "$_lflr_live_start" ] || return 1
        fi
        if [ -n "$_lflr_saved_boot" ]; then
            _lflr_live_boot="$(luoshu_current_boot_id)" || return 1
            [ "$_lflr_saved_boot" = "$_lflr_live_boot" ] || return 1
        fi
    fi

    if [ -d "$_lflr_path" ]; then
        rm -f "$_lflr_path/pid" "$_lflr_path/.init-observed" 2>/dev/null || return 1
        rmdir "$_lflr_path" 2>/dev/null || return 1
    else
        rm -f "$_lflr_path" 2>/dev/null || return 1
    fi
    luoshu_font_lock_forget_owned "$_lflr_path" "$_lflr_owner"
    return 0
}

# Unconditionally clear both directory/file lock shapes plus interrupted owner temp files.
luoshu_font_lock_force_clear() {
    _lflfc_path="${1:-$MODULE_DIR/.font_switch.lock}"
    rm -f "$_lflfc_path/pid" "$_lflfc_path/.init-observed" 2>/dev/null || true
    rmdir "$_lflfc_path" 2>/dev/null || true
    rm -f "$_lflfc_path" 2>/dev/null || true
    for _lflfc_tmp in "$_lflfc_path".owner.*; do
        [ -e "$_lflfc_tmp" ] || continue
        rm -f "$_lflfc_tmp" 2>/dev/null || true
    done
    _lflfc_pid="${2:-$$}"
    luoshu_font_lock_forget_owned "$_lflfc_path" "$_lflfc_pid" >/dev/null 2>&1 || true
    [ ! -e "$_lflfc_path" ]
}

# Return 0 only while a live owner is present. Empty mkdir-owned locks receive one
# initialization grace period because acquire creates the directory before metadata mv.
# This function never reaps; callers that need cleanup must call reap_stale separately.
luoshu_font_lock_busy() {
    _lflbz_path="${1:-$MODULE_DIR/.font_switch.lock}"
    [ -e "$_lflbz_path" ] || return 1
    luoshu_font_lock_active "$_lflbz_path" && return 0
    if [ -d "$_lflbz_path" ] && [ ! -s "$_lflbz_path/pid" ]; then
        : > "$_lflbz_path/.init-observed" 2>/dev/null || true
        _lflbz_grace="${LUOSHU_FONT_LOCK_INIT_GRACE_SECONDS:-1}"
        case "$_lflbz_grace" in ''|*[!0-9.]*|*.*.*) _lflbz_grace=1 ;; esac
        sleep "$_lflbz_grace" 2>/dev/null || sleep 1
        [ -e "$_lflbz_path" ] || return 1
        luoshu_font_lock_active "$_lflbz_path" && return 0
    fi
    return 1
}
