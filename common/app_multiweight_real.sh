#!/system/bin/sh
# Stable App-only real-weight composite engine.
set +e

MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"; else MODDIR=/data/adb/modules/LuoShu; fi
fi
MODULE_DIR="$MODDIR"
CONFIG_DIR="$MODDIR/config"
CACHE_ROOT="$MODDIR/cache/app-multiweight"
FONT_MANAGER="$MODDIR/common/font_manager.sh"
INSTANCE_PY="$MODDIR/common/font_instance.py"
REWRITE_PY="$MODDIR/common/font_family_rewrite.py"
COMPOSITE_RUNNER="$MODDIR/common/luoshu_composite.sh"
PYROOT="$MODDIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"
TASK_FILE="$CONFIG_DIR/app_multiweight_task.conf"
APP_MODE_CONF="$CONFIG_DIR/app_weight_mode.conf"
MIX_CONF="$CONFIG_DIR/font_mix.conf"
AXIS_CONF="$CONFIG_DIR/v143_axes_mix.conf"
ACTIVE_CONF="$CONFIG_DIR/active_font.conf"
TEXT_REBOOT_REQUIRED="$CONFIG_DIR/text_reboot_required.conf"
WORKER_PID="$CONFIG_DIR/app_multiweight_worker.pid"
LOCK_FILE="$MODDIR/.font_switch.lock"
LOG_FILE="$MODDIR/logs/fontswitch.log"
PRIVATE_FAMILY=LuoShuAppMix
LUOSHU_PUBLIC_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}"
USER_FONTS_DIR="$LUOSHU_PUBLIC_DIR/fonts"

[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/font_check.sh" ] && . "$MODDIR/common/font_check.sh"

json_escape() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '; }
read_value() { sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'; }
is_auto() { [ "$1" = auto ]; }
axis_value() {
    _value=$(printf '%s' "$1" | tr ',' '\n' | sed -n "s/^${2}=//p" | head -n1)
    case "$_value" in ''|*[!0-9.-]*) _value="$3" ;; esac
    printf '%s\n' "$_value"
}
manual_weight() {
    _w=$(axis_value "$1" wght 400); _w=${_w%%.*}; case "$_w" in ''|*[!0-9]*) _w=400 ;; esac
    [ "$_w" -ge 1 ] 2>/dev/null || _w=1; [ "$_w" -le 1000 ] 2>/dev/null || _w=1000
    printf '%s\n' "$_w"
}
spec_weight() { if is_auto "$1"; then echo 400; else manual_weight "$1"; fi; }
weight_role() {
    _n="$1"
    if [ "$_n" -le 149 ] 2>/dev/null; then echo Thin
    elif [ "$_n" -le 249 ] 2>/dev/null; then echo ExtraLight
    elif [ "$_n" -le 349 ] 2>/dev/null; then echo Light
    elif [ "$_n" -le 449 ] 2>/dev/null; then echo Regular
    elif [ "$_n" -le 549 ] 2>/dev/null; then echo Medium
    elif [ "$_n" -le 649 ] 2>/dev/null; then echo SemiBold
    elif [ "$_n" -le 749 ] 2>/dev/null; then echo Bold
    elif [ "$_n" -le 849 ] 2>/dev/null; then echo ExtraBold
    else echo Black; fi
}
json_weight_array() {
    _set="$1"; [ -n "$_set" ] || _set=400
    printf '[%s]' "$(printf '%s' "$_set" | sed 's/,/,/g')"
}

write_task() {
    _tmp="$TASK_FILE.tmp.$$"
    {
        printf 'task=%s\nstate=%s\nmessage=%s\n' "$1" "$2" "$3"
        printf 'cjk=%s\nlatin=%s\ndigit=%s\n' "$4" "$5" "$6"
        printf 'cjkAxes=%s\nlatinAxes=%s\ndigitAxes=%s\n' "$7" "$8" "$9"
        shift 9
        printf 'root=%s\nstarted=%s\nfinished=%s\npercent=%s\nweightSet=%s\n' "$1" "$2" "$3" "$4" "$5"
    } >"$_tmp" 2>/dev/null && mv -f "$_tmp" "$TASK_FILE"
    chmod 0644 "$TASK_FILE" 2>/dev/null || true
}
update_task() {
    _wanted="$1"; _state="$2"; _message="$3"; _percent="$4"; _finished="$5"; _set="$6"
    [ "$(read_value "$TASK_FILE" task)" = "$_wanted" ] || return 1
    [ -n "$_finished" ] || _finished=$(read_value "$TASK_FILE" finished)
    [ -n "$_set" ] || _set=$(read_value "$TASK_FILE" weightSet)
    write_task "$_wanted" "$_state" "$_message" \
        "$(read_value "$TASK_FILE" cjk)" "$(read_value "$TASK_FILE" latin)" "$(read_value "$TASK_FILE" digit)" \
        "$(read_value "$TASK_FILE" cjkAxes)" "$(read_value "$TASK_FILE" latinAxes)" "$(read_value "$TASK_FILE" digitAxes)" \
        "$(read_value "$TASK_FILE" root)" "$(read_value "$TASK_FILE" started)" "$_finished" "$_percent" "$_set"
}

