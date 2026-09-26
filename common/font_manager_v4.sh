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
# Old direct/async APIs are public compatibility routes, not another mapper.
# Delegate before loading index helpers so missing generation components fail closed.
case "${1:-}:${2:-}" in
    action:switch|action:switch_async|action:switch_status)
        _router="$MODDIR/common/font_manager.sh"
        [ -f "$_router" ] || {
            printf '{"status":"error","message":"通用字体管理入口缺失"}\n'; exit 1;
        }
        export MODDIR
        exec sh "$_router" "$@"
        ;;
esac

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
[ -f "$MODULE_DIR/common/font_validation_cache.sh" ] && . "$MODULE_DIR/common/font_validation_cache.sh"
[ -f "$MODULE_DIR/common/font_library_cache.sh" ] && . "$MODULE_DIR/common/font_library_cache.sh"
[ -f "$MODULE_DIR/common/font_boot_state.sh" ] && . "$MODULE_DIR/common/font_boot_state.sh"
[ -f "$MODULE_DIR/common/font_active_state.sh" ] && . "$MODULE_DIR/common/font_active_state.sh"

case "${1:-}:${2:-}" in
    action:font_weight_status) ;; # A settings read must never migrate /sdcard/Fonts.
    *)
        type ensure_public_storage >/dev/null 2>&1 && ensure_public_storage
        mkdir -p "$CONFIG_DIR" "$SYSTEM_FONTS_DIR" "$USER_FONTS_DIR" "$USER_REPORT_DIR" 2>/dev/null || true
        ;;
esac

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

if ! type detect_font_weight >/dev/null 2>&1; then
    detect_font_weight() {
        _name="${1%.*}"
        case "$_name" in
            *-Thin|*-thin) printf '100\n' ;;
            *-ExtraLight|*-UltraLight|*-extralight|*-ultralight) printf '200\n' ;;
            *-Light|*-light) printf '300\n' ;;
            *-Medium|*-medium) printf '500\n' ;;
            *-SemiBold|*-DemiBold|*-semibold|*-demibold) printf '600\n' ;;
            *-Bold|*-bold) printf '700\n' ;;
            *-ExtraBold|*-UltraBold|*-extrabold|*-ultrabold) printf '800\n' ;;
            *-Black|*-Heavy|*-black|*-heavy) printf '900\n' ;;
            *) printf '400\n' ;;
        esac
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

invalidate_font_index_cache() {
    rm -f "$FONT_INDEX_JSON" "$FONT_INDEX_KEY" 2>/dev/null || true
}

switch_font() {
    # Deleting the selected family must queue default through the same safe path.
    # The live payload remains pinned until boot even after its library source is deleted.
    [ -f "$MODULE_DIR/common/font_manager.sh" ] || return 1
    MODDIR="$MODULE_DIR" sh "$MODULE_DIR/common/font_manager.sh" action switch "$1"
}

font_weight_normalize_int() {
    case "$1" in ''|null|undefined|2147483647|-2147483648|*[!0-9-]*) printf '0\n' ;; *) printf '%s\n' "$1" ;; esac
}

font_weight_get_system() {
    if ! command -v settings >/dev/null 2>&1; then
        printf '0\n'
        return 0
    fi
    _fwgs_value=$(settings --user current get secure font_weight_adjustment 2>/dev/null)
    _fwgs_rc=$?
    if [ "$_fwgs_rc" -ne 0 ]; then
        _fwgs_value=$(settings get secure font_weight_adjustment 2>/dev/null)
        FONT_WEIGHT_SCOPE=legacy-default-user
    else
        FONT_WEIGHT_SCOPE=current-user
    fi
    export FONT_WEIGHT_SCOPE
    font_weight_normalize_int "$_fwgs_value"
}

