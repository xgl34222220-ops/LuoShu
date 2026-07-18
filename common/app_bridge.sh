#!/system/bin/sh
# 洛书 Hybrid App 原生核心桥：状态、字体库、原生预览、轴能力、字体切换与复合任务接口。
set +e

MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then
        MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"
    else
        MODDIR="/data/adb/modules/LuoShu"
    fi
fi
FONT_MANAGER="$MODDIR/common/font_manager.sh"
MIX_ENGINE="$MODDIR/common/v142_weighted_mix.sh"
APP_MULTI_ENGINE="$MODDIR/common/app_multiweight_mix.sh"
APP_MODE_CONF="$MODDIR/config/app_weight_mode.conf"
AXIS_INFO="$MODDIR/common/font_axis_info.py"
PYROOT="$MODDIR/common/python"
PYBIN="$PYROOT/bin/luoshu-python"
USER_FONTS_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}/fonts"
[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"
[ -f "$MODDIR/common/font_check.sh" ] && . "$MODDIR/common/font_check.sh"

json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
}

read_prop() {
    sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n'
}

root_manager() {
    if command -v apd >/dev/null 2>&1 || [ -d /data/adb/ap ] || [ -d /data/adb/apatch ]; then
        printf 'APatch'
    elif command -v ksud >/dev/null 2>&1 || [ -d /data/adb/ksu ]; then
        _info="$(ksud -V 2>/dev/null || ksud --version 2>/dev/null)"
        case "$_info $(getprop ro.build.version.incremental 2>/dev/null)" in
            *SukiSU*|*sukisu*|*SUKISU*) printf 'SukiSU Ultra' ;;
            *) printf 'KernelSU' ;;
        esac
    elif command -v magisk >/dev/null 2>&1 || [ -d /data/adb/magisk ]; then
        printf 'Magisk'
    else
        printf 'Root'
    fi
}

mount_engine() {
    if { [ -d /data/adb/modules/mountify ] && [ ! -f /data/adb/modules/mountify/disable ] && [ ! -f /data/adb/modules/mountify/remove ]; } || [ -d /data/adb/mountify ]; then
        printf 'Mountify'
    else
        printf '原生模块挂载'
    fi
}

status_json() {
    _installed=false
    _version='未安装'
    _version_code=0
    if [ -f "$MODDIR/module.prop" ]; then
        _installed=true
        _version="$(read_prop "$MODDIR/module.prop" version)"
        _version_code="$(read_prop "$MODDIR/module.prop" versionCode)"
    fi
    _active="$(head -n1 "$MODDIR/config/active_font.conf" 2>/dev/null | tr -d '\r\n')"
    [ -n "$_active" ] || _active='default'

    _task_file=""
    _task_mtime=-1
    for _candidate in "$MODDIR/config/app_multiweight_task.conf" "$MODDIR/config/v143_axes_task.conf" "$MODDIR/config/mix_task.conf"; do
        [ -s "$_candidate" ] || continue
        _mtime=$(stat -c %Y "$_candidate" 2>/dev/null || echo 0)
        case "$_mtime" in ''|*[!0-9]*) _mtime=0 ;; esac
        if [ "$_mtime" -gt "$_task_mtime" ] 2>/dev/null; then _task_file="$_candidate"; _task_mtime="$_mtime"; fi
    done
    _task_state="$(read_prop "$_task_file" state)"
    _task_message="$(read_prop "$_task_file" message)"
    [ -n "$_task_state" ] || _task_state='idle'
    [ -n "$_task_message" ] || _task_message='暂无后台任务'

    printf '{"status":"ok","data":{"root":true,"installed":%s,"version":"%s","versionCode":%s,"active":"%s","taskState":"%s","taskMessage":"%s","rootManager":"%s","mountEngine":"%s","moduleDir":"%s"}}\n' \
        "$_installed" "$(json_escape "$_version")" "${_version_code:-0}" "$(json_escape "$_active")" \
        "$(json_escape "$_task_state")" "$(json_escape "$_task_message")" "$(json_escape "$(root_manager)")" \
        "$(json_escape "$(mount_engine)")" "$(json_escape "$MODDIR")"
}

manager_ready() {
    [ -x "$FONT_MANAGER" ] || [ -f "$FONT_MANAGER" ] || {
        printf '{"status":"error","message":"字体管理器不存在"}\n'
        return 1
    }
    return 0
}

mix_ready() {
    [ -x "$MIX_ENGINE" ] || [ -f "$MIX_ENGINE" ] || {
        printf '{"status":"error","message":"复合字体引擎不存在"}\n'
        return 1
    }
    return 0
}

