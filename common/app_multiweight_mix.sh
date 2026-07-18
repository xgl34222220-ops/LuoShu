#!/system/bin/sh
# 洛书原生 App 专属：默认多字重复合引擎。
# WebUI 不调用本脚本；只有 app_bridge.sh 在收到 auto 字重规格时进入此流程。
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
CACHE_ROOT="$MODDIR/cache/app-multiweight"
CACHE_FONTS="$MODDIR/cache/app-multiweight-v1"
USER_FONTS_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/fonts"
FONT_MANAGER="$MODDIR/common/font_manager.sh"
INSTANCE_PY="$MODDIR/common/font_instance.py"
COMPOSITE_RUNNER="$MODDIR/common/luoshu_composite.sh"
PYROOT="$MODDIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"
TASK_FILE="$CONFIG_DIR/app_multiweight_task.conf"
MIX_CONF="$CONFIG_DIR/font_mix.conf"
AXIS_CONF="$CONFIG_DIR/v143_axes_mix.conf"
ACTIVE_CONF="$CONFIG_DIR/active_font.conf"
TEXT_REBOOT_REQUIRED="$CONFIG_DIR/text_reboot_required.conf"
WORKER_PID="$CONFIG_DIR/app_multiweight_worker.pid"
LOCK_FILE="$MODDIR/.font_switch.lock"
LOG_FILE="$MODDIR/logs/fontswitch.log"
PRIVATE_FAMILY="LuoShuAppMix"
AUTO_SET="300:Light 400:Regular 500:Medium 600:SemiBold 700:Bold"

MODULE_DIR="$MODDIR"
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/font_check.sh" ] && . "$MODDIR/common/font_check.sh"

json_escape() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '; }
read_value() { sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'; }
clean_spec() { printf '%s' "$1" | tr -d '\r\n'; }
is_auto() { [ "$1" = auto ]; }
axis_value() {
    _value=$(printf '%s' "$1" | tr ',' '\n' | sed -n "s/^${2}=//p" | head -n1)
    case "$_value" in ''|*[!0-9.-]*) _value="$3" ;; esac
    printf '%s' "$_value"
}
clamp_weight() {
    if is_auto "$1"; then printf '400'; return; fi
    _w=$(axis_value "$1" wght 400); _w=${_w%%.*}
    case "$_w" in ''|*[!0-9]*) _w=400 ;; esac
    [ "$_w" -ge 100 ] 2>/dev/null || _w=100
    [ "$_w" -le 900 ] 2>/dev/null || _w=900
    printf '%s' "$_w"
}
role_weight() {
    case "$1" in thin) echo 100 ;; light) echo 300 ;; regular) echo 400 ;; medium) echo 500 ;;
        semibold) echo 600 ;; bold) echo 700 ;; black) echo 900 ;; variable) echo "$2" ;; *) echo 400 ;; esac
}
resolved_spec() { if is_auto "$1"; then printf 'wght=%s' "$2"; else printf '%s' "$1"; fi; }
file_hash() {
    if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
    elif command -v toybox >/dev/null 2>&1; then toybox sha256sum "$1" | awk '{print $1}'
    else cksum "$1" | awk '{print $1 "-" $2}'
    fi
}

write_task() {
    _tmp="$TASK_FILE.tmp.$$"
    {
        printf 'task=%s\nstate=%s\nmessage=%s\n' "$1" "$2" "$3"
        printf 'cjk=%s\nlatin=%s\ndigit=%s\n' "$4" "$5" "$6"
        printf 'cjkAxes=%s\nlatinAxes=%s\ndigitAxes=%s\n' "$7" "$8" "$9"
        shift 9
        printf 'root=%s\nstarted=%s\nfinished=%s\npercent=%s\n' "$1" "$2" "$3" "$4"
    } >"$_tmp" 2>/dev/null && mv -f "$_tmp" "$TASK_FILE" 2>/dev/null
    chmod 0644 "$TASK_FILE" 2>/dev/null || true
}

