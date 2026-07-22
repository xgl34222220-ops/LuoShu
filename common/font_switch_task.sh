#!/system/bin/sh
# 洛书 v2.0.0：轻量字体切换任务。状态查询不会重复扫描字体索引。
set +e

MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then
        MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"
    else
        MODDIR="/data/adb/modules/LuoShu"
    fi
fi

MANAGER="$MODDIR/common/font_manager.sh"
TASK_FILE="$MODDIR/config/switch_task.conf"
STATUS_SCRIPT="$MODDIR/common/module_status.sh"

json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '
}

read_value() {
    _key="$1"
    sed -n "s/^${_key}=//p" "$TASK_FILE" 2>/dev/null | head -n1 | tr -d '\r\n'
}

case "${1:-status}" in
    start)
        _font="$2"
        [ -n "$_font" ] || { printf '{"status":"error","message":"未指定字体"}\n'; exit 0; }
        sh "$MANAGER" action switch_async "$_font"
        ;;
    status)
        _wanted="$2"
        if [ ! -s "$TASK_FILE" ]; then
            printf '{"status":"error","message":"暂无切换任务"}\n'
            exit 0
        fi
        _task=$(read_value task)
        _state=$(read_value state)
        _font=$(read_value font)
        _message=$(read_value message)
        _started=$(read_value started)
        _finished=$(read_value finished)
        if [ -n "$_wanted" ] && [ "$_wanted" != "$_task" ]; then
            printf '{"status":"error","message":"任务不存在或已被新任务替换"}\n'
            exit 0
        fi
        if [ "$_state" = "success" ] && [ -f "$STATUS_SCRIPT" ]; then
            MODDIR="$MODDIR" sh "$STATUS_SCRIPT" "$_font" >/dev/null 2>&1 || true
        fi
        printf '{"status":"ok","data":{"task":"%s","state":"%s","font":"%s","message":"%s","started":%s,"finished":%s}}\n' \
            "$(json_escape "$_task")" "$(json_escape "$_state")" "$(json_escape "$_font")" "$(json_escape "$_message")" \
            "${_started:-0}" "${_finished:-0}"
        ;;
    *)
        printf '{"status":"error","message":"未知切换命令"}\n'
        ;;
esac
exit 0
