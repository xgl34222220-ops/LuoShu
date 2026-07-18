#!/system/bin/sh
# 洛书 v14.2：独立字重组合桥。
# 先把三个来源各自实例化为指定字重，再复用 v14 已验证的完整复合、事务与回滚核心。
set +e

MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"; else MODDIR="/data/adb/modules/LuoShu"; fi
fi
CONFIG_DIR="$MODDIR/config"
CACHE_ROOT="$MODDIR/cache/weighted-mix"
USER_FONTS_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/fonts"
BASE_ENGINE="$MODDIR/common/font_mix.sh"
INSTANCE_PY="$MODDIR/common/font_instance.py"
PYROOT="$MODDIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"
TASK_FILE="$CONFIG_DIR/mix_task.conf"
MAP_FILE="$CONFIG_DIR/v142_weighted_task.conf"
WEIGHT_CONF="$CONFIG_DIR/v142_weighted_mix.conf"
MIX_CONF="$CONFIG_DIR/font_mix.conf"
ACTIVE_CONF="$CONFIG_DIR/active_font.conf"
PROGRESS_FILE="$CONFIG_DIR/composite_progress.json"
LOG_FILE="$MODDIR/logs/fontswitch.log"

MODULE_DIR="$MODDIR"
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/font_check.sh" ] && . "$MODDIR/common/font_check.sh"

json_escape() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '; }
read_value() { _f="$1"; _k="$2"; sed -n "s/^${_k}=//p" "$_f" 2>/dev/null | head -n1 | tr -d '\r\n'; }
clamp_weight() {
    _w="$1"; case "$_w" in ''|*[!0-9]*) _w=400 ;; esac
    [ "$_w" -ge 1 ] 2>/dev/null || _w=1
    [ "$_w" -le 1000 ] 2>/dev/null || _w=1000
    printf '%s' "$_w"
}
role_weight() {
    case "$1" in thin) echo 100 ;; light) echo 300 ;; regular) echo 400 ;; medium) echo 500 ;; semibold) echo 600 ;; bold) echo 700 ;; black) echo 900 ;; variable) echo "$2" ;; *) echo 400 ;; esac
}

find_best_source() {
    _family="$1"; _target="$2"; _best=""; _best_score=99999
    for _f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
              "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_f" ] || continue
        _name=$(basename "$_f")
        _fam=$(detect_font_family "$_name")
        [ "$_fam" = "$_family" ] || continue
        if is_variable_font "$_f" 2>/dev/null; then
            printf '%s\n' "$_f"
            return 0
        fi
        _role=$(detect_font_weight "$_name")
        _num=$(role_weight "$_role" "$_target")
        _score=$((_num - _target)); [ "$_score" -ge 0 ] 2>/dev/null || _score=$((-_score))
        if [ -z "$_best" ] || [ "$_score" -lt "$_best_score" ] 2>/dev/null; then
            _best="$_f"; _best_score="$_score"
        fi
    done
    [ -n "$_best" ] || return 1
    printf '%s\n' "$_best"
}

run_instance() {
    _src="$1"; _dest="$2"; _role="$3"; _weight="$4"; _report="${_dest}.json"; _err="${_dest}.err"
    [ -x "$PYBIN" ] || chmod 0755 "$PYBIN" 2>/dev/null || true
    (
        export PYTHONHOME="$PYROOT"
        export PYTHONPATH="$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages"
        export LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
        export TMPDIR="${TMPDIR:-$MODDIR/cache/tmp}"
        mkdir -p "$TMPDIR" 2>/dev/null || true
        "$PYBIN" "$INSTANCE_PY" --input "$_src" --output "$_dest" --role "$_role" --weight "$_weight"
    ) >"$_report" 2>"$_err"
    _rc=$?
    if [ "$_rc" -ne 0 ] || [ ! -s "$_dest" ]; then
        _msg=$(sed -n 's/^.*"message":"\([^"]*\)".*$/\1/p' "$_err" "$_report" 2>/dev/null | tail -n1)
        [ -n "$_msg" ] || _msg=$(tail -n1 "$_err" 2>/dev/null | tr -d '\r')
        [ -n "$_msg" ] || _msg="字重实例化失败（返回 $_rc）"
        echo "错误：$_msg" >&2
        return 1
    fi
    rm -f "$_err" 2>/dev/null || true
    chmod 0644 "$_dest" "$_report" 2>/dev/null || true
    return 0
}

prepare_slot() {
    _role="$1"; _family="$2"; _weight="$3"; _root="$4"; _internal="$5"
    _src=$(find_best_source "$_family" "$_weight")
    [ -f "$_src" ] || { echo "错误：找不到字体族 $_family" >&2; return 1; }
    font_validate "$_src" text || { echo "错误：字体 $_family 无效：$FONT_CHECK_ERROR" >&2; return 1; }
    _dest="$_root/fonts/${_internal}-Regular.ttf"
    mkdir -p "${_dest%/*}" 2>/dev/null || return 1
    if [ "$FONT_CHECK_VARIABLE" = true ] || [ "$FONT_CHECK_FORMAT" = TTC ]; then
        run_instance "$_src" "$_dest" "$_role" "$_weight" || return 1
    else
        cp -f "$_src" "$_dest" 2>/dev/null || return 1
        chmod 0644 "$_dest" 2>/dev/null || true
    fi
    [ -s "$_dest" ] || return 1
    return 0
}

