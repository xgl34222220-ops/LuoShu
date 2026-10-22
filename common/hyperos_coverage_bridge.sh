#!/system/bin/sh
# App bridge for font coverage: status, HyperOS settings and the locator.
#   status                     JSON: ROM (hyperos/coloros/other), HyperOS optional
#                              slot groups, seed-XML rewrite, theme-store state
#   set <key> <0|1>            HyperOS only: group:miui_ex | group:misans_ext |
#                              group:lockscreen_styles | xml | theme_takeover
#   locate <package>           JSON from common/font_coverage_locator.py (any ROM)
#   scan                       JSON: running processes without LuoShu's font (any ROM)
#   export                     JSON {path,bytes}: one sanitized full coverage report
#                              /sdcard/LuoShu/reports/LuoShu-coverage-full-<time>.json
# Settings only write config files; they take effect after the next apply/reboot,
# which the JSON says so the App can tell the user.
set +e

MODDIR="${MODDIR:-${LUOSHU_REAL_MODDIR:-/data/adb/modules/LuoShu}}"
CONFIG="$MODDIR/config"
GROUPS_CONF="${LUOSHU_HYPEROS_SLOT_GROUPS_CONF:-$CONFIG/hyperos_slot_groups.conf}"
XML_CONF="${LUOSHU_HYPEROS_SOURCE_XML_CONF:-$CONFIG/hyperos_source_xml.conf}"
TAKEOVER_CONF="${LUOSHU_THEME_TAKEOVER_CONF:-$CONFIG/hyperos_theme_takeover.conf}"
PYROOT="$MODDIR/common/python"
PYBIN="${LUOSHU_COVERAGE_PYTHON:-$PYROOT/bin/luoshu-python}"

_hcb_json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r\t' '   '
}

_hcb_is_hyperos() {
    [ "${IS_HYPEROS:-}" = true ] && return 0
    [ "${IS_HYPEROS:-}" = false ] && return 1
    [ -n "$(getprop ro.mi.os.version.name 2>/dev/null)$(getprop ro.miui.ui.version.name 2>/dev/null)" ]
}

# hyperos | coloros | other. Same markers as util_functions / mix_router.
_hcb_rom() {
    case "${LUOSHU_COVERAGE_ROM:-}" in hyperos|coloros|other) printf '%s\n' "$LUOSHU_COVERAGE_ROM"; return 0 ;; esac
    if _hcb_is_hyperos; then printf 'hyperos\n'; return 0; fi
    if [ -n "$(getprop ro.build.version.oplusrom 2>/dev/null)$(getprop ro.build.version.opporom 2>/dev/null)$(getprop ro.oxygen.version 2>/dev/null)" ] || \
       [ -d /data/oplus/os ] || [ -d /system_ext/oplus ]; then
        printf 'coloros\n'; return 0
    fi
    printf 'other\n'
}

# Same defaults/rule as hyperos_physical_policy.parse_groups.
_hcb_group_value() {
    case "$1" in lockscreen_styles) _hcb_default=0 ;; *) _hcb_default=1 ;; esac
    _hcb_value=$(sed -n "s/^$1=\\([01]\\)\\r\\{0,1\\}\$/\\1/p" "$GROUPS_CONF" 2>/dev/null | tail -n1)
    printf '%s\n' "${_hcb_value:-$_hcb_default}"
}

_hcb_bool() { [ "$1" = 1 ] && printf true || printf false; }

_hcb_write() {
    _hcb_target="$1"; shift
    mkdir -p "${_hcb_target%/*}" 2>/dev/null || return 1
    _hcb_tmp="${_hcb_target}.tmp.$$"
    printf '%s\n' "$@" > "$_hcb_tmp" 2>/dev/null || { rm -f "$_hcb_tmp"; return 1; }
    chmod 0644 "$_hcb_tmp" 2>/dev/null || true
    mv -f "$_hcb_tmp" "$_hcb_target"
}

