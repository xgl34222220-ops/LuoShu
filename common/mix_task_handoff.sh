#!/system/bin/sh
# 嵌套复合任务交接：标准输出可能因 Android 后台 Shell 行为丢失，持久化任务文件是最终依据。

luoshu_mix_progress_percent() {
    # Android 15 bionic regexec can crash on the old greedy UTF-8 sed pattern.
    # Read the numeric field from our atomic JSON writer in the byte locale.
    # This remains one finite, inexpensive reader in the existing task scope.
    LC_ALL=C awk '
        {
            key="\"percent\""; p=index($0,key); if (!p) next
            s=substr($0,p+length(key)); sub(/^[ \t\r]*/,"",s)
            if (substr(s,1,1)!=":") exit
            s=substr(s,2); sub(/^[ \t\r]*/,"",s)
            i=1; while (i<=length(s) && index("0123456789",substr(s,i,1))) i++
            value=substr(s,1,i-1); rest=substr(s,i); sub(/^[ \t\r]*/,"",rest)
            if (!length(value) || length(value)>3 || value+0>100 ||
                (substr(rest,1,1)!="," && substr(rest,1,1)!="}")) exit
            print value+0; found=1; exit
        }
        END { if (!found) print 0 }
    ' "$1" 2>/dev/null
}

luoshu_mix_task_value() {
    _file="$1"
    _key="$2"
    sed -n "s/^${_key}=//p" "$_file" 2>/dev/null | head -n1 | tr -d '\r\n'
}

luoshu_mix_task_message_from_response() (
    # Startup/instance failures are infrequent. Reuse the shipped bounded JSON
    # reader so escaped text survives without Android libc regex calls or task
    # field injection. Never start another Python process for progress polling.
    [ -s "$1" ] || return 1
    type luoshu_task_helper >/dev/null 2>&1 || return 1
    luoshu_task_helper error-message "$1"
)

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

    # The engine persists admission before printing its response. Stdout may
    # contain a stale/nested task or disappear entirely on Android. Only the
    # new persisted task with all three requested inputs can own this handoff.
    _candidate=$(luoshu_mix_task_value "$_task_file" task)
    if luoshu_mix_task_matches_request "$_task_file" "$_candidate" "$_previous" "$_cjk" "$_latin" "$_digit"; then
        printf '%s\n' "$_candidate"
        return 0
    fi
    return 1
}
