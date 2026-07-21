#!/system/bin/sh
# 洛书原生 App 字体管理后端：字体索引、校验、切换、删除和系统字重。
set +e

MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then
        MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"
    else
        MODDIR="/data/adb/modules/LuoShu"
    fi
fi
MODULE_DIR="$MODDIR"
CONFIG_DIR="$MODULE_DIR/config"
SYSTEM_FONTS_DIR="$MODULE_DIR/system/fonts"
ACTIVE_FONT_CONF="$CONFIG_DIR/active_font.conf"
LUOSHU_PUBLIC_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}"
USER_FONTS_DIR="$LUOSHU_PUBLIC_DIR/fonts"
USER_REPORT_DIR="$LUOSHU_PUBLIC_DIR/reports"
LEGACY_FONTS_DIR="/sdcard/Fonts"
TEXT_REBOOT_REQUIRED="$CONFIG_DIR/text_reboot_required.conf"
FONT_WEIGHT_REBOOT_REQUIRED="$CONFIG_DIR/font_weight_reboot_required.conf"
SWITCH_TASK_FILE="$CONFIG_DIR/switch_task.conf"
FONT_WEIGHT_CONF="$CONFIG_DIR/font_weight.conf"
FONT_WEIGHT_ORIGINAL_CONF="$CONFIG_DIR/font_weight_original.conf"
FONT_INDEX_JSON="$CONFIG_DIR/native_font_index.json"
FONT_INDEX_KEY="$CONFIG_DIR/native_font_index.key"

[ -f "$MODULE_DIR/common/util_functions.sh" ] && . "$MODULE_DIR/common/util_functions.sh"
[ -f "$MODULE_DIR/common/font_check.sh" ] && . "$MODULE_DIR/common/font_check.sh"
[ -f "$MODULE_DIR/common/rom_adapters.sh" ] && . "$MODULE_DIR/common/rom_adapters.sh"
[ -f "$MODULE_DIR/common/font_library_cache.sh" ] && . "$MODULE_DIR/common/font_library_cache.sh"
[ -f "$MODULE_DIR/common/font_config_runtime.sh" ] && . "$MODULE_DIR/common/font_config_runtime.sh"
[ -f "$MODULE_DIR/common/font_config_weights.sh" ] && . "$MODULE_DIR/common/font_config_weights.sh"
[ -f "$MODULE_DIR/common/mount_compat.sh" ] && . "$MODULE_DIR/common/mount_compat.sh"

type ensure_public_storage >/dev/null 2>&1 && ensure_public_storage
type check_coloros >/dev/null 2>&1 && check_coloros
type check_hyperos >/dev/null 2>&1 && check_hyperos
mkdir -p "$CONFIG_DIR" "$SYSTEM_FONTS_DIR" "$USER_FONTS_DIR" "$USER_REPORT_DIR" 2>/dev/null || true

json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
}

format_filesize() {
    _bytes="$1"
    case "$_bytes" in ''|*[!0-9]*) _bytes=0 ;; esac
    if [ "$_bytes" -lt 1024 ]; then
        printf '%s B' "$_bytes"
    elif [ "$_bytes" -lt 1048576 ]; then
        printf '%s KB' "$((_bytes / 1024))"
    elif [ "$_bytes" -lt 1073741824 ]; then
        printf '%s.%s MB' "$((_bytes / 1048576))" "$(((_bytes % 1048576) / 104857))"
    else
        printf '%s.%s GB' "$((_bytes / 1073741824))" "$(((_bytes % 1073741824) / 107374182))"
    fi
}

if ! type detect_font_family >/dev/null 2>&1; then
    detect_font_family() {
        _name="${1%.*}"
        case "$_name" in
            *-Regular|*-Bold|*-Light|*-Medium|*-Thin|*-Black|*-Heavy|*-regular|*-bold|*-light|*-medium|*-thin|*-black|*-heavy)
                _name="${_name%-*}"
                ;;
        esac
        printf '%s\n' "$_name"
    }
fi