update_task() {
    _wanted="$1"; _state="$2"; _message="$3"; _percent="$4"; _finished="$5"
    [ "$(read_value "$TASK_FILE" task)" = "$_wanted" ] || return 1
    _cjk=$(read_value "$TASK_FILE" cjk); _latin=$(read_value "$TASK_FILE" latin); _digit=$(read_value "$TASK_FILE" digit)
    _ca=$(read_value "$TASK_FILE" cjkAxes); _la=$(read_value "$TASK_FILE" latinAxes); _da=$(read_value "$TASK_FILE" digitAxes)
    _root=$(read_value "$TASK_FILE" root); _started=$(read_value "$TASK_FILE" started)
    [ -n "$_finished" ] || _finished=$(read_value "$TASK_FILE" finished)
    write_task "$_wanted" "$_state" "$_message" "$_cjk" "$_latin" "$_digit" "$_ca" "$_la" "$_da" "$_root" "$_started" "$_finished" "$_percent"
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
        [ -n "$_msg" ] || _msg="字体实例化失败（返回 $_rc）"
        echo "错误：$_msg" >&2
        return 1
    fi
    rm -f "$_err" 2>/dev/null || true
    chmod 0644 "$_dest" "$_report" 2>/dev/null || true
}

prepare_source() {
    _role="$1"; _family="$2"; _spec="$3"; _target="$4"; _root="$5"; _label="$6"
    _axes=$(resolved_spec "$_spec" "$_target")
    _source_weight=$(clamp_weight "$_axes")
    _src=$(find_best_source "$_family" "$_source_weight")
    [ -f "$_src" ] || { echo "错误：找不到字体族 $_family" >&2; return 1; }
    font_validate "$_src" text || { echo "错误：字体 $_family 无效：$FONT_CHECK_ERROR" >&2; return 1; }
    _dest="$_root/sources/${_label}-${_target}.ttf"
    mkdir -p "${_dest%/*}" 2>/dev/null || return 1
    if [ "$FONT_CHECK_VARIABLE" = true ] || [ "$FONT_CHECK_FORMAT" = TTC ]; then
        run_instance "$_src" "$_dest" "$_role" "$_axes" || return 1
    else
        cp -f "$_src" "$_dest" 2>/dev/null || return 1
        chmod 0644 "$_dest" 2>/dev/null || true
    fi
    [ -s "$_dest" ] || return 1
    printf '%s\n' "$_dest"
}

