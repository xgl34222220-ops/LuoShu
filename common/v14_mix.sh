#!/system/bin/sh
# 洛书 v14.2：字体组合轻量桥。
# Alpha3 优先使用异步完整多轴引擎；缺失时回退 v14 原始组合引擎。
set +e
MODDIR="${MODDIR:-}"
if [ -z "$MODDIR" ]; then
    if [ -f "${0%/*}/../module.prop" ]; then MODDIR="$(CDPATH= cd -- "${0%/*}/.." 2>/dev/null && pwd)"; else MODDIR="/data/adb/modules/LuoShu"; fi
fi
WEIGHTED="$MODDIR/common/v142_weighted_mix.sh"
ENGINE="$MODDIR/common/font_mix.sh"
TASK_FILE="$MODDIR/config/mix_task.conf"
STATUS_SCRIPT="$MODDIR/common/module_status.sh"
json_escape(){ printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n\r' '  '; }
read_value(){ sed -n "s/^${1}=//p" "$TASK_FILE" 2>/dev/null | head -n1 | tr -d '\r\n'; }

if [ -f "$WEIGHTED" ]; then
    case "${1:-config}" in
        start) sh "$WEIGHTED" start "$2" "$3" "$4" "${5:-wght=400}" "${6:-wght=400}" "${7:-wght=400}" ;;
        config) sh "$WEIGHTED" config ;;
        status) sh "$WEIGHTED" status "$2" ;;
        recover) sh "$WEIGHTED" recover ;;
        *) printf '{"status":"error","message":"未知组合桥命令"}\n' ;;
    esac
    exit 0
fi

case "${1:-status}" in
    start) sh "$ENGINE" start "$2" "$3" "$4" ;;
    config) sh "$ENGINE" status ;;
    status)
        _wanted="$2"
        [ -s "$TASK_FILE" ] || { printf '{"status":"error","message":"暂无组合任务"}\n'; exit 0; }
        _task=$(read_value task); _state=$(read_value state); _message=$(read_value message)
        _cjk=$(read_value cjk); _latin=$(read_value latin); _digit=$(read_value digit)
        _started=$(read_value started); _finished=$(read_value finished)
        [ -z "$_wanted" ] || [ "$_wanted" = "$_task" ] || { printf '{"status":"error","message":"任务不存在或已被新任务替换"}\n'; exit 0; }
        if [ "$_state" = success ] && [ -f "$STATUS_SCRIPT" ]; then MODDIR="$MODDIR" sh "$STATUS_SCRIPT" mix >/dev/null 2>&1 || true; fi
        printf '{"status":"ok","data":{"task":"%s","state":"%s","message":"%s","cjk":"%s","latin":"%s","digit":"%s","cjkWeight":400,"latinWeight":400,"digitWeight":400,"cjkAxes":"wght=400","latinAxes":"wght=400","digitAxes":"wght=400","started":%s,"finished":%s}}\n' \
            "$(json_escape "$_task")" "$(json_escape "$_state")" "$(json_escape "$_message")" "$(json_escape "$_cjk")" "$(json_escape "$_latin")" "$(json_escape "$_digit")" "${_started:-0}" "${_finished:-0}"
        ;;
    recover) sh "$ENGINE" recover ;;
    *) printf '{"status":"error","message":"未知组合命令"}\n' ;;
esac
exit 0
