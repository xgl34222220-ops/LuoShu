#!/system/bin/sh
# 洛书 v14.2 Alpha3：异步多轴字体组合桥。
# 立即返回包装任务 ID；字体实例化与完整复合全部在后台执行。
set +e

MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"; else MODDIR="/data/adb/modules/LuoShu"; fi
fi
CONFIG_DIR="$MODDIR/config"
CACHE_ROOT="$MODDIR/cache/axes-mix"
USER_FONTS_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/fonts"
BASE_ENGINE="$MODDIR/common/font_mix.sh"
INSTANCE_PY="$MODDIR/common/font_instance.py"
PYROOT="$MODDIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"
BASE_TASK_FILE="$CONFIG_DIR/mix_task.conf"
MAP_FILE="$CONFIG_DIR/v143_axes_task.conf"
AXIS_CONF="$CONFIG_DIR/v143_axes_mix.conf"
MIX_CONF="$CONFIG_DIR/font_mix.conf"
ACTIVE_CONF="$CONFIG_DIR/active_font.conf"
PROGRESS_FILE="$CONFIG_DIR/composite_progress.json"
TEXT_REBOOT_REQUIRED="$CONFIG_DIR/text_reboot_required.conf"
LOCK_FILE="$MODDIR/.font_switch.lock"
WORKER_PID="$CONFIG_DIR/v143_axes_worker.pid"
LOG_FILE="$MODDIR/logs/fontswitch.log"

MODULE_DIR="$MODDIR"
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/font_check.sh" ] && . "$MODDIR/common/font_check.sh"

json_escape() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '; }
read_value() { _f="$1"; _k="$2"; sed -n "s/^${_k}=//p" "$_f" 2>/dev/null | head -n1 | tr -d '\r\n'; }
clean_spec() { printf '%s' "$1" | tr -d '\r\n'; }
axis_value() {
    _spec="$1"; _tag="$2"; _fallback="$3"
    _value=$(printf '%s' "$_spec" | tr ',' '\n' | sed -n "s/^${_tag}=//p" | head -n1)
    case "$_value" in ''|*[!0-9.-]*) _value="$_fallback" ;; esac
    printf '%s' "$_value"
}
clamp_weight() {
    _w=$(axis_value "$1" wght 400)
    _w=${_w%%.*}; case "$_w" in ''|*[!0-9]*) _w=400 ;; esac
    [ "$_w" -ge 1 ] 2>/dev/null || _w=1
    [ "$_w" -le 1000 ] 2>/dev/null || _w=1000
    printf '%s' "$_w"
}
role_weight() {
    case "$1" in thin) echo 100 ;; light) echo 300 ;; regular) echo 400 ;; medium) echo 500 ;; semibold) echo 600 ;; bold) echo 700 ;; black) echo 900 ;; variable) echo "$2" ;; *) echo 400 ;; esac
}

write_map() {
    _tmp="$MAP_FILE.tmp.$$"
    {
        printf 'task=%s\nstate=%s\nmessage=%s\n' "$1" "$2" "$3"
        printf 'cjk=%s\nlatin=%s\ndigit=%s\n' "$4" "$5" "$6"
        printf 'cjkAxes=%s\nlatinAxes=%s\ndigitAxes=%s\n' "$7" "$8" "$9"
        shift 9
        printf 'root=%s\nchildTask=%s\nstarted=%s\nfinished=%s\npercent=%s\n' "$1" "$2" "$3" "$4" "$5"
    } >"$_tmp" 2>/dev/null && mv -f "$_tmp" "$MAP_FILE" 2>/dev/null
    chmod 0644 "$MAP_FILE" 2>/dev/null || true
}

