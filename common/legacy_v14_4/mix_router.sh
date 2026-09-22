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
LEGACY="$REALMOD/common/legacy_v14_4"
RUNTIME="$REALMOD/.legacy-v14-runtime"
LIVE_PAYLOAD="$REALMOD/.luoshu-payload"
MIX_STAGE="$REALMOD/.luoshu-mix-stage"
NEXT_PAYLOAD="$REALMOD/.luoshu-payload-next"
NEXT_STATE="$REALMOD/config/font-payload-next.conf"
MIX_STAGE_STATE="$REALMOD/config/mix-stage-next.conf"
MIX_MANIFEST="$MIX_STAGE/.luoshu-mix-generation.conf"
ACTIVE_CONF="$REALMOD/config/active_font.conf"
LEGACY_MODE="$REALMOD/config/font_runtime_legacy_v14_4.conf"
REBOOT_CONF="$REALMOD/config/text_reboot_required.conf"
LOG_FILE="$REALMOD/logs/fontswitch.log"
FINALIZE_LOCK="$REALMOD/.mix-stage-finalize.lock"
PRECOMMIT_STATE="$MIX_STAGE/.luoshu-precommit-ready.conf"
[ -f "$LEGACY/payload_clone.sh" ] && . "$LEGACY/payload_clone.sh"
[ -f "$REALMOD/common/background_task.sh" ] && . "$REALMOD/common/background_task.sh"