find_preview_source() {
    _family="$1"
    for _f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \
              "$USER_FONTS_DIR"/*.TTF "$USER_FONTS_DIR"/*.OTF "$USER_FONTS_DIR"/*.TTC; do
        [ -f "$_f" ] || continue
        if type detect_font_family >/dev/null 2>&1; then
            _detected="$(detect_font_family "$(basename "$_f")")"
        else
            _detected="$(basename "$_f")"; _detected="${_detected%.*}"; _detected="${_detected%-Regular}"
        fi
        [ "$_detected" = "$_family" ] && { printf '%s\n' "$_f"; return 0; }
    done
    return 1
}

preview_export() {
    _family="$1"
    _dest="$2"
    case "$_dest" in
        /data/user/0/io.github.xgl34222220.luoshu/cache/*|/data/data/io.github.xgl34222220.luoshu/cache/*|\
        /data/user/0/io.github.xgl34222220.luoshu.debug/cache/*|/data/data/io.github.xgl34222220.luoshu.debug/cache/*) ;;
        *) printf '{"status":"error","message":"预览目标目录不受信任"}\n'; return 1 ;;
    esac
    _src="$(find_preview_source "$_family")"
    [ -f "$_src" ] || { printf '{"status":"error","message":"找不到预览字体"}\n'; return 1; }
    mkdir -p "${_dest%/*}" 2>/dev/null || true
    cp -f "$_src" "$_dest" 2>/dev/null || { printf '{"status":"error","message":"无法导出预览字体"}\n'; return 1; }
    chmod 0644 "$_dest" 2>/dev/null || true
    printf '{"status":"ok","data":{"path":"%s"}}\n' "$(json_escape "$_dest")"
}

weight_axis_info() {
    _family="$1"
    _src="$(find_preview_source "$_family")"
    [ -f "$_src" ] || { printf '{"status":"error","message":"找不到字体轴来源"}\n'; return 1; }
    [ -f "$AXIS_INFO" ] && [ -x "$PYBIN" ] || { printf '{"status":"error","message":"字体轴分析器不可用"}\n'; return 1; }
    export PYTHONHOME="$PYROOT"
    export PYTHONPATH="$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages"
    export LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    "$PYBIN" "$AXIS_INFO" "$_src"
}

app_cache_path_allowed() {
    case "$1" in
        /data/user/0/io.github.xgl34222220.luoshu/cache/font-import/*|/data/data/io.github.xgl34222220.luoshu/cache/font-import/*|\
        /data/user/0/io.github.xgl34222220.luoshu.debug/cache/font-import/*|/data/data/io.github.xgl34222220.luoshu.debug/cache/font-import/*) return 0 ;;
        *) return 1 ;;
    esac
}

import_font() {
    _src="$1"
    _requested=$(printf '%s' "$2" | tr -d '\r\n')
    app_cache_path_allowed "$_src" || { printf '{"status":"error","message":"字体来源不是受信任的 App 私有缓存"}\n'; return 1; }
    [ -f "$_src" ] || { printf '{"status":"error","message":"所选字体缓存不存在"}\n'; return 1; }
    _name=$(basename "$_requested")
    [ -n "$_name" ] || _name=$(basename "$_src")
    case "$_name" in ''|.|..|*/*|*\\*) printf '{"status":"error","message":"字体文件名无效"}\n'; return 1 ;; esac
    _ext=${_name##*.}
    case "$_ext" in ttf|TTF|otf|OTF|ttc|TTC) ;; *) printf '{"status":"error","message":"仅支持 TTF、OTF 或 TTC 字体"}\n'; return 1 ;; esac
    _size=$(wc -c <"$_src" 2>/dev/null | tr -d '[:space:]')
    case "$_size" in ''|*[!0-9]*) _size=0 ;; esac
    [ "$_size" -ge 12 ] 2>/dev/null && [ "$_size" -le 134217728 ] 2>/dev/null || { printf '{"status":"error","message":"字体文件大小异常或超过 128 MB"}\n'; return 1; }
    type ensure_public_storage >/dev/null 2>&1 && ensure_public_storage
    mkdir -p "$USER_FONTS_DIR" 2>/dev/null || { printf '{"status":"error","message":"无法创建用户字体目录"}\n'; return 1; }
    _stem=${_name%.*}; _dest="$USER_FONTS_DIR/$_name"
    if [ -f "$_dest" ]; then
        if cmp -s "$_src" "$_dest" 2>/dev/null; then
            _family=$(detect_font_family "$_name")
            printf '{"status":"ok","data":{"imported":false,"duplicate":true,"file":"%s","family":"%s"}}\n' "$(json_escape "$_name")" "$(json_escape "$_family")"
            return 0
        fi
        _index=2
        while [ -e "$_dest" ]; do
            _name="${_stem}-${_index}.${_ext}"; _dest="$USER_FONTS_DIR/$_name"; _index=$((_index + 1))
        done
    fi
    _tmp="$USER_FONTS_DIR/.app-import-$$-${_name}"
    rm -f "$_tmp" 2>/dev/null || true
    cp -f "$_src" "$_tmp" 2>/dev/null || { printf '{"status":"error","message":"无法复制字体到用户目录"}\n'; return 1; }
    chmod 0644 "$_tmp" 2>/dev/null || true
    if type font_validate >/dev/null 2>&1 && ! font_validate "$_tmp" text; then
        _error=${FONT_CHECK_ERROR:-字体文件校验失败}
        rm -f "$_tmp" 2>/dev/null || true
        printf '{"status":"error","message":"%s"}\n' "$(json_escape "$_error")"
        return 1
    fi
    mv -f "$_tmp" "$_dest" 2>/dev/null || { rm -f "$_tmp"; printf '{"status":"error","message":"无法提交字体文件"}\n'; return 1; }
    chmod 0644 "$_dest" 2>/dev/null || true
    rm -f "$MODDIR/config/webui_font_list.json" "$MODDIR/config/webui_font_list.key" 2>/dev/null || true
    _family=$(detect_font_family "$_name")
    printf '{"status":"ok","data":{"imported":true,"duplicate":false,"file":"%s","family":"%s","size":%s}}\n' "$(json_escape "$_name")" "$(json_escape "$_family")" "$_size"
}

