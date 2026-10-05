#!/system/bin/sh
# Current App -> v14.4 composite-core compatibility router.
# Composite generation is isolated from the payload mounted by the current boot.
# The compatibility runtime writes into .luoshu-mix-stage; a successful task is then
# committed as the real module's .luoshu-payload-next for atomic activation next boot.
set +e

REALMOD="${MODDIR:-}"
if [ -z "$REALMOD" ]; then
    if [ -f "${0%/*}/../../module.prop" ]; then
        REALMOD="$(CDPATH= cd -- "${0%/*}/../.." 2>/dev/null && pwd)"
    else
        REALMOD="/data/adb/modules/LuoShu"
    fi
fi
[ -f "$REALMOD/common/runtime_paths.sh" ] && {
    . "$REALMOD/common/runtime_paths.sh"
    luoshu_runtime_paths_init "$REALMOD" || exit 126
}
LEGACY="$REALMOD/common/legacy_v14_4"
RUNTIME="${LUOSHU_CACHE_DIR:-$REALMOD/cache}/legacy-v14-runtime"
LIVE_PAYLOAD="$REALMOD/.luoshu-payload"
MIX_STAGE="${LUOSHU_TMP_DIR:-$REALMOD/.luoshu-state/tmp}/mix-stage"
NEXT_PAYLOAD="$REALMOD/.luoshu-payload-next"
NEXT_STATE="$REALMOD/config/font-payload-next.conf"
MIX_STAGE_STATE="$REALMOD/config/mix-stage-next.conf"
MIX_MANIFEST="$MIX_STAGE/.luoshu-mix-generation.conf"
ACTIVE_CONF="$REALMOD/config/active_font.conf"
LEGACY_MODE="$REALMOD/config/font_runtime_legacy_v14_4.conf"
REBOOT_CONF="$REALMOD/config/text_reboot_required.conf"
LOG_FILE="$REALMOD/logs/fontswitch.log"
FINALIZE_LOCK="${LUOSHU_TASKS_DIR:-$REALMOD/.luoshu-state/tasks}/mix-stage-finalize.lock"
[ -f "$LEGACY/payload_clone.sh" ] && . "$LEGACY/payload_clone.sh"
. "$REALMOD/common/font_next_transaction.sh" || exit 126
. "$REALMOD/common/font_switch_lock.sh" || exit 126
FINALIZE_FONT_LOCK="$REALMOD/.font_switch.lock"

read_value() {
    sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

json_escape_router() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
}

mix_transaction_pending() {
    [ -e "$REALMOD/config/font-live-transaction.conf" ] || [ -L "$REALMOD/config/font-live-transaction.conf" ] || \
    [ -e "$REALMOD/.luoshu-state/backup/next-transaction" ] || [ -L "$REALMOD/.luoshu-state/backup/next-transaction" ]
}

# The App reads this on every entry to the combination page.  Building the entire
# compatibility runtime just to read three small config files can exceed the App's
# 25-second Root timeout while another worker owns the filesystem, which surfaced
# as `read interrupted by close() on another thread`.  The config is atomically
# persisted in REALMOD/config, so answer it directly without touching payloads.
mix_config_json_fast() {
    _source="$REALMOD/config/axes_mix.conf"
    [ -s "$_source" ] || _source="$REALMOD/config/font_mix.conf"
    _cjk=$(read_value "$_source" cjk)
    _latin=$(read_value "$_source" latin)
    _digit=$(read_value "$_source" digit)
    _cjk_weight=$(read_value "$_source" cjkWeight)
    _latin_weight=$(read_value "$_source" latinWeight)
    _digit_weight=$(read_value "$_source" digitWeight)
    case "$_cjk_weight" in ''|*[!0-9]*) _cjk_weight=400 ;; esac
    case "$_latin_weight" in ''|*[!0-9]*) _latin_weight=400 ;; esac
    case "$_digit_weight" in ''|*[!0-9]*) _digit_weight=400 ;; esac
    _cjk_axes=$(read_value "$_source" cjkAxes)
    _latin_axes=$(read_value "$_source" latinAxes)
    _digit_axes=$(read_value "$_source" digitAxes)
    [ -n "$_cjk_axes" ] || _cjk_axes="wght=$_cjk_weight"
    [ -n "$_latin_axes" ] || _latin_axes="wght=$_latin_weight"
    [ -n "$_digit_axes" ] || _digit_axes="wght=$_digit_weight"
    _enabled=false
    [ "$(head -n1 "$ACTIVE_CONF" 2>/dev/null | tr -d '\r\n')" = mix ] && _enabled=true
    printf '{"status":"ok","data":{"enabled":%s,"cjk":"%s","latin":"%s","digit":"%s","cjkWeight":%s,"latinWeight":%s,"digitWeight":%s,"cjkAxes":"%s","latinAxes":"%s","digitAxes":"%s"}}\n' \
        "$_enabled" "$(json_escape_router "$_cjk")" "$(json_escape_router "$_latin")" "$(json_escape_router "$_digit")" \
        "$_cjk_weight" "$_latin_weight" "$_digit_weight" \
        "$(json_escape_router "$_cjk_axes")" "$(json_escape_router "$_latin_axes")" "$(json_escape_router "$_digit_axes")"
}

# Inspect every controller/engine/monitor slot without signalling processes.
# 0 = proved cleanup, 1 = safe absence without a terminal proof, 3 = live,
# 125 = unconfirmed cleanup. Successful work always requires a matching proof.
mix_scope_state_fast() (
    _mssf_file="$1"; _mssf_task=$(read_value "$1" task)
    _mssf_child=$(read_value "$1" childTask); [ -n "$_mssf_child" ] || _mssf_child="$_mssf_task"
    _mssf_root="${LUOSHU_TASKS_DIR:-$REALMOD/.luoshu-state/tasks}"
    . "$REALMOD/common/background_task.sh" || return 125
    _mssf_live=0; _mssf_unknown=0; _mssf_exact=0
    for _mssf_slot in "axes_worker.pid|$_mssf_task" "auto_multiweight_worker.pid|$_mssf_task" \
        "mix_worker.pid|$_mssf_child" "mix-monitor-$_mssf_child.pid|$_mssf_child.monitor"; do
        _mssf_pidfile="$_mssf_root/${_mssf_slot%%|*}"; _mssf_expected="${_mssf_slot#*|}"
        sh "$(luoshu_scope_runner)" settled "$_mssf_pidfile" >/dev/null 2>&1
        _mssf_rc=$?
        case "$_mssf_rc" in 0) ;; 3) _mssf_live=1; continue ;; *) _mssf_unknown=1; continue ;; esac
        if [ "$_mssf_exact" -eq 0 ]; then
            if sh "$(luoshu_scope_runner)" cleaned "$_mssf_pidfile" "$_mssf_expected" >/dev/null 2>&1; then
                _mssf_exact=1
            else
                # Previous-boot registrations/proofs have no surviving tasks.
                _mssf_boot=$(cat "$_mssf_pidfile.boot" 2>/dev/null | tr -d '\r\n')
                _mssf_saved_task=$(cat "$_mssf_pidfile.task" 2>/dev/null | tr -d '\r\n')
                if [ -z "$_mssf_boot" ] && grep -Fq '"task": "'"$_mssf_expected"'"' "$_mssf_pidfile.cleanup.json" 2>/dev/null; then
                    _mssf_boot=$(sed -n 's/.*"boot": "\([^"]*\)".*/\1/p' "$_mssf_pidfile.cleanup.json" 2>/dev/null)
                    _mssf_saved_task="$_mssf_expected"
                fi
                if [ "$_mssf_saved_task" = "$_mssf_expected" ] && [ -n "$_mssf_boot" ] && \
                   [ "$_mssf_boot" != "$(luoshu_current_boot_id)" ]; then _mssf_exact=1; fi
            fi
        fi
    done
    [ "$_mssf_live" -eq 0 ] || return 3
    [ "$_mssf_unknown" -eq 0 ] || return 125
    [ "$_mssf_exact" -eq 1 ] || [ "$(read_value "$_mssf_file" cleanupConfirmed)" = true ] || return 1
    return 0
)