hcb_status() {
    _hcb_rom=false; _hcb_is_hyperos && _hcb_rom=true
    _hcb_family=$(_hcb_rom)
    _hcb_xml=true
    grep -qx 'enabled=0' "$XML_CONF" 2>/dev/null && _hcb_xml=false
    _hcb_state=none; _hcb_files=0; _hcb_user=0; _hcb_own=0; _hcb_names=''; _hcb_take=0; _hcb_owned=0
    if [ -f "$MODDIR/common/hyperos_theme_takeover.sh" ]; then
        _hcb_kv=$(MODDIR="$MODDIR" LUOSHU_REAL_MODDIR="$MODDIR" LUOSHU_THEME_TAKEOVER_CONF="$TAKEOVER_CONF" \
            sh "$MODDIR/common/hyperos_theme_takeover.sh" status 2>/dev/null)
        _hcb_state=$(printf '%s\n' "$_hcb_kv" | sed -n 's/^state=//p' | head -n1)
        _hcb_files=$(printf '%s\n' "$_hcb_kv" | sed -n 's/^files=//p' | head -n1)
        _hcb_user=$(printf '%s\n' "$_hcb_kv" | sed -n 's/^userFiles=//p' | head -n1)
        _hcb_own=$(printf '%s\n' "$_hcb_kv" | sed -n 's/^luoshuFiles=//p' | head -n1)
        _hcb_names=$(printf '%s\n' "$_hcb_kv" | sed -n 's/^names=//p' | head -n1)
        _hcb_take=$(printf '%s\n' "$_hcb_kv" | sed -n 's/^takeover=//p' | head -n1)
        _hcb_owned=$(printf '%s\n' "$_hcb_kv" | sed -n 's/^owned=//p' | head -n1)
    fi
    case "$_hcb_state" in none|placeholder|user-theme) ;; *) _hcb_state=none ;; esac
    case "$_hcb_files" in ''|*[!0-9]*) _hcb_files=0 ;; esac
    case "$_hcb_user" in ''|*[!0-9]*) _hcb_user=0 ;; esac
    case "$_hcb_own" in ''|*[!0-9]*) _hcb_own=0 ;; esac
    printf '{"status":"ok","data":{"hyperos":%s,"rom":"%s","groups":{"miui_ex":%s,"misans_ext":%s,"lockscreen_styles":%s},' \
        "$_hcb_rom" "$_hcb_family" "$(_hcb_bool "$(_hcb_group_value miui_ex)")" \
        "$(_hcb_bool "$(_hcb_group_value misans_ext)")" "$(_hcb_bool "$(_hcb_group_value lockscreen_styles)")"
    printf '"sourceXml":%s,"theme":{"state":"%s","files":%s,"userFiles":%s,"luoshuFiles":%s,"names":"%s","takeover":%s,"owned":%s}}}\n' \
        "$_hcb_xml" "$_hcb_state" "$_hcb_files" "$_hcb_user" "$_hcb_own" "$(_hcb_json_escape "$_hcb_names")" \
        "$(_hcb_bool "$_hcb_take")" "$(_hcb_bool "$_hcb_owned")"
}

hcb_set() {
    _hcb_key="$1"; _hcb_val="$2"
    case "$_hcb_val" in 0|1) ;; *) printf '{"status":"error","message":"设置值只能是 0 或 1"}\n'; return 1 ;; esac
    case "$_hcb_key" in
        group:miui_ex|group:misans_ext|group:lockscreen_styles)
            _hcb_group=${_hcb_key#group:}
            _hcb_lines=''
            for _hcb_g in miui_ex misans_ext lockscreen_styles; do
                if [ "$_hcb_g" = "$_hcb_group" ]; then _hcb_v=$_hcb_val; else _hcb_v=$(_hcb_group_value "$_hcb_g"); fi
                _hcb_lines="$_hcb_lines $_hcb_g=$_hcb_v"
            done
            # shellcheck disable=SC2086
            _hcb_write "$GROUPS_CONF" '# HyperOS optional slot groups (LuoShu App)' $_hcb_lines || {
                printf '{"status":"error","message":"无法写入设置"}\n'; return 1; }
            _hcb_reapply=true
            ;;
        xml)
            _hcb_write "$XML_CONF" "enabled=$_hcb_val" || { printf '{"status":"error","message":"无法写入设置"}\n'; return 1; }
            _hcb_reapply=true
            ;;
        theme_takeover)
            _hcb_write "$TAKEOVER_CONF" "enabled=$_hcb_val" || { printf '{"status":"error","message":"无法写入设置"}\n'; return 1; }
            _hcb_reapply=false
            ;;
        *) printf '{"status":"error","message":"未知设置项"}\n'; return 1 ;;
    esac
    printf '{"status":"ok","data":{"key":"%s","value":%s,"needsReapply":%s,"needsReboot":true}}\n' \
        "$(_hcb_json_escape "$_hcb_key")" "$(_hcb_bool "$_hcb_val")" "$_hcb_reapply"
}

_hcb_python_env() {
    if [ "$PYBIN" = "$PYROOT/bin/luoshu-python" ]; then
        export PYTHONHOME="$PYROOT"
        export PYTHONPATH="$MODDIR/common:$PYROOT/lib/python3.14:$PYROOT/lib/python3.14/site-packages"
        export LD_LIBRARY_PATH="$PYROOT/lib:$PYROOT/lib/python3.14/lib-dynload${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    fi
}

