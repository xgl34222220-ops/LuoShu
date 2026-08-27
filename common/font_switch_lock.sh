#!/system/bin/sh
# LuoShu font-switch lock helpers.
# This file is intentionally independent from the font generation/mapping engine so
# the v14.4 compatibility backend can retain current concurrency safety without
# importing the v4 payload/template pipeline.
set +e

luoshu_process_starttime() {
    _lps_pid="$1"
    case "$_lps_pid" in ''|*[!0-9]*) return 1 ;; esac
    _lps_stat_path="/proc/$_lps_pid/stat"
    if [ "$_lps_pid" = "$$" ] && [ ! -r "$_lps_stat_path" ]; then
        if [ -n "${PPID:-}" ] && [ -r "/proc/$PPID/stat" ]; then
            _lps_stat_path="/proc/$PPID/stat"
        else
            _lps_stat_path=/proc/self/stat
        fi
    fi
    [ -r "$_lps_stat_path" ] || return 1
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
                luoshu_font_lock_recent_token "$_lfla_path" && return 0
                return 1
            fi
            return 0
        fi
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
    while [ "$_lfla_attempt" -lt 6 ]; do
        _lfla_tmp="$(mktemp "${_lfla_path}.owner.XXXXXX" 2>/dev/null)" || return 1
        _lfla_token="${_lfla_tmp##*.owner.}"
        {
            printf '%s\n' "$_lfla_owner"
            [ -n "$_lfla_start" ] && printf 'starttime=%s\n' "$_lfla_start"
            [ -n "$_lfla_boot" ] && printf 'boot_id=%s\n' "$_lfla_boot"
            printf 'token=%s\n' "$_lfla_token"
            printf 'created=%s\n' "$_lfla_created"
        } > "$_lfla_tmp" 2>/dev/null || { rm -f "$_lfla_tmp" 2>/dev/null || true; return 1; }
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
        [ -e "$_lfla_path" ] || { _lfla_attempt=$((_lfla_attempt + 1)); continue; }
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