font_weight_put_system() {
    _fwps_value="$1"
    command -v settings >/dev/null 2>&1 || return 5
    if settings --user current put secure font_weight_adjustment "$_fwps_value" >/dev/null 2>&1; then
        FONT_WEIGHT_SCOPE=current-user
        _fwps_read=$(settings --user current get secure font_weight_adjustment 2>/dev/null)
    elif settings put secure font_weight_adjustment "$_fwps_value" >/dev/null 2>&1; then
        FONT_WEIGHT_SCOPE=legacy-default-user
        _fwps_read=$(settings get secure font_weight_adjustment 2>/dev/null)
    else
        return 4
    fi
    export FONT_WEIGHT_SCOPE
    _fwps_read=$(font_weight_normalize_int "$_fwps_read")
    [ "$_fwps_read" = "$_fwps_value" ] || return 6
    return 0
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
    font_weight_put_system "$_adjustment" || return $?
    {
        printf 'weight=%s\n' "$_weight"
        printf 'adjustment=%s\n' "$_adjustment"
        printf 'scope=%s\n' "${FONT_WEIGHT_SCOPE:-current-user}"
        printf 'time=%s\n' "$(date +%s)"
    } > "$FONT_WEIGHT_CONF" 2>/dev/null || return 1
    chmod 0644 "$FONT_WEIGHT_CONF" 2>/dev/null || true
    rm -f "$FONT_WEIGHT_REBOOT_REQUIRED" 2>/dev/null || true
    # font_weight_adjustment is a Configuration setting, not a downloadable-font
    # database. FontManagerService --update does not apply it. The secure-setting
    # observer is authoritative; this broadcast is only an OEM UI nudge.
    command -v am >/dev/null 2>&1 && \
        am broadcast -a android.intent.action.CONFIGURATION_CHANGED >/dev/null 2>&1 || true
    return 0
}

font_weight_reset() {
    command -v settings >/dev/null 2>&1 || return 5
    _restore=0
    [ -f "$FONT_WEIGHT_ORIGINAL_CONF" ] && _restore="$(sed -n 's/^adjustment=//p' "$FONT_WEIGHT_ORIGINAL_CONF" 2>/dev/null | head -n1)"
    _restore="$(font_weight_normalize_int "$_restore")"
    font_weight_put_system "$_restore" || return $?
    rm -f "$FONT_WEIGHT_CONF" "$FONT_WEIGHT_REBOOT_REQUIRED" 2>/dev/null || true
    command -v am >/dev/null 2>&1 && \
        am broadcast -a android.intent.action.CONFIGURATION_CHANGED >/dev/null 2>&1 || true
    return 0
}

font_weight_status_json() {
    _supported=false
    command -v settings >/dev/null 2>&1 && _supported=true
    _system="$(font_weight_get_system)"
    # One Binder query per refresh; missing saved configuration formerly queried
    # Settings three times, multiplying slow/system-busy responses.
    _saved="$_system"
    _desired=$((400 + _system))
    if [ -f "$FONT_WEIGHT_CONF" ]; then
        _saved="$(font_weight_get_saved)"
        _desired="$(font_weight_get_desired)"
    fi
    [ "$_desired" -ge 300 ] || _desired=300
    [ "$_desired" -le 700 ] || _desired=700
    _original=0
    [ -f "$FONT_WEIGHT_ORIGINAL_CONF" ] && _original="$(sed -n 's/^adjustment=//p' "$FONT_WEIGHT_ORIGINAL_CONF" 2>/dev/null | head -n1)"
    _original="$(font_weight_normalize_int "$_original")"
    _scope="${FONT_WEIGHT_SCOPE:-current-user}"
    printf '{"status":"ok","data":{"supported":%s,"weight":%s,"adjustment":%s,"systemAdjustment":%s,"originalAdjustment":%s,"scope":"%s","min":300,"max":700,"step":10}}\n' \
        "$_supported" "$_desired" "$_saved" "$_system" "$_original" "$(json_escape "$_scope")"
}

