#!/system/bin/sh
# 洛书 v14.3.9：组合页自动多字重复合引擎。
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
CACHE_ROOT="$MODDIR/cache/auto-multiweight-mix"
COMPOSITE_CACHE="$CACHE_ROOT/composites-v1"
PUBLIC_ROOT="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}"
SOURCE_FONTS="$PUBLIC_ROOT/fonts"
USER_FONTS_DIR="$SOURCE_FONTS"
FONT_MANAGER="$MODDIR/common/font_manager.sh"
FALLBACK_ENGINE="$MODDIR/common/v142_weighted_mix.sh"
MODE_HELPER="$MODDIR/common/mix_weight_mode.sh"
ROLE_CHECK="$MODDIR/common/font_role_check.sh"
INSTANCE_PY="$MODDIR/common/font_instance.py"
COMPOSITE_RUNNER="$MODDIR/common/luoshu_composite.sh"
PYROOT="$MODDIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"
TASK_FILE="$CONFIG_DIR/axes_task.conf"
MIX_CONF="$CONFIG_DIR/font_mix.conf"
AXES_CONF="$CONFIG_DIR/axes_mix.conf"
ACTIVE_CONF="$CONFIG_DIR/active_font.conf"
REBOOT_CONF="$CONFIG_DIR/text_reboot_required.conf"
WORKER_PID="$CONFIG_DIR/auto_multiweight_worker.pid"
LOG_FILE="$MODDIR/logs/fontswitch.log"
LOCK_FILE="$MODDIR/.font_switch.lock"

[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/font_check.sh" ] && . "$MODDIR/common/font_check.sh"
[ -f "$MODE_HELPER" ] && . "$MODE_HELPER"

json_escape() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '; }
read_value() { sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'; }
clean_spec() { printf '%s' "$1" | tr -d '\r\n'; }
normalize_mode() { case "$1" in auto) printf 'auto\n' ;; *) printf 'fixed\n' ;; esac; }

resolve_mode() {
    _requested="$1"
    _family="$2"
    _axes="$3"
    case "$_requested" in
        auto|fixed) printf '%s\n' "$_requested" ;;
        *)
            if type infer_mix_weight_mode >/dev/null 2>&1; then
                infer_mix_weight_mode "$_family" "$_axes"
            else
                printf 'fixed\n'
            fi
            ;;
    esac
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

with_weight() {
    _spec="$1"
    _weight="$2"
    _out=''
    _found=false
    _old_ifs="$IFS"
    IFS=','
    for _entry in $_spec; do
        case "$_entry" in
            wght=*) _entry="wght=$_weight"; _found=true ;;
        esac
        [ -n "$_entry" ] || continue
        [ -z "$_out" ] || _out="$_out,"
        _out="$_out$_entry"
    done
    IFS="$_old_ifs"
    [ "$_found" = true ] || {
        [ -z "$_out" ] || _out="$_out,"
        _out="${_out}wght=$_weight"
    }
    printf '%s' "$_out"
}

role_weight() {
    case "$1" in
        thin) echo 100 ;; extralight) echo 200 ;; light) echo 300 ;; regular|normal) echo 400 ;;
        medium) echo 500 ;; semibold) echo 600 ;; bold) echo 700 ;; extrabold) echo 800 ;;
        black|heavy) echo 900 ;; variable) echo "$2" ;; *) echo 400 ;;
    esac
}

weight_role() {
    case "$1" in
        100) echo Thin ;; 200) echo ExtraLight ;; 300) echo Light ;; 500) echo Medium ;;
        600) echo SemiBold ;; 700) echo Bold ;; 800) echo ExtraBold ;; 900) echo Black ;;
        *) echo Regular ;;
    esac
}

