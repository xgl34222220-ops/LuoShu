#!/system/bin/sh
# Composite (mix) switching on the Universal Font Engine.
# Same App protocol as the legacy mix engine (start/status/config/recover and
# config/axes_task.conf), but no legacy runtime: the worker writes the role
# assignment and runs the Universal pipeline for the reserved family "mix".
set +e

MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then
        MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"
    else
        MODDIR=/data/adb/modules/LuoShu
    fi
fi
MODULE_DIR="$MODDIR"
CONFIG_DIR="$MODDIR/config"
USER_FONTS_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/fonts"
TASK_FILE="$CONFIG_DIR/axes_task.conf"
MIX_CONF="$CONFIG_DIR/font_mix.conf"
AXES_CONF="$CONFIG_DIR/axes_mix.conf"
ACTIVE_CONF="$CONFIG_DIR/active_font.conf"
REBOOT_CONF="$CONFIG_DIR/text_reboot_required.conf"
COMPOSITE_CONF="$CONFIG_DIR/universal-composite.conf"
WORKER_PID="$CONFIG_DIR/axes_worker.pid"
PROGRESS_FILE="$CONFIG_DIR/universal-composite-progress.conf"
LOCK_FILE="$MODDIR/.font_switch.lock"
LOG_FILE="$MODDIR/logs/fontswitch.log"
ROLE_CHECK="$MODDIR/common/font_role_check.sh"
CUTOVER="$MODDIR/common/universal_font_cutover.sh"

[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/background_task.sh" ] && . "$MODDIR/common/background_task.sh"
[ -f "$MODDIR/common/font_switch_lock.sh" ] && . "$MODDIR/common/font_switch_lock.sh"
[ -f "$MODDIR/common/mix_weight_mode.sh" ] && . "$MODDIR/common/mix_weight_mode.sh"

json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
}

read_value() {
    sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

clean_spec() {
    printf '%s' "$1" | tr -d '\r\n'
}

safe_weight() {
    _sw=$(printf '%s' "$1" | tr ',;' '\n\n' | sed -n 's/^wght=//p' | head -n1)
    _sw=${_sw%%.*}
    case "$_sw" in ''|*[!0-9]*) _sw=400 ;; esac
    printf '%s' "$_sw"
}

ucm_resolve_mode() {
    case "$1" in
        auto|fixed) printf '%s\n' "$1" ;;
        *)
            if type infer_mix_weight_mode >/dev/null 2>&1; then
                infer_mix_weight_mode "$2" "$3"
            else
                printf 'fixed\n'
            fi
            ;;
    esac
}

write_task() {
    # task state message cjk latin digit cjkAxes latinAxes digitAxes
    # cjkMode latinMode digitMode started finished percent
    _wt_tmp="$TASK_FILE.tmp.$$"
    {
        printf 'task=%s\nstate=%s\nmessage=%s\n' "$1" "$2" "$3"
        printf 'cjk=%s\nlatin=%s\ndigit=%s\n' "$4" "$5" "$6"
        printf 'cjkAxes=%s\nlatinAxes=%s\ndigitAxes=%s\n' "$7" "$8" "$9"
        shift 9
        printf 'cjkMode=%s\nlatinMode=%s\ndigitMode=%s\n' "$1" "$2" "$3"
        printf 'started=%s\nfinished=%s\npercent=%s\nengine=universal\n' "$4" "$5" "$6"
    } > "$_wt_tmp" 2>/dev/null && mv -f "$_wt_tmp" "$TASK_FILE" 2>/dev/null
    chmod 0644 "$TASK_FILE" 2>/dev/null || true
}

update_task() {
    # task state message percent finished
    [ "$(read_value "$TASK_FILE" task)" = "$1" ] || return 1
    write_task "$1" "$2" "$3" \
        "$(read_value "$TASK_FILE" cjk)" "$(read_value "$TASK_FILE" latin)" "$(read_value "$TASK_FILE" digit)" \
        "$(read_value "$TASK_FILE" cjkAxes)" "$(read_value "$TASK_FILE" latinAxes)" "$(read_value "$TASK_FILE" digitAxes)" \
        "$(read_value "$TASK_FILE" cjkMode)" "$(read_value "$TASK_FILE" latinMode)" "$(read_value "$TASK_FILE" digitMode)" \
        "$(read_value "$TASK_FILE" started)" "$5" "$4"
}

ucm_precheck_mix() {
    [ -n "$1" ] && [ -n "$2" ] && [ -n "$3" ] || return 1
    [ -f "$ROLE_CHECK" ] || return 0
    MODDIR="$MODDIR" sh "$ROLE_CHECK" "$1" cjk >/dev/null 2>&1 || return 2
    MODDIR="$MODDIR" sh "$ROLE_CHECK" "$2" latin >/dev/null 2>&1 || return 3
    MODDIR="$MODDIR" sh "$ROLE_CHECK" "$3" digit >/dev/null 2>&1 || return 4
}

