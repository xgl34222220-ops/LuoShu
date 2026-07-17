#!/system/bin/sh
# 洛书 v14.1：轻量字体切换桥。启动事务引擎，状态查询只读取任务文件。
set +e
MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"; else MODDIR="/data/adb/modules/LuoShu"; fi
fi
ENGINE="$MODDIR/common/font_switch_v141.sh"
TASK_FILE="$MODDIR/config/switch_task.conf"
STATUS_SCRIPT="$MODDIR/common/module_status.sh"
json_escape(){ printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '; }
read_value(){ sed -n "s/^${1}=//p" "$TASK_FILE" 2>/dev/null | head -n1 | tr -d '\r\n'; }
case "${1:-status}" in
    start) sh "$ENGINE" start "$2" ;;
    status)
        _wanted="$2"
        [ -s "$TASK_FILE" ] || { printf '{"status":"error","message":"暂无切换任务"}\n'; exit 0; }
        _task=$(read_value task); _state=$(read_value state); _font=$(read_value font); _message=$(read_value message)
        _started=$(read_value started); _finished=$(read_value finished)
        [ -z "$_wanted" ] || [ "$_wanted" = "$_task" ] || { printf '{"status":"error","message":"任务不存在或已被新任务替换"}\n'; exit 0; }
        if [ "$_state" = success ] && [ -f "$STATUS_SCRIPT" ]; then MODDIR="$MODDIR" sh "$STATUS_SCRIPT" "$_font" >/dev/null 2>&1 || true; fi
        printf '{"status":"ok","data":{"task":"%s","state":"%s","font":"%s","message":"%s","started":%s,"finished":%s}}\n' \
            "$(json_escape "$_task")" "$(json_escape "$_state")" "$(json_escape "$_font")" "$(json_escape "$_message")" "${_started:-0}" "${_finished:-0}"
        ;;
    *) printf '{"status":"error","message":"未知切换命令"}\n' ;;
esac
exit 0
