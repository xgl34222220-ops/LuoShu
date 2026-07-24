#!/bin/sh
set -e

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
TMP="$(mktemp -d)"
PID_FILE="$TMP/task.pid"
LOG_FILE="$TMP/task.log"
TASK="detached-task-regression"
WORKER="$TMP/worker.sh"

cleanup() {
    if [ -f "$PID_FILE" ]; then
        pid="$(sed -n '1{s/[^0-9].*$//;p;}' "$PID_FILE" 2>/dev/null)"
        [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
    fi
    rm -rf "$TMP"
}
trap cleanup EXIT INT TERM

cat > "$WORKER" <<'EOF_WORKER'
#!/bin/sh
sleep 30
EOF_WORKER
chmod +x "$WORKER"

. "$ROOT/common/background_task.sh"
luoshu_start_detached "$PID_FILE" "$TASK" "$LOG_FILE" sh "$WORKER" worker "$TASK"

test -s "$PID_FILE"
test -s "${PID_FILE}.task"
test "$(cat "${PID_FILE}.task")" = "$TASK"
luoshu_task_pid_alive "$PID_FILE" "$TASK"

luoshu_stop_task_pid "$PID_FILE"
test ! -e "$PID_FILE"
test ! -e "${PID_FILE}.task"

echo 'background_task_test: PASS'