# Reconcile task metadata only: no runtime links, font reads or payload changes.
mix_reconcile_fast() (
    _mrf_file="$REALMOD/config/axes_task.conf"
    [ -s "$_mrf_file" ] || _mrf_file="$REALMOD/config/mix_task.conf"
    [ -s "$_mrf_file" ] || return 0
    _mrf_snapshot=$(cat "$_mrf_file" 2>/dev/null) || return 0
    _mrf_state=$(read_value "$_mrf_file" state)
    case "$_mrf_state" in queued|running|success|failed|cleanup-pending) ;; *) return 0 ;; esac
    _mrf_task=$(read_value "$_mrf_file" task)
    [ -n "$_mrf_task" ] || return 0
    [ -f "$REALMOD/common/background_task.sh" ] || return 0
    . "$REALMOD/common/background_task.sh"
    mix_scope_state_fast "$_mrf_file"; _mrf_scope=$?
    [ "$_mrf_scope" -ne 3 ] || return 0
    _mrf_started=$(read_value "$_mrf_file" started)
    _mrf_now=$(date +%s 2>/dev/null) || return 0
    case "$_mrf_now" in ''|*[!0-9]*) return 0 ;; esac
    case "$_mrf_started" in
        ''|*[!0-9]*) _mrf_started=$(stat -c '%Y' "$_mrf_file" 2>/dev/null) ;;
    esac
    case "$_mrf_started" in ''|*[!0-9]*) _mrf_started=0 ;; esac
    # The queued record precedes the detached worker and its sidecar writes.
    # Preserve that startup window, including a worker already marked running.
    _mrf_age=$((_mrf_now - _mrf_started))
    case "$_mrf_state" in queued|running)
        [ "$_mrf_age" -ge 20 ] 2>/dev/null || return 0 ;;
    esac
    _mrf_terminal=$(read_value "$_mrf_file" terminalState)
    _mrf_message=$(read_value "$_mrf_file" message)
    _mrf_terminal_message=$(read_value "$_mrf_file" terminalMessage)
    _mrf_confirmed=false
    if [ "$_mrf_scope" -eq 125 ] || mix_transaction_pending; then
        case "$_mrf_state" in success|failed) _mrf_terminal="$_mrf_state"; _mrf_terminal_message="$_mrf_message" ;; esac
        [ -n "$_mrf_terminal" ] || _mrf_terminal=failed
        _mrf_new=cleanup-pending; _mrf_message='字体组合任务清理尚未确认，请刷新重试'
    elif [ "$_mrf_scope" -eq 1 ] && { [ "$_mrf_state" = success ] || \
         { [ "$_mrf_state" = cleanup-pending ] && [ "$_mrf_terminal" = success ]; }; }; then
        [ "$_mrf_state" != success ] || _mrf_terminal_message="$_mrf_message"
        _mrf_new=cleanup-pending; _mrf_terminal=success
        _mrf_message='字体组合任务清理尚未确认，请刷新重试'
    else
        _mrf_confirmed=true
        case "$_mrf_state" in
            success|failed)
                [ "$_mrf_scope" -ne 0 ] || return 0
                _mrf_new="$_mrf_state" ;;
            cleanup-pending) _mrf_new="${_mrf_terminal:-failed}"; _mrf_message="${_mrf_terminal_message:-字体组合进程已退出，任务子进程已回收}" ;;
            *) _mrf_new=failed; _mrf_message='字体组合进程已退出，任务子进程已回收' ;;
        esac
        _mrf_terminal=''; _mrf_terminal_message=''
    fi
    _mrf_tmp="${_mrf_file}.reconcile.$$"
    printf '%s\n' "$_mrf_snapshot" | awk -F '=' -v now="$_mrf_now" -v state="$_mrf_new" -v message="$_mrf_message" \
        -v terminal="$_mrf_terminal" -v terminal_message="$_mrf_terminal_message" -v confirmed="$_mrf_confirmed" '
        $1 != "state" && $1 != "message" && $1 != "percent" && $1 != "finished" &&
        $1 != "terminalState" && $1 != "terminalMessage" && $1 != "cleanupConfirmed" {print}
        END {print "state=" state; print "message=" message; print "percent=100"; print "finished=" now;
             print "terminalState=" terminal; print "terminalMessage=" terminal_message; print "cleanupConfirmed=" confirmed}' > "$_mrf_tmp" || return 0
    # A new request or worker may have arrived while the lightweight checks ran.
    # Do not publish a stale failure over its task record or erase its sidecars.
    if [ "$(cat "$_mrf_file" 2>/dev/null)" != "$_mrf_snapshot" ]; then
        rm -f "$_mrf_tmp" 2>/dev/null || true
        return 0
    fi
    mv -f "$_mrf_tmp" "$_mrf_file" 2>/dev/null || { rm -f "$_mrf_tmp"; return 0; }
)

