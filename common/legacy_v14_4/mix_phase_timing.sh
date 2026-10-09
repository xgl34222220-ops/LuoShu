#!/system/bin/sh
# Diagnostic only: no traps, processes, task cleanup, hashes or business writes.
# proc-uptime normally has 10ms resolution and includes suspend. These spans are
# not the Python-monotonic outer cleanup duration, App latency or phone reboot.

_luompt_pair() {
    case "$1" in *-*) ;; *) return 1 ;; esac
    _luompt_first=${1%%-*}; _luompt_last=${1#*-}
    case "$_luompt_first:$_luompt_last" in :*|*:|*[!0-9:]*) return 1 ;; esac
    [ "${#_luompt_first}" -le 12 ] && [ "${#_luompt_last}" -le 12 ]
}

_luompt_task() {
    _luompt_tag=$1
    case "$_luompt_tag" in *.apply) _luompt_tag=${_luompt_tag%.apply} ;; *.monitor) _luompt_tag=${_luompt_tag%.monitor} ;; esac
    case "$_luompt_tag" in auto-mix-*) _luompt_pair "${_luompt_tag#auto-mix-}" ;;
        axes-*) _luompt_pair "${_luompt_tag#axes-}" ;;
        mix-*) _luompt_pair "${_luompt_tag#mix-}" ;; *) return 1 ;; esac
}

_luompt_clock() {
    IFS=' ' read -r _luompt_raw _luompt_unused < /proc/uptime 2>/dev/null || return 1
    case "$_luompt_raw" in *.*) ;; *) return 1 ;; esac
    _luompt_now_s=${_luompt_raw%%.*}; _luompt_fraction=${_luompt_raw#*.}
    case "$_luompt_now_s:$_luompt_fraction" in :*|*:|*[!0-9:]*) return 1 ;; esac
    [ "${#_luompt_now_s}" -le 10 ] || return 1
    _luompt_fraction=${_luompt_fraction}000
    _luompt_fraction=${_luompt_fraction%"${_luompt_fraction#???}"}
    _luompt_now_ms=$((1$_luompt_fraction - 1000))
}

_luompt_context() {
    case "${LUOSHU_MIX_REQUEST_ID:-}" in mix-request-*)
        _luompt_pair "${LUOSHU_MIX_REQUEST_ID#mix-request-}" || return 1 ;; *) return 1 ;; esac
    _luompt_outer=${LUOSHU_MIX_PHASE_OUTER_TASK:-${LUOSHU_TASK_SCOPE_TASK:-}}
    case "$_luompt_outer" in auto-mix-*|axes-*) _luompt_task "$_luompt_outer" || return 1 ;; *) return 1 ;; esac
    _luompt_current=${LUOSHU_TASK_SCOPE_TASK:-$_luompt_outer}
    _luompt_task "$_luompt_current" || return 1
    IFS= read -r _luompt_boot < /proc/sys/kernel/random/boot_id 2>/dev/null || return 1
    case "$_luompt_boot" in ''|*[!0-9a-f-]*) return 1 ;; esac
    [ "${#_luompt_boot}" -eq 36 ] || return 1
    _luompt_scope_start=unknown
    if [ -n "${LUOSHU_TASK_SCOPE_PIDFILE:-}" ]; then
        { IFS= read -r _luompt_scope_start < "${LUOSHU_TASK_SCOPE_PIDFILE}.start"; } 2>/dev/null || _luompt_scope_start=unknown
        case "$_luompt_scope_start" in ''|*[!0-9]*) _luompt_scope_start=unknown ;; esac
        [ "${#_luompt_scope_start}" -le 20 ] || _luompt_scope_start=unknown
    fi
    [ -n "${LOG_FILE:-}" ]
}

_luompt_write() {
    # Redirect the whole group first so an unavailable/unwritable log is silent.
    { if [ -n "${KSH_VERSION:-}" ]; then print -r -- "$1"
      else printf '%s\n' "$1"; fi >> "$LOG_FILE"; } 2>/dev/null || true
    return 0
}

luoshu_mix_phase_begin() {
    _luompt_active=false
    case "$1" in prepare|composite|fixed-apply|finalize|worker) ;; *) return 0 ;; esac
    case "$2" in prepare|cache_lookup|cold_composite_runner|validate|cache_publish|reuse_output|source_validate|map_payload|local_commit|child_start|wait_child_cleanup|worker_finalize|safe_apply|finalize_lock|complete_hyperos|complete_coloros|next_commit|live_mount|finalize_release) ;; *) return 0 ;; esac
    case "$3" in cjk|latin|digit|fixed|w100|w200|w300|w400|w500|w600|w700|w800|w900) ;; *) return 0 ;; esac
    _luompt_weight=${LUOSHU_MIX_PHASE_WEIGHT:-fixed}
    case "$_luompt_weight" in fixed|100|200|300|400|500|600|700|800|900) ;; *) return 0 ;; esac
    _luompt_method "${4:-probe}" || return 0
    _luompt_context && _luompt_clock || return 0
    _luompt_component=$1; _luompt_phase=$2; _luompt_unit=$3; _luompt_initial_method=$4
    _luompt_start_s=$_luompt_now_s; _luompt_start_ms=$_luompt_now_ms
    _luompt_prefix="[MIX-PHASE] schema=1 request=$LUOSHU_MIX_REQUEST_ID outer=$_luompt_outer task=$_luompt_current boot=$_luompt_boot start=$_luompt_scope_start component=$1 phase=$2 unit=$3 weight=$_luompt_weight clock=proc-uptime"
    _luompt_active=true
    _luompt_write "$_luompt_prefix event=begin method=$4 uptimeSeconds=$_luompt_raw"
    return 0
}

_luompt_method() {
    case "$1" in probe|miss|cold|receipt-hit|legacy-validated-hit|same-source|copy|prepare|apply|wait|finalize|skipped) return 0 ;; *) return 1 ;; esac
}

luoshu_mix_phase_end() {
    [ "${_luompt_active:-false}" = true ] || return 0
    _luompt_active=false
    _luompt_clock || return 0
    _luompt_elapsed=$(((_luompt_now_s - _luompt_start_s) * 1000 + _luompt_now_ms - _luompt_start_ms))
    [ "$_luompt_elapsed" -ge 0 ] && [ "$_luompt_elapsed" -le 86400000 ] || return 0
    _luompt_result=failed; [ "$1" != 0 ] || _luompt_result=ok
    _luompt_final_method=${2:-$_luompt_initial_method}
    _luompt_method "$_luompt_final_method" || return 0
    _luompt_write "$_luompt_prefix event=end method=$_luompt_final_method uptimeSeconds=$_luompt_raw elapsedMs=$_luompt_elapsed result=$_luompt_result"
    return 0
}

luoshu_mix_phase_run() {
    luoshu_mix_phase_begin "$1" "$2" "$3" "$4"
    shift 4
    "$@"
    _luompt_command_rc=$?
    luoshu_mix_phase_end "$_luompt_command_rc"
    return "$_luompt_command_rc"
}