spec_auto() { [ "$1" = auto ]; }
write_app_weight_mode() {
    _ca=false; spec_auto "$1" && _ca=true
    _la=false; spec_auto "$2" && _la=true
    _da=false; spec_auto "$3" && _da=true
    mkdir -p "${APP_MODE_CONF%/*}" 2>/dev/null || true
    _tmp="${APP_MODE_CONF}.tmp.$$"
    printf 'cjkAuto=%s\nlatinAuto=%s\ndigitAuto=%s\n' "$_ca" "$_la" "$_da" >"$_tmp" 2>/dev/null && mv -f "$_tmp" "$APP_MODE_CONF" 2>/dev/null
    chmod 0644 "$APP_MODE_CONF" 2>/dev/null || true
}

case "${1:-status}" in
    status)
        status_json
        ;;
    fonts)
        manager_ready || exit 1
        if [ "${2:-}" = refresh ]; then
            sh "$FONT_MANAGER" action list refresh
        else
            sh "$FONT_MANAGER" action list
        fi
        ;;
    preview_export)
        preview_export "${2:-}" "${3:-}"
        ;;
    weight_axis)
        weight_axis_info "${2:-}"
        ;;
    validate)
        manager_ready || exit 1
        sh "$FONT_MANAGER" action validate "${2:-}"
        ;;
    switch_start)
        manager_ready || exit 1
        sh "$FONT_MANAGER" action switch_async "${2:-default}"
        ;;
    switch_status)
        manager_ready || exit 1
        sh "$FONT_MANAGER" action switch_status "${2:-}"
        ;;
    delete)
        manager_ready || exit 1
        sh "$FONT_MANAGER" action delete "${2:-}"
        ;;
    import)
        import_font "${2:-}" "${3:-}"
        ;;
    mix_config)
        if [ -f "$APP_MULTI_ENGINE" ]; then sh "$APP_MULTI_ENGINE" config; else mix_ready || exit 1; sh "$MIX_ENGINE" config; fi
        ;;
    mix_start)
        _ca="${5:-auto}"; _la="${6:-auto}"; _da="${7:-auto}"
        write_app_weight_mode "$_ca" "$_la" "$_da"
        case "$_ca $_la $_da" in
            *auto*) [ -f "$APP_MULTI_ENGINE" ] || { printf '{"status":"error","message":"APP 多字重引擎不存在"}\n'; exit 1; }; sh "$APP_MULTI_ENGINE" start "${2:-}" "${3:-}" "${4:-}" "$_ca" "$_la" "$_da" ;;
            *) mix_ready || exit 1; sh "$MIX_ENGINE" start "${2:-}" "${3:-}" "${4:-}" "$_ca" "$_la" "$_da" ;;
        esac
        ;;
    mix_status)
        case "${2:-}" in appmw-*) [ -f "$APP_MULTI_ENGINE" ] || exit 1; sh "$APP_MULTI_ENGINE" status "${2:-}" ;; *) mix_ready || exit 1; sh "$MIX_ENGINE" status "${2:-}" ;; esac
        ;;
    reboot)
        manager_ready || exit 1
        sh "$FONT_MANAGER" action reboot_device
        ;;
    logs)
        _lines="${2:-160}"
        case "$_lines" in ''|*[!0-9]*) _lines=160 ;; esac
        [ "$_lines" -le 500 ] 2>/dev/null || _lines=500
        tail -n "$_lines" "$MODDIR/logs/fontswitch.log" 2>/dev/null
        ;;
    *)
        printf '{"status":"error","message":"未知 App 桥命令"}\n'
        ;;
esac
exit 0
