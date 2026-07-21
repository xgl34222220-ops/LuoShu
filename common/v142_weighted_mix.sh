#!/system/bin/sh
# 洛书 v14.2 RC2：异步真实字重与多轴字体组合桥。
# 任务状态持久化在模块目录，App 或 WebUI 退出后可重新接管。
set +e

MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then
        MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"
    else
        MODDIR="/data/adb/modules/LuoShu"
    fi
fi

CONFIG_DIR="$MODDIR/config"
CACHE_ROOT="$MODDIR/cache/axes-mix"
USER_FONTS_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/fonts"
BASE_ENGINE="$MODDIR/common/font_mix.sh"
INSTANCE_PY="$MODDIR/common/font_instance.py"
PYROOT="$MODDIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"
BASE_TASK_FILE="$CONFIG_DIR/mix_task.conf"
TASK_FILE="$CONFIG_DIR/axes_task.conf"
AXES_CONF="$CONFIG_DIR/axes_mix.conf"
MIX_CONF="$CONFIG_DIR/font_mix.conf"
ACTIVE_CONF="$CONFIG_DIR/active_font.conf"
PROGRESS_FILE="$CONFIG_DIR/composite_progress.json"
TEXT_REBOOT_REQUIRED="$CONFIG_DIR/text_reboot_required.conf"
LOCK_FILE="$MODDIR/.font_switch.lock"
WORKER_PID="$CONFIG_DIR/axes_worker.pid"
LOG_FILE="$MODDIR/logs/fontswitch.log"
ROLE_CHECK="$MODDIR/common/font_role_check.sh"

MODULE_DIR="$MODDIR"
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/font_check.sh" ] && . "$MODDIR/common/font_check.sh"
[ -f "$MODDIR/common/background_task.sh" ] && . "$MODDIR/common/background_task.sh"

json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
}

read_value() {
    sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

clean_spec() {
    printf '%s' "$1" | tr -d '\r\n'
}

axis_value() {
    _spec="$1"
    _tag="$2"
    _fallback="$3"
    _value=$(printf '%s' "$_spec" | tr ',' '\n' | sed -n "s/^${_tag}=//p" | head -n1)
    case "$_value" in ''|*[!0-9.-]*) _value="$_fallback" ;; esac
    printf '%s' "$_value"
}

safe_weight() {
    _weight=$(axis_value "$1" wght 400)
    _weight=${_weight%%.*}
    case "$_weight" in ''|*[!0-9]*) _weight=400 ;; esac
    [ "$_weight" -ge 1 ] 2>/dev/null || _weight=1
    [ "$_weight" -le 1000 ] 2>/dev/null || _weight=1000
    printf '%s' "$_weight"
}

role_weight() {
    case "$1" in
        thin) echo 100 ;;
        extralight) echo 200 ;;
        light) echo 300 ;;
        regular|normal) echo 400 ;;
        medium) echo 500 ;;
        semibold) echo 600 ;;
        bold) echo 700 ;;
        extrabold) echo 800 ;;
        black|heavy) echo 900 ;;
        variable) echo "$2" ;;
        *) echo 400 ;;
    esac
}

write_task() {
    _tmp="$TASK_FILE.tmp.$$"
    {
        printf 'task=%s\n' "$1"
        printf 'state=%s\n' "$2"
        printf 'message=%s\n' "$3"
        printf 'cjk=%s\nlatin=%s\ndigit=%s\n' "$4" "$5" "$6"
        printf 'cjkAxes=%s\nlatinAxes=%s\ndigitAxes=%s\n' "$7" "$8" "$9"
        shift 9
        printf 'root=%s\nchildTask=%s\nstarted=%s\nfinished=%s\npercent=%s\n' "$1" "$2" "$3" "$4" "$5"
    } >"$_tmp" 2>/dev/null && mv -f "$_tmp" "$TASK_FILE" 2>/dev/null
    chmod 0644 "$TASK_FILE" 2>/dev/null || true
}