font_index_fingerprint() {
    if type font_library_fingerprint_value >/dev/null 2>&1; then
        font_library_fingerprint_value
    else
        stat -c '%Y:%s' "$USER_FONTS_DIR" 2>/dev/null || printf '0:0\n'
    fi
}

font_index_manifest() {
    _manifest="$1"
    : > "$_manifest" 2>/dev/null || return 1
    for _font_file in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
            "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_font_file" ] || continue
        _name=$(basename "$_font_file" 2>/dev/null)
        _family=$(detect_font_family "$_name")
        case "$_family" in ''|SysFont*|SysSans*) continue ;; esac
        case "$_name" in *'|'*) continue ;; esac
        case "$_family" in *'|'*) continue ;; esac
        _weight=$(detect_font_weight "$_name")
        _size=$(stat -c %s "$_font_file" 2>/dev/null)
        _mtime=$(stat -c %Y "$_font_file" 2>/dev/null)
        case "$_size" in ''|*[!0-9]*) _size=0 ;; esac
        case "$_mtime" in ''|*[!0-9]*) _mtime=0 ;; esac
        printf '%s|%s|%s|%s|%s|%s
' "$_family" "$_weight" "$_font_file" "$_name" "$_size" "$_mtime" >> "$_manifest"
    done
}