write_task() {
    _tmp="$TASK_FILE.tmp.$$"
    {
        printf 'task=%s\nstate=%s\nmessage=%s\n' "$1" "$2" "$3"
        printf 'cjk=%s\nlatin=%s\ndigit=%s\n' "$4" "$5" "$6"
        printf 'cjkAxes=%s\nlatinAxes=%s\ndigitAxes=%s\n' "$7" "$8" "$9"
        shift 9
        printf 'cjkMode=%s\nlatinMode=%s\ndigitMode=%s\n' "$1" "$2" "$3"
        printf 'root=%s\nchildTask=%s\nstarted=%s\nfinished=%s\npercent=%s\n' "$4" "$5" "$6" "$7" "$8"
    } >"$_tmp" 2>/dev/null && mv -f "$_tmp" "$TASK_FILE" 2>/dev/null
    chmod 0644 "$TASK_FILE" 2>/dev/null || true
}

update_task() {
    _wanted="$1"
    _state="$2"
    _message="$3"
    _percent="$4"
    _finished="$5"
    [ "$(read_value "$TASK_FILE" task)" = "$_wanted" ] || return 1
    write_task "$_wanted" "$_state" "$_message" \
        "$(read_value "$TASK_FILE" cjk)" "$(read_value "$TASK_FILE" latin)" "$(read_value "$TASK_FILE" digit)" \
        "$(read_value "$TASK_FILE" cjkAxes)" "$(read_value "$TASK_FILE" latinAxes)" "$(read_value "$TASK_FILE" digitAxes)" \
        "$(read_value "$TASK_FILE" cjkMode)" "$(read_value "$TASK_FILE" latinMode)" "$(read_value "$TASK_FILE" digitMode)" \
        "$(read_value "$TASK_FILE" root)" '' "$(read_value "$TASK_FILE" started)" "$_finished" "$_percent"
}