update_task() {
    _wanted="$1"
    _state="$2"
    _message="$3"
    _percent="$4"
    _child="$5"
    _finished="$6"
    [ "$(read_value "$TASK_FILE" task)" = "$_wanted" ] || return 1
    _cjk=$(read_value "$TASK_FILE" cjk)
    _latin=$(read_value "$TASK_FILE" latin)
    _digit=$(read_value "$TASK_FILE" digit)
    _cjk_axes=$(read_value "$TASK_FILE" cjkAxes)
    _latin_axes=$(read_value "$TASK_FILE" latinAxes)
    _digit_axes=$(read_value "$TASK_FILE" digitAxes)
    _root=$(read_value "$TASK_FILE" root)
    _started=$(read_value "$TASK_FILE" started)
    [ -n "$_child" ] || _child=$(read_value "$TASK_FILE" childTask)
    [ -n "$_finished" ] || _finished=$(read_value "$TASK_FILE" finished)
    write_task "$_wanted" "$_state" "$_message" "$_cjk" "$_latin" "$_digit" \
        "$_cjk_axes" "$_latin_axes" "$_digit_axes" "$_root" "$_child" "$_started" "$_finished" "$_percent"
}

find_best_source() {
    _family="$1"
    _target="$2"
    _best=""
    _best_score=99999
    for _font in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
                 "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_font" ] || continue
        _name=$(basename "$_font")
        _detected=$(detect_font_family "$_name")
        [ "$_detected" = "$_family" ] || continue
        if is_variable_font "$_font" 2>/dev/null; then
            printf '%s\n' "$_font"
            return 0
        fi
        _role=$(detect_font_weight "$_name")
        _number=$(role_weight "$_role" "$_target")
        _score=$((_number - _target))
        [ "$_score" -ge 0 ] 2>/dev/null || _score=$((-_score))
        if [ -z "$_best" ] || [ "$_score" -lt "$_best_score" ] 2>/dev/null; then
            _best="$_font"
            _best_score="$_score"
        fi
    done
    [ -n "$_best" ] || return 1
    printf '%s\n' "$_best"
}

run_instance() {
    _source="$1"
    _destination="$2"
    _role="$3"
    _axes="$4"
    _weight=$(safe_weight "$_axes")
    _report="${_destination}.json"
    _error="${_destination}.err"
    [ -x "$PYBIN" ] || chmod 0755 "$PYBIN" 2>/dev/null || true
    (
        export PYTHONHOME="$PYROOT"
        export PYTHONPATH="$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages"
        export LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
        export TMPDIR="${TMPDIR:-$MODDIR/cache/tmp}"
        mkdir -p "$TMPDIR" 2>/dev/null || true
        "$PYBIN" "$INSTANCE_PY" --input "$_source" --output "$_destination" \
            --role "$_role" --weight "$_weight" --axes "$_axes"
    ) >"$_report" 2>"$_error"
    _code=$?
    if [ "$_code" -ne 0 ] || [ ! -s "$_destination" ]; then
        _message=$(sed -n 's/^.*"message":"\([^"]*\)".*$/\1/p' "$_error" "$_report" 2>/dev/null | tail -n1)
        [ -n "$_message" ] || _message=$(tail -n1 "$_error" 2>/dev/null | tr -d '\r')
        [ -n "$_message" ] || _message="字体实例化失败（代码 $_code）"
        echo "错误：$_message" >&2
        return 1
    fi
    rm -f "$_error" 2>/dev/null || true
    chmod 0644 "$_destination" "$_report" 2>/dev/null || true
    return 0
}