hcb_scan() {
    _hcb_helper="$MODDIR/common/font_coverage_locator.py"
    if [ ! -f "$_hcb_helper" ] || [ ! -x "$PYBIN" ]; then
        printf '{"status":"error","message":"定位组件不可用，请先安装匹配版本的模块"}\n'
        return 1
    fi
    _hcb_python_env
    "$PYBIN" "$_hcb_helper" --scan --module "$MODDIR" --rom "$(_hcb_rom)" \
        ${LUOSHU_COVERAGE_PROC_ROOT:+--proc-root "$LUOSHU_COVERAGE_PROC_ROOT"} \
        ${LUOSHU_COVERAGE_THEME_DIR:+--theme-dir "$LUOSHU_COVERAGE_THEME_DIR"}
}

hcb_locate() {
    _hcb_pkg="$1"
    case "$_hcb_pkg" in
        ''|*[!A-Za-z0-9._:]*|.*|*..*) printf '{"status":"error","message":"包名格式不正确"}\n'; return 1 ;;
    esac
    _hcb_pid=$(pidof "$_hcb_pkg" 2>/dev/null | awk '{print $1}')
    [ -n "${LUOSHU_COVERAGE_PID:-}" ] && _hcb_pid=$LUOSHU_COVERAGE_PID
    _hcb_helper="$MODDIR/common/font_coverage_locator.py"
    if [ ! -f "$_hcb_helper" ] || [ ! -x "$PYBIN" ]; then
        printf '{"status":"error","message":"定位组件不可用，请先安装匹配版本的模块"}\n'
        return 1
    fi
    _hcb_python_env
    "$PYBIN" "$_hcb_helper" --package "$_hcb_pkg" --pid "${_hcb_pid:-}" --module "$MODDIR" --rom "$(_hcb_rom)" \
        ${LUOSHU_COVERAGE_PROC_ROOT:+--proc-root "$LUOSHU_COVERAGE_PROC_ROOT"} \
        ${LUOSHU_COVERAGE_THEME_DIR:+--theme-dir "$LUOSHU_COVERAGE_THEME_DIR"}
}

_hcb_root_manager() {
    if command -v apd >/dev/null 2>&1 || [ -d /data/adb/ap ] || [ -d /data/adb/apatch ]; then
        printf 'APatch\n'
    elif command -v ksud >/dev/null 2>&1 || [ -d /data/adb/ksu ]; then
        printf 'KernelSU\n'
    elif command -v magisk >/dev/null 2>&1 || [ -d /data/adb/magisk ]; then
        printf 'Magisk\n'
    else
        printf 'Root\n'
    fi
}

# One file with every coverage fact (sanitized like the existing diagnostic).
hcb_export() {
    _hcb_helper="$MODDIR/common/font_coverage_locator.py"
    if [ ! -f "$_hcb_helper" ] || [ ! -x "$PYBIN" ]; then
        printf '{"status":"error","message":"诊断组件不可用，请先安装匹配版本的模块"}\n'
        return 1
    fi
    _hcb_dir="${LUOSHU_COVERAGE_REPORT_DIR:-/sdcard/LuoShu/reports}"
    mkdir -p "$_hcb_dir" 2>/dev/null || { printf '{"status":"error","message":"无法创建报告目录"}\n'; return 1; }
    _hcb_family=$(_hcb_rom)
    case "$_hcb_family" in
        hyperos) _hcb_romver="$(getprop ro.mi.os.version.name 2>/dev/null)$(getprop ro.miui.ui.version.name 2>/dev/null)" ;;
        coloros) _hcb_romver="$(getprop ro.build.version.oplusrom 2>/dev/null)$(getprop ro.oxygen.version 2>/dev/null)" ;;
        *) _hcb_romver="$(getprop ro.build.version.release 2>/dev/null)" ;;
    esac
    _hcb_python_env
    "$PYBIN" "$_hcb_helper" --export "$_hcb_dir" --module "$MODDIR" --rom "$_hcb_family" \
        --device "romVersion=${_hcb_romver:-unknown}" \
        --device "androidSdk=$(getprop ro.build.version.sdk 2>/dev/null)" \
        --device "rootManager=$(_hcb_root_manager)" \
        ${LUOSHU_COVERAGE_PROC_ROOT:+--proc-root "$LUOSHU_COVERAGE_PROC_ROOT"} \
        ${LUOSHU_COVERAGE_HOST_ROOT:+--host-root "$LUOSHU_COVERAGE_HOST_ROOT"} \
        ${LUOSHU_COVERAGE_THEME_DIR:+--theme-dir "$LUOSHU_COVERAGE_THEME_DIR"}
}

case "${1:-status}" in
    status) hcb_status ;;
    set)
        if [ "$(_hcb_rom)" != hyperos ]; then
            printf '{"status":"error","message":"该设置仅适用于 HyperOS"}\n'
        else
            hcb_set "${2:-}" "${3:-}"
        fi
        ;;
    locate) hcb_locate "${2:-}" ;;
    scan) hcb_scan ;;
    export) hcb_export ;;
    *) printf '{"status":"error","message":"未知覆盖定位命令"}\n' ;;
esac
exit 0
