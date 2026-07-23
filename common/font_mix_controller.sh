#!/system/bin/sh
# 洛书 v2.0.0：字体组合控制器。
set +e
MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then
        MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"
    else
        MODDIR="/data/adb/modules/LuoShu"
    fi
fi
WEIGHTED="$MODDIR/common/weighted_mix_task.sh"
AUTO_WEIGHTED="$MODDIR/common/multiweight_mix_task.sh"
MODE_HELPER="$MODDIR/common/mix_weight_mode.sh"
ENGINE="$MODDIR/common/font_mix.sh"
ROLE_CHECK="$MODDIR/common/font_role_check.sh"
TASK_FILE="$MODDIR/config/mix_task.conf"
AXES_TASK_FILE="$MODDIR/config/axes_task.conf"
AXES_WORKER_PID="$MODDIR/config/axes_worker.pid"
AUTO_WORKER_PID="$MODDIR/config/auto_multiweight_worker.pid"
STATUS_SCRIPT="$MODDIR/common/module_status.sh"
USER_FONTS_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/fonts"
MODULE_DIR="$MODDIR"
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/font_check.sh" ] && . "$MODDIR/common/font_check.sh"
[ -f "$MODE_HELPER" ] && . "$MODE_HELPER"
[ -f "$MODDIR/common/background_task.sh" ] && . "$MODDIR/common/background_task.sh"
json_escape(){ printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '; }
read_value(){ sed -n "s/^${1}=//p" "$TASK_FILE" 2>/dev/null | head -n1 | tr -d '\r\n'; }

reconcile_mix_task() {
    _state=$(sed -n 's/^state=//p' "$AXES_TASK_FILE" 2>/dev/null | head -n1 | tr -d '\r\n')
    case "$_state" in queued|running) ;; *) return 0 ;; esac
    _task=$(sed -n 's/^task=//p' "$AXES_TASK_FILE" 2>/dev/null | head -n1 | tr -d '\r\n')
    [ -n "$_task" ] || return 0

    if type luoshu_task_pid_alive >/dev/null 2>&1; then
        luoshu_task_pid_alive "$AXES_WORKER_PID" "$_task" && return 0
        luoshu_task_pid_alive "$AUTO_WORKER_PID" "$_task" && return 0
    fi

    # The task file is written immediately before the detached PID. Keep a short grace
    # window so a status refresh cannot cancel a worker while it is still being spawned.
    _started=$(sed -n 's/^started=//p' "$AXES_TASK_FILE" 2>/dev/null | head -n1 | tr -d '\r\n')
    _now=$(date +%s 2>/dev/null)
    case "$_started:$_now" in *[!0-9:]*|:*) ;; *)
        [ $((_now - _started)) -gt 20 ] 2>/dev/null || return 0
        ;;
    esac

    if [ -f "$AUTO_WEIGHTED" ]; then
        MODDIR="$MODDIR" sh "$AUTO_WEIGHTED" recover >/dev/null 2>&1 || true
    elif [ -f "$WEIGHTED" ]; then
        MODDIR="$MODDIR" sh "$WEIGHTED" recover >/dev/null 2>&1 || true
    fi
    return 2
}

precheck_mix() {
    [ -n "${1:-}" ] && [ -n "${2:-}" ] && [ -n "${3:-}" ] || {
        printf '{"status":"error","message":"请选择中文、英文和数字字体"}\n'
        return 1
    }
    MODDIR="$MODDIR" sh "$ROLE_CHECK" "$1" cjk >/dev/null 2>&1 || {
        printf '{"status":"error","message":"中文基底缺少必要的中文、英文字母或数字字形"}\n'
        return 1
    }
    MODDIR="$MODDIR" sh "$ROLE_CHECK" "$2" latin >/dev/null 2>&1 || {
        printf '{"status":"error","message":"英文字体缺少必要的大小写拉丁字母"}\n'
        return 1
    }
    MODDIR="$MODDIR" sh "$ROLE_CHECK" "$3" digit >/dev/null 2>&1 || {
        printf '{"status":"error","message":"数字字体缺少必要的 0–9 数字字形"}\n'
        return 1
    }
}