prepare_slot() {
    _role="$1"
    _family="$2"
    _axes="$3"
    _root="$4"
    _internal="$5"
    _weight=$(safe_weight "$_axes")
    _source=$(find_best_source "$_family" "$_weight")
    [ -f "$_source" ] || { echo "错误：找不到字体族 $_family" >&2; return 1; }
    font_validate "$_source" text || { echo "错误：字体 $_family 无效：$FONT_CHECK_ERROR" >&2; return 1; }
    _destination="$_root/fonts/${_internal}-Regular.ttf"
    mkdir -p "${_destination%/*}" 2>/dev/null || return 1
    if [ "$FONT_CHECK_VARIABLE" = true ] || [ "$FONT_CHECK_FORMAT" = TTC ]; then
        run_instance "$_source" "$_destination" "$_role" "$_axes" || return 1
    else
        cp -f "$_source" "$_destination" 2>/dev/null || return 1
        chmod 0644 "$_destination" 2>/dev/null || true
    fi
    [ -s "$_destination" ]
}

rewrite_public_config() {
    [ -s "$TASK_FILE" ] || return 0
    [ "$(read_value "$TASK_FILE" state)" = success ] || return 0
    _cjk=$(read_value "$TASK_FILE" cjk)
    _latin=$(read_value "$TASK_FILE" latin)
    _digit=$(read_value "$TASK_FILE" digit)
    _cjk_axes=$(read_value "$TASK_FILE" cjkAxes)
    _latin_axes=$(read_value "$TASK_FILE" latinAxes)
    _digit_axes=$(read_value "$TASK_FILE" digitAxes)
    _tmp="$MIX_CONF.axes.$$"
    {
        printf 'cjk=%s\nlatin=%s\ndigit=%s\n' "$_cjk" "$_latin" "$_digit"
        printf 'cjkWeight=%s\nlatinWeight=%s\ndigitWeight=%s\n' \
            "$(safe_weight "$_cjk_axes")" "$(safe_weight "$_latin_axes")" "$(safe_weight "$_digit_axes")"
        printf 'cjkAxes=%s\nlatinAxes=%s\ndigitAxes=%s\n' "$_cjk_axes" "$_latin_axes" "$_digit_axes"
        [ ! -f "$MIX_CONF" ] || grep -v -E '^(cjk|latin|digit|cjkWeight|latinWeight|digitWeight|cjkAxes|latinAxes|digitAxes)=' "$MIX_CONF" 2>/dev/null
    } >"$_tmp" 2>/dev/null && mv -f "$_tmp" "$MIX_CONF" 2>/dev/null
    cp -f "$MIX_CONF" "$AXES_CONF" 2>/dev/null || true
    chmod 0644 "$MIX_CONF" "$AXES_CONF" 2>/dev/null || true
}