ucm_save_mix_config() {
    # cjk latin digit cjkAxes latinAxes digitAxes cjkMode latinMode digitMode
    _sm_tmp="$MIX_CONF.tmp.$$"
    {
        printf 'cjk=%s\nlatin=%s\ndigit=%s\n' "$1" "$2" "$3"
        printf 'cjkWeight=%s\nlatinWeight=%s\ndigitWeight=%s\n' "$(safe_weight "$4")" "$(safe_weight "$5")" "$(safe_weight "$6")"
        printf 'cjkAxes=%s\nlatinAxes=%s\ndigitAxes=%s\n' "$4" "$5" "$6"
        printf 'cjkMode=%s\nlatinMode=%s\ndigitMode=%s\n' "$7" "$8" "$9"
        printf 'engine=universal\ncomposite=true\ntime=%s\n' "$(date +%s)"
    } > "$_sm_tmp" 2>/dev/null && mv -f "$_sm_tmp" "$MIX_CONF" 2>/dev/null || return 1
    cp -f "$MIX_CONF" "$AXES_CONF" 2>/dev/null || true
    chmod 0644 "$MIX_CONF" "$AXES_CONF" 2>/dev/null || true
}

start_mix() {
    _cjk="$1"; _latin="$2"; _digit="$3"
    _cjk_axes=$(clean_spec "$4"); _latin_axes=$(clean_spec "$5"); _digit_axes=$(clean_spec "$6")
    [ -n "$_cjk_axes" ] || _cjk_axes='wght=400'
    [ -n "$_latin_axes" ] || _latin_axes='wght=400'
    [ -n "$_digit_axes" ] || _digit_axes='wght=400'
    _cjk_mode=$(ucm_resolve_mode "$7" "$_cjk" "$_cjk_axes")
    _latin_mode=$(ucm_resolve_mode "$8" "$_latin" "$_latin_axes")
    _digit_mode=$(ucm_resolve_mode "$9" "$_digit" "$_digit_axes")

    ucm_precheck_mix "$_cjk" "$_latin" "$_digit"
    case "$?" in
        1) printf '{"status":"error","message":"请选择中文、英文和数字字体"}\n'; return ;;
        2) printf '{"status":"error","message":"中文基底缺少必要字形"}\n'; return ;;
        3) printf '{"status":"error","message":"英文字体缺少必要字形"}\n'; return ;;
        4) printf '{"status":"error","message":"数字字体缺少必要字形"}\n'; return ;;
    esac
    if type luoshu_task_pid_alive >/dev/null 2>&1 && luoshu_task_pid_alive "$WORKER_PID" "$(read_value "$TASK_FILE" task)"; then
        printf '{"status":"error","message":"已有字体组合任务正在运行"}\n'
        return
    fi
    [ ! -e "$LOCK_FILE" ] || {
        printf '{"status":"error","message":"字体正在切换中"}\n'
        return
    }
    mkdir -p "$CONFIG_DIR" "$MODDIR/logs" 2>/dev/null || {
        printf '{"status":"error","message":"无法创建任务目录"}\n'
        return
    }
    _task="universal-mix-$(date +%s)-$$"
    write_task "$_task" queued '组合任务已进入队列' "$_cjk" "$_latin" "$_digit" \
        "$_cjk_axes" "$_latin_axes" "$_digit_axes" "$_cjk_mode" "$_latin_mode" "$_digit_mode" \
        "$(date +%s)" 0 1
    if type luoshu_start_detached >/dev/null 2>&1; then
        luoshu_start_detached "$WORKER_PID" "$_task" "$LOG_FILE" sh "$0" worker "$_task" || {
            update_task "$_task" failed '无法启动独立后台任务' 100 "$(date +%s)"
            printf '{"status":"error","message":"无法启动独立后台任务"}\n'
            return
        }
    else
        ( trap '' HUP; MODDIR="$MODDIR" sh "$0" worker "$_task" ) </dev/null >>"$LOG_FILE" 2>&1 &
        printf '%s\n' "$!" > "$WORKER_PID" 2>/dev/null || true
    fi
    printf '{"status":"ok","data":{"task":"%s","cjkMode":"%s","latinMode":"%s","digitMode":"%s"}}\n' \
        "$(json_escape "$_task")" "$_cjk_mode" "$_latin_mode" "$_digit_mode"
}