if ! type link_or_copy_font >/dev/null 2>&1; then
    link_or_copy_font() {
        ln -f "$1" "$2" 2>/dev/null || cp -f "$1" "$2" 2>/dev/null
    }
fi

if ! type get_all_coloros_names >/dev/null 2>&1; then
    get_all_coloros_names() { printf '%s\n' ''; }
fi
if ! type get_all_hyperos_files >/dev/null 2>&1; then
    get_all_hyperos_files() { printf '%s\n' ''; }
fi
if ! type apply_font_by_rom >/dev/null 2>&1; then
    apply_font_by_rom() {
        _src="$1"
        _dest="$2"
        for _name in SysSans-Hant-Regular SysSans-Hans-Regular SysFont-Static-Regular SysFont-Myanmar SysFont-Hant-Regular SysFont-Hans-Regular SysFont-Regular SysSans-En-Regular; do
            cp -f "$_src" "$_dest/${_name}.ttf" 2>/dev/null || return 1
        done
    }
fi

scan_user_families_lines() {
    [ -d "$USER_FONTS_DIR" ] || return 0
    for _file in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
                 "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_file" ] || continue
        _family="$(detect_font_family "$(basename "$_file")")"
        case "$_family" in ''|SysFont*|SysSans*) continue ;; esac
        printf '%s\n' "$_family"
    done | awk '!seen[$0]++'
}

get_current_font_id() {
    _active="$(head -n1 "$ACTIVE_FONT_CONF" 2>/dev/null | tr -d '\r\n')"
    [ -n "$_active" ] || _active=default
    printf '%s\n' "$_active"
}

find_text_font_file() {
    _wanted="$1"
    for _file in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
                 "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_file" ] || continue
        _family="$(detect_font_family "$(basename "$_file")")"
        case "$_family" in SysFont*|SysSans*) continue ;; esac
        [ "$_family" = "$_wanted" ] && { printf '%s\n' "$_file"; return 0; }
    done
    return 1
}

get_managed_text_files() {
    if [ "${IS_COLOROS:-false}" = true ]; then
        for _name in $(get_all_coloros_names); do printf '%s.ttf\n' "$_name"; done
    elif [ "${IS_HYPEROS:-false}" = true ]; then
        get_all_hyperos_files
    else
        printf '%s\n' 'Roboto-Regular.ttf Roboto-Medium.ttf Roboto-Bold.ttf Roboto-Light.ttf Roboto-Thin.ttf NotoSansCJK-Regular.ttc NotoSansSC-Regular.otf NotoSansTC-Regular.otf'
    fi
}

clear_managed_text_fonts() {
    for _file in $(get_managed_text_files); do
        rm -f "$SYSTEM_FONTS_DIR/$_file" "$MODULE_DIR/system_ext/fonts/$_file" "$MODULE_DIR/product/fonts/$_file" 2>/dev/null || true
    done
    rm -rf "$SYSTEM_FONTS_DIR/.luoshu-font-store" 2>/dev/null || true
    type font_config_disable >/dev/null 2>&1 && font_config_disable
}

invalidate_font_index_cache() {
    rm -f "$FONT_INDEX_JSON" "$FONT_INDEX_KEY" \
          "$CONFIG_DIR/webui_font_list.json" "$CONFIG_DIR/webui_font_list.key" 2>/dev/null || true
}