build_composite() {
    _target="$1"; _cjk="$2"; _latin="$3"; _digit="$4"; _output="$5"
    mkdir -p "$CACHE_FONTS" "$MODDIR/cache/tmp" "${_output%/*}" 2>/dev/null || return 1
    _key_src="$(file_hash "$_cjk")-$(file_hash "$_latin")-$(file_hash "$_digit")-${_target}-app-multiweight-v1"
    _key=$(printf '%s' "$_key_src" | { if command -v sha256sum >/dev/null 2>&1; then sha256sum; elif command -v toybox >/dev/null 2>&1; then toybox sha256sum; else cksum; fi; } | awk '{print $1}')
    _cached="$CACHE_FONTS/${_key}.ttf"
    if [ -s "$_cached" ]; then
        cp -f "$_cached" "$_output" 2>/dev/null || return 1
        chmod 0644 "$_output" 2>/dev/null || true
        return 0
    fi
    _tmp="$CACHE_FONTS/.${_key}.$$.tmp.ttf"; _report="$CACHE_FONTS/.${_key}.$$.json"; _err="$CACHE_FONTS/.${_key}.$$.err"
    rm -f "$_tmp" "$_report" "$_err" 2>/dev/null || true
    if command -v timeout >/dev/null 2>&1; then
        MODDIR="$MODDIR" timeout 480 sh "$COMPOSITE_RUNNER" --cjk "$_cjk" --latin "$_latin" --digit "$_digit" --weight "$_target" --output "$_tmp" >"$_report" 2>"$_err"
        _rc=$?
    elif command -v toybox >/dev/null 2>&1 && toybox timeout --help >/dev/null 2>&1; then
        MODDIR="$MODDIR" toybox timeout 480 sh "$COMPOSITE_RUNNER" --cjk "$_cjk" --latin "$_latin" --digit "$_digit" --weight "$_target" --output "$_tmp" >"$_report" 2>"$_err"
        _rc=$?
    else
        MODDIR="$MODDIR" sh "$COMPOSITE_RUNNER" --cjk "$_cjk" --latin "$_latin" --digit "$_digit" --weight "$_target" --output "$_tmp" >"$_report" 2>"$_err"
        _rc=$?
    fi
    [ ! -s "$_err" ] || cat "$_err" >>"$LOG_FILE" 2>/dev/null || true
    if [ "$_rc" -ne 0 ] || [ ! -s "$_tmp" ]; then
        _msg=$(sed -n 's/^.*"message":"\([^"]*\)".*$/\1/p' "$_err" "$_report" 2>/dev/null | tail -n1)
        [ -n "$_msg" ] || _msg="多字重复合字体 ${_target} 生成失败（返回 $_rc）"
        echo "错误：$_msg" >&2
        rm -f "$_tmp" "$_report" "$_err" 2>/dev/null || true
        return 1
    fi
    if type font_validate_global >/dev/null 2>&1; then
        font_validate_global "$_tmp" || { echo "错误：${FONT_CHECK_ERROR:-多字重复合字体验证失败}" >&2; rm -f "$_tmp" "$_report" "$_err"; return 1; }
    elif type font_validate >/dev/null 2>&1; then
        font_validate "$_tmp" text || { echo "错误：${FONT_CHECK_ERROR:-多字重复合字体验证失败}" >&2; rm -f "$_tmp" "$_report" "$_err"; return 1; }
    fi
    chmod 0644 "$_tmp" 2>/dev/null || true
    mv -f "$_tmp" "$_cached" 2>/dev/null || return 1
    cp -f "$_cached" "$_output" 2>/dev/null || return 1
    rm -f "$_report" "$_err" 2>/dev/null || true
    chmod 0644 "$_cached" "$_output" 2>/dev/null || true
    _count=0
    for _old in $(ls -1t "$CACHE_FONTS"/*.ttf 2>/dev/null); do
        _count=$((_count + 1)); [ "$_count" -le 25 ] || rm -f "$_old" 2>/dev/null || true
    done
}

write_mix_config() {
    _cjk="$1"; _latin="$2"; _digit="$3"; _ca="$4"; _la="$5"; _da="$6"
    _tmp="$MIX_CONF.appmw.$$"
    {
        printf 'cjk=%s\nlatin=%s\ndigit=%s\n' "$_cjk" "$_latin" "$_digit"
        printf 'cjkWeight=%s\nlatinWeight=%s\ndigitWeight=%s\n' "$(clamp_weight "$_ca")" "$(clamp_weight "$_la")" "$(clamp_weight "$_da")"
        printf 'cjkAxes=%s\nlatinAxes=%s\ndigitAxes=%s\n' "$_ca" "$_la" "$_da"
        printf 'appOnly=true\nmultiWeight=true\nmultiWeightSet=300,400,500,600,700\n'
        [ ! -f "$MIX_CONF" ] || grep -v -E '^(cjk|latin|digit|cjkWeight|latinWeight|digitWeight|cjkAxes|latinAxes|digitAxes|appOnly|multiWeight|multiWeightSet)=' "$MIX_CONF" 2>/dev/null
    } >"$_tmp" 2>/dev/null && mv -f "$_tmp" "$MIX_CONF" 2>/dev/null || return 1
    cp -f "$MIX_CONF" "$AXIS_CONF" 2>/dev/null || true
    printf 'mix\n' >"$ACTIVE_CONF" 2>/dev/null || return 1
    chmod 0644 "$MIX_CONF" "$AXIS_CONF" "$ACTIVE_CONF" 2>/dev/null || true
}

worker() {
    _wanted="$1"
    [ "$(read_value "$TASK_FILE" task)" = "$_wanted" ] || exit 0
    _cjk=$(read_value "$TASK_FILE" cjk); _latin=$(read_value "$TASK_FILE" latin); _digit=$(read_value "$TASK_FILE" digit)
    _ca=$(read_value "$TASK_FILE" cjkAxes); _la=$(read_value "$TASK_FILE" latinAxes); _da=$(read_value "$TASK_FILE" digitAxes)
    _root=$(read_value "$TASK_FILE" root)
    mkdir -p "$_root/fonts" "$_root/sources" "$MODDIR/logs" 2>/dev/null || { update_task "$_wanted" failed '无法创建多字重缓存目录' 100 "$(date +%s)"; exit 1; }
    _index=0
    for _entry in $AUTO_SET; do
        _target=${_entry%%:*}; _label=${_entry#*:}
        _percent=$((4 + _index * 15))
        update_task "$_wanted" running "正在生成 ${_target} 字重复合字体" "$_percent" ''
        rm -rf "$_root/sources" 2>/dev/null || true
        mkdir -p "$_root/sources" 2>/dev/null || true
        _cjk_src=$(prepare_source cjk "$_cjk" "$_ca" "$_target" "$_root" cjk) || { update_task "$_wanted" failed "中文 ${_target} 字重准备失败" 100 "$(date +%s)"; rm -rf "$_root"; exit 1; }
        _latin_src=$(prepare_source latin "$_latin" "$_la" "$_target" "$_root" latin) || { update_task "$_wanted" failed "英文 ${_target} 字重准备失败" 100 "$(date +%s)"; rm -rf "$_root"; exit 1; }
        _digit_src=$(prepare_source digit "$_digit" "$_da" "$_target" "$_root" digit) || { update_task "$_wanted" failed "数字 ${_target} 字重准备失败" 100 "$(date +%s)"; rm -rf "$_root"; exit 1; }
        build_composite "$_target" "$_cjk_src" "$_latin_src" "$_digit_src" "$_root/fonts/${PRIVATE_FAMILY}-${_label}.ttf" || { update_task "$_wanted" failed "${_target} 字重复合失败" 100 "$(date +%s)"; rm -rf "$_root"; exit 1; }
        _index=$((_index + 1))
    done
    [ -s "$_root/fonts/${PRIVATE_FAMILY}-Regular.ttf" ] || { update_task "$_wanted" failed '默认常规字重缺失' 100 "$(date +%s)"; rm -rf "$_root"; exit 1; }
    update_task "$_wanted" running '正在原子应用 APP 多字重字体族' 84 ''
    _switch=$(LUOSHU_PRIVATE_LIBRARY=1 LUOSHU_PUBLIC_DIR="$_root" MODDIR="$MODDIR" sh "$FONT_MANAGER" action switch "$PRIVATE_FAMILY" 2>&1)
    if ! printf '%s\n' "$_switch" | grep -q '"status":"ok"'; then
        _message=$(printf '%s\n' "$_switch" | sed -n 's/^.*"message":"\([^"]*\)".*$/\1/p' | tail -n1)
        [ -n "$_message" ] || _message='多字重字体族应用失败'
        update_task "$_wanted" failed "$_message" 100 "$(date +%s)"
        rm -rf "$_root" 2>/dev/null || true
        rm -f "$WORKER_PID" 2>/dev/null || true
        exit 1
    fi
    write_mix_config "$_cjk" "$_latin" "$_digit" "$_ca" "$_la" "$_da" || {
        update_task "$_wanted" failed '多字重字体已生成，但组合状态提交失败' 100 "$(date +%s)"
        rm -rf "$_root" 2>/dev/null || true
        rm -f "$WORKER_PID" 2>/dev/null || true
        exit 1
    }
    [ ! -f "$CONFIG_DIR/recent_fonts.conf" ] || sed -i "/^${PRIVATE_FAMILY}$/d" "$CONFIG_DIR/recent_fonts.conf" 2>/dev/null || true
    update_task "$_wanted" success 'APP 默认多字重已准备，完整重启后生效' 100 "$(date +%s)"
    rm -rf "$_root" 2>/dev/null || true
    rm -f "$WORKER_PID" 2>/dev/null || true
    command -v cmd >/dev/null 2>&1 && cmd notification post -t 洛书 luoshu-app-multiweight 'APP 默认多字重已准备，请完整重启手机。' >/dev/null 2>&1 || true
}

status_json() {
    _wanted="$1"
    [ -s "$TASK_FILE" ] || { printf '{"status":"error","message":"暂无 APP 多字重任务"}\n'; return; }
    _task=$(read_value "$TASK_FILE" task)
    [ -z "$_wanted" ] || [ "$_wanted" = "$_task" ] || { printf '{"status":"error","message":"任务不存在或已被新任务替换"}\n'; return; }
    _state=$(read_value "$TASK_FILE" state); _message=$(read_value "$TASK_FILE" message)
    _cjk=$(read_value "$TASK_FILE" cjk); _latin=$(read_value "$TASK_FILE" latin); _digit=$(read_value "$TASK_FILE" digit)
    _ca=$(read_value "$TASK_FILE" cjkAxes); _la=$(read_value "$TASK_FILE" latinAxes); _da=$(read_value "$TASK_FILE" digitAxes)
    _started=$(read_value "$TASK_FILE" started); _finished=$(read_value "$TASK_FILE" finished); _percent=$(read_value "$TASK_FILE" percent)
    _cauto=false; is_auto "$_ca" && _cauto=true; _lauto=false; is_auto "$_la" && _lauto=true; _dauto=false; is_auto "$_da" && _dauto=true
    printf '{"status":"ok","data":{"task":"%s","state":"%s","message":"%s","cjk":"%s","latin":"%s","digit":"%s","cjkWeight":%s,"latinWeight":%s,"digitWeight":%s,"cjkAuto":%s,"latinAuto":%s,"digitAuto":%s,"multiWeightSet":[300,400,500,600,700],"started":%s,"finished":%s,"progress":{"message":"%s","percent":%s}}}\n' \
        "$(json_escape "$_task")" "$(json_escape "$_state")" "$(json_escape "$_message")" "$(json_escape "$_cjk")" "$(json_escape "$_latin")" "$(json_escape "$_digit")" \
        "$(clamp_weight "$_ca")" "$(clamp_weight "$_la")" "$(clamp_weight "$_da")" "$_cauto" "$_lauto" "$_dauto" "${_started:-0}" "${_finished:-0}" "$(json_escape "$_message")" "${_percent:-0}"
}

config_json() {
    _source="$AXIS_CONF"; [ -s "$_source" ] || _source="$MIX_CONF"
    _cjk=$(read_value "$_source" cjk); _latin=$(read_value "$_source" latin); _digit=$(read_value "$_source" digit)
    _ca=$(read_value "$_source" cjkAxes); _la=$(read_value "$_source" latinAxes); _da=$(read_value "$_source" digitAxes)
    if [ ! -s "$_source" ]; then _ca=auto; _la=auto; _da=auto; fi
    [ -n "$_ca" ] || _ca="wght=$(read_value "$_source" cjkWeight)"
    [ -n "$_la" ] || _la="wght=$(read_value "$_source" latinWeight)"
    [ -n "$_da" ] || _da="wght=$(read_value "$_source" digitWeight)"
    _cauto=false; is_auto "$_ca" && _cauto=true; _lauto=false; is_auto "$_la" && _lauto=true; _dauto=false; is_auto "$_da" && _dauto=true
    _active=$(head -n1 "$ACTIVE_CONF" 2>/dev/null | tr -d '\r\n'); _enabled=false; [ "$_active" = mix ] && _enabled=true
    printf '{"status":"ok","data":{"enabled":%s,"cjk":"%s","latin":"%s","digit":"%s","cjkWeight":%s,"latinWeight":%s,"digitWeight":%s,"cjkAuto":%s,"latinAuto":%s,"digitAuto":%s,"multiWeightSet":[300,400,500,600,700]}}\n' \
        "$_enabled" "$(json_escape "$_cjk")" "$(json_escape "$_latin")" "$(json_escape "$_digit")" "$(clamp_weight "$_ca")" "$(clamp_weight "$_la")" "$(clamp_weight "$_da")" "$_cauto" "$_lauto" "$_dauto"
}

start_mix() {
    _cjk="$1"; _latin="$2"; _digit="$3"; _ca=$(clean_spec "$4"); _la=$(clean_spec "$5"); _da=$(clean_spec "$6")
    [ -n "$_cjk" ] && [ -n "$_latin" ] && [ -n "$_digit" ] || { printf '{"status":"error","message":"请选择中文、英文和数字字体"}\n'; return; }
    [ ! -f "$TEXT_REBOOT_REQUIRED" ] || { printf '{"status":"error","message":"本次开机已更改文字字体，请先重启手机"}\n'; return; }
    if [ -s "$WORKER_PID" ]; then _old=$(cat "$WORKER_PID" 2>/dev/null); [ -z "$_old" ] || ! kill -0 "$_old" 2>/dev/null || { printf '{"status":"error","message":"已有 APP 多字重任务正在运行"}\n'; return; }; fi
    [ ! -e "$LOCK_FILE" ] || { printf '{"status":"error","message":"字体正在切换中"}\n'; return; }
    [ -n "$_ca" ] || _ca=auto; [ -n "$_la" ] || _la=auto; [ -n "$_da" ] || _da=auto
    mkdir -p "$CONFIG_DIR" "$CACHE_ROOT" "$CACHE_FONTS" "$MODDIR/cache/tmp" "$MODDIR/logs" 2>/dev/null || { printf '{"status":"error","message":"无法创建 APP 多字重缓存目录"}\n'; return; }
    _request="appmw-$(date +%s)-$$"; _root="$CACHE_ROOT/$_request"
    mkdir -p "$_root/fonts" "$_root/sources" 2>/dev/null || { printf '{"status":"error","message":"无法创建字体暂存目录"}\n'; return; }
    write_task "$_request" queued 'APP 默认多字重任务已进入后台队列' "$_cjk" "$_latin" "$_digit" "$_ca" "$_la" "$_da" "$_root" "$(date +%s)" '' 1
    ( MODDIR="$MODDIR" sh "$0" worker "$_request" ) </dev/null >>"$LOG_FILE" 2>&1 &
    _pid=$!; printf '%s\n' "$_pid" >"$WORKER_PID" 2>/dev/null || true
    printf '{"status":"ok","data":{"task":"%s"}}\n' "$(json_escape "$_request")"
}

recover_task() {
    if [ -s "$TASK_FILE" ]; then
        _state=$(read_value "$TASK_FILE" state); _task=$(read_value "$TASK_FILE" task); _root=$(read_value "$TASK_FILE" root)
        case "$_state" in queued|running) update_task "$_task" failed '上次 APP 多字重任务被开机恢复中止' 100 "$(date +%s)" ;; esac
        [ -z "$_root" ] || rm -rf "$_root" 2>/dev/null || true
    fi
    rm -f "$WORKER_PID" 2>/dev/null || true
    printf '{"status":"ok"}\n'
}

case "${1:-config}" in
    start) start_mix "$2" "$3" "$4" "${5:-auto}" "${6:-auto}" "${7:-auto}" ;;
    status) status_json "${2:-}" ;;
    config) config_json ;;
    worker) worker "$2" ;;
    recover) recover_task ;;
    *) printf '{"status":"error","message":"未知 APP 多字重命令"}\n' ;;
esac
exit 0