worker() {
    trap '' HUP
    _wanted="$1"
    [ "$(read_value "$TASK_FILE" task)" = "$_wanted" ] || exit 0
    _cjk=$(read_value "$TASK_FILE" cjk)
    _latin=$(read_value "$TASK_FILE" latin)
    _digit=$(read_value "$TASK_FILE" digit)
    _cjk_axes=$(read_value "$TASK_FILE" cjkAxes)
    _latin_axes=$(read_value "$TASK_FILE" latinAxes)
    _digit_axes=$(read_value "$TASK_FILE" digitAxes)
    _root=$(read_value "$TASK_FILE" root)

    if [ -f "$ROLE_CHECK" ]; then
        MODDIR="$MODDIR" sh "$ROLE_CHECK" "$_cjk" cjk >/dev/null 2>&1 || { update_task "$_wanted" failed '中文基底缺少必要字形' 100 '' "$(date +%s)"; luoshu_clear_task_pid "$WORKER_PID" "$_wanted"; exit 1; }
        MODDIR="$MODDIR" sh "$ROLE_CHECK" "$_latin" latin >/dev/null 2>&1 || { update_task "$_wanted" failed '英文字体缺少必要字形' 100 '' "$(date +%s)"; luoshu_clear_task_pid "$WORKER_PID" "$_wanted"; exit 1; }
        MODDIR="$MODDIR" sh "$ROLE_CHECK" "$_digit" digit >/dev/null 2>&1 || { update_task "$_wanted" failed '数字字体缺少必要字形' 100 '' "$(date +%s)"; luoshu_clear_task_pid "$WORKER_PID" "$_wanted"; exit 1; }
    fi

    update_task "$_wanted" running '正在准备中文字体' 4 '' ''
    prepare_slot cjk "$_cjk" "$_cjk_axes" "$_root" LuoShuMixCJK || {
        update_task "$_wanted" failed '中文字体准备失败' 100 '' "$(date +%s)"
        rm -rf "$_root"; luoshu_clear_task_pid "$WORKER_PID" "$_wanted"; exit 1
    }
    update_task "$_wanted" running '正在准备英文字体' 14 '' ''
    prepare_slot latin "$_latin" "$_latin_axes" "$_root" LuoShuMixLatin || {
        update_task "$_wanted" failed '英文字体准备失败' 100 '' "$(date +%s)"
        rm -rf "$_root"; luoshu_clear_task_pid "$WORKER_PID" "$_wanted"; exit 1
    }
    update_task "$_wanted" running '正在准备数字字体' 24 '' ''
    prepare_slot digit "$_digit" "$_digit_axes" "$_root" LuoShuMixDigit || {
        update_task "$_wanted" failed '数字字体准备失败' 100 '' "$(date +%s)"
        rm -rf "$_root"; luoshu_clear_task_pid "$WORKER_PID" "$_wanted"; exit 1
    }

    update_task "$_wanted" running '正在启动完整复合字体引擎' 34 '' ''
    _output=$(LUOSHU_PUBLIC_DIR="$_root" MODDIR="$MODDIR" sh "$BASE_ENGINE" start LuoShuMixCJK LuoShuMixLatin LuoShuMixDigit 2>&1)
    _child=$(printf '%s\n' "$_output" | sed -n 's/^.*"task":"\([^"]*\)".*$/\1/p' | tail -n1)
    if [ -z "$_child" ]; then
        _message=$(printf '%s\n' "$_output" | sed -n 's/^.*"message":"\([^"]*\)".*$/\1/p' | tail -n1)
        [ -n "$_message" ] || _message='无法启动完整复合字体引擎'
        update_task "$_wanted" failed "$_message" 100 '' "$(date +%s)"
        rm -rf "$_root"; luoshu_clear_task_pid "$WORKER_PID" "$_wanted"; exit 1
    fi

    update_task "$_wanted" running '完整复合字体正在后台生成' 36 "$_child" ''
    _loops=0
    while [ "$_loops" -lt 360 ]; do
        _base_task=$(read_value "$BASE_TASK_FILE" task)
        _base_state=$(read_value "$BASE_TASK_FILE" state)
        if [ "$_base_task" = "$_child" ]; then
            _base_message=$(read_value "$BASE_TASK_FILE" message)
            _base_percent=0
            if [ -s "$PROGRESS_FILE" ]; then
                _base_percent=$(sed -n 's/^.*"percent":\([0-9][0-9]*\).*$/\1/p' "$PROGRESS_FILE" 2>/dev/null | head -n1)
            fi
            case "$_base_percent" in ''|*[!0-9]*) _base_percent=0 ;; esac
            _mapped=$((36 + (_base_percent * 64 / 100)))
            [ "$_mapped" -le 99 ] || _mapped=99
            [ -n "$_base_message" ] || _base_message='完整复合字体正在后台生成'
            case "$_base_state" in
                success)
                    update_task "$_wanted" success "$_base_message" 100 "$_child" "$(date +%s)"
                    rewrite_public_config
                    rm -rf "$_root"; luoshu_clear_task_pid "$WORKER_PID" "$_wanted"; exit 0
                    ;;
                failed)
                    update_task "$_wanted" failed "$_base_message" 100 "$_child" "$(date +%s)"
                    rm -rf "$_root"; luoshu_clear_task_pid "$WORKER_PID" "$_wanted"; exit 1
                    ;;
                *) update_task "$_wanted" running "$_base_message" "$_mapped" "$_child" '' ;;
            esac
        fi
        sleep 2
        _loops=$((_loops + 1))
    done

    update_task "$_wanted" failed '完整复合字体生成超时' 100 "$_child" "$(date +%s)"
    rm -rf "$_root"; luoshu_clear_task_pid "$WORKER_PID" "$_wanted"
    exit 1
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
    _cjk=$(read_value "$TASK_FILE" cjk)
    _latin=$(read_value "$TASK_FILE" latin)
    _digit=$(read_value "$TASK_FILE" digit)
    _cjk_axes=$(read_value "$TASK_FILE" cjkAxes)
    _latin_axes=$(read_value "$TASK_FILE" latinAxes)
    _digit_axes=$(read_value "$TASK_FILE" digitAxes)
    _started=$(read_value "$TASK_FILE" started)
    _finished=$(read_value "$TASK_FILE" finished)
    _percent=$(read_value "$TASK_FILE" percent)
    printf '{"status":"ok","data":{"task":"%s","state":"%s","message":"%s","cjk":"%s","latin":"%s","digit":"%s","cjkWeight":%s,"latinWeight":%s,"digitWeight":%s,"cjkAxes":"%s","latinAxes":"%s","digitAxes":"%s","started":%s,"finished":%s,"progress":{"message":"%s","percent":%s}}}\n' \
        "$(json_escape "$_task")" "$(json_escape "$_state")" "$(json_escape "$_message")" \
        "$(json_escape "$_cjk")" "$(json_escape "$_latin")" "$(json_escape "$_digit")" \
        "$(safe_weight "$_cjk_axes")" "$(safe_weight "$_latin_axes")" "$(safe_weight "$_digit_axes")" \
        "$(json_escape "$_cjk_axes")" "$(json_escape "$_latin_axes")" "$(json_escape "$_digit_axes")" \
        "${_started:-0}" "${_finished:-0}" "$(json_escape "$_message")" "${_percent:-0}"
}