update_map() {
    _wanted="$1"; _state="$2"; _message="$3"; _percent="$4"; _child="$5"; _finished="$6"
    [ "$(read_value "$MAP_FILE" task)" = "$_wanted" ] || return 1
    _cjk=$(read_value "$MAP_FILE" cjk); _latin=$(read_value "$MAP_FILE" latin); _digit=$(read_value "$MAP_FILE" digit)
    _ca=$(read_value "$MAP_FILE" cjkAxes); _la=$(read_value "$MAP_FILE" latinAxes); _da=$(read_value "$MAP_FILE" digitAxes)
    _root=$(read_value "$MAP_FILE" root); _started=$(read_value "$MAP_FILE" started)
    [ -n "$_child" ] || _child=$(read_value "$MAP_FILE" childTask)
    [ -n "$_finished" ] || _finished=$(read_value "$MAP_FILE" finished)
    write_map "$_wanted" "$_state" "$_message" "$_cjk" "$_latin" "$_digit" "$_ca" "$_la" "$_da" "$_root" "$_child" "$_started" "$_finished" "$_percent"
}

find_best_source() {
    _family="$1"; _target="$2"; _best=""; _best_score=99999
    for _f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
              "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_f" ] || continue
        _name=$(basename "$_f"); _fam=$(detect_font_family "$_name")
        [ "$_fam" = "$_family" ] || continue
        if is_variable_font "$_f" 2>/dev/null; then printf '%s\n' "$_f"; return 0; fi
        _role=$(detect_font_weight "$_name"); _num=$(role_weight "$_role" "$_target")
        _score=$((_num - _target)); [ "$_score" -ge 0 ] 2>/dev/null || _score=$((-_score))
        if [ -z "$_best" ] || [ "$_score" -lt "$_best_score" ] 2>/dev/null; then _best="$_f"; _best_score="$_score"; fi
    done
    [ -n "$_best" ] || return 1
    printf '%s\n' "$_best"
}

run_instance() {
    _src="$1"; _dest="$2"; _role="$3"; _axes="$4"; _weight=$(clamp_weight "$_axes")
    _report="${_dest}.json"; _err="${_dest}.err"
    [ -x "$PYBIN" ] || chmod 0755 "$PYBIN" 2>/dev/null || true
    (
        export PYTHONHOME="$PYROOT"
        export PYTHONPATH="$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages"
        export LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
        export TMPDIR="${TMPDIR:-$MODDIR/cache/tmp}"
        mkdir -p "$TMPDIR" 2>/dev/null || true
        "$PYBIN" "$INSTANCE_PY" --input "$_src" --output "$_dest" --role "$_role" --weight "$_weight" --axes "$_axes"
    ) >"$_report" 2>"$_err"
    _rc=$?
    if [ "$_rc" -ne 0 ] || [ ! -s "$_dest" ]; then
        _msg=$(sed -n 's/^.*"message":"\([^"]*\)".*$/\1/p' "$_err" "$_report" 2>/dev/null | tail -n1)
        [ -n "$_msg" ] || _msg=$(tail -n1 "$_err" 2>/dev/null | tr -d '\r')
        [ -n "$_msg" ] || _msg="可变轴实例化失败（返回 $_rc）"
        echo "错误：$_msg" >&2
        return 1
    fi
    rm -f "$_err" 2>/dev/null || true
    chmod 0644 "$_dest" "$_report" 2>/dev/null || true
    return 0
}

prepare_slot() {
    _role="$1"; _family="$2"; _axes="$3"; _root="$4"; _internal="$5"; _weight=$(clamp_weight "$_axes")
    _src=$(find_best_source "$_family" "$_weight")
    [ -f "$_src" ] || { echo "错误：找不到字体族 $_family" >&2; return 1; }
    font_validate "$_src" text || { echo "错误：字体 $_family 无效：$FONT_CHECK_ERROR" >&2; return 1; }
    _dest="$_root/fonts/${_internal}-Regular.ttf"
    mkdir -p "${_dest%/*}" 2>/dev/null || return 1
    if [ "$FONT_CHECK_VARIABLE" = true ] || [ "$FONT_CHECK_FORMAT" = TTC ]; then
        run_instance "$_src" "$_dest" "$_role" "$_axes" || return 1
    else
        cp -f "$_src" "$_dest" 2>/dev/null || return 1
        chmod 0644 "$_dest" 2>/dev/null || true
    fi
    [ -s "$_dest" ] || return 1
    return 0
}

