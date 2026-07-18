#!/system/bin/sh
# 洛书 Hybrid App 统一桥：为原生页面提供稳定 JSON 状态、字体库和任务接口。
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

    _task_file="$MODDIR/config/v143_axis_task.conf"
    [ -s "$_task_file" ] || _task_file="$MODDIR/config/mix_task.conf"
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
    webroot)
        printf '%s\n' "$MODDIR/webroot/index.html"
        ;;
    *)
        printf '{"status":"error","message":"未知 App 桥命令"}\n'
        ;;
esac
exit 0