config_json() {
    rewrite_public_config
    _source="$AXES_CONF"
    [ -s "$_source" ] || _source="$MIX_CONF"
    _cjk=$(read_value "$_source" cjk)
    _latin=$(read_value "$_source" latin)
    _digit=$(read_value "$_source" digit)
    _cjk_axes=$(read_value "$_source" cjkAxes)
    _latin_axes=$(read_value "$_source" latinAxes)
    _digit_axes=$(read_value "$_source" digitAxes)
    [ -n "$_cjk_axes" ] || _cjk_axes="wght=$(read_value "$_source" cjkWeight)"
    [ -n "$_latin_axes" ] || _latin_axes="wght=$(read_value "$_source" latinWeight)"
    [ -n "$_digit_axes" ] || _digit_axes="wght=$(read_value "$_source" digitWeight)"
    _active=$(head -n1 "$ACTIVE_CONF" 2>/dev/null | tr -d '\r\n')
    _enabled=false
    [ "$_active" = mix ] && _enabled=true
    printf '{"status":"ok","data":{"enabled":%s,"cjk":"%s","latin":"%s","digit":"%s","cjkWeight":%s,"latinWeight":%s,"digitWeight":%s,"cjkAxes":"%s","latinAxes":"%s","digitAxes":"%s"}}\n' \
        "$_enabled" "$(json_escape "$_cjk")" "$(json_escape "$_latin")" "$(json_escape "$_digit")" \
        "$(safe_weight "$_cjk_axes")" "$(safe_weight "$_latin_axes")" "$(safe_weight "$_digit_axes")" \
        "$(json_escape "$_cjk_axes")" "$(json_escape "$_latin_axes")" "$(json_escape "$_digit_axes")"
}