rewrite_public_config() {
    [ -s "$MAP_FILE" ] || return 0
    [ "$(read_value "$MAP_FILE" state)" = success ] || return 0
    _cjk=$(read_value "$MAP_FILE" cjk); _latin=$(read_value "$MAP_FILE" latin); _digit=$(read_value "$MAP_FILE" digit)
    _ca=$(read_value "$MAP_FILE" cjkAxes); _la=$(read_value "$MAP_FILE" latinAxes); _da=$(read_value "$MAP_FILE" digitAxes)
    _cw=$(clamp_weight "$_ca"); _lw=$(clamp_weight "$_la"); _dw=$(clamp_weight "$_da")
    _tmp="$MIX_CONF.v143.$$"
    {
        printf 'cjk=%s\nlatin=%s\ndigit=%s\n' "$_cjk" "$_latin" "$_digit"
        printf 'cjkWeight=%s\nlatinWeight=%s\ndigitWeight=%s\n' "$_cw" "$_lw" "$_dw"
        printf 'cjkAxes=%s\nlatinAxes=%s\ndigitAxes=%s\n' "$_ca" "$_la" "$_da"
        [ ! -f "$MIX_CONF" ] || grep -v -E '^(cjk|latin|digit|cjkWeight|latinWeight|digitWeight|cjkAxes|latinAxes|digitAxes)=' "$MIX_CONF" 2>/dev/null
    } >"$_tmp" 2>/dev/null && mv -f "$_tmp" "$MIX_CONF" 2>/dev/null
    cp -f "$MIX_CONF" "$AXIS_CONF" 2>/dev/null || true
    chmod 0644 "$MIX_CONF" "$AXIS_CONF" 2>/dev/null || true
}

worker() {
    _wanted="$1"
    [ "$(read_value "$MAP_FILE" task)" = "$_wanted" ] || exit 0
    _cjk=$(read_value "$MAP_FILE" cjk); _latin=$(read_value "$MAP_FILE" latin); _digit=$(read_value "$MAP_FILE" digit)
    _ca=$(read_value "$MAP_FILE" cjkAxes); _la=$(read_value "$MAP_FILE" latinAxes); _da=$(read_value "$MAP_FILE" digitAxes)
    _root=$(read_value "$MAP_FILE" root)
    update_map "$_wanted" running '正在准备中文字体可变轴' 4 '' ''
    prepare_slot cjk "$_cjk" "$_ca" "$_root" LuoShuV143CJK || { update_map "$_wanted" failed '中文字体可变轴准备失败' 100 '' "$(date +%s)"; rm -rf "$_root"; exit 1; }
    update_map "$_wanted" running '正在准备英文字体可变轴' 14 '' ''
    prepare_slot latin "$_latin" "$_la" "$_root" LuoShuV143Latin || { update_map "$_wanted" failed '英文字体可变轴准备失败' 100 '' "$(date +%s)"; rm -rf "$_root"; exit 1; }
    update_map "$_wanted" running '正在准备数字字体可变轴' 24 '' ''
    prepare_slot digit "$_digit" "$_da" "$_root" LuoShuV143Digit || { update_map "$_wanted" failed '数字字体可变轴准备失败' 100 '' "$(date +%s)"; rm -rf "$_root"; exit 1; }
    update_map "$_wanted" running '正在启动完整复合字体引擎' 34 '' ''
    _output=$(LUOSHU_PUBLIC_DIR="$_root" MODDIR="$MODDIR" sh "$BASE_ENGINE" start LuoShuV143CJK LuoShuV143Latin LuoShuV143Digit 2>&1)
    _child=$(printf '%s\n' "$_output" | sed -n 's/^.*"task":"\([^"]*\)".*$/\1/p' | tail -n1)
    if [ -z "$_child" ]; then
        _message=$(printf '%s\n' "$_output" | sed -n 's/^.*"message":"\([^"]*\)".*$/\1/p' | tail -n1)
        [ -n "$_message" ] || _message='无法启动完整复合字体引擎'
        update_map "$_wanted" failed "$_message" 100 '' "$(date +%s)"
        rm -rf "$_root" 2>/dev/null || true
        exit 1
    fi
    update_map "$_wanted" running '完整复合字体正在后台生成' 36 "$_child" ''
    _loops=0
    while [ "$_loops" -lt 360 ]; do
        _base_task=$(read_value "$BASE_TASK_FILE" task); _base_state=$(read_value "$BASE_TASK_FILE" state)
        if [ "$_base_task" = "$_child" ]; then
            _base_message=$(read_value "$BASE_TASK_FILE" message)
            _base_percent=0
            if [ -s "$PROGRESS_FILE" ]; then
                _base_percent=$(sed -n 's/^.*"percent":\([0-9][0-9]*\).*$/\1/p' "$PROGRESS_FILE" 2>/dev/null | head -n1)
            fi
            case "$_base_percent" in ''|*[!0-9]*) _base_percent=0 ;; esac
            _mapped=$((36 + (_base_percent * 64 / 100))); [ "$_mapped" -le 99 ] || _mapped=99
            [ -n "$_base_message" ] || _base_message='完整复合字体正在后台生成'
            case "$_base_state" in
                success)
                    update_map "$_wanted" success "$_base_message" 100 "$_child" "$(date +%s)"
                    rewrite_public_config
                    rm -rf "$_root" 2>/dev/null || true
                    rm -f "$WORKER_PID" 2>/dev/null || true
                    exit 0
                    ;;
                failed)
                    update_map "$_wanted" failed "$_base_message" 100 "$_child" "$(date +%s)"
                    rm -rf "$_root" 2>/dev/null || true
                    rm -f "$WORKER_PID" 2>/dev/null || true
                    exit 1
                    ;;
                *) update_map "$_wanted" running "$_base_message" "$_mapped" "$_child" '' ;;
            esac
        fi
        sleep 2; _loops=$((_loops + 1))
    done
    update_map "$_wanted" failed '完整复合字体生成超时' 100 "$_child" "$(date +%s)"
    rm -rf "$_root" 2>/dev/null || true
    rm -f "$WORKER_PID" 2>/dev/null || true
    exit 1
}

