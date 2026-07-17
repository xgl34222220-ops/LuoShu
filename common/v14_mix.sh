#!/system/bin/sh
# 洛书 v14：字体组合轻量桥，轮询仅读取任务文件。
set +e
MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"; else MODDIR="/data/adb/modules/LuoShu"; fi
fi
ENGINE="$MODDIR/common/font_mix.sh"
TASK_FILE="$MODDIR/config/mix_task.conf"
STATUS_SCRIPT="$MODDIR/common/module_status.sh"
json_escape(){ printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '; }
read_value(){ sed -n "s/^${1}=//p" "$TASK_FILE" 2>/dev/null | head -n1 | tr -d '\r\n'; }
case "${1:-status}" in
    start) sh "$ENGINE" start "$2" "$3" "$4" "$5" "$6" "$7" ;;
    config) sh "$ENGINE" status ;;
    status)
        _wanted="$2"
        [ -s "$TASK_FILE" ] || { printf '{"status":"error","message":"暂无组合任务"}\n'; exit 0; }
        _task=$(read_value task); _state=$(read_value state); _message=$(read_value message)
        _cjk=$(read_value cjk); _latin=$(read_value latin); _digit=$(read_value digit)
        _started=$(read_value started); _finished=$(read_value finished)
        [ -z "$_wanted" ] || [ "$_wanted" = "$_task" ] || { printf '{"status":"error","message":"任务不存在或已被新任务替换"}\n'; exit 0; }
        if [ "$_state" = success ] && [ -f "$STATUS_SCRIPT" ]; then MODDIR="$MODDIR" sh "$STATUS_SCRIPT" mix >/dev/null 2>&1 || true; fi
        printf '{"status":"ok","data":{"task":"%s","state":"%s","message":"%s","cjk":"%s","latin":"%s","digit":"%s","started":%s,"finished":%s}}\n' \
            "$(json_escape "$_task")" "$(json_escape "$_state")" "$(json_escape "$_message")" "$(json_escape "$_cjk")" "$(json_escape "$_latin")" "$(json_escape "$_digit")" "${_started:-0}" "${_finished:-0}"
        ;;
    *) printf '{"status":"error","message":"未知组合桥命令"}\n' ;;
esac
exit 0