append_weights() {
    _current="$1"; _incoming="$2"; _oldifs="$IFS"; IFS=','
    for _n in $_incoming; do
        case "$_n" in ''|*[!0-9]*) continue ;; esac
        case ",$_current," in *,$_n,*) ;; *) _current="${_current:+$_current,}$_n" ;; esac
    done
    IFS="$_oldifs"; printf '%s\n' "$_current"
}
slot_weights() { if is_auto "$2"; then family_weight_numbers "$1"; else manual_weight "$2"; fi; }
resolve_weight_set() {
    _set=""
    _set=$(append_weights "$_set" "$(slot_weights "$1" "$4")")
    _set=$(append_weights "$_set" "$(slot_weights "$2" "$5")")
    _set=$(append_weights "$_set" "$(slot_weights "$3" "$6")")
    [ -n "$_set" ] || _set=400
    printf '%s\n' "$_set" | tr ',' '\n' | sort -n -u | paste -sd, -
}

run_instance() {
    _src="$1"; _dest="$2"; _role="$3"; _weight="$4"; _axes="$5"
    PYTHONHOME="$PYROOT" PYTHONPATH="$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$PYBIN" "$INSTANCE_PY" --input "$_src" --output "$_dest" --role "$_role" --weight "$_weight" --axes "$_axes" \
        >"${_dest}.json" 2>"${_dest}.err"
    _rc=$?; [ "$_rc" -eq 0 ] && [ -s "$_dest" ]
}
prepare_source() {
    _role="$1"; _family="$2"; _spec="$3"; _target="$4"; _root="$5"; _label="$6"
    if is_auto "$_spec"; then _requested="$_target"; _axes="wght=$_target"; else _requested=$(manual_weight "$_spec"); _axes="$_spec"; fi
    _src=$(family_file_for_weight "$_family" "$_requested")
    [ -f "$_src" ] || { echo "找不到字体族 $_family" >&2; return 1; }
    font_validate "$_src" text || { echo "字体 $_family 无效：$FONT_CHECK_ERROR" >&2; return 1; }
    _dest="$_root/sources/${_label}-${_target}.ttf"; mkdir -p "${_dest%/*}" 2>/dev/null || return 1
    if font_file_is_variable "$_src" || [ "$FONT_CHECK_FORMAT" = TTC ]; then
        run_instance "$_src" "$_dest" "$_role" "$_requested" "$_axes" || return 1
    else
        cp -f "$_src" "$_dest" 2>/dev/null || return 1
    fi
    chmod 0644 "$_dest" 2>/dev/null || true; [ -s "$_dest" ] || return 1
    printf '%s\n' "$_dest"
}

build_composite() {
    _target="$1"; _cjk="$2"; _latin="$3"; _digit="$4"; _output="$5"
    _raw="${_output}.raw.ttf"; _report="${_output}.json"; _err="${_output}.err"
    rm -f "$_raw" "$_output" "$_report" "$_err" 2>/dev/null || true
    if command -v timeout >/dev/null 2>&1; then
        MODDIR="$MODDIR" timeout 480 sh "$COMPOSITE_RUNNER" --cjk "$_cjk" --latin "$_latin" --digit "$_digit" --weight "$_target" --output "$_raw" >"$_report" 2>"$_err"
    else
        MODDIR="$MODDIR" sh "$COMPOSITE_RUNNER" --cjk "$_cjk" --latin "$_latin" --digit "$_digit" --weight "$_target" --output "$_raw" >"$_report" 2>"$_err"
    fi
    _rc=$?; [ "$_rc" -eq 0 ] && [ -s "$_raw" ] || return 1
    PYTHONHOME="$PYROOT" PYTHONPATH="$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        "$PYBIN" "$REWRITE_PY" "$_raw" "$_output" --family "$PRIVATE_FAMILY" --weight "$_target" >>"$_report" 2>>"$_err" || return 1
    rm -f "$_raw" 2>/dev/null || true
    font_validate_global "$_output" || return 1
    chmod 0644 "$_output" 2>/dev/null || true
}