status_json() {
    _wanted="$1"
    [ -s "$MAP_FILE" ] || { printf '{"status":"error","message":"暂无多轴组合任务"}\n'; return; }
    _task=$(read_value "$MAP_FILE" task)
    [ -z "$_wanted" ] || [ "$_wanted" = "$_task" ] || { printf '{"status":"error","message":"任务不存在或已被新任务替换"}\n'; return; }
    _state=$(read_value "$MAP_FILE" state); _message=$(read_value "$MAP_FILE" message)
    _cjk=$(read_value "$MAP_FILE" cjk); _latin=$(read_value "$MAP_FILE" latin); _digit=$(read_value "$MAP_FILE" digit)
    _ca=$(read_value "$MAP_FILE" cjkAxes); _la=$(read_value "$MAP_FILE" latinAxes); _da=$(read_value "$MAP_FILE" digitAxes)
    _cw=$(clamp_weight "$_ca"); _lw=$(clamp_weight "$_la"); _dw=$(clamp_weight "$_da")
    _started=$(read_value "$MAP_FILE" started); _finished=$(read_value "$MAP_FILE" finished); _percent=$(read_value "$MAP_FILE" percent)
    printf '{"status":"ok","data":{"task":"%s","state":"%s","message":"%s","cjk":"%s","latin":"%s","digit":"%s","cjkWeight":%s,"latinWeight":%s,"digitWeight":%s,"cjkAxes":"%s","latinAxes":"%s","digitAxes":"%s","started":%s,"finished":%s,"progress":{"message":"%s","percent":%s}}}\n' \
        "$(json_escape "$_task")" "$(json_escape "$_state")" "$(json_escape "$_message")" \
        "$(json_escape "$_cjk")" "$(json_escape "$_latin")" "$(json_escape "$_digit")" "$_cw" "$_lw" "$_dw" \
        "$(json_escape "$_ca")" "$(json_escape "$_la")" "$(json_escape "$_da")" "${_started:-0}" "${_finished:-0}" "$(json_escape "$_message")" "${_percent:-0}"
}

