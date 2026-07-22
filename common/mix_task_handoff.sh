#!/system/bin/sh
# 嵌套复合任务交接：标准输出可能因 Android 后台 Shell 行为丢失，持久化任务文件是最终依据。

luoshu_mix_task_value() {
    _file="$1"
    _key="$2"
    sed -n "s/^${_key}=//p" "$_file" 2>/dev/null | head -n1 | tr -d '\r\n'
}

luoshu_mix_task_from_response() {
    _response="$1"
    [ -s "$_response" ] || return 1
    sed -n 's/^.*"task":"\([^"]*\)".*$/\1/p' "$_response" 2>/dev/null | tail -n1
}

luoshu_mix_task_message_from_response() {
    _response="$1"
    [ -s "$_response" ] || return 1
    sed -n 's/^.*"message":"\([^"]*\)".*$/\1/p' "$_response" 2>/dev/null | tail -n1
}

luoshu_mix_task_matches_request() {
    _task_file="$1"
    _candidate="$2"
    _previous="$3"
    _cjk="$4"
    _latin="$5"
    _digit="$6"

    [ -n "$_candidate" ] || return 1
    [ "$_candidate" != "$_previous" ] || return 1
    [ "$(luoshu_mix_task_value "$_task_file" task)" = "$_candidate" ] || return 1
    [ "$(luoshu_mix_task_value "$_task_file" cjk)" = "$_cjk" ] || return 1
    [ "$(luoshu_mix_task_value "$_task_file" latin)" = "$_latin" ] || return 1
    [ "$(luoshu_mix_task_value "$_task_file" digit)" = "$_digit" ] || return 1
    case "$(luoshu_mix_task_value "$_task_file" state)" in
        queued|running|success|failed) return 0 ;;
    esac
    return 1
}

luoshu_resolve_nested_mix_task() {
    _response="$1"
    _task_file="$2"
    _previous="$3"
    _cjk="$4"
    _latin="$5"
    _digit="$6"

    # “无启动输出”正是需要回退到持久化任务文件的正常场景；不得让 set -e 提前终止。
    _child=$(luoshu_mix_task_from_response "$_response" 2>/dev/null || true)
    if [ -n "$_child" ]; then
        printf '%s\n' "$_child"
        return 0
    fi

    _candidate=$(luoshu_mix_task_value "$_task_file" task)
    if luoshu_mix_task_matches_request "$_task_file" "$_candidate" "$_previous" "$_cjk" "$_latin" "$_digit"; then
        printf '%s\n' "$_candidate"
        return 0
    fi
    return 1
}