worker() {
    trap '' HUP
    _wanted="$1"
    [ "$(read_value "$TASK_FILE" task)" = "$_wanted" ] || exit 0
    if type luoshu_font_lock_acquire >/dev/null 2>&1; then
        luoshu_font_lock_acquire "$LOCK_FILE" "$$" || {
            update_task "$_wanted" failed '字体正在切换中' 100 "$(date +%s)"
            exit 1
        }
        trap 'luoshu_font_lock_release "$LOCK_FILE" "$$" >/dev/null 2>&1 || true' EXIT
    fi
    _cjk=$(read_value "$TASK_FILE" cjk); _latin=$(read_value "$TASK_FILE" latin); _digit=$(read_value "$TASK_FILE" digit)
    _cjk_axes=$(read_value "$TASK_FILE" cjkAxes); _latin_axes=$(read_value "$TASK_FILE" latinAxes); _digit_axes=$(read_value "$TASK_FILE" digitAxes)
    _cjk_mode=$(read_value "$TASK_FILE" cjkMode); _latin_mode=$(read_value "$TASK_FILE" latinMode); _digit_mode=$(read_value "$TASK_FILE" digitMode)

    _cc_tmp="$COMPOSITE_CONF.tmp.$$"
    {
        printf 'cjk=%s\nlatin=%s\ndigit=%s\n' "$_cjk" "$_latin" "$_digit"
        printf 'cjkAxes=%s\nlatinAxes=%s\ndigitAxes=%s\n' "$_cjk_axes" "$_latin_axes" "$_digit_axes"
        printf 'cjkMode=%s\nlatinMode=%s\ndigitMode=%s\n' "$_cjk_mode" "$_latin_mode" "$_digit_mode"
    } > "$_cc_tmp" 2>/dev/null && mv -f "$_cc_tmp" "$COMPOSITE_CONF" 2>/dev/null || {
        update_task "$_wanted" failed '组合设置写入失败' 100 "$(date +%s)"
        exit 1
    }
    update_task "$_wanted" running '通用引擎正在生成组合字体' 5 0

    rm -f "$PROGRESS_FILE" 2>/dev/null || true
    _result=$(MODDIR="$MODDIR" LUOSHU_SWITCH_PROGRESS_FILE="$PROGRESS_FILE" \
        LUOSHU_UNIVERSAL_BUDGET_SECONDS="${LUOSHU_COMPOSITE_BUDGET_SECONDS:-600}" \
        sh "$CUTOVER" switch-composite 2>&1)
    _rc=$?
    printf '%s\n' "$_result" >> "$LOG_FILE" 2>/dev/null || true
    if [ "$_rc" -ne 0 ] || ! printf '%s\n' "$_result" | grep -q '"status":"ok"'; then
        _message=$(printf '%s\n' "$_result" | sed -n 's/.*"message":"\([^"]*\)".*/\1/p' | tail -n1)
        update_task "$_wanted" failed "${_message:-通用引擎无法生成该组合，当前字体未改变}" 100 "$(date +%s)"
        exit 1
    fi
    ucm_save_mix_config "$_cjk" "$_latin" "$_digit" "$_cjk_axes" "$_latin_axes" "$_digit_axes" \
        "$_cjk_mode" "$_latin_mode" "$_digit_mode" || {
        update_task "$_wanted" failed '组合配置保存失败' 100 "$(date +%s)"
        exit 1
    }
    update_task "$_wanted" success '组合字体已准备，完整重启后生效' 100 "$(date +%s)"
    if type luoshu_clear_task_pid >/dev/null 2>&1; then luoshu_clear_task_pid "$WORKER_PID" "$_wanted"; fi
}

