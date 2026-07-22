#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-mix-handoff)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

. "$ROOT/common/mix_task_handoff.sh"

RESPONSE="$TMP/response.json"
TASK="$TMP/mix_task.conf"

printf '%s\n' '{"status":"ok","data":{"task":"from-output"}}' >"$RESPONSE"
cat >"$TASK" <<'EOF_TASK'
task=stale
state=success
cjk=LuoShuMixCJK
latin=LuoShuMixLatin
digit=LuoShuMixDigit
EOF_TASK
test "$(luoshu_resolve_nested_mix_task "$RESPONSE" "$TASK" stale LuoShuMixCJK LuoShuMixLatin LuoShuMixDigit)" = from-output

: >"$RESPONSE"
cat >"$TASK" <<'EOF_TASK'
task=from-state
state=running
message=正在生成
cjk=LuoShuMixCJK
latin=LuoShuMixLatin
digit=LuoShuMixDigit
EOF_TASK
test "$(luoshu_resolve_nested_mix_task "$RESPONSE" "$TASK" stale LuoShuMixCJK LuoShuMixLatin LuoShuMixDigit)" = from-state

if luoshu_resolve_nested_mix_task "$RESPONSE" "$TASK" from-state LuoShuMixCJK LuoShuMixLatin LuoShuMixDigit >/dev/null 2>&1; then
    echo 'stale task was accepted' >&2
    exit 1
fi

sed 's/^latin=.*/latin=WrongLatin/' "$TASK" >"$TASK.tmp"
mv -f "$TASK.tmp" "$TASK"
if luoshu_resolve_nested_mix_task "$RESPONSE" "$TASK" stale LuoShuMixCJK LuoShuMixLatin LuoShuMixDigit >/dev/null 2>&1; then
    echo 'mismatched task was accepted' >&2
    exit 1
fi

printf '%s\n' '{"status":"error","message":"真实启动错误"}' >"$RESPONSE"
test "$(luoshu_mix_task_message_from_response "$RESPONSE")" = 真实启动错误

# 真实复现：内层引擎成功登记任务并开始运行，但标准输出完全为空。
# 外层 Worker 必须从 mix_task.conf 接管子任务，不能误判失败并删除输入目录。
FONT=$(find /usr/share/fonts -type f \( -iname 'DejaVuSans.ttf' -o -iname 'LiberationSans-Regular.ttf' \) -print -quit 2>/dev/null || true)
if [ -s "$FONT" ]; then
    MODULE="$TMP/module"
    PUBLIC="$TMP/public"
    mkdir -p "$MODULE/common" "$MODULE/config" "$MODULE/logs" "$PUBLIC/fonts"
    cp "$ROOT/common/v142_weighted_mix.sh" "$MODULE/common/v142_weighted_mix.sh"
    cp "$ROOT/common/util_functions.sh" "$MODULE/common/util_functions.sh"
    cp "$ROOT/common/font_check.sh" "$MODULE/common/font_check.sh"
    cp "$ROOT/common/background_task.sh" "$MODULE/common/background_task.sh"
    cp "$ROOT/common/mix_task_handoff.sh" "$MODULE/common/mix_task_handoff.sh"

    cat >"$MODULE/common/font_role_check.sh" <<'EOF_ROLE'
#!/bin/sh
exit 0
EOF_ROLE
    cat >"$MODULE/common/font_mix.sh" <<'EOF_ENGINE'
#!/bin/sh
MODDIR="${MODDIR:-${0%/*}/..}"
TASK="$MODDIR/config/mix_task.conf"
case "${1:-}" in
    start)
        cat >"$TASK" <<EOF_INNER
task=base-no-output
state=success
message=内层任务已完成
cjk=$2
latin=$3
digit=$4
started=1
finished=2
EOF_INNER
        chmod 0644 "$TASK" 2>/dev/null || true
        # 故意不输出 JSON，模拟部分 Android Root Shell 上丢失启动输出。
        ;;
    recover) exit 0 ;;
esac
exit 0
EOF_ENGINE
    chmod 0755 "$MODULE/common"/*.sh

    cp "$FONT" "$PUBLIC/fonts/CJK-Regular.ttf"
    cp "$FONT" "$PUBLIC/fonts/Latin-Regular.ttf"
    cp "$FONT" "$PUBLIC/fonts/Digit-Regular.ttf"

    START=$(MODDIR="$MODULE" LUOSHU_PUBLIC_DIR="$PUBLIC" sh "$MODULE/common/v142_weighted_mix.sh" \
        start CJK Latin Digit wght=400 wght=400 wght=400)
    OUTER=$(printf '%s\n' "$START" | sed -n 's/^.*"task":"\([^"]*\)".*$/\1/p' | tail -n1)
    test -n "$OUTER"

    COUNT=0
    while [ "$COUNT" -lt 30 ]; do
        STATE=$(sed -n 's/^state=//p' "$MODULE/config/axes_task.conf" 2>/dev/null | head -n1)
        case "$STATE" in success|failed) break ;; esac
        sleep 1
        COUNT=$((COUNT + 1))
    done
    STATE=$(sed -n 's/^state=//p' "$MODULE/config/axes_task.conf" 2>/dev/null | head -n1)
    if [ "$STATE" != success ]; then
        echo "nested handoff integration failed: state=${STATE:-missing}" >&2
        echo '--- axes_task.conf ---' >&2
        cat "$MODULE/config/axes_task.conf" >&2 2>/dev/null || true
        echo '--- mix_task.conf ---' >&2
        cat "$MODULE/config/mix_task.conf" >&2 2>/dev/null || true
        echo '--- fontswitch.log ---' >&2
        tail -n 80 "$MODULE/logs/fontswitch.log" >&2 2>/dev/null || true
        exit 1
    fi
    test "$(sed -n 's/^childTask=//p' "$MODULE/config/axes_task.conf")" = base-no-output
    ! grep -q '无法启动完整复合字体引擎' "$MODULE/config/axes_task.conf"
fi

grep -q 'mix_task_handoff.sh' "$ROOT/common/v142_weighted_mix.sh"
grep -q 'luoshu_resolve_nested_mix_task' "$ROOT/common/v142_weighted_mix.sh"
grep -q '_response_file=' "$ROOT/common/v142_weighted_mix.sh"
! grep -q '_output=$(LUOSHU_PUBLIC_DIR=' "$ROOT/common/v142_weighted_mix.sh"

echo 'Nested mix task handoff survives missing startup output.'
