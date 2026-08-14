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
    _lps_stat="$(cat "/proc/$_lps_pid/stat" 2>/dev/null)" || return 1
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

luoshu_font_lock_active() {
    _lfla_path="${1:-$MODULE_DIR/.font_switch.lock}"
    _lfla_pid="$(luoshu_font_lock_pid "$_lfla_path")"
    case "$_lfla_pid" in ''|*[!0-9]*) return 1 ;; esac
    kill -0 "$_lfla_pid" 2>/dev/null || return 1

    _lfla_saved_start="$(luoshu_font_lock_starttime "$_lfla_path")"
    if [ -n "$_lfla_saved_start" ]; then
        case "$_lfla_saved_start" in *[!0-9]*) return 1 ;; esac
        _lfla_live_start="$(luoshu_process_starttime "$_lfla_pid")" || return 0
        [ "$_lfla_saved_start" = "$_lfla_live_start" ] || return 1
    fi

    _lfla_saved_boot="$(luoshu_font_lock_boot_id "$_lfla_path")"
    if [ -n "$_lfla_saved_boot" ]; then
        _lfla_live_boot="$(luoshu_current_boot_id)" || return 0
        [ "$_lfla_saved_boot" = "$_lfla_live_boot" ] || return 1
    fi
    return 0
}

luoshu_font_lock_reap_stale() {
    _lfls_path="${1:-$MODULE_DIR/.font_switch.lock}"
    [ -e "$_lfls_path" ] || return 0
    luoshu_font_lock_active "$_lfls_path" && return 1

    # mkdir is the atomic ownership primitive. If another process has just won
    # mkdir but has not renamed the prepared metadata file into place yet,
    # give it one short grace period before deciding that the directory is stale.
    if [ -d "$_lfls_path" ] && [ ! -s "$_lfls_path/pid" ]; then
        _lfls_grace="${LUOSHU_FONT_LOCK_INIT_GRACE_SECONDS:-1}"
        case "$_lfls_grace" in ''|*[!0-9.]*|*.*.*) _lfls_grace=1 ;; esac
        sleep "$_lfls_grace" 2>/dev/null || sleep 1
        [ -e "$_lfls_path" ] || return 0
        luoshu_font_lock_active "$_lfls_path" && return 1
    fi

    if [ -d "$_lfls_path" ]; then
        rm -f "$_lfls_path/pid" 2>/dev/null || true
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
    _lfla_attempt=0
    while [ "$_lfla_attempt" -lt 3 ]; do
        _lfla_tmp="$(mktemp "${_lfla_path}.owner.XXXXXX" 2>/dev/null)" || return 1
        {
            printf '%s\n' "$_lfla_owner"
            [ -n "$_lfla_start" ] && printf 'starttime=%s\n' "$_lfla_start"
            [ -n "$_lfla_boot" ] && printf 'boot_id=%s\n' "$_lfla_boot"
        } > "$_lfla_tmp" 2>/dev/null || {
            rm -f "$_lfla_tmp" 2>/dev/null || true
            return 1
        }
        chmod 0600 "$_lfla_tmp" 2>/dev/null || true

        if mkdir "$_lfla_path" 2>/dev/null; then
            if mv -f "$_lfla_tmp" "$_lfla_path/pid" 2>/dev/null; then
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
    if [ -n "$_lflr_saved_start" ]; then
        _lflr_live_start="$(luoshu_process_starttime "$_lflr_owner")" || return 1
        [ "$_lflr_saved_start" = "$_lflr_live_start" ] || return 1
    fi
    _lflr_saved_boot="$(luoshu_font_lock_boot_id "$_lflr_path")"
    if [ -n "$_lflr_saved_boot" ]; then
        _lflr_live_boot="$(luoshu_current_boot_id)" || return 1
        [ "$_lflr_saved_boot" = "$_lflr_live_boot" ] || return 1
    fi

    if [ -d "$_lflr_path" ]; then
        rm -f "$_lflr_path/pid" 2>/dev/null || return 1
        rmdir "$_lflr_path" 2>/dev/null
    else
        rm -f "$_lflr_path" 2>/dev/null
    fi
}