status_json() {
    _wanted="$1"
    [ -s "$TASK_FILE" ] || { printf '{"status":"error","message":"暂无字体组合任务"}\n'; return; }
    _task=$(read_value "$TASK_FILE" task)
    [ -z "$_wanted" ] || [ "$_wanted" = "$_task" ] || {
        printf '{"status":"error","message":"任务不存在或已被新任务替换"}\n'; return
    }
    _state=$(read_value "$TASK_FILE" state)
    _message=$(read_value "$TASK_FILE" message)
    _percent=$(read_value "$TASK_FILE" percent)
    if [ "$_state" = running ] && [ -s "$PROGRESS_FILE" ]; then
        _live=$(read_value "$PROGRESS_FILE" percent)
        _live_message=$(read_value "$PROGRESS_FILE" message)
        case "$_live" in ''|*[!0-9]*) ;; *) _percent=$((5 + _live * 90 / 100)) ;; esac
        [ -z "$_live_message" ] || _message="$_live_message"
    fi
    _cjk_axes=$(read_value "$TASK_FILE" cjkAxes); _latin_axes=$(read_value "$TASK_FILE" latinAxes); _digit_axes=$(read_value "$TASK_FILE" digitAxes)
    printf '{"status":"ok","data":{"task":"%s","state":"%s","message":"%s","cjk":"%s","latin":"%s","digit":"%s","cjkWeight":%s,"latinWeight":%s,"digitWeight":%s,"cjkAxes":"%s","latinAxes":"%s","digitAxes":"%s","started":%s,"finished":%s,"progress":{"message":"%s","percent":%s}}}\n' \
        "$(json_escape "$_task")" "$(json_escape "$_state")" "$(json_escape "$_message")" \
        "$(json_escape "$(read_value "$TASK_FILE" cjk)")" "$(json_escape "$(read_value "$TASK_FILE" latin)")" "$(json_escape "$(read_value "$TASK_FILE" digit)")" \
        "$(safe_weight "$_cjk_axes")" "$(safe_weight "$_latin_axes")" "$(safe_weight "$_digit_axes")" \
        "$(json_escape "$_cjk_axes")" "$(json_escape "$_latin_axes")" "$(json_escape "$_digit_axes")" \
        "$(read_value "$TASK_FILE" started | sed 's/^$/0/')" "$(read_value "$TASK_FILE" finished | sed 's/^$/0/')" \
        "$(json_escape "$_message")" "${_percent:-0}"
}

config_json() {
    _source="$AXES_CONF"
    [ -s "$_source" ] || _source="$MIX_CONF"
    _cjk=$(read_value "$_source" cjk); _latin=$(read_value "$_source" latin); _digit=$(read_value "$_source" digit)
    _cjk_axes=$(read_value "$_source" cjkAxes); _latin_axes=$(read_value "$_source" latinAxes); _digit_axes=$(read_value "$_source" digitAxes)
    [ -n "$_cjk_axes" ] || _cjk_axes="wght=$(read_value "$_source" cjkWeight)"
    [ -n "$_latin_axes" ] || _latin_axes="wght=$(read_value "$_source" latinWeight)"
    [ -n "$_digit_axes" ] || _digit_axes="wght=$(read_value "$_source" digitWeight)"
    _cjk_mode=$(ucm_resolve_mode "$(read_value "$_source" cjkMode)" "$_cjk" "$_cjk_axes")
    _latin_mode=$(ucm_resolve_mode "$(read_value "$_source" latinMode)" "$_latin" "$_latin_axes")
    _digit_mode=$(ucm_resolve_mode "$(read_value "$_source" digitMode)" "$_digit" "$_digit_axes")
    _enabled=false
    [ "$(head -n1 "$ACTIVE_CONF" 2>/dev/null | tr -d '\r\n')" = mix ] && _enabled=true
    printf '{"status":"ok","data":{"enabled":%s,"cjk":"%s","latin":"%s","digit":"%s","cjkWeight":%s,"latinWeight":%s,"digitWeight":%s,"cjkAxes":"%s","latinAxes":"%s","digitAxes":"%s","cjkMode":"%s","latinMode":"%s","digitMode":"%s"}}\n' \
        "$_enabled" "$(json_escape "$_cjk")" "$(json_escape "$_latin")" "$(json_escape "$_digit")" \
        "$(safe_weight "$_cjk_axes")" "$(safe_weight "$_latin_axes")" "$(safe_weight "$_digit_axes")" \
        "$(json_escape "$_cjk_axes")" "$(json_escape "$_latin_axes")" "$(json_escape "$_digit_axes")" \
        "$_cjk_mode" "$_latin_mode" "$_digit_mode"
}

recover_task() {
    _task=$(read_value "$TASK_FILE" task)
    if [ -s "$WORKER_PID" ]; then
        _pid=$(sed -n '1p' "$WORKER_PID" 2>/dev/null)
        [ -z "$_pid" ] || ! kill -0 "$_pid" 2>/dev/null || kill "$_pid" 2>/dev/null || true
    fi
    if type luoshu_clear_task_pid >/dev/null 2>&1; then luoshu_clear_task_pid "$WORKER_PID" ''; fi
    case "$(read_value "$TASK_FILE" state)" in
        queued|running) update_task "$_task" failed '组合任务已中断，当前字体未改变' 100 "$(date +%s)" ;;
    esac
    printf '{"status":"ok"}\n'
}

case "${1:-config}" in
    start) start_mix "$2" "$3" "$4" "${5:-wght=400}" "${6:-wght=400}" "${7:-wght=400}" "${8:-infer}" "${9:-infer}" "${10:-infer}" ;;
    worker) worker "$2" ;;
    status) status_json "${2:-}" ;;
    config) config_json ;;
    recover) recover_task ;;
    reconcile) printf '{"status":"ok"}\n' ;;
    *) printf '{"status":"error","message":"未知组合命令"}\n' ;;
esac
exit 0