build_font_index_json() {
    _refresh="$1"
    _current=$(get_current_font_id)
    _fingerprint=$(font_index_fingerprint)
    _cache_key="native-v3|${_current}|${_fingerprint}"
    _saved_key=$(cat "$FONT_INDEX_KEY" 2>/dev/null)
    if [ "$_refresh" != refresh ] && [ "$_saved_key" = "$_cache_key" ] && [ -s "$FONT_INDEX_JSON" ] && grep -q '"status":"ok"' "$FONT_INDEX_JSON" 2>/dev/null; then
        cat "$FONT_INDEX_JSON"
        return 0
    fi

    _manifest="$CONFIG_DIR/.native-font-manifest.$$"
    _families="$CONFIG_DIR/.native-font-families.$$"
    font_index_manifest "$_manifest" || : > "$_manifest"
    awk -F'|' 'NF >= 6 && !seen[$1]++ {print $1}' "$_manifest" > "$_families" 2>/dev/null || : > "$_families"
    _output="${FONT_INDEX_JSON}.tmp.$$"
    {
        _first=true
        _font_count=$(grep -c . "$_families" 2>/dev/null)
        _total_bytes=$(awk -F'|' '{total += $5} END {print total + 0}' "$_manifest" 2>/dev/null)
        case "$_font_count" in ''|*[!0-9]*) _font_count=0 ;; esac
        case "$_total_bytes" in ''|*[!0-9]*) _total_bytes=0 ;; esac
        printf '{"status":"ok","data":{"current":"%s","scanner":{"primary":"manifest-fast","nativeAvailable":false},"stats":{"count":%s,"totalSize":"%s"},"fonts":[' \
  "$(json_escape "$_current")" "$_font_count" "$(format_filesize "$_total_bytes")"

        while IFS= read -r _family; do
  [ -n "$_family" ] || continue
  _weights=$(awk -F'|' -v wanted="$_family" '
      $1 == wanted {seen[$2] = 1}
      END {
          count = split("variable thin extralight light regular medium semibold bold extrabold black", order, " ")
          out = ""
          for (i = 1; i <= count; i++) if (seen[order[i]]) out = out (out ? "," : "") order[i]
          print out
      }
  ' "$_manifest")
  [ -n "$_weights" ] || continue
  _record=$(awk -F'|' -v wanted="$_family" '
      BEGIN {
          priority["regular"]=1; priority["medium"]=2; priority["bold"]=3; priority["semibold"]=4
          priority["variable"]=5; priority["light"]=6; priority["extralight"]=7; priority["thin"]=8
          priority["extrabold"]=9; priority["black"]=10; best=999
      }
      $1 == wanted {
          p = ($2 in priority) ? priority[$2] : 50
          if (p < best) {best=p; line=$0}
      }
      END {print line}
  ' "$_manifest")
  [ -n "$_record" ] || continue
  IFS='|' read -r _record_family _record_weight _file _record_name _bytes _record_mtime <<EOF_RECORD
$_record
EOF_RECORD
  [ -f "$_file" ] || continue

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
      _variant_name=$(awk -F'|' -v wanted="$_family" -v role="$_weight" '$1 == wanted && $2 == role {print $4; exit}' "$_manifest")
      if [ -n "$_variant_name" ]; then
          [ -n "$_variants_json" ] && _variants_json="$_variants_json,"
          _variants_json="${_variants_json}\"$(json_escape "$_weight")\":\"$(json_escape "$_variant_name")\""
      fi
  done
  IFS="$_old_ifs"

  case "$_bytes" in ''|*[!0-9]*) _bytes=0 ;; esac
  _format=UNKNOWN
  type font_detect_format >/dev/null 2>&1 && _format=$(font_detect_format "$_file" 2>/dev/null)
  _valid=true
  _error=''
  if [ "$_bytes" -lt 4096 ] 2>/dev/null; then
      _valid=false; _error='字体文件过小'
  elif [ -z "$_format" ] || [ "$_format" = UNKNOWN ]; then
      _valid=false; _error='字体格式无法识别'
  fi
  _variable=false
  case ",$_weights," in *,variable,*) _variable=true ;; esac
  _family_type=single
  [ "$_weight_count" -ge 2 ] 2>/dev/null && _family_type=static-family
  [ "$_variable" = true ] && _family_type=variable
  _date=$(stat -c '%y' "$_file" 2>/dev/null | cut -c1-10)
  _display_name="$_family"
  _supports_cjk=true
  _cfg="$USER_FONTS_DIR/${_family}.conf"
  if [ -f "$_cfg" ]; then
      _configured_name=$(sed -n 's/^name=//p' "$_cfg" 2>/dev/null | head -n1 | tr -d '
')
      [ -n "$_configured_name" ] && _display_name="$_configured_name"
      _configured_cjk=$(sed -n 's/^supports_cjk=//p' "$_cfg" 2>/dev/null | head -n1 | tr -d '
')
      case "$_configured_cjk" in true) _supports_cjk=true ;; false) _supports_cjk=false ;; esac
  fi

  [ "$_first" = true ] || printf ','
  printf '{"id":"%s","name":"%s","weights":[%s],"variants":{%s},"familyType":"%s","file":"%s","size":"%s","bytes":%s,"format":"%s","valid":%s,"warning":"","error":"%s","variable":%s,"supportsCjk":%s,"date":"%s"}' \
      "$(json_escape "$_family")" "$(json_escape "$_display_name")" "$_weights_json" "$_variants_json" "$(json_escape "$_family_type")" \
      "$(json_escape "$_record_name")" "$(format_filesize "$_bytes")" "$_bytes" "$(json_escape "$_format")" "$_valid" \
      "$(json_escape "$_error")" "$_variable" "$_supports_cjk" "$(json_escape "$_date")"
  _first=false
        done < "$_families"
        printf ']}}
'
    } > "$_output" 2>/dev/null
    _result=$?
    rm -f "$_manifest" "$_families" 2>/dev/null || true
    if [ "$_result" -ne 0 ] || [ ! -s "$_output" ]; then
        rm -f "$_output" 2>/dev/null || true
        printf '{"status":"error","message":"字体索引生成失败"}
'
        return 1
    fi
    mv -f "$_output" "$FONT_INDEX_JSON" 2>/dev/null || {
        rm -f "$_output" 2>/dev/null || true
        printf '{"status":"error","message":"字体索引缓存写入失败"}
'
        return 1
    }
    printf '%s
' "$_cache_key" > "$FONT_INDEX_KEY" 2>/dev/null || true
    chmod 0644 "$FONT_INDEX_JSON" "$FONT_INDEX_KEY" 2>/dev/null || true
    cat "$FONT_INDEX_JSON"
}

