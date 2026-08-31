#!/bin/sh
set -e

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export MODDIR="$TMP/module"
export LUOSHU_SWITCH_TASK_FILE="$MODDIR/config/switch_task.conf"
export LUOSHU_SWITCH_LOG="$MODDIR/logs/fontswitch.log"
# Production clamps the task timeout to at least 30 seconds. Keep this integration
# fixture on the same contract instead of depending on the old 5-second test path.
export LUOSHU_SWITCH_TIMEOUT_SECONDS=30
export LUOSHU_SWITCH_WORKER_PID_FILE="$MODDIR/config/switch_task_worker.pid"
mkdir -p "$MODDIR/common" "$MODDIR/config" "$MODDIR/logs"
cp "$ROOT/common/background_task.sh" "$MODDIR/common/background_task.sh"
cp "$ROOT/common/util_functions.sh" "$ROOT/common/util_functions_core.sh" "$MODDIR/common/"

MANAGER="$TMP/fake-manager.sh"
cat > "$MANAGER" <<'EOF_MANAGER'
#!/bin/sh
case "${3:-}" in
    good) printf '%s\n' '{"status":"ok","data":{"font":"good"}}' ;;
    reused) printf '%s\n' '{"status":"ok","data":{"font":"reused","reused":true}}' ;;
    bad) printf '%s\n' '{"status":"error","message":"fake failure"}' ;;
    slow)
        trap 'printf "%s\n" rolled-back > "${ROLLBACK_MARKER:?}"; exit 143' TERM INT
        # Leave scheduling headroom around the 30-second boundary. On a loaded
        # CI host the one-second polling loop can be delayed long enough for a
        # 31-second child to exit just before the timeout branch runs.
        sleep 36
        printf '%s\n' '{"status":"ok"}'
        ;;
    hold)
        sleep 2
        printf '%s\n' '{"status":"ok","data":{"font":"hold"}}'
        ;;
    *) printf '%s\n' '{"status":"error","message":"unknown"}' ;;
esac
EOF_MANAGER
chmod +x "$MANAGER"
export LUOSHU_FONT_MANAGER="$MANAGER"
export ROLLBACK_MARKER="$TMP/rollback"

wait_state() {
    wanted="$1"
    i=0
    state=''
    while [ "$i" -lt 420 ]; do
        state="$(sed -n 's/^state=//p' "$LUOSHU_SWITCH_TASK_FILE" 2>/dev/null | head -n1)"
        [ "$state" = "$wanted" ] && return 0
        sleep 0.1
        i=$((i + 1))
    done
    echo "timed out waiting for state=$wanted; current=${state:-missing}" >&2
    cat "$LUOSHU_SWITCH_TASK_FILE" >&2 || true
    return 1
}

start_output="$(sh "$ROOT/common/font_switch_task.sh" start good)"
printf '%s\n' "$start_output" | grep -q '"status":"ok"'
wait_state success
grep -q '^message=100% · 字体已准备完成，完整重启后生效$' "$LUOSHU_SWITCH_TASK_FILE"
grep -q '^percent=100$' "$LUOSHU_SWITCH_TASK_FILE"
grep -q '^state=pending$' "$MODDIR/config/device-font-load-verification.conf"
grep -q '^reason=awaiting-full-reboot$' "$MODDIR/config/device-font-load-verification.conf"
grep -q '^heartbeat=[0-9][0-9]*$' "$LUOSHU_SWITCH_TASK_FILE"
grep -q '^timeout=30$' "$LUOSHU_SWITCH_TASK_FILE"
grep -q '^elapsed=[0-9][0-9]*$' "$LUOSHU_SWITCH_TASK_FILE"
grep -q '^bootId=.' "$LUOSHU_SWITCH_TASK_FILE"
grep -q '^reused=false$' "$LUOSHU_SWITCH_TASK_FILE"