read_value() {
    sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

mix_finalize_state_write() {
    _mfs_state="$1"
    _mfs_message="$2"
    _mfs_task="${3:-}"
    _mfs_percent="${4:-}"
    _mfs_file="$REALMOD/config/mix-finalize-state.conf"
    _mfs_tmp="${_mfs_file}.tmp.$"
    {
        printf 'state=%s\n' "$_mfs_state"
        printf 'task=%s\n' "$_mfs_task"
        printf 'message=%s\n' "$_mfs_message"
        [ -z "$_mfs_percent" ] || printf 'percent=%s\n' "$_mfs_percent"
        printf 'time=%s\n' "$(date +%s 2>/dev/null || echo 0)"
    } >"$_mfs_tmp" 2>/dev/null && mv -f "$_mfs_tmp" "$_mfs_file" 2>/dev/null || true
    chmod 0644 "$_mfs_file" 2>/dev/null || true
}

mix_finalize_worker() {
    _mfw_task="$1"
    mix_finalize_state_write running '正在提交下一启动字体负载' "$_mfw_task" 99
    if finalize_mix_stage >>"$LOG_FILE" 2>&1; then
        mix_finalize_state_write success '复合字体负载已提交，完整重启后生效' "$_mfw_task" 100
    else
        mix_finalize_state_write failed '复合字体已生成，但下一启动负载提交失败' "$_mfw_task" 100
    fi
    if type luoshu_clear_task_pid >/dev/null 2>&1; then
        luoshu_clear_task_pid "$REALMOD/config/mix_finalize_worker.pid" "mix-finalize-$_mfw_task"
    else
        rm -f "$REALMOD/config/mix_finalize_worker.pid" \
              "$REALMOD/config/mix_finalize_worker.pid.task" \
              "$REALMOD/config/mix_finalize_worker.pid.boot" 2>/dev/null || true
    fi
}

ensure_mix_finalize_worker() {
    _emfw_task="$1"
    [ -n "$_emfw_task" ] || return 1
    [ -s "$MIX_STAGE_STATE" ] || return 1
    [ -d "$MIX_STAGE" ] || [ -d "$NEXT_PAYLOAD" ] || return 1
    _emfw_pid="$REALMOD/config/mix_finalize_worker.pid"
    _emfw_identity="mix-finalize-$_emfw_task"
    if type luoshu_task_pid_alive >/dev/null 2>&1 && \
       luoshu_task_pid_alive "$_emfw_pid" "$_emfw_identity"; then
        return 0
    fi
    if type luoshu_start_detached >/dev/null 2>&1; then
        MODDIR="$REALMOD" LUOSHU_REAL_MODDIR="$REALMOD" \
            luoshu_start_detached "$_emfw_pid" "$_emfw_identity" "$LOG_FILE" \
                sh "$0" finalize-worker "$_emfw_task" "$_emfw_identity"
        _emfw_rc=$?
        [ "$_emfw_rc" -eq 0 ] || [ "$_emfw_rc" -eq 3 ]
        return $?
    fi
    ( trap '' HUP; MODDIR="$REALMOD" LUOSHU_REAL_MODDIR="$REALMOD" sh "$0" finalize-worker "$_emfw_task" "$_emfw_identity" ) \
        </dev/null >>"$LOG_FILE" 2>&1 &
    return 0
}

json_escape_router() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
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

# Reconcile only the detached axes controller used by the App. Its PID sidecars
# include task and boot identity; the older base engine's bare PID does not.
# This runs without setting up a runtime, reading fonts or touching payloads.
mix_reconcile_fast() (
    _mrf_file="$REALMOD/config/axes_task.conf"
    [ -s "$_mrf_file" ] || return 0
    _mrf_snapshot=$(cat "$_mrf_file" 2>/dev/null) || return 0
    _mrf_state=$(read_value "$_mrf_file" state)
    case "$_mrf_state" in queued|running) ;; *) return 0 ;; esac
    _mrf_task=$(read_value "$_mrf_file" task)
    [ -n "$_mrf_task" ] || return 0
    [ -f "$REALMOD/common/background_task.sh" ] || return 0
    . "$REALMOD/common/background_task.sh"
    mix_worker_alive_fast() {
        for _mwaf_file in "$REALMOD/config/axes_worker.pid" \
            "$REALMOD/config/auto_multiweight_worker.pid"; do
            luoshu_task_pid_alive "$_mwaf_file" "$_mrf_task" || continue
            _mwaf_pid=$(luoshu_pid_value "$_mwaf_file")
            # The shared helper checks recycled PID/task/boot identities. Require
            # an exact task argument as well, rather than a task-prefix match.
            [ -r "/proc/$_mwaf_pid/cmdline" ] || return 0
            tr '\000' '\n' < "/proc/$_mwaf_pid/cmdline" 2>/dev/null | \
                grep -Fxq -- "$_mrf_task" && return 0
        done
        return 1
    }
    mix_worker_alive_fast && return 0
    _mrf_started=$(read_value "$_mrf_file" started)
    _mrf_now=$(date +%s 2>/dev/null) || return 0
    case "$_mrf_now" in ''|*[!0-9]*) return 0 ;; esac
    case "$_mrf_started" in
        ''|*[!0-9]*) _mrf_started=$(stat -c '%Y' "$_mrf_file" 2>/dev/null) ;;
    esac
    case "$_mrf_started" in ''|*[!0-9]*) return 0 ;; esac
    # The queued record precedes the detached worker and its sidecar writes.
    # Preserve that startup window, including a worker already marked running.
    _mrf_age=$((_mrf_now - _mrf_started))
    [ "$_mrf_age" -ge 20 ] 2>/dev/null || return 0
    _mrf_tmp="${_mrf_file}.reconcile.$$"
    printf '%s\n' "$_mrf_snapshot" | awk -F '=' -v now="$_mrf_now" '
        $1 != "state" && $1 != "message" && $1 != "percent" && $1 != "finished" {print}
        END {print "state=failed"; print "message=字体组合后台进程已退出，任务已自动释放，请重新应用";
             print "percent=100"; print "finished=" now}' > "$_mrf_tmp" || return 0
    # A new request or worker may have arrived while the lightweight checks ran.
    # Do not publish a stale failure over its task record or erase its sidecars.
    if [ "$(cat "$_mrf_file" 2>/dev/null)" != "$_mrf_snapshot" ] || mix_worker_alive_fast; then
        rm -f "$_mrf_tmp" 2>/dev/null || true
        return 0
    fi
    mv -f "$_mrf_tmp" "$_mrf_file" 2>/dev/null || { rm -f "$_mrf_tmp"; return 0; }
    for _mrf_pid_file in "$REALMOD/config/axes_worker.pid" \
        "$REALMOD/config/auto_multiweight_worker.pid"; do
        luoshu_clear_task_pid "$_mrf_pid_file" "$_mrf_task"
    done
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
    _message=$(read_value "$_task_file" message)
    _percent=$(read_value "$_task_file" percent)
    case "$_percent" in ''|*[!0-9]*) _percent=0 ;; esac

    if [ "$_state" = success ]; then
        _next_font=$(read_value "$NEXT_STATE" font)
        if [ -d "$NEXT_PAYLOAD" ] && [ "$_next_font" = mix ]; then
            _percent=100
        else
            _finalize_state=$(read_value "$REALMOD/config/mix-finalize-state.conf" state)
            _finalize_message=$(read_value "$REALMOD/config/mix-finalize-state.conf" message)
            if [ "$_finalize_state" = failed ]; then
                _state=failed
                _message="${_finalize_message:-复合字体负载提交失败}"
                _percent=100
            else
                # The generator is done but the durable next-boot payload is not.
                # Never leave a successful axes task parked at 99% forever if the
                # original finalize monitor was reclaimed with its su session.
                ensure_mix_finalize_worker "$_task" >/dev/null 2>&1 || true
                _state=running
                _message="${_finalize_message:-字体已生成，正在提交下一启动负载}"
                _percent=99
            fi
        fi
    fi

    if [ "$_state" = running ]; then
        _finalize_task=$(read_value "$REALMOD/config/mix-finalize-state.conf" task)
        _finalize_state=$(read_value "$REALMOD/config/mix-finalize-state.conf" state)
        _finalize_message=$(read_value "$REALMOD/config/mix-finalize-state.conf" message)
        _finalize_percent=$(read_value "$REALMOD/config/mix-finalize-state.conf" percent)
        case "$_finalize_percent" in ''|*[!0-9]*) _finalize_percent=0 ;; esac
        if { [ -z "$_finalize_task" ] || [ "$_finalize_task" = "$_task" ]; } && \
           [ "$_finalize_state" != failed ] && [ "$_finalize_percent" -gt "$_percent" ] 2>/dev/null; then
            _percent="$_finalize_percent"
            [ -z "$_finalize_message" ] || _message="$_finalize_message"
        fi
    fi

    _cjk=$(read_value "$_task_file" cjk)
    _latin=$(read_value "$_task_file" latin)
    _digit=$(read_value "$_task_file" digit)
    _cjk_axes=$(read_value "$_task_file" cjkAxes); [ -n "$_cjk_axes" ] || _cjk_axes=wght=400
    _latin_axes=$(read_value "$_task_file" latinAxes); [ -n "$_latin_axes" ] || _latin_axes=wght=400
    _digit_axes=$(read_value "$_task_file" digitAxes); [ -n "$_digit_axes" ] || _digit_axes=wght=400
    printf '{"status":"ok","data":{"task":"%s","state":"%s","message":"%s","cjk":"%s","latin":"%s","digit":"%s","cjkWeight":400,"latinWeight":400,"digitWeight":400,"cjkAxes":"%s","latinAxes":"%s","digitAxes":"%s","timeout":720,"progress":{"message":"%s","percent":%s}}}\n' \
        "$(json_escape_router "$_task")" "$(json_escape_router "$_state")" "$(json_escape_router "$_message")" \
        "$(json_escape_router "$_cjk")" "$(json_escape_router "$_latin")" "$(json_escape_router "$_digit")" \
        "$(json_escape_router "$_cjk_axes")" "$(json_escape_router "$_latin_axes")" "$(json_escape_router "$_digit_axes")" \
        "$(json_escape_router "$_message")" "$_percent"
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
    for _part in $(luoshu_payload_partitions "$REALMOD"); do
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
    _request="mix-request-$(date +%s 2>/dev/null || echo 0)-$"
    _coverage_remediate=false
    _coverage_plan=''
    if [ "${LUOSHU_COVERAGE_REMEDIATE:-0}" = 1 ]; then
        _coverage_remediate=true
        _coverage_plan="${LUOSHU_COVERAGE_PLAN:-}"
        case "$_coverage_plan" in
            "$REALMOD"/config/*) [ -s "$_coverage_plan" ] || return 1 ;;
            *) return 1 ;;
        esac
    fi
    {
        printf 'requestId=%s\n' "$_request"
        printf 'coverageRemediate=%s\n' "$_coverage_remediate"
        printf 'coveragePlan=%s\n' "$_coverage_plan"
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
    _tmp="${NEXT_STATE}.tmp.$$"
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
    mv -f "$_tmp" "$NEXT_STATE" 2>/dev/null || return 1
    chmod 0644 "$NEXT_STATE" 2>/dev/null || true

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

    # At this point both .luoshu-payload-next and font-payload-next.conf are
    # durable. The explicit coverage rebuild has finished; leaving its intent
    # behind makes post-fs-data treat the freshly generated payload as an old
    # preserved payload and skip boot verification forever.
    if [ "$(read_value "$MIX_STAGE_STATE" coverageRemediate)" = true ]; then
        rm -f "$REALMOD/config/font-payload-rebuild-pending.conf" \
              "$REALMOD/config/font-payload-reapply-notified.conf" \
              "$REALMOD/config/device-font-load-verification.conf" \
              "$REALMOD/config/device-font-load-verification.json" 2>/dev/null || true
    fi
    return 0
}

precommit_ready() {
    [ -s "$PRECOMMIT_STATE" ] || return 1
    _pcr_request=$(read_value "$MIX_STAGE_STATE" requestId)
    [ -n "$_pcr_request" ] || return 1
    [ "$(read_value "$PRECOMMIT_STATE" requestId)" = "$_pcr_request" ] || return 1
    [ "$(read_value "$PRECOMMIT_STATE" state)" = ready ] || return 1
    return 0
}

prepare_mix_stage_for_commit() {
    precommit_ready && return 0
    stage_has_fonts || return 1
    stage_generation_matches || return 1

    mix_finalize_state_write running "正在完成 ROM 字体槽位对齐" "$(read_value "$REALMOD/config/axes_task.conf" task)"
    complete_hyperos_stage || return 1
    complete_coloros_stage || return 1

    if [ "$(read_value "$MIX_STAGE_STATE" coverageRemediate)" = true ]; then
        mix_finalize_state_write running "正在完成字体补齐批处理" "$(read_value "$REALMOD/config/axes_task.conf" task)"
        _coverage_helper="$REALMOD/common/coverage_payload_remediate.sh"
        _coverage_plan=$(read_value "$MIX_STAGE_STATE" coveragePlan)
        [ -f "$_coverage_helper" ] && [ -s "$_coverage_plan" ] || return 1
        LUOSHU_REAL_MODDIR="$REALMOD" \
        LUOSHU_PUBLIC_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}" \
        LUOSHU_COVERAGE_PLAN="$_coverage_plan" \
            sh "$_coverage_helper" "$MIX_STAGE" mix mix >> "$LOG_FILE" 2>&1 || return 1
    fi

    _pm_request=$(read_value "$MIX_STAGE_STATE" requestId)
    _pm_tmp="${PRECOMMIT_STATE}.tmp.$"
    {
        printf "state=ready\n"
        printf "requestId=%s\n" "$_pm_request"
        printf "time=%s\n" "$(date +%s 2>/dev/null || echo 0)"
    } >"$_pm_tmp" 2>/dev/null || return 1
    mv -f "$_pm_tmp" "$PRECOMMIT_STATE" 2>/dev/null || return 1
    chmod 0644 "$PRECOMMIT_STATE" 2>/dev/null || true
    mix_finalize_state_write ready '预提交处理完成，正在原子提交下一启动负载' "$(read_value "$REALMOD/config/axes_task.conf" task)" 98
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
                rm -rf "$MIX_STAGE" 2>/dev/null || true
                rm -f "$MIX_STAGE_STATE" 2>/dev/null || true
                return 0
            fi
        fi
    fi

    # Recover a process killed after the stage directory was atomically renamed
    # but before its small state file was committed. MIX_STAGE_STATE is retained
    # until both pieces are durable, so the next status poll can finish the commit.
    if [ -d "$NEXT_PAYLOAD" ] && [ ! -s "$NEXT_STATE" ] && [ -s "$MIX_STAGE_STATE" ]; then
        write_next_state || return 1
        rm -f "$MIX_STAGE_STATE" 2>/dev/null || true
        return 0
    fi

    prepare_mix_stage_for_commit || return 1
    rm -rf "$NEXT_PAYLOAD" 2>/dev/null || true
    mv "$MIX_STAGE" "$NEXT_PAYLOAD" 2>/dev/null || return 1
    if ! write_next_state; then
        mv "$NEXT_PAYLOAD" "$MIX_STAGE" 2>/dev/null || true
        return 1
    fi
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
    } >"$_tmp" 2>/dev/null && mv -f "$_tmp" "$REALMOD/config/font_runtime_legacy_v14_4.conf" 2>/dev/null || true
    chmod 0600 "$REALMOD/config/font_runtime_legacy_v14_4.conf" 2>/dev/null || true
}

finalize_mix_stage() {
    if ! finalize_lock_acquire; then
        printf '{"status":"error","message":"复合字体已生成但提交锁不可用，请稍后重试"}\n'
        return 1
    fi
    commit_mix_stage_if_needed
    _commit_rc=$?
    finalize_lock_release >/dev/null 2>&1 || true
    if [ "$_commit_rc" -ne 0 ]; then
        printf '{"status":"error","message":"复合字体已生成但下一启动负载提交失败"}\n'
        return 1
    fi
    write_legacy_mix_mode
    printf '{"status":"ok","data":{"font":"mix","rebootRequired":true,"pipeline":"atomic-next-boot-composite"}}\n'
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

    for _part in $(luoshu_payload_partitions "$REALMOD"); do
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
    force_link "$REALMOD/common/mix_task_handoff.sh" "$RUNTIME/common/mix_task_handoff.sh" || return 1
    force_link "$REALMOD/common/font_provenance.sh" "$RUNTIME/common/font_provenance.sh" || return 1
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

coverage_intent_abort_if_owned() {
    [ "$(read_value "$MIX_STAGE_STATE" coverageRemediate)" = true ] || return 0
    rm -f "$REALMOD/config/font-payload-rebuild-pending.conf" \
          "$REALMOD/config/font-payload-reapply-notified.conf" \
          "$REALMOD/config/font-coverage-remediation-paths.txt" 2>/dev/null || true
}

mark_mix_mode_if_success() {
    _out="$1"
    if printf '%s\n' "$_out" | grep -q '"state":"failed"'; then
        coverage_intent_abort_if_owned
        return 0
    fi
    printf '%s\n' "$_out" | grep -q '"state":"success"' || return 0
    finalize_mix_stage >/dev/null 2>&1 || return 1
    rm -f "$REALMOD/config/font-coverage-remediation-paths.txt" 2>/dev/null || true
    return 0
}

_cmd="${1:-config}"
if [ "$_cmd" = finalize-worker ]; then
    mix_finalize_worker "${2:-}"
    exit 0
fi
if [ "$_cmd" = prepare-finalize ]; then
    if prepare_mix_stage_for_commit; then
        printf '{"status":"ok","data":{"stage":"prepared"}}\n'
        exit 0
    fi
    printf '{"status":"error","message":"复合字体预提交处理失败"}\n'
    exit 1
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