write_mix_config() {
    _cjk="$1"; _latin="$2"; _digit="$3"; _ca="$4"; _la="$5"; _da="$6"; _set="$7"
    _tmp="$MIX_CONF.appmw.$$"
    {
        printf 'cjk=%s\nlatin=%s\ndigit=%s\n' "$_cjk" "$_latin" "$_digit"
        printf 'cjkWeight=%s\nlatinWeight=%s\ndigitWeight=%s\n' "$(spec_weight "$_ca")" "$(spec_weight "$_la")" "$(spec_weight "$_da")"
        printf 'cjkAxes=%s\nlatinAxes=%s\ndigitAxes=%s\n' "$_ca" "$_la" "$_da"
        printf 'appOnly=true\nmultiWeight=true\nmultiWeightSet=%s\n' "$_set"
        [ ! -f "$MIX_CONF" ] || grep -v -E '^(cjk|latin|digit|cjkWeight|latinWeight|digitWeight|cjkAxes|latinAxes|digitAxes|appOnly|multiWeight|multiWeightSet)=' "$MIX_CONF" 2>/dev/null
    } >"$_tmp" 2>/dev/null && mv -f "$_tmp" "$MIX_CONF" || return 1
    _cauto=false; is_auto "$_ca" && _cauto=true; _lauto=false; is_auto "$_la" && _lauto=true; _dauto=false; is_auto "$_da" && _dauto=true
    _mode_tmp="$APP_MODE_CONF.tmp.$$"
    printf 'cjkAuto=%s\nlatinAuto=%s\ndigitAuto=%s\n' "$_cauto" "$_lauto" "$_dauto" >"$_mode_tmp" && mv -f "$_mode_tmp" "$APP_MODE_CONF"
    cp -f "$MIX_CONF" "$AXIS_CONF" 2>/dev/null || true; printf 'mix\n' >"$ACTIVE_CONF"
    chmod 0644 "$MIX_CONF" "$AXIS_CONF" "$APP_MODE_CONF" "$ACTIVE_CONF" 2>/dev/null || true
}