rm -f "$MODDIR/config/device-font-load-verification.conf"
start_output="$(sh "$ROOT/common/font_switch_task.sh" start reused)"
printf '%s\n' "$start_output" | grep -q '"status":"ok"'
wait_state success
grep -q '^message=100% · 当前字体已验证，无需重新生成或重启$' "$LUOSHU_SWITCH_TASK_FILE"
grep -q '^percent=100$' "$LUOSHU_SWITCH_TASK_FILE"
grep -q '^reused=true$' "$LUOSHU_SWITCH_TASK_FILE"
test ! -e "$MODDIR/config/device-font-load-verification.conf"
reused_task=$(sed -n 's/^task=//p' "$LUOSHU_SWITCH_TASK_FILE")
reused_status="$(sh "$ROOT/common/font_switch_task.sh" status "$reused_task")"
printf '%s\n' "$reused_status" | grep -q '"reused":true'
printf '%s\n' "$reused_status" | grep -q '"percent":100'

start_output="$(sh "$ROOT/common/font_switch_task.sh" start bad)"
printf '%s\n' "$start_output" | grep -q '"status":"ok"'
wait_state failed
grep -q 'fake failure' "$LUOSHU_SWITCH_TASK_FILE"
grep -q '^percent=100$' "$LUOSHU_SWITCH_TASK_FILE"

# Two simultaneous App requests must produce exactly one accepted task. The
# launch lock protects the queued/running task record before the manager lock
# exists, so the rejected request cannot overwrite the accepted task ID. Both
# launch-lock contention and an already-live worker use the same user-facing state.
sh "$ROOT/common/font_switch_task.sh" start hold > "$TMP/concurrent-a.out" &
start_a=$!
sh "$ROOT/common/font_switch_task.sh" start hold > "$TMP/concurrent-b.out" &
start_b=$!
wait "$start_a"
wait "$start_b"
accepted=$(grep -l '"status":"ok"' "$TMP/concurrent-a.out" "$TMP/concurrent-b.out" | wc -l | tr -d '[:space:]')
rejected=$(grep -l '已有字体任务在运行中，请查看当前进度' "$TMP/concurrent-a.out" "$TMP/concurrent-b.out" | wc -l | tr -d '[:space:]')
[ "$accepted" = 1 ]
[ "$rejected" = 1 ]
wait_state success

# Exercise the real bounded timeout at the production minimum. The worker must be
# terminated and the task must converge to a visible terminal failure, not remain
# permanently running.
start_output="$(sh "$ROOT/common/font_switch_task.sh" start slow)"
printf '%s\n' "$start_output" | grep -q '"status":"ok"'
wait_state failed
grep -q '超过 30 秒' "$LUOSHU_SWITCH_TASK_FILE"
grep -q '^percent=100$' "$LUOSHU_SWITCH_TASK_FILE"

cat > "$LUOSHU_SWITCH_TASK_FILE" <<'EOF_STALE'
task=old-boot-task
state=running
font=stale-font
message=running
started=1
finished=
pid=1
heartbeat=1
timeout=360
elapsed=1
percent=50
bootId=different-boot-id
EOF_STALE
sh "$ROOT/common/font_switch_task.sh" reconcile
grep -q '^state=failed$' "$LUOSHU_SWITCH_TASK_FILE"
grep -q '^message=设备已重启，上一字体切换任务已结束$' "$LUOSHU_SWITCH_TASK_FILE"
grep -q '^percent=100$' "$LUOSHU_SWITCH_TASK_FILE"

status_output="$(sh "$ROOT/common/font_switch_task.sh" status)"
printf '%s\n' "$status_output" | grep -q '"state":"failed"'
printf '%s\n' "$status_output" | grep -q '"bootId":"'
printf '%s\n' "$status_output" | grep -q '"percent":100'
grep -q 'luoshu_start_detached' "$ROOT/common/font_switch_task.sh"

echo 'font_switch_task_test: PASS'