mix_status_json_fast() {
    mix_reconcile_fast
    _wanted="$1"
    _task_file="$REALMOD/config/axes_task.conf"
    [ -s "$_task_file" ] || _task_file="$REALMOD/config/mix_task.conf"
    [ -s "$_task_file" ] || {
        printf '{"status":"error","message":"暂无字体组合任务"}\n'
        return 0
    }
    _task=$(read_value "$_task_file" task)
    if [ -n "$_wanted" ] && [ "$_wanted" != "$_task" ]; then
        printf '{"status":"error","message":"任务不存在或已被新任务替换"}\n'
        return 0
    fi
    _state=$(read_value "$_task_file" state)
    _status_original_state="$_state"
    _status_scope=''
    _status_child=$(read_value "$_task_file" childTask)
    [ -n "$_status_child" ] || _status_child="$_task"
    case "$_state" in success|failed|cleanup-pending)
        mix_scope_state_fast "$_task_file"; _status_scope=$?
        case "$_status_scope" in 0) ;; 3) _state=running ;; *) _state=cleanup-pending ;; esac
        ;;
    esac
    _message=$(read_value "$_task_file" message)
    _percent=$(read_value "$_task_file" percent)
    case "$_percent" in ''|*[!0-9]*) _percent=0 ;; esac

    if [ "$_state" = success ]; then
        _task_request=$(read_value "$_task_file" requestId)
        _task_committed=$(read_value "$_task_file" committedRequestId)
        _task_receipt="$REALMOD/config/mix-commit.conf"
        if [ -n "$_task_request" ] && [ "$(read_value "$_task_receipt" font)" = mix ] && \
           [ "$(read_value "$_task_receipt" requestId)" = "$_task_request" ] && ! mix_transaction_pending; then
            _task_committed="$_task_request"
        fi
        _next_font=$(read_value "$NEXT_STATE" font)
        _next_request=$(read_value "$NEXT_STATE" requestId)
        _stage_request=$(read_value "$MIX_STAGE_STATE" requestId)
        _finalize_state=$(read_value "$REALMOD/config/mix-finalize-state.conf" state)
        _finalize_message=$(read_value "$REALMOD/config/mix-finalize-state.conf" message)
        if [ -n "$_task_request" ] && [ "$_task_committed" = "$_task_request" ]; then
            # This task's publish was already proved. Its historical completion
            # survives the next boot consuming NEXT, or a later selection.
            _percent=100
        elif [ -z "$_task_request" ] && [ -z "$_stage_request" ] && [ ! -e "$MIX_STAGE" ] && [ ! -L "$MIX_STAGE" ]; then
            # Older installed controllers persisted terminal success after their
            # finalize step, but had no per-task request field. Keep this proven
            # history terminal; it cannot assert a current live activation.
            _percent=100
        elif [ -n "$_task_request" ] && [ -d "$NEXT_PAYLOAD" ] && [ "$_next_font" = mix ] && \
           [ "$_task_request" = "$_next_request" ] && \
           { [ -z "$_stage_request" ] || [ "$_stage_request" = "$_next_request" ]; }; then
            _percent=100
        else
            if [ "$_finalize_state" = failed ]; then
                _state=failed
                _message="${_finalize_message:-复合字体负载提交失败}"
                _percent=100
            else
                _state=running
                _message="${_finalize_message:-正在提交下一启动字体负载}"
                _percent=99
            fi
        fi
    fi

    _live_applied=false; _activation=pending-reboot
    _live_file="$REALMOD/config/font-live.conf"
    _live_request=$(read_value "$_live_file" requestId)
    _task_request=$(read_value "$_task_file" requestId)
    _next_request=$(read_value "$NEXT_STATE" requestId)
    _current_boot=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n')
    if [ "$_state" = success ] && ! mix_transaction_pending && [ -n "$_live_request" ] && \
       [ "$_live_request" = "$_task_request" ] && [ "$_live_request" = "$_next_request" ] && \
       [ "$(read_value "$_live_file" bootId)" = "$_current_boot" ] && \
       [ "$(read_value "$_live_file" font)" = mix ] && [ "$(read_value "$_live_file" state)" = mounted ] && \
       [ "$(read_value "$REALMOD/config/self-mount.conf" state)" = mounted ]; then
        _live_applied=true; _activation=live-mounted
        _message='当前启动已挂载新字体，重启后完整生效'
    fi
    if mix_transaction_pending; then
        _status_active=false
        [ "$_status_scope" != 3 ] || _status_active=true
        case "$_status_original_state" in queued|running)
            if [ -z "$_status_scope" ]; then
                mix_scope_state_fast "$_task_file"; _status_scope=$?
            fi
            if [ "$_status_scope" -eq 3 ]; then
                _status_active=true
            elif [ "$_status_scope" -eq 1 ]; then
                # The queued record can precede supervisor registration. Keep
                # only this original startup grace, never derived running99.
                _status_started=$(read_value "$_task_file" started)
                _status_now=$(date +%s 2>/dev/null)
                case "$_status_started:$_status_now" in *[!0-9:]*|:*) ;; *)
                    [ $((_status_now - _status_started)) -ge 20 ] 2>/dev/null || _status_active=true ;;
                esac
            fi
            ;;
        esac
        if [ "$_status_active" != true ]; then
            _state=cleanup-pending; _message='等待恢复上次字体挂载事务，请刷新后重试'
            _live_applied=false; _activation=pending-reboot
        fi
    fi
    _cjk=$(read_value "$_task_file" cjk)
    _latin=$(read_value "$_task_file" latin)
    _digit=$(read_value "$_task_file" digit)
    _cjk_axes=$(read_value "$_task_file" cjkAxes); [ -n "$_cjk_axes" ] || _cjk_axes=wght=400
    _latin_axes=$(read_value "$_task_file" latinAxes); [ -n "$_latin_axes" ] || _latin_axes=wght=400
    _digit_axes=$(read_value "$_task_file" digitAxes); [ -n "$_digit_axes" ] || _digit_axes=wght=400
    printf '{"status":"ok","data":{"task":"%s","state":"%s","message":"%s","cjk":"%s","latin":"%s","digit":"%s","cjkWeight":400,"latinWeight":400,"digitWeight":400,"cjkAxes":"%s","latinAxes":"%s","digitAxes":"%s","timeout":720,"rebootRequired":true,"liveApplied":%s,"activation":"%s","progress":{"message":"%s","percent":%s}}}\n' \
        "$(json_escape_router "$_task")" "$(json_escape_router "$_state")" "$(json_escape_router "$_message")" \
        "$(json_escape_router "$_cjk")" "$(json_escape_router "$_latin")" "$(json_escape_router "$_digit")" \
        "$(json_escape_router "$_cjk_axes")" "$(json_escape_router "$_latin_axes")" "$(json_escape_router "$_digit_axes")" \
        "$_live_applied" "$_activation" "$(json_escape_router "$_message")" "$_percent"
}