config_json() {
    rewrite_public_config
    _source="$AXIS_CONF"; [ -s "$_source" ] || _source="$MIX_CONF"
    _cjk=$(read_value "$_source" cjk); _latin=$(read_value "$_source" latin); _digit=$(read_value "$_source" digit)
    _ca=$(read_value "$_source" cjkAxes); _la=$(read_value "$_source" latinAxes); _da=$(read_value "$_source" digitAxes)
    [ -n "$_ca" ] || _ca="wght=$(read_value "$_source" cjkWeight)"; [ -n "$_la" ] || _la="wght=$(read_value "$_source" latinWeight)"; [ -n "$_da" ] || _da="wght=$(read_value "$_source" digitWeight)"
    _cw=$(clamp_weight "$_ca"); _lw=$(clamp_weight "$_la"); _dw=$(clamp_weight "$_da")
    _active=$(head -n1 "$ACTIVE_CONF" 2>/dev/null | tr -d '\r\n'); _enabled=false; [ "$_active" = mix ] && _enabled=true
    printf '{"status":"ok","data":{"enabled":%s,"cjk":"%s","latin":"%s","digit":"%s","cjkWeight":%s,"latinWeight":%s,"digitWeight":%s,"cjkAxes":"%s","latinAxes":"%s","digitAxes":"%s"}}\n' \
        "$_enabled" "$(json_escape "$_cjk")" "$(json_escape "$_latin")" "$(json_escape "$_digit")" "$_cw" "$_lw" "$_dw" "$(json_escape "$_ca")" "$(json_escape "$_la")" "$(json_escape "$_da")"
}

start_mix() {
    _cjk="$1"; _latin="$2"; _digit="$3"; _ca=$(clean_spec "$4"); _la=$(clean_spec "$5"); _da=$(clean_spec "$6")
    [ -n "$_cjk" ] && [ -n "$_latin" ] && [ -n "$_digit" ] || { printf '{"status":"error","message":"请选择中文、英文和数字字体"}\n'; return; }
    [ ! -f "$TEXT_REBOOT_REQUIRED" ] || { printf '{"status":"error","message":"本次开机已更改文字字体，请先重启手机"}\n'; return; }
    if [ -s "$WORKER_PID" ]; then _old=$(cat "$WORKER_PID" 2>/dev/null); [ -z "$_old" ] || ! kill -0 "$_old" 2>/dev/null || { printf '{"status":"error","message":"已有多轴字体任务正在运行"}\n'; return; }; fi
    [ ! -e "$LOCK_FILE" ] || { printf '{"status":"error","message":"字体正在切换中"}\n'; return; }
    [ -n "$_ca" ] || _ca='wght=400'; [ -n "$_la" ] || _la='wght=400'; [ -n "$_da" ] || _da='wght=400'
    mkdir -p "$CONFIG_DIR" "$CACHE_ROOT" "$MODDIR/cache/tmp" "$MODDIR/logs" 2>/dev/null || { printf '{"status":"error","message":"无法创建多轴字体缓存目录"}\n'; return; }
    _request="v143-$(date +%s)-$$"; _root="$CACHE_ROOT/$_request"
    mkdir -p "$_root/fonts" 2>/dev/null || { printf '{"status":"error","message":"无法创建字体暂存目录"}\n'; return; }
    write_map "$_request" queued '任务已进入后台队列' "$_cjk" "$_latin" "$_digit" "$_ca" "$_la" "$_da" "$_root" '' "$(date +%s)" '' 1
    ( MODDIR="$MODDIR" sh "$0" worker "$_request" ) </dev/null >>"$LOG_FILE" 2>&1 &
    _pid=$!; printf '%s\n' "$_pid" >"$WORKER_PID" 2>/dev/null || true
    printf '{"status":"ok","data":{"task":"%s"}}\n' "$(json_escape "$_request")"
}

recover_task() {
    MODDIR="$MODDIR" sh "$BASE_ENGINE" recover >/dev/null 2>&1 || true
    if [ -s "$MAP_FILE" ]; then
        _state=$(read_value "$MAP_FILE" state); _task=$(read_value "$MAP_FILE" task); _root=$(read_value "$MAP_FILE" root)
        case "$_state" in queued|running) update_map "$_task" failed '上次多轴组合任务被开机恢复中止' 100 '' "$(date +%s)" ;; esac
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