switch_font() {
    _font_id="$1"
    [ -n "$_font_id" ] || { echo '错误：未指定字体' >&2; return 1; }

    _lock="$MODULE_DIR/.font_switch.lock"
    if [ -e "$_lock" ]; then
        _old_pid="$(cat "$_lock" 2>/dev/null)"
        if [ -n "$_old_pid" ] && kill -0 "$_old_pid" 2>/dev/null; then
            echo '错误：字体正在切换中，请稍候' >&2
            return 2
        fi
        rm -f "$_lock" 2>/dev/null || true
    fi
    if [ -f "$TEXT_REBOOT_REQUIRED" ]; then
        echo '错误：本次开机已更改文字字体，请先重启手机后再切换' >&2
        return 3
    fi

    printf '%s\n' "$$" > "$_lock" 2>/dev/null || return 1
    trap 'type luoshu_payload_transaction_abort >/dev/null 2>&1 && luoshu_payload_transaction_abort; rm -f "$MODULE_DIR/.font_switch.lock" 2>/dev/null' EXIT HUP INT TERM

    _source=''
    if [ "$_font_id" != default ]; then
        _source="$(find_text_font_file "$_font_id")"
        [ -f "$_source" ] || { echo "错误：字体 $_font_id 不存在" >&2; return 1; }
        if type font_validate_global >/dev/null 2>&1; then
            font_validate_global "$_source" || { echo "错误：$FONT_CHECK_ERROR" >&2; return 4; }
        elif type font_validate >/dev/null 2>&1; then
            font_validate "$_source" text || { echo "错误：$FONT_CHECK_ERROR" >&2; return 4; }
        fi
    fi

    if ! type luoshu_payload_transaction_begin >/dev/null 2>&1 || ! luoshu_payload_transaction_begin; then
        echo '错误：无法创建字体负载安全快照' >&2
        return 5
    fi
    clear_managed_text_fonts
    if [ "$_font_id" != default ]; then
        apply_font_by_rom "$_source" "$SYSTEM_FONTS_DIR" quick "$_font_id" || {
            echo '错误：ROM 字体映射失败' >&2
            return 5
        }
        if [ "${IS_COLOROS:-false}" = true ]; then
            mkdir -p "$MODULE_DIR/system_ext/fonts" "$MODULE_DIR/product/fonts" 2>/dev/null || true
            for _name in $(get_all_coloros_names); do
                _mapped="$SYSTEM_FONTS_DIR/${_name}.ttf"
                [ -f "$_mapped" ] || continue
                [ -e "/system_ext/fonts/${_name}.ttf" ] && link_or_copy_font "$_mapped" "$MODULE_DIR/system_ext/fonts/${_name}.ttf" 2>/dev/null || true
                [ -e "/product/fonts/${_name}.ttf" ] && link_or_copy_font "$_mapped" "$MODULE_DIR/product/fonts/${_name}.ttf" 2>/dev/null || true
            done
        fi
    fi

    printf '%s\n' "$_font_id" > "$ACTIVE_FONT_CONF"
    chmod 0644 "$ACTIVE_FONT_CONF" "$SYSTEM_FONTS_DIR"/* 2>/dev/null || true
    if [ "$_font_id" != default ]; then
        _recent="$CONFIG_DIR/recent_fonts.conf"
        _tmp="${_recent}.tmp.$$"
        {
            printf '%s\n' "$_font_id"
            if [ -f "$_recent" ]; then
                awk -v selected="$_font_id" 'NF && $0 != selected && !seen[$0]++ { print; if (++count >= 9) exit }' "$_recent"
            fi
        } > "$_tmp" 2>/dev/null && mv -f "$_tmp" "$_recent" 2>/dev/null || rm -f "$_tmp" 2>/dev/null
    fi

    printf 'font=%s\ntime=%s\n' "$_font_id" "$(date +%s)" > "$TEXT_REBOOT_REQUIRED"
    printf '%s\n' "$_font_id" > "$CONFIG_DIR/last_switch_result.conf"
    date '+%Y-%m-%d %H:%M:%S' > "$CONFIG_DIR/last_switch_time.conf" 2>/dev/null || true
    chmod 0644 "$TEXT_REBOOT_REQUIRED" 2>/dev/null || true
    invalidate_font_index_cache
    return 0
}

write_switch_task() {
    _task_id="$1"
    _task_state="$2"
    _task_font="$3"
    _task_message="$4"
    _task_started="$5"
    _task_finished="$6"
    _tmp="${SWITCH_TASK_FILE}.tmp.$$"
    {
        printf 'task=%s\n' "$_task_id"
        printf 'state=%s\n' "$_task_state"
        printf 'font=%s\n' "$_task_font"
        printf 'message=%s\n' "$_task_message"
        printf 'started=%s\n' "$_task_started"
        printf 'finished=%s\n' "$_task_finished"
    } > "$_tmp" 2>/dev/null && mv -f "$_tmp" "$SWITCH_TASK_FILE" 2>/dev/null || rm -f "$_tmp" 2>/dev/null
    chmod 0644 "$SWITCH_TASK_FILE" 2>/dev/null || true
}

read_switch_task_value() {
    sed -n "s/^${1}=//p" "$SWITCH_TASK_FILE" 2>/dev/null | head -n1 | tr -d '\r\n'
}

notify_user() {
    _title="$1"
    _message="$2"
    _tag="${3:-luoshu}"
    command -v cmd >/dev/null 2>&1 || return 1
    cmd notification post -S bigtext -t "$_title" "$_tag" "$_message" >/dev/null 2>&1 || \
        cmd notification post -t "$_title" "$_tag" "$_message" >/dev/null 2>&1
}

font_weight_normalize_int() {
    case "$1" in ''|null|undefined|2147483647|-2147483648|*[!0-9-]*) printf '0\n' ;; *) printf '%s\n' "$1" ;; esac
}

font_weight_get_system() {
    if command -v settings >/dev/null 2>&1; then
        font_weight_normalize_int "$(settings get secure font_weight_adjustment 2>/dev/null)"
    else
        printf '0\n'
    fi
}

font_weight_get_saved() {
    if [ -f "$FONT_WEIGHT_CONF" ]; then
        font_weight_normalize_int "$(sed -n 's/^adjustment=//p' "$FONT_WEIGHT_CONF" 2>/dev/null | head -n1)"
    else
        font_weight_get_system
    fi
}

font_weight_get_desired() {
    if [ -f "$FONT_WEIGHT_CONF" ]; then
        _weight="$(sed -n 's/^weight=//p' "$FONT_WEIGHT_CONF" 2>/dev/null | head -n1)"
    else
        _weight=$((400 + $(font_weight_get_system)))
    fi
    case "$_weight" in ''|*[!0-9]*) _weight=400 ;; esac
    [ "$_weight" -lt 300 ] 2>/dev/null && _weight=300
    [ "$_weight" -gt 700 ] 2>/dev/null && _weight=700
    printf '%s\n' "$_weight"
}

font_weight_backup_original() {
    [ -s "$FONT_WEIGHT_ORIGINAL_CONF" ] && return 0
    printf 'adjustment=%s\n' "$(font_weight_get_system)" > "$FONT_WEIGHT_ORIGINAL_CONF" 2>/dev/null
}

font_weight_set() {
    _weight="$1"
    case "$_weight" in ''|*[!0-9]*) return 2 ;; esac
    [ "$_weight" -ge 300 ] 2>/dev/null && [ "$_weight" -le 700 ] 2>/dev/null || return 2
    command -v settings >/dev/null 2>&1 || return 5
    _adjustment=$((_weight - 400))
    font_weight_backup_original || return 1
    settings put secure font_weight_adjustment "$_adjustment" >/dev/null 2>&1 || return 4
    {
        printf 'weight=%s\n' "$_weight"
        printf 'adjustment=%s\n' "$_adjustment"
        printf 'time=%s\n' "$(date +%s)"
    } > "$FONT_WEIGHT_CONF" 2>/dev/null || return 1
    chmod 0644 "$FONT_WEIGHT_CONF" 2>/dev/null || true
    rm -f "$FONT_WEIGHT_REBOOT_REQUIRED" 2>/dev/null || true
    cmd font system --update >/dev/null 2>&1 || true
    am broadcast -a android.intent.action.CONFIGURATION_CHANGED >/dev/null 2>&1 || true
    return 0
}

font_weight_reset() {
    command -v settings >/dev/null 2>&1 || return 5
    _restore=0
    [ -f "$FONT_WEIGHT_ORIGINAL_CONF" ] && _restore="$(sed -n 's/^adjustment=//p' "$FONT_WEIGHT_ORIGINAL_CONF" 2>/dev/null | head -n1)"
    _restore="$(font_weight_normalize_int "$_restore")"
    settings put secure font_weight_adjustment "$_restore" >/dev/null 2>&1 || return 4
    rm -f "$FONT_WEIGHT_CONF" "$FONT_WEIGHT_REBOOT_REQUIRED" 2>/dev/null || true
    cmd font system --update >/dev/null 2>&1 || true
    am broadcast -a android.intent.action.CONFIGURATION_CHANGED >/dev/null 2>&1 || true
    return 0
}

font_weight_status_json() {
    _supported=false
    command -v settings >/dev/null 2>&1 && _supported=true
    _system="$(font_weight_get_system)"
    _saved="$(font_weight_get_saved)"
    _desired="$(font_weight_get_desired)"
    _original=0
    [ -f "$FONT_WEIGHT_ORIGINAL_CONF" ] && _original="$(sed -n 's/^adjustment=//p' "$FONT_WEIGHT_ORIGINAL_CONF" 2>/dev/null | head -n1)"
    _original="$(font_weight_normalize_int "$_original")"
    printf '{"status":"ok","data":{"supported":%s,"weight":%s,"adjustment":%s,"systemAdjustment":%s,"originalAdjustment":%s,"min":300,"max":700,"step":10}}\n' \
        "$_supported" "$_desired" "$_saved" "$_system" "$_original"
}

font_index_fingerprint() {
    if type font_library_fingerprint_value >/dev/null 2>&1; then
        font_library_fingerprint_value
    else
        stat -c '%Y:%s' "$USER_FONTS_DIR" 2>/dev/null || printf '0:0\n'
    fi
}

build_font_index_json() {
    _refresh="$1"
    _current="$(get_current_font_id)"
    _fingerprint="$(font_index_fingerprint)"
    _cache_key="native-v1|${_current}|${_fingerprint}"
    _saved_key="$(cat "$FONT_INDEX_KEY" 2>/dev/null)"
    if [ "$_refresh" != refresh ] && [ "$_saved_key" = "$_cache_key" ] && [ -s "$FONT_INDEX_JSON" ] && grep -q '"status":"ok"' "$FONT_INDEX_JSON" 2>/dev/null; then
        cat "$FONT_INDEX_JSON"
        return 0
    fi

    _families="$CONFIG_DIR/.native-font-families.$$"
    scan_user_families_lines > "$_families" 2>/dev/null || : > "$_families"
    _output="${FONT_INDEX_JSON}.tmp.$$"
    {
        _first=true
        _total_bytes=0
        _font_count="$(grep -c . "$_families" 2>/dev/null)"
        case "$_font_count" in ''|*[!0-9]*) _font_count=0 ;; esac

        while IFS= read -r _family; do
            [ -n "$_family" ] || continue
            _representative="$(get_weight_file "$_family" regular 2>/dev/null)"
            [ -f "$_representative" ] || _representative="$(get_weight_file "$_family" bold 2>/dev/null)"
            [ -f "$_representative" ] || continue
            _bytes="$(wc -c < "$_representative" 2>/dev/null | tr -d '[:space:]')"
            case "$_bytes" in ''|*[!0-9]*) _bytes=0 ;; esac
            _total_bytes=$((_total_bytes + _bytes))
        done < "$_families"

        printf '{"status":"ok","data":{"current":"%s","scanner":{"primary":"shell","nativeAvailable":false},"stats":{"count":%s,"totalSize":"%s"},"fonts":[' \
            "$(json_escape "$_current")" "$_font_count" "$(format_filesize "$_total_bytes")"

        while IFS= read -r _family; do
            [ -n "$_family" ] || continue
            _weights="$(scan_family_weights "$_family" 2>/dev/null)"
            _weights_json=''
            _variants_json=''
            _weight_count=0
            _old_ifs="$IFS"
            IFS=','
            for _weight in $_weights; do
                [ -n "$_weight" ] || continue
                [ -n "$_weights_json" ] && _weights_json="$_weights_json,"
                _weights_json="${_weights_json}\"$(json_escape "$_weight")\""
                _weight_count=$((_weight_count + 1))
                _variant_file="$(get_weight_file "$_family" "$_weight" 2>/dev/null)"
                if [ -f "$_variant_file" ]; then
                    _variant_name="$(basename "$_variant_file")"
                    [ -n "$_variants_json" ] && _variants_json="$_variants_json,"
                    _variants_json="${_variants_json}\"$(json_escape "$_weight")\":\"$(json_escape "$_variant_name")\""
                fi
            done
            IFS="$_old_ifs"

            _file="$(get_weight_file "$_family" regular 2>/dev/null)"
            [ -f "$_file" ] || _file="$(get_weight_file "$_family" bold 2>/dev/null)"
            [ -f "$_file" ] || _file="$(get_weight_file "$_family" medium 2>/dev/null)"
            if [ ! -f "$_file" ]; then
                for _candidate in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
                                  "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
                    [ -f "$_candidate" ] || continue
                    [ "$(detect_font_family "$(basename "$_candidate")")" = "$_family" ] && { _file="$_candidate"; break; }
                done
            fi
            [ -f "$_file" ] || continue

            _bytes="$(wc -c < "$_file" 2>/dev/null | tr -d '[:space:]')"
            case "$_bytes" in ''|*[!0-9]*) _bytes=0 ;; esac
            _format=UNKNOWN
            type font_detect_format >/dev/null 2>&1 && _format="$(font_detect_format "$_file" 2>/dev/null)"
            _valid=true
            _warning=''
            _error=''
            if type font_validate >/dev/null 2>&1; then
                if font_validate "$_file" text 2>/dev/null; then
                    _warning="$FONT_CHECK_WARNING"
                else
                    _valid=false
                    _error="$FONT_CHECK_ERROR"
                fi
            fi
            _variable=false
            type is_variable_font >/dev/null 2>&1 && is_variable_font "$_file" 2>/dev/null && _variable=true
            _family_type=single
            [ "$_weight_count" -ge 2 ] 2>/dev/null && _family_type=static-family
            [ "$_variable" = true ] && _family_type=variable
            _date="$(stat -c '%y' "$_file" 2>/dev/null | cut -c1-10)"
            _name="$(basename "$_file")"

            [ "$_first" = true ] || printf ','
            printf '{"id":"%s","name":"%s","weights":[%s],"variants":{%s},"familyType":"%s","file":"%s","size":"%s","bytes":%s,"format":"%s","valid":%s,"warning":"%s","error":"%s","variable":%s,"date":"%s"}' \
                "$(json_escape "$_family")" "$(json_escape "$_family")" "$_weights_json" "$_variants_json" "$(json_escape "$_family_type")" \
                "$(json_escape "$_name")" "$(format_filesize "$_bytes")" "$_bytes" "$(json_escape "$_format")" "$_valid" \
                "$(json_escape "$_warning")" "$(json_escape "$_error")" "$_variable" "$(json_escape "$_date")"
            _first=false
        done < "$_families"
        printf ']}}\n'
    } > "$_output" 2>/dev/null
    _result=$?
    rm -f "$_families" 2>/dev/null || true
    if [ "$_result" -ne 0 ] || [ ! -s "$_output" ]; then
        rm -f "$_output" 2>/dev/null || true
        printf '{"status":"error","message":"字体索引生成失败"}\n'
        return 1
    fi
    mv -f "$_output" "$FONT_INDEX_JSON" 2>/dev/null || {
        rm -f "$_output" 2>/dev/null || true
        printf '{"status":"error","message":"字体索引缓存写入失败"}\n'
        return 1
    }
    printf '%s\n' "$_cache_key" > "$FONT_INDEX_KEY" 2>/dev/null || true
    chmod 0644 "$FONT_INDEX_JSON" "$FONT_INDEX_KEY" 2>/dev/null || true
    cat "$FONT_INDEX_JSON"
}

validate_font_json() {
    _font_id="$1"
    _file="$(find_text_font_file "$_font_id")"
    [ -f "$_file" ] || { printf '{"status":"error","message":"未找到字体"}\n'; return 0; }
    if type font_validate_global >/dev/null 2>&1; then
        if font_validate_global "$_file"; then
            printf '{"status":"ok","data":{"valid":true,"format":"%s","bytes":%s,"variable":%s,"color":%s,"warning":"%s"}}\n' \
                "$(json_escape "$FONT_CHECK_FORMAT")" "${FONT_CHECK_SIZE:-0}" "${FONT_CHECK_VARIABLE:-false}" "${FONT_CHECK_COLOR:-false}" "$(json_escape "$FONT_CHECK_WARNING")"
        else
            printf '{"status":"ok","data":{"valid":false,"format":"%s","bytes":%s,"variable":%s,"color":%s,"error":"%s"}}\n' \
                "$(json_escape "$FONT_CHECK_FORMAT")" "${FONT_CHECK_SIZE:-0}" "${FONT_CHECK_VARIABLE:-false}" "${FONT_CHECK_COLOR:-false}" "$(json_escape "$FONT_CHECK_ERROR")"
        fi
    elif type font_check_json >/dev/null 2>&1; then
        _check="$(font_check_json "$_file" text 2>/dev/null | tr -d '\n')"
        [ -n "$_check" ] || _check='{"valid":false,"error":"字体验证器未返回结果"}'
        printf '{"status":"ok","data":%s}\n' "$_check"
    else
        printf '{"status":"error","message":"字体验证器不可用"}\n'
    fi
}

start_switch_task() {
    _font_id="$1"
    [ -n "$_font_id" ] || { printf '{"status":"error","message":"未指定字体"}\n'; return 0; }
    [ ! -f "$TEXT_REBOOT_REQUIRED" ] || { printf '{"status":"error","message":"本次开机已更改文字字体，请先重启手机"}\n'; return 0; }

    if [ -e "$MODULE_DIR/.font_switch.lock" ]; then
        _lock_pid="$(cat "$MODULE_DIR/.font_switch.lock" 2>/dev/null)"
        if [ -n "$_lock_pid" ] && kill -0 "$_lock_pid" 2>/dev/null; then
            printf '{"status":"error","message":"字体正在切换中，请稍候"}\n'
            return 0
        fi
        rm -f "$MODULE_DIR/.font_switch.lock" 2>/dev/null || true
    fi

    mkdir -p "$MODULE_DIR/logs" "$CONFIG_DIR" 2>/dev/null || true
    _task_id="$(date +%s)-$$"
    _started="$(date +%s)"
    write_switch_task "$_task_id" running "$_font_id" '正在应用字体' "$_started" ''
    (
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] async switch start: $_font_id task=$_task_id" >> "$MODULE_DIR/logs/fontswitch.log" 2>/dev/null
        if switch_font "$_font_id" >> "$MODULE_DIR/logs/fontswitch.log" 2>&1; then
            _finished="$(date +%s)"
            write_switch_task "$_task_id" success "$_font_id" '字体已准备，必须重启手机后全局生效' "$_started" "$_finished"
            notify_user '洛书' "文字字体已准备：$_font_id。请完整重启手机。" luoshu-text || true
        else
            _code=$?
            _finished="$(date +%s)"
            write_switch_task "$_task_id" failed "$_font_id" "切换失败（代码 $_code）" "$_started" "$_finished"
        fi
    ) &
    printf '{"status":"ok","data":{"font":"%s","task":"%s","message":"任务已开始"}}\n' "$(json_escape "$_font_id")" "$(json_escape "$_task_id")"
}

switch_task_status_json() {
    _wanted="$1"
    [ -s "$SWITCH_TASK_FILE" ] || { printf '{"status":"error","message":"暂无切换任务"}\n'; return 0; }
    _task="$(read_switch_task_value task)"
    if [ -n "$_wanted" ] && [ "$_wanted" != "$_task" ]; then
        printf '{"status":"error","message":"任务不存在或已被新任务替换"}\n'
        return 0
    fi
    _state="$(read_switch_task_value state)"
    _font="$(read_switch_task_value font)"
    _message="$(read_switch_task_value message)"
    _started="$(read_switch_task_value started)"
    _finished="$(read_switch_task_value finished)"
    printf '{"status":"ok","data":{"task":"%s","state":"%s","font":"%s","message":"%s","started":%s,"finished":%s}}\n' \
        "$(json_escape "$_task")" "$(json_escape "$_state")" "$(json_escape "$_font")" "$(json_escape "$_message")" \
        "${_started:-0}" "${_finished:-0}"
}

delete_font_json() {
    _font_id="$1"
    _current="$(get_current_font_id)"
    [ -n "$_font_id" ] && [ "$_font_id" != default ] || { printf '{"status":"error","message":"未指定可删除字体"}\n'; return 0; }
    if [ "$_font_id" = "$_current" ] && [ -f "$TEXT_REBOOT_REQUIRED" ]; then
        printf '{"status":"error","message":"当前字体已等待重启，请先重启后再删除"}\n'
        return 0
    fi
    if [ "$_font_id" = "$_current" ]; then
        switch_font default >/dev/null 2>&1 || { printf '{"status":"error","message":"无法先恢复系统默认字体"}\n'; return 0; }
    fi

    _deleted=0
    for _file in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
                 "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_file" ] || continue
        [ "$(detect_font_family "$(basename "$_file")")" = "$_font_id" ] || continue
        rm -f "$_file" 2>/dev/null && _deleted=$((_deleted + 1))
    done
    if [ "$_deleted" -gt 0 ]; then
        invalidate_font_index_cache
        printf '{"status":"ok","data":{"deleted":%s,"message":"已删除 %s 个文件"}}\n' "$_deleted" "$_deleted"
    else
        printf '{"status":"error","message":"未找到字体文件"}\n'
    fi
}

handle_action() {
    _action="$1"
    _param="$2"
    case "$_action" in
        list) build_font_index_json "$_param" ;;
        current) printf '{"status":"ok","data":{"current":"%s"}}\n' "$(json_escape "$(get_current_font_id)")" ;;
        validate) validate_font_json "$_param" ;;
        switch) if switch_font "$_param"; then printf '{"status":"ok","data":{"font":"%s","message":"已准备，重启手机后生效"}}\n' "$(json_escape "$_param")"; else printf '{"status":"error","message":"切换失败"}\n'; fi ;;
        switch_async) start_switch_task "$_param" ;;
        switch_status) switch_task_status_json "$_param" ;;
        delete) delete_font_json "$_param" ;;
        font_weight_status) font_weight_status_json ;;
        font_weight_set)
            if font_weight_set "$_param"; then
                printf '{"status":"ok","data":{"weight":%s,"adjustment":%s,"message":"系统粗细已更新；未刷新的应用请重新打开"}}\n' "$(font_weight_get_desired)" "$(font_weight_get_saved)"
            else
                _code=$?
                case "$_code" in 2) _message='字重超出安全范围（仅支持 300–700）' ;; 5) _message='当前系统不支持字体粗细调节' ;; *) _message='无法写入系统字体粗细设置' ;; esac
                printf '{"status":"error","message":"%s"}\n' "$(json_escape "$_message")"
            fi
            ;;
        font_weight_reset)
            if font_weight_reset; then
                printf '{"status":"ok","data":{"weight":%s,"adjustment":%s,"message":"已恢复系统原始字体粗细"}}\n' "$(font_weight_get_desired)" "$(font_weight_get_system)"
            else
                printf '{"status":"error","message":"无法恢复系统字体粗细"}\n'
            fi
            ;;
        reboot_required)
            _required=false
            [ -f "$TEXT_REBOOT_REQUIRED" ] && _required=true
            printf '{"status":"ok","data":{"required":%s,"text":%s,"weight":false}}\n' "$_required" "$_required"
            ;;
        reboot_device)
            printf '{"status":"ok","data":{"message":"正在重启手机"}}\n'
            (sleep 1; svc power reboot 2>/dev/null || reboot 2>/dev/null) &
            ;;
        *) printf '{"status":"error","message":"未知字体管理操作"}\n' ;;
    esac
}

case "${1:-}" in
    action) handle_action "${2:-}" "${3:-}" ;;
    list) handle_action list "${2:-}" ;;
    current) handle_action current '' ;;
    *) printf '{"status":"error","message":"请通过洛书 App 或安全 CLI 使用字体管理器"}\n'; exit 1 ;;
esac
exit 0