force_link() {
    _target="$1"; _link="$2"
    if [ -L "$_link" ]; then
        ln -sfn "$_target" "$_link" 2>/dev/null || return 1
    elif [ -e "$_link" ]; then
        rm -rf "$_link" 2>/dev/null || return 1
        ln -s "$_target" "$_link" 2>/dev/null || return 1
    else
        ln -s "$_target" "$_link" 2>/dev/null || return 1
    fi
}

mix_clone_source() {
    if [ -d "$LIVE_PAYLOAD" ]; then
        printf '%s\n' "$LIVE_PAYLOAD"
        return 0
    fi

    # Match the normal safe-switch recovery path: if early boot retired the live
    # payload and was interrupted before completing activation, recover only from
    # the retired tree recorded by this module.
    _activated="$REALMOD/config/font-payload-activated.conf"
    _retired=$(read_value "$_activated" retired)
    case "$_retired" in
        "$REALMOD"/.luoshu-retired/*)
            [ -d "$_retired" ] && { printf '%s\n' "$_retired"; return 0; }
            ;;
    esac
    return 1
}

clone_mix_tree() {
    _source="$1"
    rm -rf "$MIX_STAGE" 2>/dev/null || true
    mkdir -p "$MIX_STAGE" 2>/dev/null || return 1

    if luoshu_clone_payload_metadata "$_source" "$MIX_STAGE"; then
        return 0
    fi
    rm -rf "$MIX_STAGE" 2>/dev/null || true
    return 1
}

clear_mix_text_payload() {
    _payload="$1"
    # A second composite starts from the previous live tree only so non-font
    # payload state can be retained. No previous text alias may survive into the
    # new generation: otherwise slots not rediscovered on this pass keep the old
    # digit/Latin source and Android displays two composite generations at once.
    for _part in system system_ext product vendor odm oem my_product \
                 my_engineering my_company my_preload my_region my_stock \
                 oplus_product oplus_engineering oplus_version oplus_region \
                 mi_ext cust hw_product; do
        rm -rf "$_payload/$_part/fonts" 2>/dev/null || true
        _etc="$_payload/$_part/etc"
        [ -d "$_etc" ] || continue
        for _xml in "$_etc"/*.xml; do
            [ -f "$_xml" ] || continue
            grep -a -qE 'LuoShuSlot-|LuoShu(Mono)?-|luoshu' "$_xml" 2>/dev/null && \
                rm -f "$_xml" 2>/dev/null || true
        done
    done
    mkdir -p "$_payload/system/fonts" 2>/dev/null || return 1
    return 0
}

prepare_mix_stage() {
    mkdir -p "$REALMOD/config" "$REALMOD/cache" "$REALMOD/logs" 2>/dev/null || return 1
    rm -rf "$MIX_STAGE" 2>/dev/null || true
    mkdir -p "$MIX_STAGE" 2>/dev/null || return 1
    if [ -d "$LIVE_PAYLOAD" ]; then
        _clone_source="$LIVE_PAYLOAD"
    else
        _clone_source=$(mix_clone_source 2>/dev/null || true)
    fi
    if [ -n "$_clone_source" ] && ! clone_mix_tree "$_clone_source"; then
        printf '[%s] [MIX] stage clone failed source=%s live=%s next=%s\n' \
            "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo unknown)" \
            "$_clone_source" "$LIVE_PAYLOAD" "$NEXT_PAYLOAD" >> "$LOG_FILE" 2>/dev/null || true
        return 1
    fi
    clear_mix_text_payload "$MIX_STAGE" || return 1

    _previous=$(head -n1 "$ACTIVE_CONF" 2>/dev/null | tr -d '\r\n')
    [ -n "$_previous" ] || _previous=default
    _previous_legacy=false
    [ -f "$LEGACY_MODE" ] && _previous_legacy=true
    # ACTIVE is the pending user selection, not necessarily this boot's source.
    # Retain the original boot baseline across default -> mix and repeated mixes.
    if [ -s "$NEXT_STATE" ]; then
        _queued_previous=$(read_value "$NEXT_STATE" previousFont)
        _queued_legacy=$(read_value "$NEXT_STATE" previousLegacy)
        [ -n "$_queued_previous" ] && _previous="$_queued_previous"
        [ "$_queued_legacy" = true ] && _previous_legacy=true || _previous_legacy=false
    fi
    _request="mix-request-$(date +%s 2>/dev/null || echo 0)-$$"
    {
        printf 'requestId=%s\n' "$_request"
        printf 'cjk=%s\nlatin=%s\ndigit=%s\n' "$1" "$2" "$3"
        printf 'cjkAxes=%s\nlatinAxes=%s\ndigitAxes=%s\n' "$4" "$5" "$6"
        printf 'previousFont=%s\n' "$_previous"
        printf 'previousLegacy=%s\n' "$_previous_legacy"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "${MIX_STAGE_STATE}.tmp.$$" 2>/dev/null && \
        mv -f "${MIX_STAGE_STATE}.tmp.$$" "$MIX_STAGE_STATE" 2>/dev/null || return 1
    chmod 0644 "$MIX_STAGE_STATE" 2>/dev/null || true
    return 0
}

stage_has_fonts() {
    [ -d "$MIX_STAGE" ] || return 1
    find "$MIX_STAGE" -type f \( -iname '*.ttf' -o -iname '*.otf' -o -iname '*.ttc' \) \
        -print -quit 2>/dev/null | grep -q .
}

stage_generation_matches() {
    _request=$(read_value "$MIX_STAGE_STATE" requestId)
    # Backward recovery for a stage produced by an older installed build.
    [ -n "$_request" ] || return 0
    [ -s "$MIX_MANIFEST" ] || return 1
    [ "$(read_value "$MIX_MANIFEST" requestId)" = "$_request" ] || return 1
    for _field in cjk latin digit; do
        [ "$(read_value "$MIX_MANIFEST" "$_field")" = "$(read_value "$MIX_STAGE_STATE" "$_field")" ] || return 1
    done
    [ -n "$(read_value "$MIX_MANIFEST" compositeHash)" ] || return 1
    return 0
}

complete_hyperos_stage() {
    _helper="$REALMOD/common/hyperos_stage_complete.sh"
    if [ -e /system/fonts/MiSansVF.ttf ] || [ -n "$(getprop ro.mi.os.version.name 2>/dev/null)" ] || \
       [ -n "$(getprop ro.miui.ui.version.name 2>/dev/null)" ]; then
        [ -f "$_helper" ] || return 1
        LUOSHU_REAL_MODDIR="$REALMOD" sh "$_helper" "$MIX_STAGE" >> "$LOG_FILE" 2>&1 || return 1
    fi
}

complete_coloros_stage() {
    # The composite worker runs in a separate shell. Detect the same ROM markers
    # as legacy util_functions instead of relying on its unexported IS_COLOROS.
    _helper="$REALMOD/common/coloros_stage_complete.sh"
    if [ -e /system/fonts/MiSansVF.ttf ] || [ -n "$(getprop ro.mi.os.version.name 2>/dev/null)" ] || \
       [ -n "$(getprop ro.miui.ui.version.name 2>/dev/null)" ]; then
        return 0
    fi
    if [ -n "$(getprop ro.build.version.oplusrom 2>/dev/null)" ] || \
       [ -n "$(getprop ro.build.version.opporom 2>/dev/null)" ] || \
       [ -d /data/oplus/os ] || [ -d /system_ext/oplus ] || \
       [ -e /system/fonts/SysSans-En-Regular.ttf ] || \
       [ -e /system/fonts/SysFont-Regular.ttf ]; then
        [ -f "$_helper" ] || return 1
        LUOSHU_REAL_MODDIR="$REALMOD" sh "$_helper" "$MIX_STAGE" >> "$LOG_FILE" 2>&1 || return 1
    fi
    return 0
}

write_next_state() {
    _previous=$(read_value "$MIX_STAGE_STATE" previousFont)
    _previous_legacy=$(read_value "$MIX_STAGE_STATE" previousLegacy)
    _request=$(read_value "$MIX_STAGE_STATE" requestId)
    _generation_manifest="$MIX_MANIFEST"
    [ -s "$_generation_manifest" ] || _generation_manifest="$NEXT_PAYLOAD/.luoshu-mix-generation.conf"
    [ -n "$_previous" ] || _previous=default
    [ "$_previous_legacy" = true ] || _previous_legacy=false
    _tmp="$LUOSHU_TMP_DIR/mix-next-state-$$"
    {
        printf 'state=prepared\n'
        printf 'font=mix\n'
        printf 'requestId=%s\n' "$_request"
        printf 'cjk=%s\nlatin=%s\ndigit=%s\n' \
            "$(read_value "$MIX_STAGE_STATE" cjk)" "$(read_value "$MIX_STAGE_STATE" latin)" "$(read_value "$MIX_STAGE_STATE" digit)"
        printf 'compositeHash=%s\n' "$(read_value "$_generation_manifest" compositeHash)"
        printf 'previousFont=%s\n' "$_previous"
        printf 'previousLegacy=%s\n' "$_previous_legacy"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$_tmp" 2>/dev/null || return 1
    STAGED_NEXT_STATE="$_tmp"
    return 0
}

write_next_selection() {
    printf 'mix\n' > "$ACTIVE_CONF" 2>/dev/null || return 1
    chmod 0644 "$ACTIVE_CONF" 2>/dev/null || true
    _boot_id=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null | tr -d '\r\n')
    {
        printf 'font=mix\n'
        printf 'reason=next-boot-payload-prepared\n'
        printf 'bootId=%s\n' "$_boot_id"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } > "$REBOOT_CONF" 2>/dev/null || true
    chmod 0644 "$REBOOT_CONF" 2>/dev/null || true
    return 0
}

mark_mix_request_committed() {
    _commit_request=$(read_value "$NEXT_STATE" requestId)
    [ -n "$_commit_request" ] && [ "$(read_value "$NEXT_STATE" font)" = mix ] || return 1
    _receipt="$REALMOD/config/mix-commit.conf"
    _receipt_tmp="$LUOSHU_TMP_DIR/mix-commit-receipt-$$"
    {
        printf 'font=mix\nrequestId=%s\nbootId=%s\n' "$_commit_request" "$(cat /proc/sys/kernel/random/boot_id 2>/dev/null)"
        for _commit_role in cjk latin digit; do
            printf '%s=%s\n' "$_commit_role" "$(read_value "$NEXT_STATE" "$_commit_role")"
        done
    } > "$_receipt_tmp" && mv -f "$_receipt_tmp" "$_receipt" || return 1
    for _commit_task in "$REALMOD/config/axes_task.conf" "$REALMOD/config/mix_task.conf"; do
        [ -s "$_commit_task" ] || continue
        [ "$(read_value "$_commit_task" requestId)" = "$_commit_request" ] || continue
        _commit_snapshot=$(cat "$_commit_task") || return 1
        _commit_tmp="$LUOSHU_TMP_DIR/mix-task-commit-$$"
        printf '%s\n' "$_commit_snapshot" | awk -F '=' -v request="$_commit_request" '
            $1 != "committedRequestId" { print }
            END { print "committedRequestId=" request }' > "$_commit_tmp" || return 1
        # A live outer worker may still publish its success. Its task writer
        # also consults the receipt; do not overwrite a concurrent new record.
        if [ "$(cat "$_commit_task")" = "$_commit_snapshot" ]; then
            mv -f "$_commit_tmp" "$_commit_task" || return 1
        else
            rm -f "$_commit_tmp" 2>/dev/null || true
        fi
    done
    return 0
}

commit_mix_stage_if_needed() {
    # Auto-multiweight may already have gone through font_switch_safe.sh. In that
    # case the real next payload is authoritative; discard this compatibility clone.
    if [ -d "$NEXT_PAYLOAD" ] && [ -s "$NEXT_STATE" ]; then
        _next_font=$(read_value "$NEXT_STATE" font)
        _stage_request=$(read_value "$MIX_STAGE_STATE" requestId)
        _next_request=$(read_value "$NEXT_STATE" requestId)
        if [ "$_next_font" = mix ]; then
            if [ ! -s "$MIX_STAGE_STATE" ] || { [ -n "$_stage_request" ] && [ "$_next_request" = "$_stage_request" ]; }; then
                mark_mix_request_committed || return 1
                rm -rf "$MIX_STAGE" 2>/dev/null || true
                rm -f "$MIX_STAGE_STATE" 2>/dev/null || true
                return 0
            fi
        fi
    fi

    _narrow_recovered=false
    if [ -d "$NEXT_PAYLOAD" ] && [ ! -s "$NEXT_STATE" ] && [ -s "$MIX_STAGE_STATE" ] && [ ! -d "$MIX_STAGE" ]; then
        _recover_manifest="$NEXT_PAYLOAD/.luoshu-mix-generation.conf"
        _recover_request=$(read_value "$MIX_STAGE_STATE" requestId)
        [ -n "$_recover_request" ] && [ "$(read_value "$_recover_manifest" requestId)" = "$_recover_request" ] || return 1
        for _recover_role in cjk latin digit; do
            [ "$(read_value "$_recover_manifest" "$_recover_role")" = "$(read_value "$MIX_STAGE_STATE" "$_recover_role")" ] || return 1
        done
        [ -n "$(read_value "$_recover_manifest" compositeHash)" ] || return 1
        # Preserve the renamed payload through the same new transaction. A
        # mismatched generation is never reused merely because its name is mix.
        luoshu_clone_payload_entry "$NEXT_PAYLOAD" "$MIX_STAGE" || return 1
        _narrow_recovered=true
    fi
    stage_has_fonts || return 1
    stage_generation_matches || return 1
    if [ "$_narrow_recovered" != true ]; then
        complete_hyperos_stage || return 1
        complete_coloros_stage || return 1
    fi
    write_next_state || return 1
    if ! luoshu_next_transaction_begin "$REALMOD" "$MIX_STAGE" "$STAGED_NEXT_STATE"; then
        rm -f "$STAGED_NEXT_STATE" 2>/dev/null || true
        return 1
    fi
    rm -f "$STAGED_NEXT_STATE" 2>/dev/null || true
    if ! write_next_selection || ! write_legacy_mix_mode || ! luoshu_next_transaction_mix_receipt "$REALMOD" || ! luoshu_next_transaction_commit "$REALMOD"; then
        luoshu_next_transaction_rollback "$REALMOD" >/dev/null 2>&1 || true
        return 1
    fi
    mark_mix_request_committed || return 1
    rm -f "$MIX_STAGE_STATE" 2>/dev/null || true
    printf '[%s] legacy composite staged for next boot: mix\n' \
        "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)" >> "$LOG_FILE" 2>/dev/null || true
    return 0
}

finalize_lock_acquire() {
    _tries=0
    while [ "$_tries" -lt 20 ]; do
        if mkdir "$FINALIZE_LOCK" 2>/dev/null; then
            printf '%s\n' "$$" > "$FINALIZE_LOCK/pid" 2>/dev/null || {
                rmdir "$FINALIZE_LOCK" 2>/dev/null || true
                return 1
            }
            return 0
        fi
        _owner=$(sed -n '1p' "$FINALIZE_LOCK/pid" 2>/dev/null)
        case "$_owner" in
            ''|*[!0-9]*) _owner='' ;;
        esac
        if [ -z "$_owner" ] || ! kill -0 "$_owner" 2>/dev/null; then
            rm -f "$FINALIZE_LOCK/pid" 2>/dev/null || true
            rmdir "$FINALIZE_LOCK" 2>/dev/null || true
            continue
        fi
        sleep 1
        _tries=$((_tries + 1))
    done
    return 1
}

finalize_lock_release() {
    _owner=$(sed -n '1p' "$FINALIZE_LOCK/pid" 2>/dev/null)
    [ -z "$_owner" ] || [ "$_owner" = "$$" ] || return 1
    rm -f "$FINALIZE_LOCK/pid" 2>/dev/null || true
    rmdir "$FINALIZE_LOCK" 2>/dev/null || true
}

write_legacy_mix_mode() {
    _tmp="$REALMOD/config/font_runtime_legacy_v14_4.conf.tmp.$$"
    {
        printf 'enabled=true\ncore=v14.4.0\nfont=mix\npipeline=atomic-next-boot-composite\ntime=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } >"$_tmp" 2>/dev/null && mv -f "$_tmp" "$REALMOD/config/font_runtime_legacy_v14_4.conf" 2>/dev/null || return 1
    chmod 0600 "$REALMOD/config/font_runtime_legacy_v14_4.conf" 2>/dev/null || true
}

finalize_mix_stage() {
    if ! finalize_lock_acquire; then
        printf '{"status":"error","message":"复合字体已生成但提交锁不可用，请稍后重试"}\n'
        return 1
    fi
    _finalize_wait=0
    while ! luoshu_font_lock_acquire "$FINALIZE_FONT_LOCK" "$$"; do
        _finalize_wait=$((_finalize_wait + 1))
        if [ "$_finalize_wait" -ge 20 ]; then
            finalize_lock_release >/dev/null 2>&1 || true
            printf '{"status":"error","message":"已有字体事务正在提交，请稍后重试"}\n'
            return 1
        fi
        sleep 1
    done
    trap 'luoshu_next_transaction_rollback "$REALMOD" >/dev/null 2>&1 || true; luoshu_font_lock_release "$FINALIZE_FONT_LOCK" "$$" >/dev/null 2>&1 || true; finalize_lock_release >/dev/null 2>&1 || true' EXIT
    trap 'exit 129' HUP
    trap 'exit 130' INT
    trap 'exit 143' TERM
    if ! luoshu_next_transaction_recover "$REALMOD" || ! commit_mix_stage_if_needed; then
        printf '{"status":"error","message":"复合字体已生成但下一启动负载提交失败"}\n'
        return 1
    fi
    _live_result=$(MODDIR="$REALMOD" LUOSHU_REAL_MODDIR="$REALMOD" sh "$REALMOD/common/font_live_switch.sh" 2>> "$LOG_FILE")
    _live_applied=false; _activation=pending-reboot
    if printf '%s\n' "$_live_result" | grep -q '"liveApplied":true'; then
        _live_applied=true; _activation=live-mounted
    fi
    printf '[LIVE-SWITCH] %s\n' "$_live_result" >> "$LOG_FILE" 2>/dev/null || true
    luoshu_font_lock_release "$FINALIZE_FONT_LOCK" "$$" >/dev/null 2>&1 || true
    finalize_lock_release >/dev/null 2>&1 || true
    trap - EXIT HUP INT TERM
    printf '{"status":"ok","data":{"font":"mix","rebootRequired":true,"liveApplied":%s,"activation":"%s","pipeline":"atomic-next-boot-composite"}}\n' "$_live_applied" "$_activation"
    return 0
}

setup_runtime() {
    _payload="$1"
    mkdir -p "$RUNTIME/common" "$REALMOD/config" "$REALMOD/cache" "$REALMOD/logs" "$_payload" 2>/dev/null || return 1
    force_link "$REALMOD/config" "$RUNTIME/config" || return 1
    force_link "$REALMOD/cache" "$RUNTIME/cache" || return 1
    force_link "$REALMOD/logs" "$RUNTIME/logs" || return 1
    force_link "$_payload" "$RUNTIME/.luoshu-payload" || return 1
    force_link "$REALMOD/module.prop" "$RUNTIME/module.prop" || return 1

    for _part in system system_ext product vendor odm oem my_product my_engineering my_company my_preload my_region my_stock oplus_product oplus_engineering oplus_version oplus_region mi_ext cust hw_product; do
        mkdir -p "$_payload/$_part" 2>/dev/null || true
        force_link "$_payload/$_part" "$RUNTIME/$_part" || return 1
    done

    force_link "$LEGACY/v14_mix.sh" "$RUNTIME/common/v14_mix.sh" || return 1
    force_link "$LEGACY/v142_weighted_mix.sh" "$RUNTIME/common/v142_weighted_mix.sh" || return 1
    force_link "$LEGACY/v143_auto_multiweight_mix.sh" "$RUNTIME/common/v143_auto_multiweight_mix.sh" || return 1
    force_link "$LEGACY/font_mix_runtime.sh" "$RUNTIME/common/font_mix.sh" || return 1
    force_link "$LEGACY/font_mix_engine.sh" "$RUNTIME/common/font_mix_engine.sh" || return 1
    force_link "$LEGACY/font_instance.py" "$RUNTIME/common/font_instance.py" || return 1
    force_link "$LEGACY/composite_font.py" "$RUNTIME/common/composite_font.py" || return 1
    force_link "$LEGACY/composite_layout.py" "$RUNTIME/common/composite_layout.py" || return 1
    force_link "$REALMOD/common/luoshu_composite.sh" "$RUNTIME/common/luoshu_composite.sh" || return 1
    force_link "$LEGACY/mix_weight_mode.sh" "$RUNTIME/common/mix_weight_mode.sh" || return 1
    force_link "$REALMOD/common/font_role_check.sh" "$RUNTIME/common/font_role_check.sh" || return 1
    force_link "$REALMOD/common/font_role_check.py" "$RUNTIME/common/font_role_check.py" || return 1
    force_link "$LEGACY/util_functions.sh" "$RUNTIME/common/util_functions.sh" || return 1
    force_link "$LEGACY/font_check.sh" "$RUNTIME/common/font_check.sh" || return 1
    force_link "$LEGACY/rom_adapters.sh" "$RUNTIME/common/rom_adapters.sh" || return 1
    # Keep the v14.4 font engine, but use the current detached-task and nested-task
    # handoff helpers. Without them Android can keep the public task at 34% until
    # the complete composite build exits.
    force_link "$REALMOD/common/background_task.sh" "$RUNTIME/common/background_task.sh" || return 1
    force_link "$REALMOD/common/task_scope.sh" "$RUNTIME/common/task_scope.sh" || return 1
    force_link "$REALMOD/common/task_scope.py" "$RUNTIME/common/task_scope.py" || return 1
    force_link "$REALMOD/common/runtime_paths.sh" "$RUNTIME/common/runtime_paths.sh" || return 1
    force_link "$REALMOD/common/mix_task_handoff.sh" "$RUNTIME/common/mix_task_handoff.sh" || return 1
    force_link "$REALMOD/common/python" "$RUNTIME/common/python" || return 1
    force_link "$REALMOD/common/font_manager.sh" "$RUNTIME/common/font_manager.sh" || return 1
    force_link "$REALMOD/common/legacy_v14_4_switch.sh" "$RUNTIME/common/legacy_v14_4_switch.sh" || return 1
    force_link "$REALMOD/common/font_switch_lock.sh" "$RUNTIME/common/font_switch_lock.sh" || return 1
    force_link "$LEGACY" "$RUNTIME/common/legacy_v14_4" || return 1
    force_link "$REALMOD/common/module_status.sh" "$RUNTIME/common/module_status.sh" || true
    force_link "$REALMOD/common/hyperos_stage_complete.sh" "$RUNTIME/common/hyperos_stage_complete.sh" || true

    cat >"$RUNTIME/common/mount_compat.sh" <<'EOF'
#!/system/bin/sh
# Compatibility runtime: partition paths resolve into an isolated staging payload.
set +e
EOF
    chmod 0755 "$RUNTIME/common/mount_compat.sh" 2>/dev/null || true
    return 0
}

mark_mix_mode_if_success() {
    _out="$1"
    printf '%s\n' "$_out" | grep -q '"state":"success"' || return 0
    finalize_mix_stage >/dev/null 2>&1 || return 1
    return 0
}

_cmd="${1:-config}"
if [ "$_cmd" = cancel ]; then
    _cancel_task="${2:-}"
    [ -n "$_cancel_task" ] || { printf '{"status":"error","message":"缺少任务身份"}\n'; exit 2; }
    . "$REALMOD/common/background_task.sh"
    _cancel_current=$(read_value "$REALMOD/config/axes_task.conf" task)
    [ -n "$_cancel_current" ] || _cancel_current=$(read_value "$REALMOD/config/mix_task.conf" task)
    if [ -n "$_cancel_current" ] && [ "$_cancel_current" != "$_cancel_task" ]; then
        printf '{"status":"ok","data":{"task":"%s","cleaned":true,"state":"absent"}}\n' "$(json_escape_router "$_cancel_task")"
        exit 0
    fi
    _cancel_rc=0
    _cancel_conf="$REALMOD/config/axes_task.conf"
    [ -s "$_cancel_conf" ] || _cancel_conf="$REALMOD/config/mix_task.conf"
    _cancel_child=$(read_value "$_cancel_conf" childTask); [ -n "$_cancel_child" ] || _cancel_child="$_cancel_task"
    for _cancel_pid in axes_worker auto_multiweight_worker; do
        _cancel_file="${LUOSHU_TASKS_DIR:-$REALMOD/.luoshu-state/tasks}/$_cancel_pid.pid"
        if [ "$(cat "$_cancel_file.task" 2>/dev/null)" = "$_cancel_task" ]; then
            luoshu_stop_task_pid "$_cancel_file" "$_cancel_task" >/dev/null || _cancel_rc=125
        else
            sh "$(luoshu_scope_runner)" settled "$_cancel_file" >/dev/null 2>&1 || _cancel_rc=125
        fi
    done
    # A dead outer worker cannot vouch for the engine/monitor it registered.
    # Inspect/cancel those exact task slots too, including interrupted handoff.
    for _cancel_slot in "mix_worker.pid|$_cancel_child" "mix-monitor-$_cancel_child.pid|$_cancel_child.monitor"; do
        _cancel_file="${LUOSHU_TASKS_DIR:-$REALMOD/.luoshu-state/tasks}/${_cancel_slot%%|*}"
        _cancel_expected="${_cancel_slot#*|}"
        if [ "$(cat "$_cancel_file.task" 2>/dev/null)" = "$_cancel_expected" ]; then
            luoshu_stop_task_pid "$_cancel_file" "$_cancel_expected" >/dev/null || _cancel_rc=125
        else
            sh "$(luoshu_scope_runner)" settled "$_cancel_file" >/dev/null 2>&1 || _cancel_rc=125
        fi
    done
    if [ "$_cancel_rc" -eq 0 ]; then
        mix_scope_state_fast "$_cancel_conf"; _cancel_scope=$?
        case "$_cancel_scope" in
            0) ;;
            1) _cancel_state=$(read_value "$_cancel_conf" state)
               _cancel_terminal=$(read_value "$_cancel_conf" terminalState)
               [ "$_cancel_state" != success ] && [ "$_cancel_terminal" != success ] || _cancel_rc=125 ;;
            *) _cancel_rc=125 ;;
        esac
    fi
    if [ "$_cancel_rc" -eq 0 ] && mix_transaction_pending; then
        MODDIR="$REALMOD" sh "$(luoshu_scope_runner)" request-run "mix-live-recover-$$-$(date +%s)" 30 -- \
            sh "$REALMOD/common/font_live_switch.sh" recover >/dev/null 2>&1 || _cancel_rc=125
        ! mix_transaction_pending || _cancel_rc=125
    fi
    if [ "$_cancel_rc" -eq 0 ]; then
        # Nested engine/monitor scopes are cancelled by their owning worker;
        # never remove a completed or queued next-boot payload here.
        _cancel_state=$(read_value "$_cancel_conf" state)
        case "$_cancel_state" in queued|running|cleanup-pending)
            sed -e 's/^state=.*/state=failed/' -e 's/^message=.*/message=字体组合已取消，任务子进程已回收/' \
                -e 's/^percent=.*/percent=100/' -e "s/^finished=.*/finished=$(date +%s)/" \
                -e '/^cleanupConfirmed=/d' -e '/^terminalState=/d' -e '/^terminalMessage=/d' \
                "$_cancel_conf" > "$_cancel_conf.cancel.$$" && \
                printf 'cleanupConfirmed=true\n' >> "$_cancel_conf.cancel.$$" && mv -f "$_cancel_conf.cancel.$$" "$_cancel_conf"
            ;;
        esac
        printf '{"status":"ok","data":{"task":"%s","cleaned":true,"state":"cancelled"}}\n' "$(json_escape_router "$_cancel_task")"
    else
        mix_reconcile_fast
        printf '{"status":"error","data":{"task":"%s","cleaned":false},"message":"任务收尾未完成"}\n' "$(json_escape_router "$_cancel_task")"
    fi
    exit "$_cancel_rc"
fi
if [ "$_cmd" = reconcile ]; then
    # Reconcile task ownership without rebuilding compatibility runtime links.
    mix_reconcile_fast
    printf '{"status":"ok"}\n'
    exit 0
fi
if [ "$_cmd" = finalize ]; then
    finalize_mix_stage
    exit $?
fi
if [ "$_cmd" = config ]; then
    mix_config_json_fast
    exit 0
fi
if [ "$_cmd" = status ]; then
    mix_status_json_fast "${2:-}"
    exit 0
fi
case "$_cmd" in
    start)
        mix_reconcile_fast
        _start_conf="$REALMOD/config/axes_task.conf"
        [ -s "$_start_conf" ] || _start_conf="$REALMOD/config/mix_task.conf"
        _start_state=$(read_value "$_start_conf" state)
        case "$_start_state" in queued|running|cleanup-pending)
            printf '{"status":"error","message":"已有字体组合任务正在运行或等待清理，请刷新重试"}\n'; exit 1 ;;
        esac
        mix_scope_state_fast "$_start_conf"; _start_scope=$?
        case "$_start_scope" in 0|1) ;; *)
            printf '{"status":"error","message":"上一字体组合任务清理尚未确认，请刷新重试"}\n'; exit 1 ;;
        esac
        prepare_mix_stage "$2" "$3" "$4" "${5:-wght=400}" "${6:-wght=400}" "${7:-wght=400}" || {
            printf '{"status":"error","message":"无法创建复合字体下一启动暂存负载"}\n'
            exit 1
        }
        _payload="$MIX_STAGE"
        ;;
    status|config|recover|reconcile)
        if [ -d "$MIX_STAGE" ]; then _payload="$MIX_STAGE"; else _payload="$LIVE_PAYLOAD"; fi
        ;;
    *)
        if [ -d "$MIX_STAGE" ]; then _payload="$MIX_STAGE"; else _payload="$LIVE_PAYLOAD"; fi
        ;;