worker() {
    _wanted="$1"; [ "$(read_value "$TASK_FILE" task)" = "$_wanted" ] || exit 0
    _cjk=$(read_value "$TASK_FILE" cjk); _latin=$(read_value "$TASK_FILE" latin); _digit=$(read_value "$TASK_FILE" digit)
    _ca=$(read_value "$TASK_FILE" cjkAxes); _la=$(read_value "$TASK_FILE" latinAxes); _da=$(read_value "$TASK_FILE" digitAxes); _root=$(read_value "$TASK_FILE" root)
    _set=$(resolve_weight_set "$_cjk" "$_latin" "$_digit" "$_ca" "$_la" "$_da")
    update_task "$_wanted" running "已识别字体自身字重：$_set" 3 '' "$_set"
    _count=$(printf '%s' "$_set" | tr ',' '\n' | grep -c .); [ "$_count" -gt 0 ] 2>/dev/null || _count=1
    _index=0; _oldifs="$IFS"; IFS=','
    for _target in $_set; do
        IFS="$_oldifs"; _index=$((_index + 1)); _percent=$((5 + (_index - 1) * 72 / _count))
        update_task "$_wanted" running "正在生成字体自身的 ${_target} 字重" "$_percent" '' "$_set"
        rm -rf "$_root/sources" 2>/dev/null || true; mkdir -p "$_root/sources" "$_root/fonts" 2>/dev/null || true
        _cjk_src=$(prepare_source cjk "$_cjk" "$_ca" "$_target" "$_root" cjk) || { update_task "$_wanted" failed "中文 ${_target} 字重准备失败" 100 "$(date +%s)" "$_set"; exit 1; }
        _latin_src=$(prepare_source latin "$_latin" "$_la" "$_target" "$_root" latin) || { update_task "$_wanted" failed "英文 ${_target} 字重准备失败" 100 "$(date +%s)" "$_set"; exit 1; }
        _digit_src=$(prepare_source digit "$_digit" "$_da" "$_target" "$_root" digit) || { update_task "$_wanted" failed "数字 ${_target} 字重准备失败" 100 "$(date +%s)" "$_set"; exit 1; }
        _role=$(weight_role "$_target")
        build_composite "$_target" "$_cjk_src" "$_latin_src" "$_digit_src" "$_root/fonts/${PRIVATE_FAMILY}-${_role}-${_target}.ttf" || { update_task "$_wanted" failed "${_target} 字重复合失败" 100 "$(date +%s)" "$_set"; exit 1; }
        IFS=','
    done
    IFS="$_oldifs"
    _default=$(find "$_root/fonts" -maxdepth 1 -type f -name '*.ttf' 2>/dev/null | head -n1)
    [ -s "$_default" ] || { update_task "$_wanted" failed '没有生成可用字体' 100 "$(date +%s)" "$_set"; exit 1; }
    update_task "$_wanted" running '正在应用真实字重字体族' 86 '' "$_set"
    _switch=$(LUOSHU_PRIVATE_LIBRARY=1 LUOSHU_PUBLIC_DIR="$_root" MODDIR="$MODDIR" sh "$FONT_MANAGER" action switch "$PRIVATE_FAMILY" 2>&1)
    if ! printf '%s\n' "$_switch" | grep -q '"status":"ok"'; then
        _message=$(printf '%s\n' "$_switch" | sed -n 's/^.*"message":"\([^"]*\)".*$/\1/p' | tail -n1); [ -n "$_message" ] || _message='真实字重字体族应用失败'
        update_task "$_wanted" failed "$_message" 100 "$(date +%s)" "$_set"; exit 1
    fi
    write_mix_config "$_cjk" "$_latin" "$_digit" "$_ca" "$_la" "$_da" "$_set" || { update_task "$_wanted" failed '字体已生成，但状态提交失败' 100 "$(date +%s)" "$_set"; exit 1; }
    update_task "$_wanted" success "已按字体自身字重生成：$_set；完整重启后生效" 100 "$(date +%s)" "$_set"
    rm -rf "$_root" 2>/dev/null || true; rm -f "$WORKER_PID" 2>/dev/null || true
}