validate_font_json() {
    _font_id="$1"
    _file="$(find_text_font_file "$_font_id")"
    [ -f "$_file" ] || { printf '{"status":"error","message":"未找到字体"}
'; return 0; }
    if type luoshu_font_validate_global_cached >/dev/null 2>&1; then
        if luoshu_font_validate_global_cached "$_file"; then
  printf '{"status":"ok","data":{"valid":true,"format":"%s","bytes":%s,"variable":%s,"color":%s,"cached":%s,"warning":"%s"}}
' \
      "$(json_escape "$FONT_CHECK_FORMAT")" "${FONT_CHECK_SIZE:-0}" "${FONT_CHECK_VARIABLE:-false}" "${FONT_CHECK_COLOR:-false}" \
      "${LUOSHU_FONT_VALIDATION_CACHE_HIT:-false}" "$(json_escape "$FONT_CHECK_WARNING")"
        else
  printf '{"status":"ok","data":{"valid":false,"format":"%s","bytes":%s,"variable":%s,"color":%s,"cached":false,"error":"%s"}}
' \
      "$(json_escape "$FONT_CHECK_FORMAT")" "${FONT_CHECK_SIZE:-0}" "${FONT_CHECK_VARIABLE:-false}" "${FONT_CHECK_COLOR:-false}" "$(json_escape "$FONT_CHECK_ERROR")"
        fi
    elif type font_validate_global >/dev/null 2>&1; then
        if font_validate_global "$_file"; then
  printf '{"status":"ok","data":{"valid":true,"format":"%s","bytes":%s,"variable":%s,"color":%s,"cached":false,"warning":"%s"}}
' \
      "$(json_escape "$FONT_CHECK_FORMAT")" "${FONT_CHECK_SIZE:-0}" "${FONT_CHECK_VARIABLE:-false}" "${FONT_CHECK_COLOR:-false}" "$(json_escape "$FONT_CHECK_WARNING")"
        else
  printf '{"status":"ok","data":{"valid":false,"format":"%s","bytes":%s,"variable":%s,"color":%s,"cached":false,"error":"%s"}}
' \
      "$(json_escape "$FONT_CHECK_FORMAT")" "${FONT_CHECK_SIZE:-0}" "${FONT_CHECK_VARIABLE:-false}" "${FONT_CHECK_COLOR:-false}" "$(json_escape "$FONT_CHECK_ERROR")"
        fi
    elif type font_check_json >/dev/null 2>&1; then
        _check="$(font_check_json "$_file" text 2>/dev/null | tr -d '
')"
        [ -n "$_check" ] || _check='{"valid":false,"error":"字体验证器未返回结果"}'
        printf '{"status":"ok","data":%s}
' "$_check"
    else
        printf '{"status":"error","message":"字体验证器不可用"}
'
    fi
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
        switch)
            if switch_font "$_param"; then
                if [ "$LUOSHU_SWITCH_REUSED" = true ]; then
                    printf '{"status":"ok","data":{"font":"%s","reused":true,"message":"当前字体已验证，无需重新生成或重启"}}\n' "$(json_escape "$_param")"
                else
                    printf '{"status":"ok","data":{"font":"%s","reused":false,"message":"已准备，重启手机后生效"}}\n' "$(json_escape "$_param")"
                fi
            else
                printf '{"status":"error","message":"切换失败"}\n'
            fi
            ;;
        switch_async) MODDIR="$MODULE_DIR" sh "$MODULE_DIR/common/font_switch_task.sh" start "$_param" ;;
        switch_status) MODDIR="$MODULE_DIR" sh "$MODULE_DIR/common/font_switch_task.sh" status "$_param" ;;
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
            (svc power reboot 2>/dev/null || reboot 2>/dev/null) </dev/null >/dev/null 2>&1 &
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