if [ -f "$WEIGHTED" ]; then
    case "${1:-config}" in
        start)
            # 多字重引擎会在独立 Root Worker 内完成角色检查；这里必须立即入队返回。
            _cjk_mode=fixed
            _latin_mode=fixed
            _digit_mode=fixed
            if type infer_mix_weight_mode >/dev/null 2>&1; then
                _cjk_mode=$(infer_mix_weight_mode "$2" "${5:-wght=400}")
                _latin_mode=$(infer_mix_weight_mode "$3" "${6:-wght=400}")
                _digit_mode=$(infer_mix_weight_mode "$4" "${7:-wght=400}")
            fi
            if [ -f "$AUTO_WEIGHTED" ]; then
                sh "$AUTO_WEIGHTED" start "$2" "$3" "$4" "${5:-wght=400}" "${6:-wght=400}" "${7:-wght=400}" "$_cjk_mode" "$_latin_mode" "$_digit_mode"
            else
                sh "$WEIGHTED" start "$2" "$3" "$4" "${5:-wght=400}" "${6:-wght=400}" "${7:-wght=400}"
            fi
            ;;
        config)
            if [ -f "$AUTO_WEIGHTED" ]; then sh "$AUTO_WEIGHTED" config
            else sh "$WEIGHTED" config
            fi
            ;;
        status)
            reconcile_mix_task >/dev/null 2>&1 || true
            if [ -f "$AUTO_WEIGHTED" ]; then sh "$AUTO_WEIGHTED" status "$2"
            else sh "$WEIGHTED" status "$2"
            fi
            ;;
        reconcile)
            reconcile_mix_task >/dev/null 2>&1 || true
            printf '{"status":"ok"}\n'
            ;;
        recover)
            if [ -f "$AUTO_WEIGHTED" ]; then sh "$AUTO_WEIGHTED" recover
            else sh "$WEIGHTED" recover
            fi
            ;;
        *) printf '{"status":"error","message":"未知组合桥命令"}\n' ;;
    esac
    exit 0
fi

case "${1:-status}" in
    start)
        precheck_mix "$2" "$3" "$4" || exit 0
        sh "$ENGINE" start "$2" "$3" "$4"
        ;;
    config) sh "$ENGINE" status ;;
    status)
        reconcile_mix_task >/dev/null 2>&1 || true
        _wanted="$2"
        [ -s "$TASK_FILE" ] || { printf '{"status":"error","message":"暂无组合任务"}\n'; exit 0; }
        _task=$(read_value task); _state=$(read_value state); _message=$(read_value message)
        _cjk=$(read_value cjk); _latin=$(read_value latin); _digit=$(read_value digit)
        _started=$(read_value started); _finished=$(read_value finished)
        [ -z "$_wanted" ] || [ "$_wanted" = "$_task" ] || { printf '{"status":"error","message":"任务不存在或已被新任务替换"}\n'; exit 0; }
        if [ "$_state" = success ] && [ -f "$STATUS_SCRIPT" ]; then MODDIR="$MODDIR" sh "$STATUS_SCRIPT" mix >/dev/null 2>&1 || true; fi
        printf '{"status":"ok","data":{"task":"%s","state":"%s","message":"%s","cjk":"%s","latin":"%s","digit":"%s","cjkWeight":400,"latinWeight":400,"digitWeight":400,"cjkAxes":"wght=400","latinAxes":"wght=400","digitAxes":"wght=400","started":%s,"finished":%s}}\n' \
            "$(json_escape "$_task")" "$(json_escape "$_state")" "$(json_escape "$_message")" "$(json_escape "$_cjk")" "$(json_escape "$_latin")" "$(json_escape "$_digit")" "${_started:-0}" "${_finished:-0}"
        ;;
    recover) sh "$ENGINE" recover ;;
    reconcile) reconcile_mix_task >/dev/null 2>&1 || true; printf '{"status":"ok"}\n' ;;
    *) printf '{"status":"error","message":"未知组合命令"}\n' ;;
esac
exit 0