find_best_source() {
    _family="$1"
    _target="$2"
    _best=''
    _best_score=99999
    _variable=''
    for _font in "$SOURCE_FONTS"/*.ttf "$SOURCE_FONTS"/*.otf "$SOURCE_FONTS"/*.ttc \
                 "$SOURCE_FONTS"/*.TTF "$SOURCE_FONTS"/*.OTF "$SOURCE_FONTS"/*.TTC; do
        [ -f "$_font" ] || continue
        [ "$(detect_font_family "$(basename "$_font")")" = "$_family" ] || continue
        if is_variable_font "$_font" 2>/dev/null; then
            [ -n "$_variable" ] || _variable="$_font"
            continue
        fi
        _number=$(role_weight "$(detect_font_weight "$(basename "$_font")")" "$_target")
        _score=$((_number - _target))
        [ "$_score" -ge 0 ] 2>/dev/null || _score=$((-_score))
        if [ -z "$_best" ] || [ "$_score" -lt "$_best_score" ] 2>/dev/null; then
            _best="$_font"
            _best_score="$_score"
        fi
    done
    if [ -n "$_variable" ]; then
        printf '%s\n' "$_variable"
    elif [ -n "$_best" ]; then
        printf '%s\n' "$_best"
    else
        return 1
    fi
}

run_instance() {
    _source="$1"
    _destination="$2"
    _role="$3"
    _axes="$4"
    _weight=$(safe_weight "$_axes")
    mkdir -p "${_destination%/*}" "$MODDIR/cache/tmp" 2>/dev/null || return 1
    PYTHONHOME="$PYROOT" \
    PYTHONPATH="$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages" \
    LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    TMPDIR="$MODDIR/cache/tmp" \
        "$PYBIN" "$INSTANCE_PY" --input "$_source" --output "$_destination" \
        --role "$_role" --weight "$_weight" --axes "$_axes" >/dev/null 2>"${_destination}.err"
    _code=$?
    [ "$_code" -eq 0 ] && [ -s "$_destination" ] || return 1
    rm -f "${_destination}.err" 2>/dev/null || true
    chmod 0644 "$_destination" 2>/dev/null || true
}

prepare_source() {
    _role="$1"
    _family="$2"
    _axes="$3"
    _mode="$4"
    _target="$5"
    _destination="$6"
    _effective="$_axes"
    [ "$_mode" != auto ] || _effective=$(with_weight "$_axes" "$_target")
    _lookup=$(safe_weight "$_effective")
    _source=$(find_best_source "$_family" "$_lookup")
    [ -f "$_source" ] || return 1
    font_validate "$_source" text || return 1
    if [ "$FONT_CHECK_VARIABLE" = true ] || [ "$FONT_CHECK_FORMAT" = TTC ]; then
        run_instance "$_source" "$_destination" "$_role" "$_effective"
    else
        mkdir -p "${_destination%/*}" 2>/dev/null || return 1
        cp -f "$_source" "$_destination" 2>/dev/null || return 1
        chmod 0644 "$_destination" 2>/dev/null || true
    fi
}

hash_file() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" 2>/dev/null | awk '{print $1}'
    elif command -v toybox >/dev/null 2>&1; then
        toybox sha256sum "$1" 2>/dev/null | awk '{print $1}'
    else
        cksum "$1" 2>/dev/null | awk '{print $1 "-" $2}'
    fi
}

hash_text() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum | awk '{print $1}'
    elif command -v toybox >/dev/null 2>&1; then
        toybox sha256sum | awk '{print $1}'
    else
        cksum | awk '{print $1 "-" $2}'
    fi
}

link_or_copy() {
    rm -f "$2" 2>/dev/null || true
    ln "$1" "$2" 2>/dev/null || cp -f "$1" "$2" 2>/dev/null
}

prune_composite_cache() {
    _count=0
    for _old in $(ls -1t "$COMPOSITE_CACHE"/*.font 2>/dev/null); do
        _count=$((_count + 1))
        [ "$_count" -le 24 ] && continue
        rm -f "$_old" "${_old}.json" 2>/dev/null || true
    done
}

build_composite_cached() {
    _cjk="$1"
    _latin="$2"
    _digit="$3"
    _output="$4"
    _progress="$5"
    mkdir -p "$COMPOSITE_CACHE" "${_output%/*}" 2>/dev/null || return 1
    _key=$(printf '%s|%s|%s|auto-multiweight-v1' \
        "$(hash_file "$_cjk")" "$(hash_file "$_latin")" "$(hash_file "$_digit")" | hash_text)
    [ -n "$_key" ] || return 1
    _cached="$COMPOSITE_CACHE/${_key}.font"
    if [ -s "$_cached" ]; then
        link_or_copy "$_cached" "$_output" || return 1
        chmod 0644 "$_output" 2>/dev/null || true
        return 0
    fi
    _tmp="$COMPOSITE_CACHE/.${_key}.$$.tmp.font"
    _tmp_report="${_tmp}.json"
    _tmp_error="${_tmp}.err"
    rm -f "$_tmp" "$_tmp_report" "$_tmp_error" 2>/dev/null || true
    MODDIR="$MODDIR" sh "$COMPOSITE_RUNNER" --cjk "$_cjk" --latin "$_latin" --digit "$_digit" \
        --output "$_tmp" --progress "$_progress" >"$_tmp_report" 2>"$_tmp_error"
    _code=$?
    [ "$_code" -eq 0 ] && [ -s "$_tmp" ] || {
        [ ! -s "$_tmp_error" ] || cat "$_tmp_error" >>"$LOG_FILE" 2>/dev/null || true
        rm -f "$_tmp" "$_tmp_report" "$_tmp_error" 2>/dev/null || true
        return 1
    }
    font_validate "$_tmp" text || {
        rm -f "$_tmp" "$_tmp_report" "$_tmp_error" 2>/dev/null || true
        return 1
    }
    chmod 0644 "$_tmp" "$_tmp_report" 2>/dev/null || true
    mv -f "$_tmp" "$_cached" 2>/dev/null || return 1
    mv -f "$_tmp_report" "${_cached}.json" 2>/dev/null || true
    rm -f "$_tmp_error" 2>/dev/null || true
    link_or_copy "$_cached" "$_output" || return 1
    chmod 0644 "$_output" 2>/dev/null || true
    prune_composite_cache
}

save_mix_config() {
    _tmp="$MIX_CONF.auto.$$"
    {
        printf 'cjk=%s\nlatin=%s\ndigit=%s\n' "$1" "$2" "$3"
        printf 'cjkWeight=%s\nlatinWeight=%s\ndigitWeight=%s\n' "$(safe_weight "$4")" "$(safe_weight "$5")" "$(safe_weight "$6")"
        printf 'cjkAxes=%s\nlatinAxes=%s\ndigitAxes=%s\n' "$4" "$5" "$6"
        printf 'cjkMode=%s\nlatinMode=%s\ndigitMode=%s\n' "$7" "$8" "$9"
        printf 'isolation=auto-multiweight-v1\ncharacterIsolation=true\ncomposite=true\nxmlOverlay=false\ntime=%s\n' "$(date +%s)"
    } >"$_tmp" 2>/dev/null && mv -f "$_tmp" "$MIX_CONF" 2>/dev/null || return 1
    cp -f "$MIX_CONF" "$AXES_CONF" 2>/dev/null || true
    printf 'mix\n' >"$ACTIVE_CONF" 2>/dev/null || return 1
    printf 'font=mix\ntime=%s\n' "$(date +%s)" >"$REBOOT_CONF" 2>/dev/null || return 1
    sed -i '/^LuoShuAutoMix$/d' "$CONFIG_DIR/recent_fonts.conf" 2>/dev/null || true
    chmod 0644 "$MIX_CONF" "$AXES_CONF" "$ACTIVE_CONF" "$REBOOT_CONF" 2>/dev/null || true
}

worker() {
    _wanted="$1"
    [ "$(read_value "$TASK_FILE" task)" = "$_wanted" ] || exit 0
    _cjk=$(read_value "$TASK_FILE" cjk)
    _latin=$(read_value "$TASK_FILE" latin)
    _digit=$(read_value "$TASK_FILE" digit)
    _cjk_axes=$(read_value "$TASK_FILE" cjkAxes)
    _latin_axes=$(read_value "$TASK_FILE" latinAxes)
    _digit_axes=$(read_value "$TASK_FILE" digitAxes)
    _cjk_mode=$(normalize_mode "$(read_value "$TASK_FILE" cjkMode)")
    _latin_mode=$(normalize_mode "$(read_value "$TASK_FILE" latinMode)")
    _digit_mode=$(normalize_mode "$(read_value "$TASK_FILE" digitMode)")
    _root=$(read_value "$TASK_FILE" root)
    _family=LuoShuAutoMix
    mkdir -p "$_root/fonts" "$_root/prepared" 2>/dev/null || {
        update_task "$_wanted" failed '无法创建自动多字重缓存' 100 "$(date +%s)"
        exit 1
    }

    _index=0
    for _weight in 100 200 300 400 500 600 700 800 900; do
        _index=$((_index + 1))
        _percent=$((4 + _index * 8))
        _role=$(weight_role "$_weight")
        update_task "$_wanted" running "正在生成 ${_weight} 字重复合字体" "$_percent" ''
        _dir="$_root/prepared/$_weight"
        mkdir -p "$_dir" 2>/dev/null || exit 1
        prepare_source cjk "$_cjk" "$_cjk_axes" "$_cjk_mode" "$_weight" "$_dir/cjk.ttf" || {
            update_task "$_wanted" failed "中文字体 ${_weight} 字重准备失败" 100 "$(date +%s)"
            rm -rf "$_root"; rm -f "$WORKER_PID"; exit 1
        }
        prepare_source latin "$_latin" "$_latin_axes" "$_latin_mode" "$_weight" "$_dir/latin.ttf" || {
            update_task "$_wanted" failed "英文字体 ${_weight} 字重准备失败" 100 "$(date +%s)"
            rm -rf "$_root"; rm -f "$WORKER_PID"; exit 1
        }
        prepare_source digit "$_digit" "$_digit_axes" "$_digit_mode" "$_weight" "$_dir/digit.ttf" || {
            update_task "$_wanted" failed "数字字体 ${_weight} 字重准备失败" 100 "$(date +%s)"
            rm -rf "$_root"; rm -f "$WORKER_PID"; exit 1
        }
        if [ "$_weight" = 400 ]; then
            _output="$_root/fonts/${_family}-Regular.ttf"
        else
            _output="$_root/fonts/${_family}-${_role}.otf"
        fi
        build_composite_cached "$_dir/cjk.ttf" "$_dir/latin.ttf" "$_dir/digit.ttf" "$_output" "$_dir/progress.json" || {
            update_task "$_wanted" failed "${_weight} 字重复合失败" 100 "$(date +%s)"
            rm -rf "$_root"; rm -f "$WORKER_PID"; exit 1
        }
        rm -rf "$_dir" 2>/dev/null || true
    done

    update_task "$_wanted" running '正在应用自动多字重字体族' 88 ''
    _result=$(LUOSHU_PUBLIC_DIR="$_root" MODDIR="$MODDIR" sh "$FONT_MANAGER" action switch "$_family" 2>&1)
    printf '%s\n' "$_result" >>"$LOG_FILE" 2>/dev/null || true
    printf '%s\n' "$_result" | grep -q '"status":"ok"' || {
        update_task "$_wanted" failed '自动多字重字体族应用失败' 100 "$(date +%s)"
        rm -rf "$_root"; rm -f "$WORKER_PID"; exit 1
    }
    save_mix_config "$_cjk" "$_latin" "$_digit" "$_cjk_axes" "$_latin_axes" "$_digit_axes" \
        "$_cjk_mode" "$_latin_mode" "$_digit_mode" || {
        update_task "$_wanted" failed '组合配置保存失败' 100 "$(date +%s)"
        rm -rf "$_root"; rm -f "$WORKER_PID"; exit 1
    }
    update_task "$_wanted" success '自动多字重复合字体已准备，完整重启后生效' 100 "$(date +%s)"
    rm -rf "$_root" 2>/dev/null || true
    rm -f "$WORKER_PID" 2>/dev/null || true
}

precheck_mix() {
    [ -n "$1" ] && [ -n "$2" ] && [ -n "$3" ] || return 1
    [ -f "$ROLE_CHECK" ] || return 0
    MODDIR="$MODDIR" sh "$ROLE_CHECK" "$1" cjk >/dev/null 2>&1 || return 2
    MODDIR="$MODDIR" sh "$ROLE_CHECK" "$2" latin >/dev/null 2>&1 || return 3
    MODDIR="$MODDIR" sh "$ROLE_CHECK" "$3" digit >/dev/null 2>&1 || return 4
}

start_mix() {
    _cjk="$1"
    _latin="$2"
    _digit="$3"
    _cjk_axes=$(clean_spec "$4")
    _latin_axes=$(clean_spec "$5")
    _digit_axes=$(clean_spec "$6")
    [ -n "$_cjk_axes" ] || _cjk_axes='wght=400'
    [ -n "$_latin_axes" ] || _latin_axes='wght=400'
    [ -n "$_digit_axes" ] || _digit_axes='wght=400'
    _cjk_mode=$(resolve_mode "$7" "$_cjk" "$_cjk_axes")
    _latin_mode=$(resolve_mode "$8" "$_latin" "$_latin_axes")
    _digit_mode=$(resolve_mode "$9" "$_digit" "$_digit_axes")

    precheck_mix "$_cjk" "$_latin" "$_digit"
    _precheck=$?
    case "$_precheck" in
        1) printf '{"status":"error","message":"请选择中文、英文和数字字体"}\n'; return ;;
        2) printf '{"status":"error","message":"中文基底缺少必要字形"}\n'; return ;;
        3) printf '{"status":"error","message":"英文字体缺少必要字形"}\n'; return ;;
        4) printf '{"status":"error","message":"数字字体缺少必要字形"}\n'; return ;;
    esac

    if [ "$_cjk_mode" = fixed ] && [ "$_latin_mode" = fixed ] && [ "$_digit_mode" = fixed ]; then
        sh "$FALLBACK_ENGINE" start "$_cjk" "$_latin" "$_digit" "$_cjk_axes" "$_latin_axes" "$_digit_axes"
        return
    fi
    [ ! -f "$REBOOT_CONF" ] || {
        printf '{"status":"error","message":"本次开机已更改文字字体，请先重启手机"}\n'
        return
    }
    if [ -s "$WORKER_PID" ]; then
        _old=$(cat "$WORKER_PID" 2>/dev/null)
        [ -z "$_old" ] || ! kill -0 "$_old" 2>/dev/null || {
            printf '{"status":"error","message":"已有自动多字重任务正在运行"}\n'
            return
        }
    fi
    [ ! -e "$LOCK_FILE" ] || {
        printf '{"status":"error","message":"字体正在切换中"}\n'
        return
    }
    mkdir -p "$CONFIG_DIR" "$CACHE_ROOT" "$COMPOSITE_CACHE" "$MODDIR/logs" 2>/dev/null || {
        printf '{"status":"error","message":"无法创建任务目录"}\n'
        return
    }
    _task="auto-mix-$(date +%s)-$$"
    _root="$CACHE_ROOT/$_task"
    mkdir -p "$_root" 2>/dev/null || {
        printf '{"status":"error","message":"无法创建任务缓存"}\n'
        return
    }
    write_task "$_task" queued '自动多字重任务已进入队列' "$_cjk" "$_latin" "$_digit" \
        "$_cjk_axes" "$_latin_axes" "$_digit_axes" "$_cjk_mode" "$_latin_mode" "$_digit_mode" \
        "$_root" '' "$(date +%s)" '' 1
    ( MODDIR="$MODDIR" sh "$0" worker "$_task" ) </dev/null >>"$LOG_FILE" 2>&1 &
    printf '%s\n' "$!" >"$WORKER_PID" 2>/dev/null || true
    printf '{"status":"ok","data":{"task":"%s","cjkMode":"%s","latinMode":"%s","digitMode":"%s"}}\n' \
        "$(json_escape "$_task")" "$_cjk_mode" "$_latin_mode" "$_digit_mode"
}

config_json() {
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
    _cjk_mode=$(resolve_mode "$(read_value "$_source" cjkMode)" "$_cjk" "$_cjk_axes")
    _latin_mode=$(resolve_mode "$(read_value "$_source" latinMode)" "$_latin" "$_latin_axes")
    _digit_mode=$(resolve_mode "$(read_value "$_source" digitMode)" "$_digit" "$_digit_axes")
    _active=$(head -n1 "$ACTIVE_CONF" 2>/dev/null | tr -d '\r\n')
    _enabled=false
    [ "$_active" = mix ] && _enabled=true
    printf '{"status":"ok","data":{"enabled":%s,"cjk":"%s","latin":"%s","digit":"%s","cjkWeight":%s,"latinWeight":%s,"digitWeight":%s,"cjkAxes":"%s","latinAxes":"%s","digitAxes":"%s","cjkMode":"%s","latinMode":"%s","digitMode":"%s"}}\n' \
        "$_enabled" "$(json_escape "$_cjk")" "$(json_escape "$_latin")" "$(json_escape "$_digit")" \
        "$(safe_weight "$_cjk_axes")" "$(safe_weight "$_latin_axes")" "$(safe_weight "$_digit_axes")" \
        "$(json_escape "$_cjk_axes")" "$(json_escape "$_latin_axes")" "$(json_escape "$_digit_axes")" \
        "$_cjk_mode" "$_latin_mode" "$_digit_mode"
}

recover_task() {
    if [ -s "$WORKER_PID" ]; then
        _pid=$(cat "$WORKER_PID" 2>/dev/null)
        [ -z "$_pid" ] || ! kill -0 "$_pid" 2>/dev/null || kill "$_pid" 2>/dev/null || true
    fi
    rm -f "$WORKER_PID" 2>/dev/null || true
    sh "$FALLBACK_ENGINE" recover
}

case "${1:-config}" in
    start) start_mix "$2" "$3" "$4" "${5:-wght=400}" "${6:-wght=400}" "${7:-wght=400}" "${8:-infer}" "${9:-infer}" "${10:-infer}" ;;
    config) config_json ;;
    status) sh "$FALLBACK_ENGINE" status "${2:-}" ;;
    worker) worker "$2" ;;
    recover) recover_task ;;
    *) printf '{"status":"error","message":"未知自动多字重命令"}\n' ;;
esac
exit 0