write_map() {
    _tmp="$MAP_FILE.tmp.$$"
    {
        printf 'task=%s\n' "$1"
        printf 'cjk=%s\n' "$2"; printf 'latin=%s\n' "$3"; printf 'digit=%s\n' "$4"
        printf 'cjkWeight=%s\n' "$5"; printf 'latinWeight=%s\n' "$6"; printf 'digitWeight=%s\n' "$7"
        printf 'root=%s\n' "$8"; printf 'started=%s\n' "$(date +%s)"
    } >"$_tmp" 2>/dev/null && mv -f "$_tmp" "$MAP_FILE" 2>/dev/null
    chmod 0644 "$MAP_FILE" 2>/dev/null || true
}

rewrite_public_config() {
    [ -s "$MAP_FILE" ] || return 0
    _task=$(read_value "$MAP_FILE" task)
    _state=$(read_value "$TASK_FILE" state)
    [ -n "$_task" ] && [ "$_task" = "$(read_value "$TASK_FILE" task)" ] || return 0
    case "$_state" in success|failed) ;; *) return 0 ;; esac
    _cjk=$(read_value "$MAP_FILE" cjk); _latin=$(read_value "$MAP_FILE" latin); _digit=$(read_value "$MAP_FILE" digit)
    _cw=$(read_value "$MAP_FILE" cjkWeight); _lw=$(read_value "$MAP_FILE" latinWeight); _dw=$(read_value "$MAP_FILE" digitWeight)
    _root=$(read_value "$MAP_FILE" root)
    if [ "$_state" = success ]; then
        _tmp="$MIX_CONF.v142.$$"
        {
            printf 'cjk=%s\nlatin=%s\ndigit=%s\n' "$_cjk" "$_latin" "$_digit"
            printf 'cjkWeight=%s\nlatinWeight=%s\ndigitWeight=%s\n' "$_cw" "$_lw" "$_dw"
            [ ! -f "$MIX_CONF" ] || grep -v -E '^(cjk|latin|digit|cjkWeight|latinWeight|digitWeight)=' "$MIX_CONF" 2>/dev/null
        } >"$_tmp" 2>/dev/null && mv -f "$_tmp" "$MIX_CONF" 2>/dev/null
        cp -f "$MIX_CONF" "$WEIGHT_CONF" 2>/dev/null || true
        chmod 0644 "$MIX_CONF" "$WEIGHT_CONF" 2>/dev/null || true
    fi
    [ -z "$_root" ] || rm -rf "$_root" 2>/dev/null || true
    rm -f "$MAP_FILE" 2>/dev/null || true
}

status_json() {
    _wanted="$1"
    rewrite_public_config
    [ -s "$TASK_FILE" ] || { printf '{"status":"error","message":"暂无组合任务"}\n'; return; }
    _task=$(read_value "$TASK_FILE" task); _state=$(read_value "$TASK_FILE" state); _message=$(read_value "$TASK_FILE" message)
    [ -z "$_wanted" ] || [ "$_wanted" = "$_task" ] || { printf '{"status":"error","message":"任务不存在或已被新任务替换"}\n'; return; }
    _cjk=$(read_value "$TASK_FILE" cjk); _latin=$(read_value "$TASK_FILE" latin); _digit=$(read_value "$TASK_FILE" digit)
    _cw=400; _lw=400; _dw=400
    if [ -s "$MAP_FILE" ] && [ "$(read_value "$MAP_FILE" task)" = "$_task" ]; then
        _cjk=$(read_value "$MAP_FILE" cjk); _latin=$(read_value "$MAP_FILE" latin); _digit=$(read_value "$MAP_FILE" digit)
        _cw=$(read_value "$MAP_FILE" cjkWeight); _lw=$(read_value "$MAP_FILE" latinWeight); _dw=$(read_value "$MAP_FILE" digitWeight)
    elif [ -s "$WEIGHT_CONF" ]; then
        _cw=$(read_value "$WEIGHT_CONF" cjkWeight); _lw=$(read_value "$WEIGHT_CONF" latinWeight); _dw=$(read_value "$WEIGHT_CONF" digitWeight)
    fi
    _started=$(read_value "$TASK_FILE" started); _finished=$(read_value "$TASK_FILE" finished)
    _progress=null
    if [ -s "$PROGRESS_FILE" ]; then
        _progress=$(tr -d '\r\n' < "$PROGRESS_FILE" 2>/dev/null)
        case "$_progress" in \{*\}) ;; *) _progress=null ;; esac
    fi
    printf '{"status":"ok","data":{"task":"%s","state":"%s","message":"%s","cjk":"%s","latin":"%s","digit":"%s","cjkWeight":%s,"latinWeight":%s,"digitWeight":%s,"started":%s,"finished":%s,"progress":%s}}\n' \
        "$(json_escape "$_task")" "$(json_escape "$_state")" "$(json_escape "$_message")" \
        "$(json_escape "$_cjk")" "$(json_escape "$_latin")" "$(json_escape "$_digit")" \
        "${_cw:-400}" "${_lw:-400}" "${_dw:-400}" "${_started:-0}" "${_finished:-0}" "$_progress"
}

