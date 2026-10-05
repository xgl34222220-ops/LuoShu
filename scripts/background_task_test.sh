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
MODDIR="$TMP/module"; export MODDIR
LUOSHU_TASK_SCOPE_PYTHON=python3; export LUOSHU_TASK_SCOPE_PYTHON
LUOSHU_RUNTIME_PATHS_PYTHON=python3; export LUOSHU_RUNTIME_PATHS_PYTHON
mkdir -p "$MODDIR/common"
printf 'id=LuoShu\n' > "$MODDIR/module.prop"
for name in task_scope.sh task_scope.py runtime_paths.sh runtime_paths_lock.py; do
    ln -s "$ROOT/common/$name" "$MODDIR/common/$name"
done
luoshu_start_detached "$PID_FILE" "$TASK" "$LOG_FILE" sh "$WORKER" worker "$TASK"

test -s "$PID_FILE"
test -s "${PID_FILE}.task"
test -s "${PID_FILE}.boot"
test -s "${PID_FILE}.start"
test "$(cat "${PID_FILE}.task")" = "$TASK"
test "$(cat "${PID_FILE}.boot")" = "$(luoshu_current_boot_id)"
luoshu_task_pid_alive "$PID_FILE" "$TASK"

printf 'different-boot\n' > "${PID_FILE}.boot"
if luoshu_task_pid_alive "$PID_FILE" "$TASK"; then
    echo 'boot-id mismatch must invalidate detached task' >&2
    exit 1
fi
luoshu_current_boot_id > "${PID_FILE}.boot"
luoshu_task_pid_alive "$PID_FILE" "$TASK"

luoshu_stop_task_pid "$PID_FILE" "$TASK"
test ! -e "$PID_FILE"
test ! -e "${PID_FILE}.task"
test ! -e "${PID_FILE}.boot"
test ! -e "${PID_FILE}.start"

echo 'background_task_test: PASS'
python3 "$ROOT/scripts/task_scope_test.py"