start_mix() {
    _cjk="$1"
    _latin="$2"
    _digit="$3"
    _cjk_axes=$(clean_spec "$4")
    _latin_axes=$(clean_spec "$5")
    _digit_axes=$(clean_spec "$6")
    [ -n "$_cjk" ] && [ -n "$_latin" ] && [ -n "$_digit" ] || {
        printf '{"status":"error","message":"请选择中文、英文和数字字体"}\n'; return
    }
    [ ! -f "$TEXT_REBOOT_REQUIRED" ] || {
        printf '{"status":"error","message":"本次开机已更改文字字体，请先重启手机"}\n'; return
    }
    if [ -s "$WORKER_PID" ]; then
        _old=$(cat "$WORKER_PID" 2>/dev/null)
        [ -z "$_old" ] || ! kill -0 "$_old" 2>/dev/null || {
            printf '{"status":"error","message":"已有字体组合任务正在运行"}\n'; return
        }
    fi
    [ ! -e "$LOCK_FILE" ] || { printf '{"status":"error","message":"字体正在切换中"}\n'; return; }
    [ -n "$_cjk_axes" ] || _cjk_axes='wght=400'
    [ -n "$_latin_axes" ] || _latin_axes='wght=400'
    [ -n "$_digit_axes" ] || _digit_axes='wght=400'
    mkdir -p "$CONFIG_DIR" "$CACHE_ROOT" "$MODDIR/cache/tmp" "$MODDIR/logs" 2>/dev/null || {
        printf '{"status":"error","message":"无法创建字体组合缓存目录"}\n'; return
    }
    _request="axes-$(date +%s)-$$"
    _root="$CACHE_ROOT/$_request"
    mkdir -p "$_root/fonts" 2>/dev/null || {
        printf '{"status":"error","message":"无法创建字体暂存目录"}\n'; return
    }
    write_task "$_request" queued '任务已进入后台队列' "$_cjk" "$_latin" "$_digit" \
        "$_cjk_axes" "$_latin_axes" "$_digit_axes" "$_root" '' "$(date +%s)" '' 1
    if type luoshu_start_detached >/dev/null 2>&1; then
        luoshu_start_detached "$WORKER_PID" "$_request" "$LOG_FILE" sh "$0" worker "$_request" || {
  update_task "$_request" failed '无法启动独立后台任务' 100 '' "$(date +%s)"
  printf '{"status":"error","message":"无法启动独立后台任务"}\n'
  return
        }
    else
        ( trap '' HUP; MODDIR="$MODDIR" sh "$0" worker "$_request" ) </dev/null >>"$LOG_FILE" 2>&1 &
        printf '%s\n' "$!" >"$WORKER_PID" 2>/dev/null || true
    fi
    printf '{"status":"ok","data":{"task":"%s"}}\n' "$(json_escape "$_request")"
}

recover_task() {
    MODDIR="$MODDIR" sh "$BASE_ENGINE" recover >/dev/null 2>&1 || true
    if [ -s "$TASK_FILE" ]; then
        _state=$(read_value "$TASK_FILE" state)
        _task=$(read_value "$TASK_FILE" task)
        _root=$(read_value "$TASK_FILE" root)
        case "$_state" in
            queued|running) update_task "$_task" failed '上次字体组合任务被开机恢复中止' 100 '' "$(date +%s)" ;;
        esac
        [ -z "$_root" ] || rm -rf "$_root" 2>/dev/null || true
    fi
    rm -f "$WORKER_PID" 2>/dev/null || true
    printf '{"status":"ok"}\n'
}

case "${1:-config}" in
    start) start_mix "$2" "$3" "$4" "${5:-wght=400}" "${6:-wght=400}" "${7:-wght=400}" ;;
    status) status_json "${2:-}" ;;
    config) config_json ;;
    worker) worker "$2" ;;
    recover) recover_task ;;
    *) printf '{"status":"error","message":"未知多轴组合命令"}\n' ;;
esac
exit 0