config_json() {
    rewrite_public_config
    _source="$WEIGHT_CONF"; [ -s "$_source" ] || _source="$MIX_CONF"
    _cjk=$(read_value "$_source" cjk); _latin=$(read_value "$_source" latin); _digit=$(read_value "$_source" digit)
    _cw=$(read_value "$_source" cjkWeight); _lw=$(read_value "$_source" latinWeight); _dw=$(read_value "$_source" digitWeight)
    _active=$(head -n1 "$ACTIVE_CONF" 2>/dev/null | tr -d '\r\n'); _enabled=false; [ "$_active" = mix ] && _enabled=true
    printf '{"status":"ok","data":{"enabled":%s,"cjk":"%s","latin":"%s","digit":"%s","cjkWeight":%s,"latinWeight":%s,"digitWeight":%s}}\n' \
        "$_enabled" "$(json_escape "$_cjk")" "$(json_escape "$_latin")" "$(json_escape "$_digit")" "${_cw:-400}" "${_lw:-400}" "${_dw:-400}"
}

start_mix() {
    _cjk="$1"; _latin="$2"; _digit="$3"
    _cw=$(clamp_weight "$4"); _lw=$(clamp_weight "$5"); _dw=$(clamp_weight "$6")
    [ -n "$_cjk" ] && [ -n "$_latin" ] && [ -n "$_digit" ] || { printf '{"status":"error","message":"请选择中文、英文和数字字体"}\n'; return; }
    mkdir -p "$CONFIG_DIR" "$CACHE_ROOT" "$MODDIR/cache/tmp" "$MODDIR/logs" 2>/dev/null || { printf '{"status":"error","message":"无法创建独立字重缓存目录"}\n'; return; }
    _request="v142-$(date +%s)-$$"; _root="$CACHE_ROOT/$_request"
    mkdir -p "$_root/fonts" 2>/dev/null || { printf '{"status":"error","message":"无法创建字体暂存目录"}\n'; return; }
    prepare_slot cjk "$_cjk" "$_cw" "$_root" LuoShuV142CJK || { rm -rf "$_root"; printf '{"status":"error","message":"中文字体字重准备失败"}\n'; return; }
    prepare_slot latin "$_latin" "$_lw" "$_root" LuoShuV142Latin || { rm -rf "$_root"; printf '{"status":"error","message":"英文字体字重准备失败"}\n'; return; }
    prepare_slot digit "$_digit" "$_dw" "$_root" LuoShuV142Digit || { rm -rf "$_root"; printf '{"status":"error","message":"数字字体字重准备失败"}\n'; return; }
    _output=$(LUOSHU_PUBLIC_DIR="$_root" MODDIR="$MODDIR" sh "$BASE_ENGINE" start LuoShuV142CJK LuoShuV142Latin LuoShuV142Digit 2>&1)
    _task=$(printf '%s\n' "$_output" | sed -n 's/^.*"task":"\([^"]*\)".*$/\1/p' | tail -n1)
    if [ -z "$_task" ]; then
        rm -rf "$_root" 2>/dev/null || true
        printf '%s\n' "$_output"
        return
    fi
    write_map "$_task" "$_cjk" "$_latin" "$_digit" "$_cw" "$_lw" "$_dw" "$_root"
    ( MODDIR="$MODDIR" sh "$0" watch "$_task" ) </dev/null >>"$LOG_FILE" 2>&1 &
    printf '{"status":"ok","data":{"task":"%s","cjkWeight":%s,"latinWeight":%s,"digitWeight":%s}}\n' "$(json_escape "$_task")" "$_cw" "$_lw" "$_dw"
}

watch_task() {
    _wanted="$1"; _loops=0
    while [ "$_loops" -lt 420 ]; do
        _task=$(read_value "$TASK_FILE" task); _state=$(read_value "$TASK_FILE" state)
        [ "$_task" = "$_wanted" ] || exit 0
        case "$_state" in success|failed) rewrite_public_config; exit 0 ;; esac
        sleep 2; _loops=$((_loops + 1))
    done
    exit 0
}

case "${1:-config}" in
    start) start_mix "$2" "$3" "$4" "${5:-400}" "${6:-400}" "${7:-400}" ;;
    status) status_json "${2:-}" ;;
    config) config_json ;;
    watch) watch_task "$2" ;;
    recover) MODDIR="$MODDIR" sh "$BASE_ENGINE" recover >/dev/null 2>&1 || true; rewrite_public_config; printf '{"status":"ok"}\n' ;;
    *) printf '{"status":"error","message":"未知独立字重组合命令"}\n' ;;
esac
exit 0