status_json() {
    _wanted="$1"; [ -s "$TASK_FILE" ] || { printf '{"status":"error","message":"暂无 APP 多字重任务"}\n'; return; }
    _task=$(read_value "$TASK_FILE" task); [ -z "$_wanted" ] || [ "$_wanted" = "$_task" ] || { printf '{"status":"error","message":"任务不存在或已被替换"}\n'; return; }
    _state=$(read_value "$TASK_FILE" state); _message=$(read_value "$TASK_FILE" message); _set=$(read_value "$TASK_FILE" weightSet); [ -n "$_set" ] || _set=400
    _ca=$(read_value "$TASK_FILE" cjkAxes); _la=$(read_value "$TASK_FILE" latinAxes); _da=$(read_value "$TASK_FILE" digitAxes)
    _cauto=false; is_auto "$_ca" && _cauto=true; _lauto=false; is_auto "$_la" && _lauto=true; _dauto=false; is_auto "$_da" && _dauto=true
    printf '{"status":"ok","data":{"task":"%s","state":"%s","message":"%s","cjk":"%s","latin":"%s","digit":"%s","cjkWeight":%s,"latinWeight":%s,"digitWeight":%s,"cjkAuto":%s,"latinAuto":%s,"digitAuto":%s,"multiWeightSet":%s,"started":%s,"finished":%s,"progress":{"message":"%s","percent":%s}}}\n' \
        "$(json_escape "$_task")" "$(json_escape "$_state")" "$(json_escape "$_message")" \
        "$(json_escape "$(read_value "$TASK_FILE" cjk)")" "$(json_escape "$(read_value "$TASK_FILE" latin)")" "$(json_escape "$(read_value "$TASK_FILE" digit)")" \
        "$(spec_weight "$_ca")" "$(spec_weight "$_la")" "$(spec_weight "$_da")" "$_cauto" "$_lauto" "$_dauto" "$(json_weight_array "$_set")" \
        "$(read_value "$TASK_FILE" started)" "$(read_value "$TASK_FILE" finished)" "$(json_escape "$_message")" "$(read_value "$TASK_FILE" percent)"
}
config_json() {
    _source="$AXIS_CONF"; [ -s "$_source" ] || _source="$MIX_CONF"
    _cjk=$(read_value "$_source" cjk); _latin=$(read_value "$_source" latin); _digit=$(read_value "$_source" digit)
    _ca=$(read_value "$_source" cjkAxes); _la=$(read_value "$_source" latinAxes); _da=$(read_value "$_source" digitAxes)
    [ -n "$_ca" ] || _ca=auto; [ -n "$_la" ] || _la=auto; [ -n "$_da" ] || _da=auto
    _set=$(read_value "$_source" multiWeightSet); [ -n "$_set" ] || _set=400
    _cauto=false; is_auto "$_ca" && _cauto=true; _lauto=false; is_auto "$_la" && _lauto=true; _dauto=false; is_auto "$_da" && _dauto=true
    _active=$(head -n1 "$ACTIVE_CONF" 2>/dev/null | tr -d '\r\n'); _enabled=false; [ "$_active" = mix ] && _enabled=true
    printf '{"status":"ok","data":{"enabled":%s,"cjk":"%s","latin":"%s","digit":"%s","cjkWeight":%s,"latinWeight":%s,"digitWeight":%s,"cjkAuto":%s,"latinAuto":%s,"digitAuto":%s,"multiWeightSet":%s}}\n' \
        "$_enabled" "$(json_escape "$_cjk")" "$(json_escape "$_latin")" "$(json_escape "$_digit")" \
        "$(spec_weight "$_ca")" "$(spec_weight "$_la")" "$(spec_weight "$_da")" "$_cauto" "$_lauto" "$_dauto" "$(json_weight_array "$_set")"
}
start_mix() {
    _cjk="$1"; _latin="$2"; _digit="$3"; _ca="$4"; _la="$5"; _da="$6"
    [ -n "$_cjk" ] && [ -n "$_latin" ] && [ -n "$_digit" ] || { printf '{"status":"error","message":"请选择中文、英文和数字字体"}\n'; return; }
    [ ! -f "$TEXT_REBOOT_REQUIRED" ] || { printf '{"status":"error","message":"本次开机已更改文字字体，请先重启手机"}\n'; return; }
    if [ -s "$WORKER_PID" ]; then _old=$(cat "$WORKER_PID" 2>/dev/null); [ -z "$_old" ] || ! kill -0 "$_old" 2>/dev/null || { printf '{"status":"error","message":"已有任务正在运行"}\n'; return; }; fi
    [ ! -e "$LOCK_FILE" ] || { printf '{"status":"error","message":"字体正在切换中"}\n'; return; }
    [ -n "$_ca" ] || _ca=auto; [ -n "$_la" ] || _la=auto; [ -n "$_da" ] || _da=auto
    _request="appmw-$(date +%s)-$$"; _root="$CACHE_ROOT/$_request"
    mkdir -p "$_root/fonts" "$_root/sources" "$CONFIG_DIR" "$MODDIR/logs" 2>/dev/null || { printf '{"status":"error","message":"无法创建任务目录"}\n'; return; }
    write_task "$_request" queued '正在识别字体自身字重' "$_cjk" "$_latin" "$_digit" "$_ca" "$_la" "$_da" "$_root" "$(date +%s)" 0 1 ''
    ( MODDIR="$MODDIR" sh "$0" worker "$_request" ) </dev/null >>"$LOG_FILE" 2>&1 &
    printf '%s\n' "$!" >"$WORKER_PID" 2>/dev/null || true
    printf '{"status":"ok","data":{"task":"%s"}}\n' "$(json_escape "$_request")"
}
recover_task() {
    if [ -s "$TASK_FILE" ]; then
        _state=$(read_value "$TASK_FILE" state); _task=$(read_value "$TASK_FILE" task)
        case "$_state" in queued|running) update_task "$_task" failed '上次任务被开机恢复中止' 100 "$(date +%s)" '' ;; esac
    fi
    rm -f "$WORKER_PID" 2>/dev/null || true; printf '{"status":"ok"}\n'
}

case "${1:-config}" in
    start) start_mix "$2" "$3" "$4" "${5:-auto}" "${6:-auto}" "${7:-auto}" ;;
    worker) worker "$2" ;;
    status) status_json "$2" ;;
    recover) recover_task ;;
    config) config_json ;;
    *) printf '{"status":"error","message":"未知 APP 多字重命令"}\n' ;;
esac