esac

setup_runtime "$_payload" || {
    printf '{"status":"error","message":"无法准备 v14.4 复合字体兼容运行时"}\n'
    [ "$_cmd" != start ] || { rm -rf "$MIX_STAGE" 2>/dev/null || true; rm -f "$MIX_STAGE_STATE" 2>/dev/null || true; }
    exit 1
}
export LUOSHU_CONTINUOUS_SWITCH=1
export LUOSHU_REAL_MODDIR="$REALMOD"
export LUOSHU_MIX_REQUEST_ID="$(read_value "$MIX_STAGE_STATE" requestId)"
export LUOSHU_MIX_MANIFEST="$MIX_MANIFEST"
export LUOSHU_MIX_EXPECTED_CJK="$(read_value "$MIX_STAGE_STATE" cjk)"
export LUOSHU_MIX_EXPECTED_LATIN="$(read_value "$MIX_STAGE_STATE" latin)"
export LUOSHU_MIX_EXPECTED_DIGIT="$(read_value "$MIX_STAGE_STATE" digit)"
export MODDIR="$RUNTIME"
export MODULE_DIR="$RUNTIME"

case "$_cmd" in
    reconcile)
        printf '{"status":"ok"}\n'
        ;;
    status)
        _out="$(sh "$RUNTIME/common/v14_mix.sh" "$@" 2>&1)"
        _rc=$?
        if ! mark_mix_mode_if_success "$_out"; then
            printf '{"status":"error","message":"复合字体已生成但下一启动负载提交失败"}\n'
            exit 1
        fi
        printf '%s\n' "$_out"
        exit "$_rc"
        ;;
    start)
        _out="$(sh "$RUNTIME/common/v14_mix.sh" "$@" 2>&1)"
        _rc=$?
        printf '%s\n' "$_out"
        if [ "$_rc" -ne 0 ] || ! printf '%s\n' "$_out" | grep -q '"status":"ok"'; then
            rm -rf "$MIX_STAGE" 2>/dev/null || true
            rm -f "$MIX_STAGE_STATE" 2>/dev/null || true
        fi
        exit "$_rc"
        ;;
    recover)
        _out="$(sh "$RUNTIME/common/v14_mix.sh" "$@" 2>&1)"
        _rc=$?
        rm -rf "$MIX_STAGE" 2>/dev/null || true
        rm -f "$MIX_STAGE_STATE" 2>/dev/null || true
        printf '%s\n' "$_out"
        exit "$_rc"
        ;;
    config)
        exec sh "$RUNTIME/common/v14_mix.sh" "$@"
        ;;
    *)
        exec sh "$RUNTIME/common/v14_mix.sh" "$@"
        ;;
esac
